"""analyze_visual — single-image VLM analysis with preprocessing.

Two input modes for `image`:
  - opaque `Index` from a prior get_visuals row (e.g. "abc.3")
        → reverse-lookup via the per-task RunIndexStore mirror, recover the
          ImageMeta fields registered by get_visuals, load the PNG
  - http(s) URL
        → download into bytes

Then: same preprocess pipeline + OCR + VLM call as get_visuals (for one
image, no selector). Always logs to auxiliary_vlm_analyze_N.json.

Local file paths are intentionally NOT accepted — keeps the agent-facing
input space narrow.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

import httpx
from PIL import Image

from exaone.auxiliary_tracer import write_vlm_analyze_log, write_vlm_ocr_log
from exaone.visual_tools._image_ops import apply_pipeline
from exaone.visual_tools._image_resolver import resolve_image_index
from exaone.visual_tools._ocr_client import run_ocr
from exaone.visual_tools._vlm_client import build_vlm_messages, call_vlm
from tools.registry import tool_error, tool_result

logger = logging.getLogger(__name__)


ANALYZE_VISUAL_SCHEMA: dict[str, Any] = {
    "name": "analyze_visual",
    "description": (
        "Run a VLM on a single image, with optional preprocessing (rotate, "
        "upscale, sharpen, perspective). Always runs OCR. Call when "
        "(a) re-analyzing an image surfaced by a prior visual retrieval "
        "with a different goal or preprocessing, or (b) inspecting an "
        "image the user pasted as a URL."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "image": {
                "type": "string",
                "description": (
                    "Image identifier — opaque `Index` value attached to a "
                    "prior visual-retrieval row, or an http(s) URL. Local "
                    "file paths are NOT accepted."
                ),
            },
            "goal": {
                "type": "string",
                "description": "What information to extract.",
            },
            "rotate":      {"type": "integer", "enum": [0, 90, 180, 270], "default": 0},
            "upscale":     {"type": "integer", "enum": [0, 2, 3, 4], "default": 0},
            "sharpen":     {"type": "boolean", "default": False},
            "perspective": {"type": "boolean", "default": False},
        },
        "required": ["image", "goal"],
    },
}


async def _fetch_url(image: str) -> tuple[bytes | None, dict[str, Any]]:
    # SSRF guard — reuses tools/url_safety.is_safe_url so private/internal
    # ranges (localhost, RFC1918, cloud metadata IPs) are blocked. Matches
    # the policy tools/vision_tools.py already applies on the same flow.
    try:
        from tools.url_safety import is_safe_url
        if not is_safe_url(image):
            return None, {"source": "url", "url": image,
                          "error": "URL blocked by SSRF policy"}
    except Exception:
        # Fail closed: if the safety module is unavailable for any reason,
        # refuse the fetch rather than silently skipping the check.
        return None, {"source": "url", "url": image,
                      "error": "URL safety check unavailable"}
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
            resp = await c.get(image)
            resp.raise_for_status()
            return resp.content, {"source": "url", "url": image}
    except Exception as exc:
        logger.warning("image URL fetch failed: %s", exc)
        return None, {"source": "url", "url": image, "error": str(exc)}


def _load_from_index(image: str, task_id: str) -> tuple[bytes | None, dict[str, Any]]:
    # resolver handles both cropped-figure path (parser dump) and whole-page
    # render path (render cache, set by pdf_page_layout). Same Index input
    # for the agent; payload's img_idx tells the resolver which path.
    png_bytes, subject, err = resolve_image_index(image_index=image, task_id=task_id)
    if png_bytes is None:
        return None, {"source": "index", "image_index": image, "error": err or ""}
    return png_bytes, subject or {"source": "index", "image_index": image}


async def handle_analyze_visual(args: dict | None = None, **kwargs) -> str:
    payload = dict(args or {})
    task_id = kwargs.get("task_id") or "default"

    image = payload.get("image")
    if not isinstance(image, str) or not image.strip():
        return tool_error("image is required (Index or http URL)")
    goal = payload.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        return tool_error("goal is required (string)")

    rotate_deg = int(payload.get("rotate") or 0)
    upscale_factor = int(payload.get("upscale") or 0)
    do_sharpen = bool(payload.get("sharpen"))
    perspective = bool(payload.get("perspective"))

    image = image.strip()
    if image.startswith(("http://", "https://")):
        png_bytes, subject = await _fetch_url(image)
    else:
        png_bytes, subject = _load_from_index(image, task_id)

    if png_bytes is None:
        return tool_error(subject.get("error") or "could not resolve image")

    try:
        img = Image.open(io.BytesIO(png_bytes))
        img.load()
        img, applied_ops = apply_pipeline(
            img,
            perspective=perspective,
            upscale_factor=upscale_factor,
            do_sharpen=do_sharpen,
            rotate_deg=rotate_deg,
        )
        out = io.BytesIO()
        img.save(out, format="PNG")
        ocr = run_ocr(img)
        ocr_text = ocr.get("text", "")
        processed_bytes = out.getvalue()
    except Exception as exc:
        logger.exception("preprocess/ocr failed")
        return tool_error(f"preprocess/ocr failed: {exc}")

    if ocr_text:
        try:
            write_vlm_ocr_log(
                image_uri=image, ocr_text=ocr_text,
                meta=dict(subject),
            )
        except Exception:
            pass

    messages = build_vlm_messages(
        png_bytes=processed_bytes,
        goal=goal,
        category=subject.get("category", ""),
        caption=subject.get("caption", ""),
        description=subject.get("description", ""),
    )
    analysis = await call_vlm(messages)

    try:
        write_vlm_analyze_log(
            messages=messages, assistant=analysis,
            meta={**subject, "goal": goal, "applied_ops": applied_ops,
                  "ocr_char_count": len(ocr_text)},
        )
    except Exception:
        pass

    envelope: dict[str, Any] = {
        "success": True,
        "image_source": subject.get("source"),
        "analysis": analysis,
        "ocr_text": ocr_text,
        "applied_ops": applied_ops,
        "goal": goal,
    }
    return tool_result(envelope)
