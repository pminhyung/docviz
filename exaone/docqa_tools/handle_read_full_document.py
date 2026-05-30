"""ReadFullDocument — full-document goal-oriented extraction.

Mirrors doc_agent_v2 ReadFullDocumentTool semantics:
    1. Resolve cached document by file_id.
    2. Join pages with [Page N] markers, cap at 50000 chars.
    3. Call EXTRACTOR_DOC_PROMPT through the LLM auxiliary client
       (temperature=0.2, max_tokens=16384 — matches original).
    4. Return the LLM extraction output as the tool result.

The auxiliary call follows the same resolution pattern as web_extract:
explicit ``task="read_full_document"`` identifier, Exaone main_runtime
injection so the EXTRACTOR call lands on the same vLLM host as the
calling agent, and an ``AUXILIARY_READ_FULL_DOCUMENT_MODEL`` env
override for per-task model selection. The EXTRACTOR_DOC_PROMPT itself
is unchanged — only the routing/transport layer was aligned with
web_extract's style.

When the EXTRACTOR LLM is unavailable (no auxiliary backend configured)
the handler returns ``tool_error`` so the caller knows extraction did
not occur — silent fallback would hide a meaningful regression vs the
original behavior.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from exaone.docqa_tools._doc_cache import get_document
from exaone.docqa_tools._extractor_prompts import EXTRACTOR_DOC_PROMPT
from tools.registry import tool_error, tool_result

logger = logging.getLogger(__name__)


_CONTENT_CHAR_CAP = 50_000  # matches doc_agent_v2 ReadFullDocumentTool
_LLM_TEMPERATURE = 0.2
_LLM_MAX_TOKENS = 16_384
_MAX_RETRIES = 2
_INITIAL_RETRY_DELAY = 2


def _is_exaone_mode() -> bool:
    return os.getenv("HERMES_EXAONE_AGENT", "").lower() in ("1", "true", "yes")


def _is_nous_auxiliary_client(client: Any) -> bool:
    base_url = str(getattr(client, "base_url", "") or "")
    host = (urlparse(base_url).hostname or "").lower()
    return host == "nousresearch.com" or host.endswith(".nousresearch.com")


def _resolve_rfd_auxiliary(
    model: Optional[str] = None,
) -> Tuple[Optional[Any], Optional[str], Dict[str, Any]]:
    """Resolve (client, model, extra_body) for the EXTRACTOR_DOC_PROMPT call.

    In Exaone mode the active inference runtime (EXAONE_BASE_URL / model)
    is injected as ``main_runtime`` so the call routes to the same vLLM
    host that the calling agent is bound to — preserving prefix-cache
    locality under multi-host batch execution.
    """
    from agent.auxiliary_client import (
        get_async_text_auxiliary_client,
        get_auxiliary_extra_body,
    )

    main_runtime: Optional[Dict[str, Any]] = None
    if _is_exaone_mode():
        try:
            from exaone.config import load_config as _load_exaone_config

            cfg = _load_exaone_config()
            main_runtime = {
                "provider": cfg.provider,
                "model": cfg.model,
                "base_url": cfg.base_url,
                "api_key": cfg.api_key,
                "api_mode": cfg.api_mode,
            }
        except Exception:
            main_runtime = None

    client, default_model = get_async_text_auxiliary_client(
        "read_full_document", main_runtime=main_runtime
    )
    configured_model = os.getenv("AUXILIARY_READ_FULL_DOCUMENT_MODEL", "").strip()
    effective_model = model or configured_model or default_model

    extra_body: Dict[str, Any] = {}
    if client is not None and _is_nous_auxiliary_client(client):
        extra_body = get_auxiliary_extra_body() or {"tags": ["product=hermes-agent"]}

    return client, effective_model, extra_body


READ_FULL_DOCUMENT_SCHEMA: dict[str, Any] = {
    "name": "ReadFullDocument",
    "description": (
        "Read the FULL parsed text of a single internal document (by "
        "document_idx) and return a goal-oriented extraction (rational / "
        "evidence / summary). Use ONLY when the user requires "
        "whole-document summarization or overall understanding — for "
        "narrow topic or issue questions, prefer targeted retrieval."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "document_idx": {
                "type": "integer",
                "description": (
                    "Single attachment idx from the [Attached documents] "
                    "block. The document must have been parsed earlier "
                    "in this task via parse_web_and_doc."
                ),
            },
            "goal": {
                "type": "string",
                "description": (
                    "Required. Information goal driving the extraction "
                    "(injected into EXTRACTOR_DOC_PROMPT)."
                ),
            },
        },
        "required": ["document_idx", "goal"],
    },
}


async def handle_read_full_document(args: dict | None = None, **kwargs) -> str:
    payload = dict(args or {})
    task_id = kwargs.get("task_id") or DEFAULT_TASK_ID

    raw_idx = payload.get("document_idx")
    if raw_idx is None:
        return tool_error("document_idx is required (integer)")
    if isinstance(raw_idx, list):
        if len(raw_idx) != 1:
            return tool_error("document_idx must be a single integer for ReadFullDocument")
        raw_idx = raw_idx[0]
    try:
        idx = int(raw_idx)
    except (TypeError, ValueError):
        return tool_error("document_idx must be an integer")

    goal = payload.get("goal")
    if not goal:
        return tool_error("goal is required")

    from exaone.docqa_tools._attachments import get_fid_by_idx
    fid = get_fid_by_idx(task_id=task_id, idx=idx)
    if fid is None:
        return tool_error(
            f"document_idx={idx} has not been parsed in this task. "
            "Parse the document first via parse_web_and_doc."
        )

    doc = get_document(task_id=task_id, fid=fid)
    if doc is None:
        return tool_error(
            f"document_idx={idx} not found in cache (fid resolved but cache miss)."
        )

    # Chunk-granular cache: group chunks per page, join with blank line,
    # cap at 50000 chars. (kind, value) tuple keys keep numeric labels
    # first and named labels (cover/appendix/…) last, avoiding the int↔str
    # TypeError on mixed page sets. See _doc_cache.py "Cache shape".
    pages_in_order = sorted(
        doc.pages,
        key=lambda p: (0, int(p)) if p.isdigit() else (1, p),
    )
    page_blocks: list[str] = []
    for page in pages_in_order:
        body = "\n\n".join(c.text for c in doc.chunks_on_page(page) if c.text)
        page_blocks.append(f"[Page {page}]\n{body}".rstrip())
    joined = "\n\n".join(page_blocks)
    capped_content = joined[:_CONTENT_CHAR_CAP]

    messages = [
        {
            "role": "user",
            "content": EXTRACTOR_DOC_PROMPT.format(
                webpage_content=capped_content,
                goal=goal,
            ),
        }
    ]

    try:
        from agent.auxiliary_client import async_call_llm, extract_content_or_reasoning
    except Exception as exc:
        return tool_error(f"auxiliary client unavailable: {exc}")

    aux_client, effective_model, extra_body = _resolve_rfd_auxiliary()
    if aux_client is None or not effective_model:
        return tool_error("auxiliary client unavailable for ReadFullDocument")

    call_kwargs: Dict[str, Any] = {
        "task": "read_full_document",
        "model": effective_model,
        "messages": messages,
        "temperature": _LLM_TEMPERATURE,
        "max_tokens": _LLM_MAX_TOKENS,
    }
    if extra_body:
        call_kwargs["extra_body"] = extra_body

    extracted_text = ""
    last_error: Optional[Exception] = None
    retry_delay = _INITIAL_RETRY_DELAY
    for attempt in range(_MAX_RETRIES):
        try:
            response = await async_call_llm(**call_kwargs)
            extracted_text = extract_content_or_reasoning(response) or ""
            if extracted_text:
                last_error = None
                break
            logger.warning(
                "RFD EXTRACTOR_DOC_PROMPT returned empty content (attempt %d/%d)",
                attempt + 1, _MAX_RETRIES,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "RFD EXTRACTOR_DOC_PROMPT attempt %d/%d failed: %s",
                attempt + 1, _MAX_RETRIES, str(exc)[:120],
            )
        if attempt < _MAX_RETRIES - 1:
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)

    if not extracted_text and last_error is not None:
        return tool_error(f"EXTRACTOR_DOC_PROMPT LLM call failed: {last_error}")

    # Aux SFT trace — preserves the EXTRACTOR prompt + raw model output as
    # its own SFT stream (auxiliary_rd_extract_N.json), uniform with the
    # other auxiliary_*.json files written by auxiliary_tracer.
    try:
        from exaone.auxiliary_tracer import write_rd_extract_log
        user_prompt_text = messages[0]["content"] if messages else ""
        write_rd_extract_log(
            system_prompt=None,
            user_prompt=user_prompt_text,
            assistant=extracted_text,
            meta={
                "file_id": fid,
                "filename": doc.filename,
                "page_count": doc.page_count,
                "goal": goal,
                "content_char_count": len(capped_content),
                "content_truncated": len(joined) > _CONTENT_CHAR_CAP,
                "model": effective_model,
            },
        )
    except Exception:
        pass

    envelope: Dict[str, Any] = {
        "tool_name": "ReadFullDocument",
        "document_idx": idx,
        "filename": doc.filename,
        "extension": doc.extension,
        "page_count": doc.page_count,
        "goal": goal,
        "content_char_count": len(capped_content),
        "content_truncated_to": _CONTENT_CHAR_CAP if len(joined) > _CONTENT_CHAR_CAP else None,
        "text": extracted_text,
    }
    return tool_result(envelope)
