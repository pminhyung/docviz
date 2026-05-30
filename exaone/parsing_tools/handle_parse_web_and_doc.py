"""parse_web_and_doc tool — register one or more attached documents into the
per-task chunk pool by **document index**, not by raw file path.

The agent never sees raw file paths in its prompt — only the synthetic
``[Attached documents]`` block (``[1] basename.pdf`` ...). It calls
``parse_web_and_doc(document_idx=[1, 2, ...])`` and the handler resolves each
idx via the per-task attachment table, then routes to one of two backends:

  - Mode A (``HERMES_DOC_SOURCE=local``, default): SFT-only. Reads
    pre-parsed JSON from ``file_mapping.json``. No parser HTTP, no IR.
  - Mode B (``HERMES_DOC_SOURCE=remote``): production-parity. Per fid:
      1. If the attachment already carries a fid (set by
         ``exaone/sft_gen/upload_to_ir.py`` after a Files API upload),
         probe IR with ``find_docs(search_pass=1, fids=[fid])`` and
         rehydrate the cache from the response when hits come back —
         no parser call needed.
      2. Otherwise derive a deterministic fid and run
         ``parser → add_doc`` directly. This is the original lgair
         create_doc path.

Both paths populate the same per-task cache and return the same
envelope shape, so downstream tools (list_documents, doc_search,
get_document_chunks, ReadFullDocument) are mode-agnostic.

Idempotence: re-registering an already-parsed idx returns ``"cached"``
status without re-parsing.

## Document flow policy (background)

See ``exaone/docqa_tools/_policy.md``. Mode B is the same flow that
runs on production master; the difference is that master assumes an
upstream system has already issued the fid, while ir-shim uses
``upload_to_ir`` to talk to the Dev Files API directly. Mode A is
SFT-only and does not exist on master.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, List

from exaone.docqa_tools._attachments import (
    Attachment,
    get_fid_by_idx,
    lookup_attachment,
    set_fid,
)
from exaone.docqa_tools._doc_cache import (
    DEFAULT_TASK_ID,
    CachedChunk,
    CachedDocument,
    get_document,
    put_document,
    rehydrate_from_ir_hits,
)
from exaone.docqa_tools._ir_client import add_doc, find_docs
from exaone.parsing_tools._parser_client import (
    SUPPORTED_EXTENSIONS,
    parse_document,
    parse_web,
)
from tools.registry import tool_error, tool_result

logger = logging.getLogger(__name__)


from exaone.docqa_tools._doc_source import is_local_mode


PARSE_WEB_AND_DOC_SCHEMA: dict[str, Any] = {
    "name": "parse_web_and_doc",
    "description": (
        "Register attached documents OR web pages into this task's "
        "document pool so they become searchable. Document branch: "
        "reference documents by the integer indices shown in the "
        "'[Attached documents]' block of the user's message "
        "(e.g. document_idx=[1] or [1, 2]). Web branch: pass `urls` "
        "(list of URLs, same key as `web_extract`). Already-parsed "
        "documents are returned as 'cached' without re-parsing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "document_idx": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Document branch. One or more document indices from "
                    "the '[Attached documents]' list. Multiple indices may "
                    "be supplied in a single call to parse several "
                    "documents at once."
                ),
            },
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Web branch. List of URLs to fetch + parse via the "
                    "doc_parser's WebParser endpoint. Same key as "
                    "`web_extract`. Each URL is registered with a "
                    "deterministic fid derived from its sha1."
                ),
            },
        },
        "required": [],
    },
}


def _validate_extension(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"unsupported extension '{ext}'. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    return ext


def _derive_fid(filename: str, raw_bytes: bytes) -> str:
    """Deterministic 12-digit fid from filename + first 1 KiB of content."""
    digest = hashlib.sha1(filename.encode("utf-8") + raw_bytes[:1024]).hexdigest()
    return str(int(digest[:14], 16))[:12]


def _build_doc_id(fid: str, slide_no: str) -> int:
    """Per-page doc_id matching lgair _create_doc_id rule (fid+slide+ms)."""
    ms = int(time.time() * 1000)
    return int(f"{fid}{slide_no}{ms}")


def _flatten(chunks: list | str) -> str:
    if isinstance(chunks, list):
        return "\n\n".join(str(c) for c in chunks)
    return str(chunks)


# ---------------------------------------------------------------------------
# Per-attachment parse helpers — return one "per-doc result" dict each
# ---------------------------------------------------------------------------


async def _parse_one_shim(att: Attachment, task_id: str) -> dict[str, Any]:
    """Shim parse for one attachment. Returns the per-doc result envelope."""
    from exaone.sft_gen.shim.pdf_index import get_index

    try:
        index = get_index()
    except (FileNotFoundError, ValueError) as exc:
        return {
            "document_idx": att.idx,
            "filename": att.filename,
            "status": "error",
            "error": f"pdf index unavailable: {exc}",
        }
    entry = index.lookup(att.file_path)
    if entry is None:
        return {
            "document_idx": att.idx,
            "filename": att.filename,
            "status": "error",
            "error": f"attachment idx={att.idx} file_path not in pdf index",
        }

    try:
        with entry.parsed_json_path.open("r", encoding="utf-8") as f:
            doc_json = json.load(f)
    except Exception as exc:
        return {
            "document_idx": att.idx,
            "filename": att.filename,
            "status": "error",
            "error": f"parsed JSON load failed: {exc}",
        }

    outputs = doc_json.get("outputs") or []
    if not outputs or not isinstance(outputs[0], dict):
        return {
            "document_idx": att.idx,
            "filename": att.filename,
            "status": "error",
            "error": "parsed JSON missing outputs[0]",
        }
    html_parsed = outputs[0].get("html_parsed") or {}
    if not isinstance(html_parsed, dict) or not html_parsed:
        return {
            "document_idx": att.idx,
            "filename": att.filename,
            "status": "error",
            "error": "parsed JSON has empty html_parsed",
        }

    # Use the caller-supplied (sanitized) attachment filename for the
    # cache record so list_documents / get_document_chunks can match by
    # exactly the same string the agent saw in [Attached documents].
    filename = att.filename or entry.original_filename
    extension = _validate_extension(filename) if "." in filename else "pdf"
    fid = entry.stem

    cached_doc = CachedDocument(
        fid=fid,
        filename=filename,
        extension=extension,
        user_id=0,
        registered_at=time.time(),
        source="shim",
    )
    # Local pre-parsed JSON only carries html_parsed in this branch; we
    # use the same text for both fields so downstream tools don't need a
    # Mode-A-specific branch.
    for page_str, chunks in sorted(
        html_parsed.items(),
        key=lambda kv: (0, int(kv[0])) if str(kv[0]).isdigit() else (1, str(kv[0])),
    ):
        text = _flatten(chunks)
        cached_doc.chunks.append(
            CachedChunk(page=str(page_str), text=text, html=text)
        )
    put_document(task_id=task_id, doc=cached_doc)
    set_fid(task_id=task_id, idx=att.idx, fid=fid)

    return {
        "document_idx": att.idx,
        "filename": filename,
        "extension": extension,
        "page_count": cached_doc.page_count,
        "char_count": cached_doc.char_count,
        "status": "registered",
        "backend": "shim (pre-parsed local)",
    }


async def _try_rehydrate_from_ir(
    *, task_id: str, fid: str, filename_fallback: str, extension_fallback: str,
) -> CachedDocument | None:
    """Probe IR via ``find_docs(search_pass=1)``; rehydrate on hit.

    Returns the rebuilt CachedDocument when IR has pages for the fid, or
    ``None`` when the probe is empty or itself fails. The pre-check is
    best-effort: on any IR error we fall through to a fresh parse,
    matching lgair's "always-try" semantics.
    """
    try:
        hits = await find_docs(
            # Some IR deployments validate ``question`` as non-empty even
            # when ``search_pass=1``. Use a sentinel placeholder so the
            # probe is accepted everywhere.
            query="fid_probe",
            fids=[fid],
            top_n=512,
            rerank=False,
            search_pass=1,
            # has_attached_doc=False so a 4xx from a strict IR is treated
            # as "not indexed" (return []) rather than RuntimeError —
            # we want to fall through to a fresh parse, not blow up.
            has_attached_doc=False,
            request_id=task_id,
        )
    except Exception:
        return None
    if not hits:
        return None
    return rehydrate_from_ir_hits(
        fid=fid,
        hits=hits,
        filename_fallback=filename_fallback,
        extension_fallback=extension_fallback,
    )


async def _parse_one_ir(att: Attachment, task_id: str) -> dict[str, Any]:
    """Mode B: production-parity flow for one attachment.

    Resolution order:
      1. If the attachment table already carries a fid (set by
         ``upload_to_ir.set_fid`` after a Files API upload), probe IR
         with ``search_pass=1`` and rehydrate on hit.
      2. Otherwise derive a deterministic fid and run parser → add_doc
         (the original lgair ``create_doc`` path).
    """
    file_path = att.file_path
    path = Path(file_path)
    filename = att.filename or (path.name if path.exists() else "unknown")

    # Path 1: pre-built artifacts via IR — applies when the SFT script
    # uploaded the file to the Dev Files API first (Mode B happy path).
    pre_assigned_fid = get_fid_by_idx(task_id=task_id, idx=att.idx)
    if pre_assigned_fid:
        extension = _validate_extension(filename) if "." in filename else "pdf"
        rehydrated = await _try_rehydrate_from_ir(
            task_id=task_id,
            fid=pre_assigned_fid,
            filename_fallback=filename,
            extension_fallback=extension,
        )
        if rehydrated is not None:
            put_document(task_id=task_id, doc=rehydrated)
            return {
                "document_idx": att.idx,
                "filename": rehydrated.filename or filename,
                "extension": rehydrated.extension or extension,
                "page_count": rehydrated.page_count,
                "char_count": rehydrated.char_count,
                "status": "rehydrated_from_ir",
                "backend": "ir (pre-built)",
            }
        # Fall through: fid was reserved but IR has no pages yet. Either
        # the parser hasn't finished server-side or the upload skipped IR
        # registration. Treat it like a fresh parse using the reserved fid
        # so the doc_ids remain consistent across reruns.

    # Path 2: parser HTTP → add_doc — the original lgair create_doc flow.
    if not path.is_file():
        return {
            "document_idx": att.idx,
            "filename": filename,
            "status": "error",
            "error": f"file not found: {file_path}",
        }
    try:
        extension = _validate_extension(filename)
    except ValueError as exc:
        return {
            "document_idx": att.idx,
            "filename": filename,
            "status": "error",
            "error": str(exc),
        }
    raw_bytes = path.read_bytes()
    fid = pre_assigned_fid or _derive_fid(filename, raw_bytes)

    try:
        html_parsed, list_parsed = await parse_document(
            filename=filename, raw_bytes=raw_bytes, request_id=task_id,
        )
    except Exception as exc:
        return {
            "document_idx": att.idx,
            "filename": filename,
            "status": "error",
            "error": f"doc_parser call failed: {exc}",
        }

    page_keys = sorted(
        set(html_parsed.keys()) | set(list_parsed.keys()),
        # (kind, value) tuple keeps numeric pages first in numeric order and
        # named pages (cover/appendix/…) in lexical order — avoids the
        # int↔str TypeError when the parser returns mixed labels.
        key=lambda k: (0, int(k)) if str(k).isdigit() else (1, str(k)),
    )
    cached_doc = CachedDocument(
        fid=fid,
        filename=filename,
        extension=extension,
        user_id=0,
        registered_at=time.time(),
        source="parser",
    )
    parsed_for_ir: list[dict] = []
    for page in page_keys:
        text = _flatten(list_parsed.get(page) or [])
        html = _flatten(html_parsed.get(page) or [])
        page_str = str(page)
        doc_id = _build_doc_id(fid, page_str)
        cached_doc.chunks.append(
            CachedChunk(page=page_str, text=text, html=html, doc_id=str(doc_id))
        )
        parsed_for_ir.append({
            "doc_id": doc_id,
            "slide_num": page,
            "context": json.dumps(text, ensure_ascii=False),
            "html_context": json.dumps(html, ensure_ascii=False),
        })

    ir_status = "skipped"
    ir_error: str | None = None
    try:
        ir_ids = await add_doc(
            user_id=0,
            file_kind=extension,
            file_id=fid,
            filename=filename,
            parsed_docs=parsed_for_ir,
            request_id=task_id,
        )
        cached_doc.ir_registered = True
        cached_doc.ir_doc_ids = list(ir_ids)
        ir_status = "registered" if ir_ids and ir_ids != [0] else "already_indexed"
    except RuntimeError as exc:
        ir_error = str(exc)
        ir_status = "failed"
    put_document(task_id=task_id, doc=cached_doc)
    set_fid(task_id=task_id, idx=att.idx, fid=fid)

    result = {
        "document_idx": att.idx,
        "filename": filename,
        "extension": extension,
        "page_count": cached_doc.page_count,
        "char_count": cached_doc.char_count,
        "status": ir_status,
        "backend": "ir",
    }
    if ir_error:
        result["error"] = ir_error
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _derive_url_fid(url: str) -> str:
    """Deterministic 12-digit fid from sha1(url). Same shape as document
    fid. Matches master 의 동일 함수 — 두 브랜치가 같은 URL 을 받으면
    같은 fid 를 생성한다."""
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return str(int(digest[:14], 16))[:12]


async def _handle_web_branch(
    *, task_id: str, urls: list,
) -> str:
    """Parse each URL via doc_parser's WebParser request_type, cache, and
    register into IR. Same shape / behavior as master 의 동일 함수.

    BE 명세에 따른 wire shape:
        params = {"inputs_format": "bytes", "version": "3.3",
                  "file_id": "dummy_id", "request_type": "WebParser",
                  "url": <input_url>}

    The parser-side `file_id` is a placeholder; we derive our own fid
    deterministically from sha1(url) so the same URL maps to the same
    cache slot. ir-shim attachment table 은 web 분기에 사용되지 않는다
    (URL 은 idx 매핑 대상이 아님).
    """
    per_doc: list[dict[str, Any]] = []
    n_registered = 0
    n_cached = 0
    n_errors = 0

    for url in sorted({u.strip() for u in urls if isinstance(u, str) and u.strip()}):
        fid = _derive_url_fid(url)
        existing = get_document(task_id=task_id, fid=fid)
        if existing is not None and existing.chunks:
            per_doc.append({
                "url":          url,
                "file_id":      fid,
                "page_count":   existing.page_count,
                "char_count":   existing.char_count,
                "status":       "cached",
                "backend":      "web",
            })
            n_cached += 1
            continue

        try:
            html_parsed, list_parsed = await parse_web(url=url, request_id=task_id)
        except Exception as exc:
            per_doc.append({
                "url":     url,
                "file_id": fid,
                "status":  "error",
                "backend": "web",
                "error":   f"web_parser call failed: {exc}",
            })
            n_errors += 1
            continue

        page_keys = sorted(
            set(html_parsed.keys()) | set(list_parsed.keys()),
            key=lambda k: (0, int(k)) if str(k).isdigit() else (1, str(k)),
        )
        cached_doc = CachedDocument(
            fid=fid, filename=url, extension="web",
            user_id=0, registered_at=time.time(), source="parser",
        )
        parsed_for_ir: list[dict] = []
        for page in page_keys:
            text = _flatten(list_parsed.get(page) or [])
            html = _flatten(html_parsed.get(page) or [])
            page_str = str(page)
            doc_id = _build_doc_id(fid, page_str)
            cached_doc.chunks.append(
                CachedChunk(text=text, html=html, page=page_str, doc_id=str(doc_id))
            )
            parsed_for_ir.append({
                "doc_id":       doc_id,
                "slide_num":    page,
                "context":      json.dumps(text, ensure_ascii=False),
                "html_context": json.dumps(html, ensure_ascii=False),
            })

        ir_status = "skipped"
        ir_error: str | None = None
        try:
            ir_success_ids = await add_doc(
                user_id=0, file_kind="web", file_id=fid,
                filename=url, parsed_docs=parsed_for_ir, request_id=task_id,
            )
            cached_doc.ir_registered = True
            cached_doc.ir_doc_ids = list(ir_success_ids)
            ir_status = "registered" if ir_success_ids and ir_success_ids != [0] else "already_indexed"
        except (RuntimeError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            ir_error = str(exc)
            ir_status = "failed"

        put_document(task_id=task_id, doc=cached_doc)
        per_doc.append({
            "url":          url,
            "file_id":      fid,
            "page_count":   cached_doc.page_count,
            "char_count":   cached_doc.char_count,
            "status":       ir_status,
            "backend":      "web",
            **({"error": ir_error} if ir_error else {}),
        })
        if ir_status == "failed":
            n_errors += 1
        else:
            n_registered += 1

    return tool_result({
        "tool_name":  "parse_web_and_doc",
        "branch":     "web",
        "registered": n_registered,
        "cached":     n_cached,
        "errors":     n_errors,
        "results":    per_doc,
    })


async def handle_parse_web_and_doc(args: dict | None = None, **kwargs) -> str:
    payload = dict(args or {})
    task_id = kwargs.get("task_id") or DEFAULT_TASK_ID

    # Web 분기: urls 가 들어오면 doc_parser 의 WebParser request_type 으로
    # 처리. doc 인자(document_idx) 와 web 인자(urls) 는 상호 배타.
    urls = payload.get("urls")
    if urls:
        if not isinstance(urls, list):
            return tool_error("urls must be a list of strings")
        return await _handle_web_branch(task_id=task_id, urls=urls)

    raw_idx = payload.get("document_idx")
    if raw_idx is None:
        return tool_error("document_idx is required (list of integers)")
    if isinstance(raw_idx, int):
        raw_idx = [raw_idx]
    if not isinstance(raw_idx, list) or not raw_idx:
        return tool_error("document_idx must be a non-empty list of integers")

    try:
        idx_list: List[int] = [int(v) for v in raw_idx]
    except (TypeError, ValueError):
        return tool_error("document_idx entries must be integers")

    use_shim = is_local_mode()
    per_doc: list[dict[str, Any]] = []
    n_registered = 0
    n_cached = 0
    n_errors = 0
    for idx in idx_list:
        att = lookup_attachment(task_id=task_id, idx=idx)
        if att is None:
            per_doc.append({
                "document_idx": idx,
                "status": "error",
                "error": (
                    f"document_idx={idx} not in this task's attachment table. "
                    "Call list_documents to see available indices."
                ),
            })
            n_errors += 1
            continue

        # Idempotence: already-parsed docs return cached without re-work.
        # Lookup via the idx -> fid mapping populated by prior parse calls.
        # Exception: in Mode B, a previous _parse_one_ir call may have
        # populated the cache *but* failed to register with IR. In that
        # case the next doc_search would return empty hits silently, so
        # we re-run _parse_one_ir to retry the IR add.
        from exaone.docqa_tools._attachments import get_fid_by_idx as _get_fid_by_idx
        already = None
        prior_fid = _get_fid_by_idx(task_id=task_id, idx=idx)
        if prior_fid is not None:
            already = get_document(task_id=task_id, fid=prior_fid)
        ir_path_needs_retry = (
            not use_shim and already is not None and not already.ir_registered
        )
        if already is not None and not ir_path_needs_retry:
            per_doc.append({
                "document_idx": idx,
                "filename": already.filename,
                "extension": already.extension,
                "page_count": already.page_count,
                "char_count": already.char_count,
                "status": "cached",
                "backend": "shim (pre-parsed local)" if use_shim else "ir",
            })
            n_cached += 1
            continue

        result = (
            await _parse_one_shim(att, task_id)
            if use_shim
            else await _parse_one_ir(att, task_id)
        )
        per_doc.append(result)
        if result.get("status") == "error":
            n_errors += 1
        else:
            n_registered += 1

    envelope: dict[str, Any] = {
        "tool_name": "parse_web_and_doc",
        "document_idx": idx_list,
        "registered": n_registered,
        "cached": n_cached,
        "errors": n_errors,
        "results": per_doc,
    }
    return tool_result(envelope)
