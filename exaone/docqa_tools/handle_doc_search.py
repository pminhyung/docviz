"""doc_search tool — query the internal document corpus (IR) for passages.

Doc-only. For web search the model should call Hermes' built-in
``web_search`` tool directly; this tool intentionally does not have a
``source`` parameter.

Backend chain: lgair IR ``find_docs`` (+ optional selector rerank).

Output shape mirrors Hermes ``web_search`` envelope for symmetry, with
``data.doc`` instead of ``data.web``:

    {
        "success": bool,
        "data": {"doc": [{Index, query_idx, document_idx, page, title, snippet, ...}]},
        "queries": [...],
        "document_idx": [...],
        "per_query_errors": {...}   # optional
    }

The agent only ever sees ``document_idx``; the fid that IR/selector uses
internally is resolved via the per-task attachment table (populated by
``parse_web_and_doc``) and never exposed in the envelope.

**SFT local mode** (``HERMES_DOC_SOURCE=local``, default): IR ``find_docs`` is bypassed.
Each idx's cached pages are converted into the sft_pipeline selector
input format and ranked via the gw-stg selector HTTP API. The returned
envelope matches the IR-backed shape exactly so calling agents cannot
distinguish the two paths.

## fid sourcing — master 와의 의미적 동등성

master 의 ``handle_doc_search`` 는 lgair-* production 의 fid 결정 규약
(``document_file_ids`` ∪ ``public_document_file_ids``) 을 그대로 받아
IR 호출에 사용한다. ir-shim 은 모델 인터페이스를 ``document_idx`` 단일
입력으로 유지하지만 **결과적으로 IR / selector 에 들어가는 fid pool 의
의미는 master 와 동일하다고 가정한다**:

  - 이번 턴 사용자 첨부분 + 사용자 보관 문서 + 공개 문서의 union 이
    SFT 상위 스크립트(또는 외부 호출자) 에 의해 attachment table 에
    register 된다 (`_attachments.register_attachments`,
    `exaone/sft_gen/upload_to_ir.upload_and_register`).
  - 그 결과 attachment table 의 모든 idx → fid 가 곧 lgair 의 union 과
    같은 모집단을 형성한다.

ir-shim 코드는 위 가정에 의존만 할 뿐 union 키 두 개를 분리해서 받지
않는다. 차이 표는 ``exaone/docqa_tools/_policy.md`` 의 "Intentional
divergence" 섹션 참고.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from exaone.docqa_tools._attachments import (
    get_fid_by_idx,
    get_idx_by_fid,
)
from exaone.docqa_tools._doc_cache import (
    DEFAULT_TASK_ID,
    CachedDocument,
    doc_to_page_dicts,
    get_document,
)
from exaone.docqa_tools._ir_client import find_docs
from tools.registry import tool_error, tool_result


from exaone.docqa_tools._doc_source import is_local_mode


DOC_SEARCH_SCHEMA: dict[str, Any] = {
    "name": "doc_search",
    "description": (
        "Search the internal document corpus for passages relevant to one "
        "or more queries. Returns scored hits per document page. Supply "
        "`document_idx` values from the [Attached documents] block (the "
        "docs must be registered first via parse_web_and_doc). This tool is "
        "scoped to internal documents only — public web search belongs "
        "to a different tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "1-3 related search queries. Each query produces up "
                    "to top_n hits. Multiple queries widen recall."
                ),
            },
            "document_idx": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Attachment indices (from the [Attached documents] block) "
                    "to search within. Must have been registered earlier via "
                    "parse_web_and_doc."
                ),
            },
            "top_n": {
                "type": "integer",
                "description": "Optional cap on hits per query.",
            },
            "rerank": {
                "type": "boolean",
                "description": "Enable IR rerank (default true).",
            },
        },
        "required": ["queries", "document_idx"],
    },
}


def _resolve_idx_to_fid(task_id: str, idxs: List[int]) -> tuple[Dict[int, str], List[int]]:
    """Map each attachment idx to its registered fid via the attachment table.

    Returns (idx_to_fid, missing_idxs). Missing idxs are those not yet parsed.
    """
    idx_to_fid: Dict[int, str] = {}
    missing: List[int] = []
    for idx in idxs:
        fid = get_fid_by_idx(task_id=task_id, idx=int(idx))
        if fid is None:
            missing.append(int(idx))
        else:
            idx_to_fid[int(idx)] = fid
    return idx_to_fid, missing


async def _handle_doc_search_shim(
    payload: dict, task_id: str, queries: List[str], idxs: List[int], top_n: int | None
) -> str:
    """Shim path: rank cached doc pages via the sft_pipeline selector."""
    import asyncio
    import httpx

    from exaone.sft_gen.shim.selector_client import rank_pages

    idx_to_fid, missing_idxs = _resolve_idx_to_fid(task_id, idxs)
    per_query_errors: Dict[str, str] = {}

    docs_by_idx: Dict[int, tuple[str, CachedDocument]] = {}
    for idx, fid in idx_to_fid.items():
        doc = get_document(task_id=task_id, fid=fid)
        if doc is None or not doc.pages:
            missing_idxs.append(idx)
            continue
        docs_by_idx[idx] = (fid, doc)

    # Build the cache-miss error once, after the docs-by-idx loop has
    # had its chance to add more misses — the earlier inline write was
    # missing the docs whose fid was set but cache had no pages.
    if missing_idxs:
        per_query_errors["__cache_miss__"] = (
            f"document_idx not parsed yet (call parse_web_and_doc first): {sorted(set(missing_idxs))}"
        )

    doc_rows: List[Dict[str, Any]] = []
    if docs_by_idx:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Fan (query × doc) selector calls out concurrently —
            # serial N×M blows the 30s tool budget on batches with many
            # parsed docs (precedent: commit 60742bcf).
            plan = [
                (q_idx, query, idx, doc, doc_to_page_dicts(doc))
                for q_idx, query in enumerate(queries)
                for idx, (_fid, doc) in docs_by_idx.items()
            ]

            async def _rank(query: str, pages: list):
                return await rank_pages(query=query, pages=pages, client=client)

            outcomes = await asyncio.gather(
                *(_rank(q, pages) for _, q, _, _, pages in plan),
                return_exceptions=True,
            )
            for (q_idx, query, idx, doc, _pages), outcome in zip(plan, outcomes):
                if isinstance(outcome, Exception):
                    per_query_errors.setdefault(
                        query, f"selector failed for document_idx {idx}: {outcome}"
                    )
                    continue
                take = outcome if top_n is None else outcome[: int(top_n)]
                for page, score in take:
                    doc_rows.append({
                        "query_idx": q_idx,
                        "document_idx": idx,
                        "page": page["page"],
                        "title": doc.filename,
                        "snippet": page["content"],
                        "selector_score": score,
                    })

    # Sort by selector_score descending so the envelope matches the
    # IR-path contract (ToolResultFormatter assigns Index = <tcid>.<n>
    # from append order). Missing scores → -inf so they tail.
    doc_rows.sort(
        key=lambda r: r["selector_score"] if r.get("selector_score") is not None else float("-inf"),
        reverse=True,
    )

    envelope: Dict[str, Any] = {
        "success": True,
        "data": {"doc": doc_rows},
        "queries": queries,
        "document_idx": idxs,
        "backend": "shim (sft_pipeline selector)",
    }
    if per_query_errors:
        envelope["per_query_errors"] = per_query_errors
    return tool_result(envelope)


async def handle_doc_search(args: dict | None = None, **kwargs) -> str:
    payload = dict(args or {})
    task_id = kwargs.get("task_id") or DEFAULT_TASK_ID

    queries = payload.get("queries") or []
    if not isinstance(queries, list) or not queries:
        return tool_error("queries must be a non-empty list of strings")

    raw_idxs = payload.get("document_idx") or []
    if isinstance(raw_idxs, int):
        raw_idxs = [raw_idxs]
    if not isinstance(raw_idxs, list) or not raw_idxs:
        return tool_error("document_idx is required and must be a non-empty list of integers")
    try:
        idxs: List[int] = [int(v) for v in raw_idxs]
    except (TypeError, ValueError):
        return tool_error("document_idx entries must be integers")

    top_n = payload.get("top_n")
    rerank = payload.get("rerank", True)

    if is_local_mode():
        return await _handle_doc_search_shim(payload, task_id, queries, idxs, top_n)

    idx_to_fid, missing_idxs = _resolve_idx_to_fid(task_id, idxs)
    if missing_idxs and not idx_to_fid:
        return tool_error(
            f"document_idx not parsed yet (call parse_web_and_doc first): {missing_idxs}"
        )
    fids = list(idx_to_fid.values())

    doc_rows: List[Dict[str, Any]] = []
    per_query_errors: dict[str, str] = {}
    if missing_idxs:
        per_query_errors["__cache_miss__"] = (
            f"document_idx not parsed yet: {missing_idxs}"
        )

    for q_idx, query in enumerate(queries):
        try:
            raw_hits = await find_docs(
                query=query,
                fids=fids,
                top_n=top_n,
                rerank=rerank,
                request_id=task_id,
            )
        except Exception as exc:
            per_query_errors[query] = str(exc)
            continue
        for hit in raw_hits:
            doc_rows.append(_normalize_doc_hit(hit, q_idx, task_id))

    # Rank by IR's own ``score`` field. The previous SELECTOR-microservice
    # rerank was removed: lgair production used IR's ``rerank=1`` output
    # directly, and the selector path produced ordering inversions when
    # it returned partial coverage. See ``_policy.md`` "Selector".
    # ir-shim Mode A (local) uses a different sft_pipeline selector in
    # ``_handle_doc_search_shim`` — it is not affected by this change.
    doc_rows.sort(
        key=lambda r: r["ir_score"] if r.get("ir_score") is not None else float("-inf"),
        reverse=True,
    )
    doc_rows = _strip_internal_keys(doc_rows)

    envelope: Dict[str, Any] = {
        "success": True,
        "data": {"doc": doc_rows},
        "queries": queries,
        "document_idx": idxs,
    }
    if per_query_errors:
        envelope["per_query_errors"] = per_query_errors
    return tool_result(envelope)


def _normalize_doc_hit(
    hit: Dict[str, Any],
    query_idx: int,
    task_id: str,
) -> Dict[str, Any]:
    doc_id = hit.get("doc_id") or hit.get("id")
    page = hit.get("page_number") or hit.get("page") or hit.get("slide_num")
    fid = hit.get("fid")
    title = hit.get("title", "")
    context = hit.get("context") or hit.get("snippet") or hit.get("text", "")
    # Preserve a legitimate score of 0.0 via explicit None check.
    score = hit.get("score") if hit.get("score") is not None else hit.get("ir_score")
    document_idx = (
        get_idx_by_fid(task_id=task_id, fid=str(fid)) if fid is not None else None
    )

    row: Dict[str, Any] = {
        "query_idx": query_idx,
        "document_idx": document_idx,
        "page": page,
        "title": title,
        "snippet": context if isinstance(context, str) else json.dumps(context, ensure_ascii=False),
        # Internal-only — used by selector rerank then stripped before envelope.
        "_doc_id": doc_id,
    }
    if score is not None:
        row["ir_score"] = score
    meta = hit.get("meta_data") or hit.get("metadata")
    if isinstance(meta, dict):
        row["meta"] = meta
    return row


def _strip_internal_keys(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop any underscore-prefixed internal keys before the envelope ships."""
    cleaned: List[Dict[str, Any]] = []
    for row in rows:
        cleaned.append({k: v for k, v in row.items() if not str(k).startswith("_")})
    return cleaned


# NOTE: ``_maybe_selector_rerank`` (external SELECTOR microservice call) was
# removed from this IR-backed path. IR ``find_docs(rerank=1)`` already
# returns each hit with a ``score`` field, and the call site above sorts
# by it directly — matching production master and the lgair production
# pipeline. ir-shim Mode A (local) lives in ``_handle_doc_search_shim``
# below and continues to use the *different* ``sft_pipeline`` selector;
# the two selectors were never the same service.
