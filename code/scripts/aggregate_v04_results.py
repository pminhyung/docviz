"""v0.4 results aggregator — 3-seed mean±std, per-axis/per-source/per-query-type
breakdown, Δ vs baselines, ablation magnitude. Writes a markdown summary.

Per track feedback (2026-05-23):
  - paired bootstrap CI deprecated for n=265 era
  - win-rate deprecated (margin info loss)
  - Use: point estimate (mean) + per-axis/source/query-type breakdown
         + 3-seed mean±std + Δ vs other baselines

Inputs:
  outputs/v0.4/judge/{b6_seed42,b6_seed43,b6_seed44,baselines,ablations,text2vis_b6}.json
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Dict, List, Tuple


def _load_judge(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def _by_strategy(records: List[Dict]) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for r in records:
        out.setdefault(r["strategy"], []).append(r)
    return out


def _strategy_mean(records: List[Dict]) -> float:
    vals = [r.get("overall", 0.0) for r in records if "overall" in r]
    return sum(vals) / len(vals) if vals else 0.0


def _strategy_axes(records: List[Dict]) -> Dict[str, float]:
    axis_sums: Dict[str, List[float]] = {}
    for r in records:
        for ax, v in (r.get("axis_scores") or {}).items():
            axis_sums.setdefault(ax, []).append(v)
    return {ax: sum(vs) / len(vs) for ax, vs in axis_sums.items() if vs}


def _bucket(records: List[Dict], key: str) -> Dict[str, float]:
    """Mean overall score grouped by record[key]."""
    by: Dict[str, List[float]] = {}
    for r in records:
        k = r.get(key, "?")
        if "overall" in r:
            by.setdefault(k, []).append(r["overall"])
    return {k: sum(vs) / len(vs) for k, vs in by.items() if vs}


def _three_seed_stats(seeds_records: List[List[Dict]]) -> Tuple[float, float]:
    """Return (mean, std) of B6 overall across 3 seeds."""
    means = [_strategy_mean(rs) for rs in seeds_records if rs]
    if len(means) < 2:
        return (means[0] if means else 0.0, 0.0)
    return statistics.mean(means), statistics.stdev(means)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge-dir", default="outputs/v0.4/judge")
    ap.add_argument("--out", default="outputs/v0.4/reports/v04_summary.md")
    args = ap.parse_args()

    jdir = Path(args.judge_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Load all judge outputs
    b6_seeds = {s: _load_judge(jdir / f"b6_seed{s}.json") for s in (42, 43, 44)}
    baselines = _load_judge(jdir / "baselines.json")
    ablations = _load_judge(jdir / "ablations.json")
    text2vis = _load_judge(jdir / "text2vis_b6.json")

    lines: List[str] = []
    lines.append("# v0.4 Results Summary")
    lines.append("")
    lines.append(f"Generated from `{jdir}/`.")
    lines.append("")

    # ── §1. B6 3-seed (NEW dataset main result) ───────────────────────────
    lines.append("## §1. B6 V4_cons — 3-seed (Qwen3.5-397B, multi-host)")
    lines.append("")
    seed_means = []
    for s in (42, 43, 44):
        rs = b6_seeds[s]
        m = _strategy_mean(rs)
        n = len(rs)
        seed_means.append((s, m, n))
        lines.append(f"  - seed{s}: overall = {m:.4f} (n={n})")
    if len([sm for sm in seed_means if sm[1] > 0]) >= 2:
        mean3, std3 = _three_seed_stats([b6_seeds[s] for s in (42, 43, 44)])
        lines.append(f"  - **3-seed mean ± std = {mean3:.4f} ± {std3:.4f}**")
    lines.append("")

    # ── §2. B6 per-axis (using seed42 representative) ─────────────────────
    rs42 = b6_seeds.get(42, [])
    if rs42:
        lines.append("## §2. B6 per-axis (seed42)")
        lines.append("")
        axes = _strategy_axes(rs42)
        for ax, v in sorted(axes.items()):
            lines.append(f"  - {ax}: {v:.4f}")
        lines.append("")

    # ── §3. B6 per-source breakdown (seed42) ──────────────────────────────
    if rs42:
        lines.append("## §3. B6 per-source overall (seed42)")
        lines.append("")
        per_src = _bucket(rs42, "source")
        for src, v in sorted(per_src.items()):
            lines.append(f"  - {src}: {v:.4f}")
        lines.append("")

    # ── §4. B6 per-dep-type breakdown (seed42) ────────────────────────────
    if rs42:
        lines.append("## §4. B6 per-dep-type overall (seed42)")
        lines.append("")
        per_dt = _bucket(rs42, "dep_type")
        if not per_dt:
            per_dt = _bucket(rs42, "query_type")  # back-compat
        for dt, v in sorted(per_dt.items()):
            lines.append(f"  - {dt}: {v:.4f}")
        lines.append("")

    # ── §5. Baselines vs B6 ───────────────────────────────────────────────
    if baselines:
        lines.append("## §5. Baselines (seed42) — overall + Δ vs B6")
        lines.append("")
        b6_overall = _strategy_mean(rs42) if rs42 else 0.0
        bl_by_strat = _by_strategy(baselines)
        for strat, rs in sorted(bl_by_strat.items()):
            m = _strategy_mean(rs)
            d = b6_overall - m
            lines.append(f"  - {strat}: {m:.4f} (Δ vs B6 = {d:+.4f})")
        lines.append("")

    # ── §6. Ablation (CIS / TMG / SAO pillar magnitude) ───────────────────
    if ablations:
        lines.append("## §6. Ablation (seed42) — pillar magnitude")
        lines.append("")
        ab_by_strat = _by_strategy(ablations)
        full_m = _strategy_mean(ab_by_strat.get("B6_Full", []))
        lines.append(f"  - B6_Full: {full_m:.4f} (reference)")
        for strat in ("B6_NoTMG", "B6_NoSAO", "B6_NoCIS"):
            rs = ab_by_strat.get(strat, [])
            if rs:
                m = _strategy_mean(rs)
                d = full_m - m
                lines.append(f"  - {strat}: {m:.4f} (pillar magnitude Δ = {d:+.4f})")
        lines.append("")

    # ── §7. Held-out Text2Vis ─────────────────────────────────────────────
    if text2vis:
        lines.append("## §7. Held-out — Text2Vis (B6 native, n=100)")
        lines.append("")
        m = _strategy_mean(text2vis)
        lines.append(f"  - overall: {m:.4f}")
        axes = _strategy_axes(text2vis)
        for ax, v in sorted(axes.items()):
            lines.append(f"    - {ax}: {v:.4f}")
        lines.append("")

    # ── §8. Notes ─────────────────────────────────────────────────────────
    lines.append("## §8. Notes")
    lines.append("")
    lines.append("- Reporting per track feedback 2026-05-23: point estimate (mean)")
    lines.append("  + per-axis/source/dep-type breakdown + Δ vs baselines.")
    lines.append("  Paired bootstrap CI and win-rate are deprecated.")
    lines.append("- 3-seed std is the §13 non-negotiable statistical strength metric.")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[aggregate] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
