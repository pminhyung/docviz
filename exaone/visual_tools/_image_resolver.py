"""Resolve get_visuals / pdf_page_layout / analyze_visual inputs to fetchable handles.

Three resolutions live here, all aligned with the existing sft-gen-ir-shim
infrastructure (same idx-based interface as docqa_tools, same RunIndexStore
for web/visual cross-handler lookup):

  scope items   →  (fid, fid_info, page-set per doc)
      `doc_idx` (int) → `_attachments.get_fid_by_idx(task_id, doc_idx)`
      fid → `_doc_cache.get_document(task_id, fid)` for filename
      filename → `_image_index.resolve_fid_by_filename` for shim PNG dir

  web_refs[i]   →  url
      `<tcid>.<n>` Index → `tool_formatting.get_index_store_for_task(task_id)`
      → `RunIndexStore.get(index)` → payload['url']

  ImageMeta     →  PNG bytes
      Simple file read via _image_index.load_png_bytes.

Failures return None / error dict per item so the handler can surface
partial results — agent can adapt without hard tool_error.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, NamedTuple

from exaone.docqa_tools._attachments import get_fid_by_idx
from exaone.docqa_tools._doc_cache import get_document
from exaone.tool_formatting import get_index_store_for_task
from exaone.visual_tools._image_index import (
    FidInfo,
    ImageMeta,
    list_images_for_fid,
    resolve_fid_by_filename,
)
from exaone.visual_tools._scope import ScopeItem

logger = logging.getLogger(__name__)


class DocScope(NamedTuple):
    doc_idx: int
    fid: str
    fid_info: FidInfo
    pages: set[int] | None      # None ⇒ all pages


class WebScope(NamedTuple):
    web_ref: str
    url: str
    title: str
    snippet: str


# ─── doc scope resolution ───────────────────────────────────────────────────

def resolve_doc_scope(
    items: Iterable[ScopeItem],
    *,
    task_id: str,
) -> tuple[list[DocScope], dict[str, str]]:
    """Group scope items by doc_idx → DocScope with merged page filters.

    Returns (resolved, errors). errors keyed by the user-facing scope-item
    string ("1@5" / "1") for traceability.
    """
    page_sets: dict[int, set[int] | None] = {}
    item_strings: dict[int, str] = {}
    for it in items:
        if it.page is None:
            page_sets[it.doc_idx] = None
            item_strings.setdefault(it.doc_idx, str(it.doc_idx))
        else:
            cur = page_sets.get(it.doc_idx, set())
            if cur is not None:
                cur.add(it.page)
                page_sets[it.doc_idx] = cur
            item_strings.setdefault(it.doc_idx, f"{it.doc_idx}@{it.page}")

    resolved: list[DocScope] = []
    errors: dict[str, str] = {}
    for doc_idx, pages in page_sets.items():
        fid = get_fid_by_idx(task_id=task_id, idx=doc_idx)
        if fid is None:
            errors[item_strings[doc_idx]] = (
                f"document_idx {doc_idx} not parsed yet — call parse_web_and_doc first"
            )
            continue
        doc = get_document(task_id=task_id, fid=fid)
        if doc is None:
            errors[item_strings[doc_idx]] = (
                f"document_idx {doc_idx} (fid {fid}) missing from task cache"
            )
            continue
        info = resolve_fid_by_filename(doc.filename)
        if info is None:
            errors[item_strings[doc_idx]] = (
                f"document_idx {doc_idx}: shim pre-parse unavailable for "
                f"{doc.filename!r}"
            )
            continue
        resolved.append(DocScope(
            doc_idx=doc_idx,
            fid=fid,
            fid_info=info,
            pages=pages if pages else None,
        ))
    return resolved, errors


def enumerate_scope_images(
    doc_scopes: Iterable[DocScope],
) -> list[tuple[DocScope, ImageMeta]]:
    out: list[tuple[DocScope, ImageMeta]] = []
    for sc in doc_scopes:
        for meta in list_images_for_fid(sc.fid_info, pages=sc.pages):
            out.append((sc, meta))
    return out


# ─── web scope resolution ──────────────────────────────────────────────────

def resolve_web_refs(
    refs: Iterable[str],
    *,
    task_id: str,
) -> tuple[list[WebScope], dict[str, str]]:
    """web_search Index strings → WebScope (url + display fields).

    web_search/web_extract results go through the same TOOL_RESULT_FORMATS
    pipeline as docqa tools, so their Index lives in the per-task mirrored
    RunIndexStore. We read URLs directly from the registered payload.
    """
    store = get_index_store_for_task(task_id)
    out: list[WebScope] = []
    errors: dict[str, str] = {}
    if store is None:
        for r in refs or []:
            errors[str(r)] = "no run index store bound for this task"
        return out, errors
    for r in refs or []:
        ref = str(r).strip()
        if not ref:
            continue
        payload = store.get(ref)
        if not payload:
            errors[ref] = f"web_ref {ref!r} not in web_search index"
            continue
        out.append(WebScope(
            web_ref=ref,
            url=str(payload.get("url") or ""),
            title=str(payload.get("site_name") or ""),
            snippet=str(payload.get("snippet") or ""),
        ))
    return out, errors


# ─── image ref resolution (analyze_visual) ─────────────────────────────────

def resolve_image_index(
    *, image_index: str, task_id: str,
) -> tuple[bytes | None, dict[str, Any] | None, str | None]:
    """Recover PNG bytes + subject meta from an Index emitted by a visual tool.

    Two paths share this resolver because both visual producers register
    payloads with the same shape (fid, page, img_idx):
      img_idx >= 0   → cropped figure from get_visuals
                       → enumerate parser dump, read PNG from disk
      img_idx == -1  → whole-page render from pdf_page_layout
                       → read bytes from _render_cache (parser dump has no
                         entry for this)

    Returns (png_bytes, subject_meta, error). On error, png_bytes/subject
    are None and error carries a human-readable reason.
    """
    store = get_index_store_for_task(task_id)
    if store is None:
        return None, None, "no run index store bound for this task"
    payload = store.get(image_index)
    if not payload:
        return None, None, (
            f"image Index {image_index!r} not found — call a visual tool "
            "in this task first"
        )
    fid = str(payload.get("fid") or "")
    page = int(payload.get("page") or 0)
    img_idx_raw = payload.get("img_idx")
    img_idx = int(img_idx_raw) if img_idx_raw is not None else -1
    if not fid:
        return None, None, f"image Index {image_index!r} payload missing 'fid'"

    if img_idx < 0:
        # Whole-page render. Bytes live in the per-task render cache.
        from exaone.visual_tools._render_cache import lookup_render
        bytes_ = lookup_render(task_id=task_id, fid=fid, page=page)
        if bytes_ is None:
            return None, None, (
                f"image Index {image_index!r}: render not cached for "
                f"(fid={fid}, page={page}) — re-run the layout tool"
            )
        return bytes_, {
            "source": "render", "image_index": image_index,
            "fid": fid, "page": page, "img_idx": img_idx,
        }, None

    # Cropped figure from get_visuals. Re-enumerate to read PNG path
    # (cheaper than caching bytes; parser dump is on local disk).
    doc = get_document(task_id=task_id, fid=fid)
    if doc is None:
        return None, None, (
            f"image Index {image_index!r}: fid {fid} not in task cache"
        )
    info = resolve_fid_by_filename(doc.filename)
    if info is None:
        return None, None, (
            f"image Index {image_index!r}: shim pre-parse unavailable for "
            f"{doc.filename!r}"
        )
    metas = [m for m in list_images_for_fid(info, pages=[page]) if m.idx == img_idx]
    if not metas:
        return None, None, (
            f"image Index {image_index!r}: meta not found for "
            f"(fid={fid}, page={page}, idx={img_idx})"
        )
    meta = metas[0]
    if not meta.png_path.is_file():
        return None, None, f"PNG missing on disk: {meta.png_path}"
    return meta.png_path.read_bytes(), {
        "source": "index", "image_index": image_index,
        "fid": meta.short_fid, "page": meta.page, "img_idx": meta.idx,
        "category": meta.category, "caption": meta.caption,
        "description": meta.description,
    }, None
