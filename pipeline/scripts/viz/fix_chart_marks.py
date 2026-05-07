"""Retrofit normalizer for Vega-Lite chart `mark` types that our
comparison models produced but vl-convert rejects.

Finding: models (qwen9b, gpt_oss_20b, gemma3_4b) wrote semantically-
correct Vega-Lite except they used mark vocabulary from their training
set (pie, doughnut, scatter, radar, …) rather than the actual Vega-Lite
mark names (arc, point, …). The Reference (qwen397b) knew the right
names; smaller models didn't.

This script normalizes already-saved `*_source.txt` JSON specs and
retries rendering. No new LLM calls. Failed-to-normalize specs stay
failed (honest).

Mapping:
    pie       → arc (+ theta already present in most cases)
    doughnut  → arc + view.innerRadius 50 (converted in spec via config)
    scatter   → point
    scattergl → point
    circle    → point  (vl-convert v6 deprecation edge case)
    radar     → skip (no clean native mapping; counted as real failure)
    timeline  → skip
    radialBar → skip

Usage:
    python -m scripts.viz.fix_chart_marks [--model MID] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.utils.rendering import render_vegalite
from scripts.config import DATA_DIR as _DATA_DIR, RESULTS_DIR

DATA_DIR = Path(_DATA_DIR)
MODEL_OUTPUT_DIR = DATA_DIR / "model_outputs"
GOLD_DIR = DATA_DIR / "gold"

MARK_NORMALIZE = {
    "pie": "arc",
    "scatter": "point",
    "scattergl": "point",
    "circle": "point",  # vl-convert v6 complains about circle mark sometimes
}

SKIP_MARKS = {"radar", "timeline", "radialBar", "radialbar"}


def _get_mark_type(spec: dict) -> str | None:
    m = spec.get("mark")
    if isinstance(m, str):
        return m
    if isinstance(m, dict):
        return m.get("type")
    return None


def _set_mark_type(spec: dict, new_type: str, extras: dict | None = None) -> None:
    old = spec.get("mark")
    if isinstance(old, dict):
        spec["mark"] = {**old, "type": new_type, **(extras or {})}
    else:
        if extras:
            spec["mark"] = {"type": new_type, **extras}
        else:
            spec["mark"] = new_type


def _coerce_font_sizes_to_str(obj) -> bool:
    """vl-convert v6 deserializes title/label.fontSize via a text-info
    struct that expects a string, not an integer. Walk the spec and
    convert any int fontSize/labelFontSize/titleFontSize to str. Returns
    True if anything was changed.
    """
    changed = False
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(k, str) and k.lower().endswith("fontsize") \
                    and isinstance(v, (int, float)):
                obj[k] = str(int(v))
                changed = True
            else:
                if _coerce_font_sizes_to_str(v):
                    changed = True
    elif isinstance(obj, list):
        for item in obj:
            if _coerce_font_sizes_to_str(item):
                changed = True
    return changed


def normalize(spec: dict) -> Tuple[dict, str]:
    """Return (normalized_spec, action). action ∈ {unchanged, normalized, skip}."""
    mt = _get_mark_type(spec)
    fontsize_changed = _coerce_font_sizes_to_str(spec)
    if mt is None:
        return spec, ("normalized" if fontsize_changed else "unchanged")
    if mt in SKIP_MARKS:
        return spec, "skip"
    if mt == "doughnut":
        _set_mark_type(spec, "arc", {"innerRadius": 50})
        return spec, "normalized"
    if mt in MARK_NORMALIZE:
        _set_mark_type(spec, MARK_NORMALIZE[mt])
        return spec, "normalized"
    return spec, ("normalized" if fontsize_changed else "unchanged")


def find_unrendered_charts(base: Path) -> list[Path]:
    """Return list of *_source.txt paths whose sibling _rendered.png is missing."""
    out = []
    for sp in sorted(base.glob("*_source.txt")):
        doc_id = sp.name.replace("_source.txt", "")
        png = base / f"{doc_id}_rendered.png"
        if not png.exists():
            out.append(sp)
    return out


def process_one(src_path: Path, dry: bool) -> dict:
    doc_id = src_path.name.replace("_source.txt", "")
    out_dir = src_path.parent
    try:
        raw = src_path.read_text(encoding="utf-8")
        spec = json.loads(raw)
    except Exception as e:
        return {"doc_id": doc_id, "status": "bad_json",
                "error": f"{type(e).__name__}: {e}"}

    orig_mark = _get_mark_type(spec)
    normalized, action = normalize(spec)
    if action == "skip":
        return {"doc_id": doc_id, "status": "skip_unsupported_mark",
                "mark": orig_mark}
    if action == "unchanged":
        # Try rendering again in case vl-convert was transiently busy.
        if dry:
            return {"doc_id": doc_id, "status": "would_retry", "mark": orig_mark}
        r = render_vegalite(normalized, str(out_dir), doc_id=doc_id, fmt="png")
        return {"doc_id": doc_id,
                "status": "retry_ok" if r["success"] else "retry_fail",
                "mark": orig_mark,
                "error": str(r.get("error") or "")[:300]}

    # action == normalized
    if dry:
        return {"doc_id": doc_id, "status": "would_normalize",
                "mark_before": orig_mark,
                "mark_after": _get_mark_type(normalized)}
    # Overwrite source.txt with normalized spec
    src_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    r = render_vegalite(normalized, str(out_dir), doc_id=doc_id, fmt="png")
    return {"doc_id": doc_id,
            "status": "normalized_ok" if r["success"] else "normalized_fail",
            "mark_before": orig_mark,
            "mark_after": _get_mark_type(normalized),
            "error": str(r.get("error") or "")[:300]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, default=None,
                    help="restrict to one model_id under data/model_outputs/")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.model:
        roots = [MODEL_OUTPUT_DIR / args.model / "chart"]
    else:
        roots = sorted((p / "chart") for p in MODEL_OUTPUT_DIR.iterdir()
                       if p.is_dir())
        # Also include gold for completeness
        roots.append(GOLD_DIR / "chart")

    grand = {"total": 0, "normalized_ok": 0, "normalized_fail": 0,
             "retry_ok": 0, "retry_fail": 0, "skip_unsupported_mark": 0,
             "bad_json": 0, "would_normalize": 0, "would_retry": 0}
    per_model = {}

    for root in roots:
        if not root.exists():
            continue
        model_key = root.parent.name
        unrendered = find_unrendered_charts(root)
        if not unrendered:
            continue
        print(f"[{model_key}] unrendered charts: {len(unrendered)}")
        m_stats = {k: 0 for k in grand}
        for sp in unrendered:
            rec = process_one(sp, args.dry_run)
            grand["total"] += 1
            m_stats["total"] += 1
            st = rec["status"]
            grand[st] = grand.get(st, 0) + 1
            m_stats[st] = m_stats.get(st, 0) + 1
            if st in ("normalized_ok", "normalized_fail"):
                pass
        per_model[model_key] = m_stats
        print(f"  {m_stats}")

    print("\n== grand total ==")
    for k, v in sorted(grand.items()):
        if v:
            print(f"  {k}: {v}")

    # write summary
    out = Path(RESULTS_DIR) / "fix-reports" / "d14_chart_mark_normalization.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    content = ["# D14 chart mark normalization (2026-04-09)\n",
               "## Problem",
               "Comparison models wrote `mark: pie/doughnut/scatter/scattergl`"
               " etc., which are not valid Vega-Lite mark types. vl-convert"
               " rejects them even though the rest of the spec is correct."
               " Reference (qwen397b) correctly used `mark: arc/point`.",
               "",
               "## Normalizer",
               "- pie → arc",
               "- doughnut → arc + innerRadius 50",
               "- scatter/scattergl → point",
               "- circle → point",
               "- radar/timeline/radialBar → SKIP (no clean mapping, honest "
               "failure retained)",
               "",
               "## Results per model",
               ""]
    for m, s in per_model.items():
        content.append(f"### {m}")
        for k, v in sorted(s.items()):
            if v:
                content.append(f"- {k}: {v}")
        content.append("")
    content.append("## Grand total")
    for k, v in sorted(grand.items()):
        if v:
            content.append(f"- {k}: {v}")
    out.write_text("\n".join(content) + "\n", encoding="utf-8")
    print(f"\n[wrote] {out}")


if __name__ == "__main__":
    main()
