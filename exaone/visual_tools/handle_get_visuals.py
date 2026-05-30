"""get_visuals — scope-based image retrieval + parallel VLM extraction.

Flow:
  1. parse scope ("1@5" / "1" — same document_idx the model uses elsewhere)
     + web_refs (Index strings from a prior web_search/web_extract result)
  2. resolve doc scope via _attachments → enumerate ImageMeta from
     docai/out parsing JSONs
  3. (optional) category filter
  4. per-query selector ranking on caption + description + category text
     → per-query top_n → concat + dedup
  5. for each selected image, in parallel:
       - load PNG bytes
       - apply preprocess pipeline (perspective → upscale → sharpen → rotate)
       - run OCR (always; ocr_text → result)
       - call VLM with assembled chat-messages + goal
       - write auxiliary_vlm_get_visuals_N.json via auxiliary_tracer
  6. return raw row list under data.results — ToolResultFormatter
     attaches the <tcid>.<n> Index and registers each row in RunIndexStore
     (payload carries fid/page/img_idx so analyze_visual can re-find the
     same image later).

Web RAG path: stubbed (web image fetch needs the prod-only Webpage Modality
Analyze endpoint). Web refs surface as per-ref errors so the agent can
fall back gracefully.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from PIL import Image

from exaone.auxiliary_tracer import write_vlm_get_visuals_log, write_vlm_ocr_log
from exaone.visual_tools._image_index import (
    ImageMeta,
    load_png_bytes,
)
from exaone.visual_tools._image_ops import apply_pipeline
from exaone.visual_tools._image_resolver import (
    enumerate_scope_images,
    resolve_doc_scope,
    resolve_web_refs,
)
from exaone.visual_tools._ocr_client import run_ocr
from exaone.visual_tools._scope import parse_scope
from exaone.visual_tools._vlm_client import build_vlm_messages, call_vlm
from tools.registry import tool_error, tool_result

logger = logging.getLogger(__name__)


_VALID_CATEGORIES = ("chart", "diagram", "photo", "table", "figure")


GET_VISUALS_SCHEMA: dict[str, Any] = {
    "name": "get_visuals",
    "description": (
        "Find figures/charts/photos relevant to the queries within the given "
        "scope of doc-pages (and/or web pages) and run a VLM on the top "
        "candidates in parallel. Returns per-image extraction + OCR + "
        "metadata. Call after the relevant doc-page scope has been "
        "identified through textual retrieval. `scope` items reference "
        "documents by the same `document_idx` integer shown in the "
        "[Attached documents] block; `web_refs` reference web results by "
        "the `Index` value attached to each prior web hit."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "scope": {
                "type": "array", "items": {"type": "string"},
                "description": (
                    "List of doc-page items. Each item is '<document_idx>@<page>' "
                    "(e.g. '1@5') for a specific page, OR '<document_idx>' "
                    "(e.g. '1') for all pages of that document. Mix freely: "
                    "['1@5','1@6','2','3@10']."
                ),
            },
            "web_refs": {
                "type": "array", "items": {"type": "string"},
                "description": (
                    "List of web result `Index` values copied verbatim from "
                    "a prior web hit (e.g. ['abc.0','abc.1']). Do NOT type URLs."
                ),
            },
            "queries": {
                "type": "array", "items": {"type": "string"},
                "minItems": 1, "maxItems": 3,
                "description": (
                    "1-3 short queries describing what visual content to "
                    "find. Used by the selector to rank candidates against "
                    "image caption + description metadata."
                ),
            },
            "goal": {
                "type": "string",
                "description": (
                    "What information to extract from each chosen image. "
                    "Restate the user-facing question this set of images "
                    "needs to answer; passed verbatim to the VLM per image."
                ),
            },
            "category": {
                "type": "string", "enum": list(_VALID_CATEGORIES),
                "description": "Optional category filter.",
            },
            "top_n": {
                "type": "integer", "minimum": 1, "maximum": 10, "default": 5,
                "description": "Per-query selector cap before dedup.",
            },
            # Global preprocessing flags applied to every selected image
            # before the VLM call, in canonical order:
            # perspective → upscale → sharpen → rotate.
            "rotate":      {"type": "integer", "enum": [0, 90, 180, 270], "default": 0},
            "upscale":     {"type": "integer", "enum": [0, 2, 3, 4], "default": 0,
                            "description": "0 = off; 2/3/4 = EDSR super-resolution scale."},
            "sharpen":     {"type": "boolean", "default": False},
            "perspective": {"type": "boolean", "default": False},
        },
        "required": ["queries", "goal"],
    },
}


# ─── selector (deterministic text overlap) ─────────────────────────────────

def _score_one(text: str, query_tokens: set[str]) -> int:
    text_lower = text.lower()
    return sum(1 for tok in query_tokens if tok in text_lower)


def _select_top(
    candidates: list[tuple[Any, ImageMeta]],   # (DocScope, ImageMeta)
    queries: list[str],
    top_n: int,
) -> list[tuple[Any, ImageMeta, float]]:
    query_token_sets = [
        {tok for tok in q.lower().split() if tok}
        for q in queries
    ]
    by_key: dict[tuple[str, int, int], tuple[Any, ImageMeta, float]] = {}
    for q_toks in query_token_sets:
        if not q_toks:
            continue
        scored: list[tuple[Any, ImageMeta, float]] = []
        for sc, meta in candidates:
            blob = f"{meta.caption} {meta.description} {meta.category}"
            s = _score_one(blob, q_toks)
            if s > 0:
                scored.append((sc, meta, float(s)))
        scored.sort(key=lambda x: x[2], reverse=True)
        for sc, meta, s in scored[: max(top_n, 1)]:
            key = (meta.short_fid, meta.page, meta.idx)
            prev = by_key.get(key)
            if prev is None or s > prev[2]:
                by_key[key] = (sc, meta, s)
    return sorted(by_key.values(), key=lambda x: x[2], reverse=True)


# ─── per-image VLM worker ──────────────────────────────────────────────────

async def _process_image(
    *,
    doc_idx: int,
    meta: ImageMeta,
    goal: str,
    perspective: bool,
    upscale_factor: int,
    do_sharpen: bool,
    rotate_deg: int,
    selector_score: float,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "source": "doc",
        "document_idx": doc_idx,
        "fid": meta.short_fid,
        "page": meta.page,
        "img_idx": meta.idx,
        "category": meta.category,
        "caption": meta.caption,
        "description": meta.description,
        "bbox": meta.bbox,
        "selector_score": selector_score,
    }
    png_bytes = await asyncio.to_thread(load_png_bytes, meta)
    if png_bytes is None:
        row["error"] = "png missing on disk"
        return row

    def _do_cpu_work() -> tuple[bytes, list[str], str]:
        img = Image.open(io.BytesIO(png_bytes))
        img.load()
        img, applied = apply_pipeline(
            img,
            perspective=perspective,
            upscale_factor=upscale_factor,
            do_sharpen=do_sharpen,
            rotate_deg=rotate_deg,
        )
        out = io.BytesIO()
        img.save(out, format="PNG")
        ocr = run_ocr(img)
        return out.getvalue(), applied, ocr.get("text", "")

    try:
        processed_bytes, applied_ops, ocr_text = await asyncio.to_thread(_do_cpu_work)
    except Exception as exc:
        logger.exception("preprocess/ocr failed for %s", meta.png_path)
        row["error"] = f"preprocess/ocr failed: {exc}"
        return row

    row["applied_ops"] = applied_ops
    row["ocr_text"] = ocr_text

    # OCR run captured separately in tool_ocr_*.json (flatter schema —
    # OCR isn't a chat turn). auxiliary_tracer manages per-run sequence
    # internally so we don't pass an idx.
    if ocr_text:
        try:
            write_vlm_ocr_log(
                image_uri=str(meta.png_path),
                ocr_text=ocr_text,
                meta={"fid": meta.short_fid, "page": meta.page,
                      "img_idx": meta.idx, "document_idx": doc_idx},
            )
        except Exception:
            pass

    messages = build_vlm_messages(
        png_bytes=processed_bytes,
        goal=goal,
        category=meta.category,
        caption=meta.caption,
        description=meta.description,
    )
    analysis = await call_vlm(messages)
    row["analysis"] = analysis

    try:
        write_vlm_get_visuals_log(
            messages=messages,
            assistant=analysis,
            meta={"document_idx": doc_idx, "fid": meta.short_fid,
                  "page": meta.page, "img_idx": meta.idx,
                  "goal": goal, "applied_ops": applied_ops,
                  "selector_score": selector_score},
        )
    except Exception:
        pass
    return row


# ─── handler ───────────────────────────────────────────────────────────────

async def handle_get_visuals(args: dict | None = None, **kwargs) -> str:
    payload = dict(args or {})
    task_id = kwargs.get("task_id") or "default"

    queries = payload.get("queries") or []
    if not isinstance(queries, list) or not queries:
        return tool_error("queries must be a non-empty list of strings")
    goal = payload.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        return tool_error("goal is required (string)")

    raw_scope = payload.get("scope") or []
    raw_web_refs = payload.get("web_refs") or []
    if not raw_scope and not raw_web_refs:
        return tool_error("at least one of scope / web_refs must be provided")
    if not raw_scope and raw_web_refs:
        # Web image fetch is a shim stub today (see resolve_web_refs path
        # below — produces error rows only). Reject a web-only call upfront
        # so the agent doesn't get a misleading success envelope full of
        # error rows. When the prod Webpage Modality Analyze backend is
        # wired, remove this gate.
        return tool_error(
            "web image fetch is not implemented in this build; pass "
            "`scope` items for in-document images"
        )

    try:
        scope_items = parse_scope(raw_scope) if raw_scope else []
    except ValueError as exc:
        return tool_error(str(exc))

    category = payload.get("category")
    if category is not None and category not in _VALID_CATEGORIES:
        return tool_error(
            f"category must be one of {list(_VALID_CATEGORIES)} or omitted"
        )

    top_n = int(payload.get("top_n") or 5)
    rotate_deg = int(payload.get("rotate") or 0)
    upscale_factor = int(payload.get("upscale") or 0)
    do_sharpen = bool(payload.get("sharpen"))
    perspective = bool(payload.get("perspective"))

    per_item_errors: dict[str, str] = {}

    doc_scopes: list = []
    if scope_items:
        doc_scopes, scope_errs = resolve_doc_scope(scope_items, task_id=task_id)
        per_item_errors.update(scope_errs)

    # enumerate_scope_images reads parser JSON files synchronously — can be
    # multi-MB per doc. Wrap in to_thread so the event loop stays free for
    # the parallel VLM calls below.
    paired = await asyncio.to_thread(enumerate_scope_images, doc_scopes)
    if category:
        paired = [(s, m) for (s, m) in paired if m.category == category]

    ranked = _select_top(paired, queries, top_n)

    web_results: list[dict[str, Any]] = []
    web_scopes, web_errs = resolve_web_refs(raw_web_refs, task_id=task_id)
    per_item_errors.update(web_errs)
    for ws in web_scopes:
        web_results.append({
            "source": "web", "web_ref": ws.web_ref, "url": ws.url,
            "title": ws.title, "snippet": ws.snippet,
            "error": ("web image fetch not implemented in shim — use "
                      "web_extract for textual content"),
        })

    tasks = [
        _process_image(
            doc_idx=sc.doc_idx, meta=meta, goal=goal,
            perspective=perspective, upscale_factor=upscale_factor,
            do_sharpen=do_sharpen, rotate_deg=rotate_deg,
            selector_score=score,
        )
        for (sc, meta, score) in ranked
    ]
    doc_results: list[dict[str, Any]] = []
    if tasks:
        doc_results = await asyncio.gather(*tasks)

    envelope: dict[str, Any] = {
        "success": True,
        "data": {"results": doc_results + web_results},
        "queries": queries,
        "goal": goal,
        "scope": raw_scope,
        "web_refs": raw_web_refs,
        "candidate_count": len(paired),
        "selected_count": len(ranked),
    }
    if per_item_errors:
        envelope["per_item_errors"] = per_item_errors
    return tool_result(envelope)
