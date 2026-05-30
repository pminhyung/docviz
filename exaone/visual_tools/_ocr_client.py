"""OCR adapter for visual_tools.

Default (shim): local paddleocr. Lazy-loaded — first call instantiates the
PaddleOCR model, subsequent calls reuse it. Always runs in `analyze_visual`
and `get_visuals` so the SFT trajectory has OCR text alongside the VLM
output (per project decision — image metadata does NOT carry OCR).

Production: set EXAONE_OCR_URL to swap to an external OCR HTTP service that
returns `{"text": "...", "blocks": [...]}`. Kept as a stub branch here so
the call surface stays identical across environments.

Failures degrade gracefully: returns empty string + flag in `extra` rather
than raising — OCR is best-effort augmentation, not a hard dependency.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

_ENGINE = None
_ENGINE_LOCK = threading.Lock()


def _get_paddle_engine():
    """Lazy-init PaddleOCR. Korean + English by default (corpus is mixed)."""
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            return _ENGINE
        try:
            from paddleocr import PaddleOCR
        except Exception:
            logger.warning("paddleocr not installed — OCR will return empty text")
            return None
        try:
            _ENGINE = PaddleOCR(use_angle_cls=True, lang="korean", show_log=False)
        except Exception:
            logger.exception("paddleocr init failed — OCR will return empty text")
            _ENGINE = None
    return _ENGINE


def run_ocr(img: Image.Image) -> dict[str, Any]:
    """Return {'text': str, 'engine': str, 'ok': bool}.

    Always returns a dict (never raises). Empty text + ok=False on failure.
    """
    prod_url = os.environ.get("EXAONE_OCR_URL", "").strip()
    if prod_url:
        # Production path — external OCR API. Implement when the prod service
        # contract is finalized; current shim deployments don't hit this.
        try:
            return _run_prod_ocr(img, prod_url)
        except Exception:
            logger.exception("prod OCR failed (%s); falling back to local", prod_url)

    engine = _get_paddle_engine()
    if engine is None:
        return {"text": "", "engine": "none", "ok": False}
    try:
        import numpy as np
        arr = np.array(img.convert("RGB"))
        result = engine.ocr(arr, cls=True)
        # paddleocr result: [[ [bbox, (text, conf)], ... ]] per page.
        lines: list[str] = []
        for page in (result or []):
            for entry in (page or []):
                if not entry or len(entry) < 2:
                    continue
                text_block = entry[1]
                if isinstance(text_block, (list, tuple)) and text_block:
                    lines.append(str(text_block[0]))
        return {"text": "\n".join(lines), "engine": "paddleocr", "ok": True}
    except Exception:
        logger.exception("paddleocr.ocr failed")
        return {"text": "", "engine": "paddleocr", "ok": False}


def _run_prod_ocr(img: Image.Image, url: str) -> dict[str, Any]:
    """Production OCR via external HTTP service. STUB — wire up when finalized."""
    raise NotImplementedError("EXAONE_OCR_URL prod path not yet wired")
