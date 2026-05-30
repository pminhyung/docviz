"""pdf_page_layout — render full PDF page(s) as images for layout inspection.

Purpose: get_visuals returns CROPPED figures, losing spatial context (which
section the figure sits in, surrounding text, column structure). For
layout-aware questions the agent needs the WHOLE page rendered.

Shim: use PyMuPDF (fitz) to rasterize the raw PDF page. Raw PDF path comes
from file_mapping.json → absolute_path.

Prod: backend can be swapped to a remote page-render endpoint with the
same scope-item input + image-handle output shape; no agent-visible change.

Returned rows go through ToolResultFormatter — each gets a `<tcid>.<n>`
Index plus a payload (fid, page) so analyze_visual can later re-render or
inspect the same page.
"""

from __future__ import annotations

import logging
from typing import Any

from exaone.docqa_tools._attachments import get_fid_by_idx
from exaone.docqa_tools._doc_cache import get_document
from exaone.visual_tools._image_index import resolve_fid_by_filename
from exaone.visual_tools._render_cache import register_render
from exaone.visual_tools._scope import parse_scope
from tools.registry import tool_error, tool_result

logger = logging.getLogger(__name__)


PDF_PAGE_LAYOUT_SCHEMA: dict[str, Any] = {
    "name": "pdf_page_layout",
    "description": (
        "Render full PDF page(s) as images for spatial/layout inspection. "
        "Use when you need to see how figures relate to surrounding text, "
        "table positions, or column structure — context that cropped "
        "figures don't convey. Returns opaque image handles; pair with a "
        "visual analysis call to extract layout info."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "scope": {
                "type": "array", "items": {"type": "string"},
                "description": (
                    "List of '<document_idx>@<page>' items (e.g. "
                    "['1@5','1@7']). Each item MUST specify a page (no "
                    "doc-only form here — that would render entire documents)."
                ),
            },
            "dpi": {
                "type": "integer", "enum": [100, 150, 200], "default": 150,
                "description": "Render resolution.",
            },
        },
        "required": ["scope"],
    },
}


def _render_pdf_page(pdf_path, page: int, dpi: int) -> bytes | None:
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF (fitz) not installed — pdf_page_layout unavailable")
        return None
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning("fitz.open failed for %s: %s", pdf_path, exc)
        return None
    try:
        if page < 1 or page > doc.page_count:
            return None
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = doc.load_page(page - 1).get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")
    except Exception:
        logger.exception("fitz render failed: %s p%d", pdf_path, page)
        return None
    finally:
        doc.close()


async def handle_pdf_page_layout(args: dict | None = None, **kwargs) -> str:
    payload = dict(args or {})
    task_id = kwargs.get("task_id") or "default"

    raw_scope = payload.get("scope") or []
    if not raw_scope:
        return tool_error("scope is required and must be non-empty")

    dpi = int(payload.get("dpi") or 150)
    if dpi not in (100, 150, 200):
        return tool_error("dpi must be 100, 150, or 200")

    try:
        scope_items = parse_scope(raw_scope)
    except ValueError as exc:
        return tool_error(str(exc))

    pages_out: list[dict[str, Any]] = []
    per_item_errors: dict[str, str] = {}

    for item in scope_items:
        item_str = (
            f"{item.doc_idx}@{item.page}" if item.page is not None
            else str(item.doc_idx)
        )
        if item.page is None:
            per_item_errors[item_str] = (
                "pdf_page_layout requires a page — use '<document_idx>@<page>'."
            )
            continue

        fid = get_fid_by_idx(task_id=task_id, idx=item.doc_idx)
        if fid is None:
            per_item_errors[item_str] = (
                f"document_idx {item.doc_idx} not parsed yet — call parse_web_and_doc first"
            )
            continue
        doc = get_document(task_id=task_id, fid=fid)
        if doc is None:
            per_item_errors[item_str] = (
                f"document_idx {item.doc_idx}: doc {fid} missing from task cache"
            )
            continue
        if doc.extension and doc.extension.lower() != "pdf":
            per_item_errors[item_str] = (
                f"pdf_page_layout supports PDF only; "
                f"{doc.filename!r} is {doc.extension!r}"
            )
            continue
        info = resolve_fid_by_filename(doc.filename)
        if info is None:
            per_item_errors[item_str] = (
                f"document_idx {item.doc_idx}: no shim pre-parse for "
                f"{doc.filename!r}"
            )
            continue

        png = _render_pdf_page(info.raw_pdf_path, item.page, dpi)
        if png is None:
            per_item_errors[item_str] = (
                f"render failed for {info.raw_pdf_path} page {item.page}"
            )
            continue

        # Cache the bytes so analyze_visual can find them later via the
        # same Index. Without this the (fid, page, img_idx=-1) payload
        # would be unresolvable since the parser dump only has positive
        # img_idx values for cropped figures.
        register_render(
            task_id=task_id, fid=info.short_fid,
            page=item.page, png_bytes=png,
        )
        pages_out.append({
            "document_idx": item.doc_idx,
            "fid": info.short_fid,
            "page": item.page,
            "img_idx": -1,
            "extension": doc.extension,
            "filename": doc.filename,
            "dpi": dpi,
            "png_bytes_len": len(png),
        })

    envelope: dict[str, Any] = {
        "success": True,
        "data": {"pages": pages_out},
        "scope": raw_scope,
        "dpi": dpi,
    }
    if per_item_errors:
        envelope["per_item_errors"] = per_item_errors
    return tool_result(envelope)
