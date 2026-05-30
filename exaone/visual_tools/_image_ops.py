"""Image preprocessing pipeline for visual_tools.

Ports OpenSearch-VL's ImageToolEngine + ImageEnhancementEngine into a small
local module so we don't pull the whole opensearch_vl package. Operates on
PIL.Image objects; cv2 is loaded lazily and ops gracefully degrade or no-op
when it is not installed.

Canonical order (applied by handlers): perspective → upscale → sharpen → rotate.
(Crop is omitted by design — see _scope/handle_get_visuals comments: docai/out
PNGs are already cropped by the parser, so re-cropping in the shim is a no-op.)

Production note: shim runs cv2 locally; in prod the same input/output shape can
be backed by a remote enhancement service (just swap the body of each op).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False


_MODELS_DIR = Path(__file__).parent / "_models"

# Lazy-loaded super-resolution model handle cache (one per scale).
_SR_CACHE: dict[int, Any] = {}


# ─── perspective_correct ────────────────────────────────────────────────────

def perspective_correct(img: Image.Image) -> Image.Image:
    """Auto-detect dominant quadrilateral and warp it flat. cv2 required."""
    if not _CV2_AVAILABLE:
        logger.debug("perspective_correct: cv2 unavailable — passthrough")
        return img
    arr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 75, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    quad = None
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            quad = approx.reshape(4, 2)
            break
    if quad is None:
        return img
    # order pts: tl, tr, br, bl
    s = quad.sum(axis=1)
    diff = np.diff(quad, axis=1)
    ordered = np.array([
        quad[np.argmin(s)], quad[np.argmin(diff)],
        quad[np.argmax(s)], quad[np.argmax(diff)],
    ], dtype="float32")
    (tl, tr, br, bl) = ordered
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if width < 10 or height < 10:
        return img
    dst = np.array([[0, 0], [width - 1, 0],
                    [width - 1, height - 1], [0, height - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(ordered, dst)
    warped = cv2.warpPerspective(arr, M, (width, height))
    return Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))


# ─── upscale ───────────────────────────────────────────────────────────────

def upscale(img: Image.Image, scale: int) -> Image.Image:
    """EDSR super-resolution via cv2.dnn_superres; LANCZOS fallback.

    `scale=0` means off. Supported scales: 2, 3, 4. CPU-only by default
    (cv2.dnn default backend); no GPU required.
    """
    if scale in (0, None):
        return img
    if scale not in (2, 3, 4):
        logger.debug("upscale: unsupported scale %s — passthrough", scale)
        return img
    if not _CV2_AVAILABLE:
        return _lanczos(img, scale)
    model_path = _MODELS_DIR / f"EDSR_x{scale}.pb"
    if not model_path.is_file():
        logger.debug("upscale: %s missing — LANCZOS fallback", model_path.name)
        return _lanczos(img, scale)
    sr = _SR_CACHE.get(scale)
    if sr is None:
        try:
            sr = cv2.dnn_superres.DnnSuperResImpl_create()
            sr.readModel(str(model_path))
            sr.setModel("edsr", scale)
            _SR_CACHE[scale] = sr
        except Exception:
            logger.exception("upscale: EDSR load failed — LANCZOS fallback")
            return _lanczos(img, scale)
    try:
        arr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        out = sr.upsample(arr)
        return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    except Exception:
        logger.exception("upscale: EDSR inference failed — LANCZOS fallback")
        return _lanczos(img, scale)


def _lanczos(img: Image.Image, scale: int) -> Image.Image:
    w, h = img.size
    return img.resize((w * scale, h * scale), Image.LANCZOS)


# ─── sharpen ────────────────────────────────────────────────────────────────

def sharpen(img: Image.Image, amount: float = 1.5) -> Image.Image:
    """Unsharp-mask via cv2 Gaussian blur subtraction.

    When cv2 is missing, falls back to PIL ImageFilter.SHARPEN (less tunable).
    """
    if _CV2_AVAILABLE:
        arr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        blurred = cv2.GaussianBlur(arr, (0, 0), sigmaX=3)
        sharp = cv2.addWeighted(arr, 1.0 + amount, blurred, -amount, 0)
        return Image.fromarray(cv2.cvtColor(sharp, cv2.COLOR_BGR2RGB))
    from PIL import ImageFilter
    return img.filter(ImageFilter.SHARPEN)


# ─── rotate ────────────────────────────────────────────────────────────────

def rotate(img: Image.Image, degrees: int) -> Image.Image:
    """Lossless 90° rotations only — anything else is rejected upstream."""
    if degrees in (0, None):
        return img
    if degrees not in (90, 180, 270):
        logger.debug("rotate: unsupported degrees %s — passthrough", degrees)
        return img
    return img.rotate(-degrees, expand=True)   # PIL rotates CCW; agent says CW.


# ─── apply pipeline ────────────────────────────────────────────────────────

def apply_pipeline(
    img: Image.Image,
    *,
    perspective: bool = False,
    upscale_factor: int = 0,
    do_sharpen: bool = False,
    rotate_deg: int = 0,
) -> tuple[Image.Image, list[str]]:
    """Run ops in canonical order. Returns (image, applied_ops_trace)."""
    applied: list[str] = []
    if perspective:
        img = perspective_correct(img)
        applied.append("perspective")
    if upscale_factor:
        img = upscale(img, upscale_factor)
        applied.append(f"upscale_{upscale_factor}")
    if do_sharpen:
        img = sharpen(img)
        applied.append("sharpen")
    if rotate_deg:
        img = rotate(img, rotate_deg)
        applied.append(f"rotate_{rotate_deg}")
    return img, applied
