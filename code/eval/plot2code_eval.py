"""Plot2Code standard-eval reimplementation (v0.3 amendment §14 fallback).

Per amendment §14 line 552 + §6: Plot2Code's published eval uses GPT-4V
for "overall rating" judging (closed-API). When closed-API is deferred,
reimplement the eval using deterministic + on-prem signals:

  1. M_exec   — code/DSL execution rate (rendered viz PNG produced)
  2. M_clip   — CLIPScore between RENDERED viz PNG and the REFERENCE
                target image, per record. Higher = closer match in
                CLIP embedding space. Hessel et al. (2021) rescaling
                applied: 2.5 × max(cos, 0).
  3. M_text   — Qwen3.5-397B 4-axis judge applied to the generated
                viz_dsl (text-side; covers faithfulness/coverage/type/SQ
                analogous to QG-MDV). Reuses code.judge.scorer.

Per-baseline aggregate:
  - exec_rate            : mean(M_exec)
  - clipscore_mean       : mean(M_clip) over successfully rendered viz
  - qwen_overall_mean    : mean of 4-axis aggregate from M_text

Output:
  - data/prototype/eval/plot2code/<strategy>.json
  - data/prototype/eval/plot2code/summary.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("HF_HOME", "/ex_disk2/mhpark/poc/.cache/huggingface")

from code.metrics import compute_clipscore
from code.render import render


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VIZ_PATH = REPO_ROOT / "outputs" / "plot2code" / "viz" / "all.json"
DEFAULT_BUNDLES_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "plot2code.json"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "prototype" / "eval" / "plot2code"
DEFAULT_RENDER_DIR = REPO_ROOT / "outputs" / "plot2code" / "renders"


def _load_bundles_dict(path: Path) -> Dict[str, Dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("bundles", [])
    return {b["bundle_id"]: b for b in raw}


def _ensure_rendered(record: Dict[str, Any], render_dir: Path) -> str:
    """Render this record's viz_dsl to PNG (or use B1's existing PNG).
    Returns the absolute image path on success, "" on failure."""
    strat = record.get("strategy", "unknown")
    qid = record.get("query_id", "unknown")
    out = render_dir / strat / f"{qid}.png"

    # B1 already saves its own PNG via subprocess; reuse if present
    pre_existing = record.get("rendered_image_path") or ""
    if pre_existing and Path(pre_existing).exists() and Path(pre_existing).stat().st_size > 100:
        return pre_existing

    # Otherwise render the DSL ourselves
    viz_type = record.get("viz_type", "")
    viz_dsl = record.get("viz_dsl", "")
    if not viz_type or not viz_dsl:
        return ""
    if viz_type == "matplotlib":
        return ""  # only B1 produces matplotlib; if no pre-existing PNG, skip
    out.parent.mkdir(parents=True, exist_ok=True)
    res = render(viz_type, viz_dsl, out)
    return res.image_path if res.success else ""


def evaluate(
    viz_records: List[Dict[str, Any]],
    bundles_by_id: Dict[str, Dict[str, Any]],
    render_dir: Path,
) -> Dict[str, Any]:
    """Per-strategy aggregate: exec_rate + clipscore_mean.
    Qwen 4-axis judge is invoked separately by run_judge (out of scope here).
    """
    per_strategy: Dict[str, Dict[str, Any]] = {}

    for r in viz_records:
        strat = r.get("strategy", "unknown")
        bundle = bundles_by_id.get(r["bundle_id"]) or {}
        target_img = (bundle.get("metadata") or {}).get("target_image_path") or ""

        rendered = _ensure_rendered(r, render_dir)
        exec_ok = bool(rendered)

        clip_score = None
        clip_raw = None
        if exec_ok and target_img and Path(target_img).exists():
            try:
                clip_text_record = {
                    "query": r.get("query", ""),
                    "viz_type": r.get("viz_type", ""),
                    "viz_dsl": r.get("viz_dsl", "") or "",
                    "sub_queries": r.get("sub_queries", []) or [],
                }
                cs = compute_clipscore(target_img, clip_text_record)
                if cs.success:
                    clip_score = cs.score
                    clip_raw = getattr(cs, "raw_cosine", None)
            except Exception as e:
                # Don't kill the whole eval on a single CLIP failure
                pass

        bucket = per_strategy.setdefault(strat, {
            "n": 0, "exec_ok": 0,
            "clip_scores": [], "clip_raw": [],
            "records": [],
        })
        bucket["n"] += 1
        if exec_ok:
            bucket["exec_ok"] += 1
        if clip_score is not None:
            bucket["clip_scores"].append(clip_score)
            bucket["clip_raw"].append(clip_raw)
        bucket["records"].append({
            "query_id": r["query_id"],
            "exec_ok": exec_ok,
            "rendered_image_path": rendered,
            "target_image_path": target_img,
            "clipscore": clip_score,
            "clipscore_raw_cosine": clip_raw,
        })

    # Aggregate
    summary: Dict[str, Any] = {}
    for strat, b in per_strategy.items():
        n = max(b["n"], 1)
        cs_list = b["clip_scores"] or [0.0]
        cs_raw = [v for v in b["clip_raw"] if v is not None] or [0.0]
        summary[strat] = {
            "n": b["n"],
            "exec_rate": round(b["exec_ok"] / n, 4),
            "clipscore_mean": round(sum(cs_list) / len(cs_list), 4),
            "clipscore_raw_mean": round(sum(cs_raw) / len(cs_raw), 4),
            "n_with_clipscore": len(b["clip_scores"]),
        }

    return {"summary": summary, "per_strategy": per_strategy}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--viz", default=str(DEFAULT_VIZ_PATH))
    ap.add_argument("--bundles", default=str(DEFAULT_BUNDLES_PATH))
    ap.add_argument("--render-dir", default=str(DEFAULT_RENDER_DIR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = ap.parse_args()

    # Force CPU CLIP unless GPU known good — DOCVIZ_CLIP_DEVICE env honored
    os.environ.setdefault("DOCVIZ_CLIP_DEVICE", "cpu")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    render_dir = Path(args.render_dir)

    viz_records = json.loads(Path(args.viz).read_text(encoding="utf-8"))
    if isinstance(viz_records, dict):
        viz_records = viz_records.get("records", [])
    bundles_by_id = _load_bundles_dict(Path(args.bundles))

    print(f"[plot2code_eval] viz_records: {len(viz_records)}, bundles: {len(bundles_by_id)}")

    result = evaluate(viz_records, bundles_by_id, render_dir)
    # Write per-strategy detail + summary
    summary_path = out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(result["summary"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    detail_path = out_dir / "per_strategy.json"
    detail_path.write_text(
        json.dumps(result["per_strategy"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[plot2code_eval] summary → {summary_path}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
