"""CLIPScore (Hessel et al., EMNLP 2021) — M5 image-text alignment metric.

Per AMENDMENT_v0.3_ACTION_SPEC.md §7.4 (D7.4):
  - Input: rendered PNG + a textual summary of the visual claims
           (auto-derived from the DSL element list)
  - Output: cosine similarity in CLIP embedding space, range typically [0, 1]
  - Cost: $0 (open-source CLIP via open_clip_torch; GPU optional)

This is a deterministic metric — same (image, text) pair always yields the
same score across runs. We use the `ViT-L-14` checkpoint as a reasonable
default for visual-document alignment (good text capacity, moderate compute);
override via `model_name` / `pretrained` kwargs if needed.

Text-summary derivation strategy:
  1. Parse the DSL with `code.judge.dsl_parser` to extract structural
     elements (labels, edge texts, dataset names, etc.).
  2. Prepend the user query so the CLIP text encoder is anchored to the
     answer intent, not just the raw label tokens.
  3. Truncate to CLIP's 77-token context (`open_clip.tokenize` does this
     automatically with `context_length=77`).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Lazy CLIP model state — loaded once per process on first call.
_CLIP_MODEL = None
_CLIP_PREPROCESS = None
_CLIP_TOKENIZER = None
_CLIP_DEVICE = None
_CLIP_NAME: Tuple[str, str] = ("", "")


@dataclass
class CLIPScoreResult:
    """Outcome of a single CLIPScore evaluation."""
    score: float           # cosine similarity in [-1, 1], typically ~[0, 1]
    text_used: str         # the truncated text we encoded
    image_path: str
    success: bool
    error: str = ""


def _load_clip(model_name: str, pretrained: str):
    """Cache-loaded CLIP model + preprocessor + tokenizer."""
    global _CLIP_MODEL, _CLIP_PREPROCESS, _CLIP_TOKENIZER, _CLIP_DEVICE, _CLIP_NAME
    if (_CLIP_MODEL is not None
            and _CLIP_NAME == (model_name, pretrained)):
        return _CLIP_MODEL, _CLIP_PREPROCESS, _CLIP_TOKENIZER, _CLIP_DEVICE

    import torch
    import open_clip

    # CUDA path requires matching cuDNN; if env's cuDNN is broken, force CPU
    # via DOCVIZ_CLIP_DEVICE=cpu.
    force_cpu = os.environ.get("DOCVIZ_CLIP_DEVICE", "").lower() == "cpu"
    device = "cpu" if force_cpu else ("cuda" if torch.cuda.is_available() else "cpu")
    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name, pretrained=pretrained, device=device,
    )
    model.eval()
    tokenizer = open_clip.get_tokenizer(model_name)

    _CLIP_MODEL = model
    _CLIP_PREPROCESS = preprocess
    _CLIP_TOKENIZER = tokenizer
    _CLIP_DEVICE = device
    _CLIP_NAME = (model_name, pretrained)
    return model, preprocess, tokenizer, device


def _derive_text_summary(record: Dict[str, Any]) -> str:
    """Build a CLIP-encodable text summary from a viz record.

    Combines: user query + viz_type + labels/edges from DSL parse.
    """
    parts: List[str] = []
    q = (record.get("query") or "").strip()
    if q:
        parts.append(q)

    vt = record.get("viz_type", "")
    if vt:
        parts.append(f"visualization type: {vt}")

    # Parse DSL structure
    try:
        from code.judge.dsl_parser import parse_viz
        parsed = parse_viz(vt, record.get("viz_dsl") or "")
    except Exception:
        parsed = {}

    kind = parsed.get("kind", "")
    if kind == "chartjs":
        labels = parsed.get("labels") or []
        if labels:
            parts.append("categories: " + ", ".join(str(l) for l in labels[:8]))
        ds_names = [d.get("label", "") for d in (parsed.get("datasets") or [])]
        ds_names = [n for n in ds_names if n]
        if ds_names:
            parts.append("series: " + ", ".join(str(n) for n in ds_names[:4]))
    elif kind == "mermaid":
        # parse_mermaid extracts node/edge counts but not labels in the
        # current implementation; fall back to a coarse token extraction
        # of the raw DSL (drop syntax keywords).
        dsl = (record.get("viz_dsl") or "")[:1500]
        if dsl:
            parts.append("diagram content: " + dsl)

    # Use sub_queries (now real search terms thanks to Fix #1+2) as
    # secondary text anchor — CLIP benefits from longer keyword-rich text.
    sub = record.get("sub_queries") or []
    if sub:
        parts.append("retrieval: " + " | ".join(str(s) for s in sub[:3]))

    return " ".join(parts)


def compute_clipscore(
    image_path: str | Path,
    record: Dict[str, Any],
    *,
    model_name: str = "ViT-L-14",
    pretrained: str = "openai",
) -> CLIPScoreResult:
    """Compute CLIPScore for a single (rendered image, viz record) pair."""
    image_path = str(image_path)
    if not Path(image_path).exists():
        return CLIPScoreResult(0.0, "", image_path, False,
                               error=f"image not found: {image_path}")

    text = _derive_text_summary(record)
    if not text.strip():
        return CLIPScoreResult(0.0, "", image_path, False,
                               error="no text summary derivable from record")

    try:
        import torch
        from PIL import Image as PILImage
    except ImportError as e:
        return CLIPScoreResult(0.0, text, image_path, False,
                               error=f"import failed: {e}")

    try:
        model, preprocess, tokenizer, device = _load_clip(model_name, pretrained)
    except Exception as e:
        return CLIPScoreResult(0.0, text, image_path, False,
                               error=f"CLIP load failed: {e}")

    try:
        img = PILImage.open(image_path).convert("RGB")
        img_t = preprocess(img).unsqueeze(0).to(device)
        # open_clip.tokenize truncates to 77 tokens by default
        text_t = tokenizer([text]).to(device)
        with torch.no_grad():
            img_feat = model.encode_image(img_t)
            txt_feat = model.encode_text(text_t)
            img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
            txt_feat = txt_feat / txt_feat.norm(dim=-1, keepdim=True)
            sim = (img_feat @ txt_feat.T).item()
    except Exception as e:
        return CLIPScoreResult(0.0, text, image_path, False,
                               error=f"CLIP eval failed: {e}")

    # Hessel et al. (2021) "CLIPScore" applies max(cos_sim, 0) * 2.5 to
    # rescale the typical alignment range (~[0.2, 0.35]) toward [0, 1]
    # so the metric is on a comparable scale to other 0-1 quality scores.
    # We return BOTH so callers can choose; the .score field uses the
    # rescaled CLIPScore by convention.
    raw_cos = float(sim)
    rescaled = max(raw_cos, 0.0) * 2.5
    rescaled = min(rescaled, 1.0)  # cap at 1.0 in the (rare) case rescaled > 1
    res = CLIPScoreResult(rescaled, text, image_path, True)
    # Stash the raw cosine on the dataclass via an attribute add (cheap):
    res.raw_cosine = raw_cos
    return res


def compute_clipscore_batch(
    records: List[Dict[str, Any]],
    images_dir: str | Path,
    *,
    model_name: str = "ViT-L-14",
    pretrained: str = "openai",
) -> List[Tuple[Dict[str, Any], CLIPScoreResult]]:
    """Compute CLIPScore for a batch of records, looking up the rendered
    image at `{images_dir}/{strategy}/{query_id}.png`.
    """
    images_dir = Path(images_dir)
    out: List[Tuple[Dict[str, Any], CLIPScoreResult]] = []
    for r in records:
        qid = r.get("query_id", "unknown")
        strat = r.get("strategy", "unknown")
        path = images_dir / strat / f"{qid}.png"
        if not path.exists():
            out.append((r, CLIPScoreResult(0.0, "", str(path), False,
                                           error="image missing")))
            continue
        res = compute_clipscore(path, r, model_name=model_name, pretrained=pretrained)
        out.append((r, res))
    return out
