"""list_documents — show every document in the session's fid pool.

Behaviour:
    Caller hands over the lgair-style fid sourcing keys
    (``document_file_ids`` + ``public_document_file_ids``); their
    union is the canonical fid pool for this turn. We sort the union
    deterministically (so the same input always yields the same
    ``document_idx`` mapping) and emit one row per fid with the cache
    state — *including fids that have not been parsed yet* so the
    model knows it still needs to call ``parse_web_and_doc`` on them.

The model never sees the underlying fid. Only ``document_idx``
(1-based, ephemeral to this listing) plus the filename and parse
metadata.

## SHARED LOGIC

This file is kept byte-identical on ``master`` and ``sft-gen-ir-shim``.
The output shape (document_idx, filename, parsed, page_count,
char_count) is the public contract — when you edit it, mirror to the
other branch in the same patch. See ``exaone/docqa_tools/_policy.md``
"Shared logic files".
"""

from __future__ import annotations

from typing import Any, Dict, List

from exaone.docqa_tools._doc_cache import DEFAULT_TASK_ID, get_document
from tools.registry import tool_error, tool_result


LIST_DOCUMENTS_SCHEMA: dict[str, Any] = {
    "name": "list_documents",
    "description": (
        "Show every document in this session's fid pool with its current "
        "parse state. Returns one row per fid (deterministic order); rows "
        "for documents that have not been parsed yet show `parsed: false` "
        "so the agent can decide whether to call `parse_web_and_doc` "
        "before issuing `doc_search`. The model only sees `document_idx` "
        "(1-based, ephemeral to this listing) and the filename — internal "
        "identifiers are not exposed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "document_file_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Caller-owned (private) file ids the user uploaded "
                    "or saved in their personal document library."
                ),
            },
            "public_document_file_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "System-public file ids (shared knowledge base). "
                    "Combined with `document_file_ids` to form the "
                    "listed pool."
                ),
            },
        },
        "required": [],
    },
}


async def handle_list_documents(args: dict | None = None, **kwargs) -> str:
    payload = dict(args or {})
    task_id = kwargs.get("task_id") or DEFAULT_TASK_ID

    private_fids = payload.get("document_file_ids") or []
    public_fids = payload.get("public_document_file_ids") or []
    if not isinstance(private_fids, list) or not isinstance(public_fids, list):
        return tool_error(
            "document_file_ids and public_document_file_ids must be lists of strings"
        )

    # Deterministic sort so the same union always yields the same
    # document_idx mapping across calls within a session. Empty union
    # → empty results (no tool_error — the caller might legitimately
    # have no documents at this point).
    fids = sorted({str(f) for f in (list(private_fids) + list(public_fids)) if f})

    rows: List[Dict[str, Any]] = []
    for idx, fid in enumerate(fids, start=1):
        doc = get_document(task_id=task_id, fid=fid)
        if doc is not None and doc.chunks:
            rows.append({
                "document_idx": idx,
                "filename":     doc.filename,
                "parsed":       True,
                "page_count":   doc.page_count,
                "char_count":   doc.char_count,
            })
        else:
            rows.append({
                "document_idx": idx,
                "filename":     "",
                "parsed":       False,
                "page_count":   0,
                "char_count":   0,
            })

    return tool_result({
        "tool_name":      "list_documents",
        "document_count": len(rows),
        "results":        rows,
    })
