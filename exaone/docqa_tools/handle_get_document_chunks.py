"""get_document_chunks — fetch specific cached pages by (document_idx, page).

Same role as doc_agent_v2 GetPage (renamed to get_document_chunks in the
5/18 design). Reads from the per-task cache populated by parse_web_and_doc —
no parser or IR round-trip needed.

Input format: each item is the string ``"<document_idx>-<page>"`` (e.g.
``"1-3"`` = page 3 of attached document 1). Multiple pages per call OK.
The agent never sees the underlying fid; the handler resolves idx -> fid
internally via the per-task attachment table.
"""

from __future__ import annotations

from typing import Any, Dict, List

from exaone.docqa_tools._attachments import get_fid_by_idx
from exaone.docqa_tools._doc_cache import DEFAULT_TASK_ID, get_document
from tools.registry import tool_error, tool_result


GET_DOCUMENT_CHUNKS_SCHEMA: dict[str, Any] = {
    "name": "get_document_chunks",
    "description": (
        "Retrieve full text for specific document pages. Each entry in "
        "`doc_page` must be the string '<document_idx>-<page>' (e.g. "
        "'1-3' = page 3 of attached document 1). The referenced documents "
        "must have been parsed earlier in this task via parse_web_and_doc."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doc_page": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of '<document_idx>-<page>' strings to retrieve."
                ),
            },
        },
        "required": ["doc_page"],
    },
}


async def handle_get_document_chunks(args: dict | None = None, **kwargs) -> str:
    payload = dict(args or {})
    task_id = kwargs.get("task_id") or DEFAULT_TASK_ID
    requested = payload.get("doc_page") or []
    if not isinstance(requested, list) or not requested:
        return tool_error(
            "doc_page must be a non-empty list of '<document_idx>-<page>' strings"
        )

    results: List[Dict[str, Any]] = []
    missing: List[str] = []

    for item in requested:
        if not isinstance(item, str) or "-" not in item:
            missing.append(item)
            continue
        idx_str, _, page = item.partition("-")
        page = page or ""
        try:
            idx = int(idx_str)
        except ValueError:
            missing.append(item)
            continue
        fid = get_fid_by_idx(task_id=task_id, idx=idx)
        if fid is None:
            missing.append(item)
            continue
        doc = get_document(task_id=task_id, fid=fid)
        if doc is None:
            missing.append(item)
            continue
        # Chunk-granular cache: fold all chunks on the requested page
        # back into a single text/html block. See _doc_cache.py
        # "Cache shape".
        chunks = doc.chunks_on_page(page)
        if not chunks:
            missing.append(item)
            continue
        text = "\n\n".join(c.text for c in chunks if c.text)
        html = "\n\n".join(c.html for c in chunks if c.html)
        results.append(
            {
                "type": "doc",
                "document_idx": idx,
                "page": page,
                "text": text,
                "html": html,
                "char_count": len(text),
                "chunk_count": len(chunks),
            }
        )

    envelope: Dict[str, Any] = {
        "tool_name": "get_document_chunks",
        "results": results,
    }
    if missing:
        envelope["missing"] = missing
    return tool_result(envelope)
