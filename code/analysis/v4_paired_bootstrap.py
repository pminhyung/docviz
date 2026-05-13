#!/usr/bin/env python3
"""V4 measurement analyzer — paired bootstrap CI + Cohen's d.

Reads outputs/prototype/judge_scores/all.json, pairs records across
strategies by query_id, computes per-axis paired Δ statistics with
95% BCa bootstrap CI (10K resamples) and Cohen's d (paired).

Key paired comparisons (mentor risk #1 + #4):
  Δ(V0 − S4)              = §11.4 ablation row "−TMG vs Full(placeholder)"
  Δ(V1 − S4)              = "rule routing alone, no one-shot"
  Δ(V1 − V0)              = "removing the placeholder one-shot's effect"
  Δ(V4_pool − V1)         = MENTOR RISK #1: tool-call complexity justification
  Δ(V4_pool − V0)         = "V4 vs current V0 placeholder baseline"
  Δ(V4_consolidated − V4_pool) = V4 design choice (consolidated vs pool sampling)
  Δ(V4_pool − S4)         = "agent inference + tool + curated pool vs no-TMG"

Outputs (markdown):
  --out path/to/report.md (default: docs/analysis/v4_paired_results.md)

Usage:
  python -m code.analysis.v4_paired_bootstrap [--out PATH] [--seed 42]

Inline implementation — no scipy dependency (matches existing
analyze_correlation.py precedent in code/judge/).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCORES = REPO_ROOT / "outputs" / "prototype" / "judge_scores" / "all.json"
DEFAULT_OUT = REPO_ROOT / "docs" / "analysis" / "v4_paired_results.md"


# ── Statistical primitives ────────────────────────────────────────────────


@dataclass
class PairedStat:
    n: int
    mean: float
    ci_lo: float
    ci_hi: float
    cohen_d: float

    def fmt(self, sign_decimal: int = 4) -> str:
        return (f"Δ={self.mean:+.{sign_decimal}f} "
                f"[{self.ci_lo:+.{sign_decimal}f}, {self.ci_hi:+.{sign_decimal}f}] "
                f"d={self.cohen_d:+.2f} n={self.n}")


def _bca_ci(deltas: Sequence[float], iters: int, rng: random.Random,
            alpha: float = 0.05) -> Tuple[float, float]:
    """Bias-corrected and accelerated bootstrap CI (Efron, 1987).

    Pure-Python implementation. For small n (≤ 5) falls back to
    percentile bootstrap (acceleration estimate degenerates).
    """
    n = len(deltas)
    if n == 0:
        return (float("nan"), float("nan"))
    if n == 1:
        return (deltas[0], deltas[0])

    obs_mean = sum(deltas) / n

    # Bootstrap distribution of mean
    boot_means: List[float] = []
    for _ in range(iters):
        sample = [deltas[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()

    # Bias correction z0 = Phi^-1(P(boot < obs))
    p_lt_obs = sum(1 for x in boot_means if x < obs_mean) / iters
    p_lt_obs = max(min(p_lt_obs, 1 - 1e-9), 1e-9)
    z0 = _norm_inv(p_lt_obs)

    # Acceleration via jackknife
    if n >= 5:
        jack_means: List[float] = []
        full_sum = sum(deltas)
        for i in range(n):
            jm = (full_sum - deltas[i]) / (n - 1)
            jack_means.append(jm)
        jack_mean_avg = sum(jack_means) / n
        num = sum((jack_mean_avg - jm) ** 3 for jm in jack_means)
        den = 6 * (sum((jack_mean_avg - jm) ** 2 for jm in jack_means)) ** 1.5
        a = num / den if den > 1e-12 else 0.0
    else:
        a = 0.0

    z_alpha_lo = _norm_inv(alpha / 2)
    z_alpha_hi = _norm_inv(1 - alpha / 2)

    def _adj(z_alpha: float) -> float:
        x = z0 + (z0 + z_alpha) / max(1 - a * (z0 + z_alpha), 1e-9)
        return _norm_cdf(x)

    p_lo = _adj(z_alpha_lo)
    p_hi = _adj(z_alpha_hi)

    def _quantile(p: float) -> float:
        idx = int(round(p * (iters - 1)))
        idx = max(0, min(iters - 1, idx))
        return boot_means[idx]

    return (_quantile(p_lo), _quantile(p_hi))


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _norm_inv(p: float) -> float:
    """Inverse of standard-normal CDF via Beasley-Springer-Moro."""
    if p <= 0:
        return -8.0
    if p >= 1:
        return 8.0
    a = [-39.696830, 220.946098, -275.928510, 138.357751, -30.664798, 2.506628]
    b = [-54.476098, 161.585836, -155.698979, 66.801311, -13.280681]
    c = [-0.007784894, -0.32239645, -2.400758, -2.549732, 4.374664, 2.938163]
    d_ = [0.007784695, 0.32246712, 2.445134, 3.754408]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return ((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5] / \
               ((((d_[0]*q + d_[1])*q + d_[2])*q + d_[3])*q + 1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5])*q / \
               (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
           ((((d_[0]*q + d_[1])*q + d_[2])*q + d_[3])*q + 1)


def _cohen_d_paired(deltas: Sequence[float]) -> float:
    n = len(deltas)
    if n < 2:
        return 0.0
    m = sum(deltas) / n
    var = sum((d - m) ** 2 for d in deltas) / (n - 1)
    sd = math.sqrt(var) if var > 0 else 1e-9
    return m / sd


def paired_stat(deltas: Sequence[float], iters: int = 10000,
                seed: int = 42) -> PairedStat:
    rng = random.Random(seed)
    n = len(deltas)
    if n == 0:
        return PairedStat(0, float("nan"), float("nan"), float("nan"), 0.0)
    mean = sum(deltas) / n
    lo, hi = _bca_ci(deltas, iters=iters, rng=rng)
    d = _cohen_d_paired(deltas)
    return PairedStat(n=n, mean=mean, ci_lo=lo, ci_hi=hi, cohen_d=d)


# ── Data loading + pairing ────────────────────────────────────────────────


def _load_scores(path: Path) -> List[Dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _index_by_strategy(records: List[Dict]) -> Dict[str, Dict[str, Dict]]:
    """Returns {strategy: {query_id: record}}."""
    out: Dict[str, Dict[str, Dict]] = defaultdict(dict)
    for r in records:
        out[r["strategy"]][r["query_id"]] = r
    return dict(out)


def _paired_axis_deltas(
    a_index: Dict[str, Dict],
    b_index: Dict[str, Dict],
    axis: str,
    filter_qids: Optional[set] = None,
) -> List[float]:
    """For each query_id present in both, compute (b - a)[axis_score]."""
    deltas: List[float] = []
    for qid, ar in a_index.items():
        if qid not in b_index:
            continue
        if filter_qids is not None and qid not in filter_qids:
            continue
        br = b_index[qid]
        ax_a = (ar.get("axis_scores") or {}).get(axis)
        ax_b = (br.get("axis_scores") or {}).get(axis)
        if ax_a is None or ax_b is None:
            continue
        deltas.append(ax_b - ax_a)
    return deltas


def _paired_overall_deltas(
    a_index: Dict[str, Dict],
    b_index: Dict[str, Dict],
    filter_qids: Optional[set] = None,
) -> List[float]:
    deltas: List[float] = []
    for qid, ar in a_index.items():
        if qid not in b_index:
            continue
        if filter_qids is not None and qid not in filter_qids:
            continue
        br = b_index[qid]
        ax_a = ar.get("overall")
        ax_b = br.get("overall")
        if ax_a is None or ax_b is None:
            continue
        deltas.append(ax_b - ax_a)
    return deltas


# ── Drop-subset detection ─────────────────────────────────────────────────


def _detect_drop_subset(
    s4_index: Dict[str, Dict],
    v0_index: Dict[str, Dict],
    axis: str = "faithfulness",
    threshold: float = 0.0,
) -> set:
    """Records where Δ(V0 − S4)[axis] < threshold.

    The 19-record drop subset from oneshot_failure_analysis.md is
    defined as faith-axis records where V0 (placeholder TMG) scored
    *worse* than S4 (no TMG). Computing it dynamically from the
    judge_scores file makes the subset reproducible from data.
    """
    drop = set()
    for qid, sr in s4_index.items():
        if qid not in v0_index:
            continue
        a = (sr.get("axis_scores") or {}).get(axis)
        b = (v0_index[qid].get("axis_scores") or {}).get(axis)
        if a is None or b is None:
            continue
        if (b - a) < threshold:
            drop.add(qid)
    return drop


# ── Report rendering ──────────────────────────────────────────────────────


_AXES = ["faithfulness", "coverage", "type_appropriateness", "search_query_quality"]
_PAIRINGS = [
    # (label, baseline_strategy, comparison_strategy)
    # ── v0.3 paper baseline matrix (B6 vs B1-B5, B7) ─────────────────────
    ("B6 − B5 (Direct-LLM)",            "S1_Direct",      "S4_AgenticTMGv4_consolidated"),
    ("B6 − B7 (SelfRefine)",            "S7_SelfRefine",  "S4_AgenticTMGv4_consolidated"),
    ("B6 − B1 (MatPlotAgent)",          "B1_MatPlotAgent", "S4_AgenticTMGv4_consolidated"),
    ("B6 − B2 (NVAGENT)",               "B2_NVAGENT",     "S4_AgenticTMGv4_consolidated"),
    ("B6 − B3 (CoDA)",                  "B3_CoDA",        "S4_AgenticTMGv4_consolidated"),
    ("B6 − B4 (ViviDoc)",               "B4_ViviDoc",     "S4_AgenticTMGv4_consolidated"),
    # ── Layer D pillar ablation (Full vs each ablation) ─────────────────
    ("B6 Full − B6 NoTMG",              "B6_NoTMG",       "B6_Full"),
    ("B6 Full − B6 NoSAO",              "B6_NoSAO",       "B6_Full"),
    # ── Historical V4-internal comparisons (kept for reference) ─────────
    ("V0 − S4 (placeholder TMG vs no-TMG)", "S4_Agentic", "S4_AgenticTMG"),
    ("V1 − S4 (rule routing, no one-shot)", "S4_Agentic", "S4_AgenticTMGv1noshot"),
    ("V4_pool − V1 (MENTOR RISK #1)", "S4_AgenticTMGv1noshot", "S4_AgenticTMGv4_pool"),
    ("V4_consolidated − V4_pool",       "S4_AgenticTMGv4_pool",
                                        "S4_AgenticTMGv4_consolidated"),
]


def _render_report(
    scores: List[Dict],
    iters: int,
    seed: int,
) -> str:
    by_strategy = _index_by_strategy(scores)
    available = sorted(by_strategy.keys())

    out: List[str] = []
    out.append("# V4 measurement — paired bootstrap CI + Cohen's d")
    out.append("")
    out.append(f"**Source**: `outputs/prototype/judge_scores/all.json` "
               f"({len(scores)} records)")
    out.append(f"**Bootstrap**: BCa, {iters} resamples, seed={seed}, α=0.05")
    out.append(f"**Cohen's d**: paired (mean of Δ ÷ SD of Δ)")
    out.append(f"**Available strategies**: {', '.join(available)}")
    out.append("")

    # Drop subset (faith axis, V0 worse than S4)
    drop_subset: set = set()
    if "S4_Agentic" in by_strategy and "S4_AgenticTMG" in by_strategy:
        drop_subset = _detect_drop_subset(
            by_strategy["S4_Agentic"], by_strategy["S4_AgenticTMG"],
            axis="faithfulness", threshold=0.0,
        )
        out.append(f"**Faith-drop subset** (records where V0 < S4 on faith axis): "
                   f"{len(drop_subset)} records")
        out.append("")

    # Per-pairing tables
    for label, base_s, comp_s in _PAIRINGS:
        if base_s not in by_strategy or comp_s not in by_strategy:
            out.append(f"## {label}")
            out.append(f"  *skipped — strategies missing "
                       f"({base_s} or {comp_s} not in judge_scores)*")
            out.append("")
            continue

        a_idx = by_strategy[base_s]
        b_idx = by_strategy[comp_s]

        out.append(f"## {label}")
        out.append("")

        # Full-set per axis
        out.append("### Full-set (all paired records)")
        out.append("")
        out.append("| Axis | Δ | 95% CI | Cohen's d | n | CI excludes 0? |")
        out.append("|---|---|---|---|---|---|")
        for axis in _AXES:
            deltas = _paired_axis_deltas(a_idx, b_idx, axis)
            if not deltas:
                out.append(f"| {axis} | — | — | — | 0 | — |")
                continue
            stat = paired_stat(deltas, iters=iters, seed=seed)
            excludes = "**YES**" if (stat.ci_lo > 0 or stat.ci_hi < 0) else "no"
            out.append(f"| {axis} | {stat.mean:+.4f} | "
                       f"[{stat.ci_lo:+.4f}, {stat.ci_hi:+.4f}] | "
                       f"{stat.cohen_d:+.2f} | {stat.n} | {excludes} |")
        # Overall
        deltas = _paired_overall_deltas(a_idx, b_idx)
        if deltas:
            stat = paired_stat(deltas, iters=iters, seed=seed)
            excludes = "**YES**" if (stat.ci_lo > 0 or stat.ci_hi < 0) else "no"
            out.append(f"| **overall** | {stat.mean:+.4f} | "
                       f"[{stat.ci_lo:+.4f}, {stat.ci_hi:+.4f}] | "
                       f"{stat.cohen_d:+.2f} | {stat.n} | {excludes} |")
        out.append("")

        # Faith-drop subset (if applicable + non-empty)
        if drop_subset:
            out.append(f"### Faith-drop subset (n={len(drop_subset)})")
            out.append("")
            out.append("| Axis | Δ | 95% CI | Cohen's d | n | CI excludes 0? |")
            out.append("|---|---|---|---|---|---|")
            for axis in _AXES:
                deltas = _paired_axis_deltas(a_idx, b_idx, axis,
                                             filter_qids=drop_subset)
                if not deltas:
                    out.append(f"| {axis} | — | — | — | 0 | — |")
                    continue
                stat = paired_stat(deltas, iters=iters, seed=seed)
                excludes = "**YES**" if (stat.ci_lo > 0 or stat.ci_hi < 0) else "no"
                out.append(f"| {axis} | {stat.mean:+.4f} | "
                           f"[{stat.ci_lo:+.4f}, {stat.ci_hi:+.4f}] | "
                           f"{stat.cohen_d:+.2f} | {stat.n} | {excludes} |")
            deltas = _paired_overall_deltas(a_idx, b_idx, filter_qids=drop_subset)
            if deltas:
                stat = paired_stat(deltas, iters=iters, seed=seed)
                excludes = "**YES**" if (stat.ci_lo > 0 or stat.ci_hi < 0) else "no"
                out.append(f"| **overall** | {stat.mean:+.4f} | "
                           f"[{stat.ci_lo:+.4f}, {stat.ci_hi:+.4f}] | "
                           f"{stat.cohen_d:+.2f} | {stat.n} | {excludes} |")
            out.append("")

    # Decision summary tied to mentor risk #1 + spec §3.2 promote/narrow/rollback
    out.append("## Decision summary (per spec §3.2 Provisional gates)")
    out.append("")
    out.append("§3.2 amendment becomes:")
    out.append("- **final** if `Δ(V4_pool − V1)` faith mean ≥ +0.05 with CI excluding 0")
    out.append("- **narrow** (drop per-type pool claim, keep agent-inference framing) "
               "if mean ∈ (+0.03, +0.05) with CI inconclusive")
    out.append("- **rollback** if mean ≤ +0.03 (tool-call complexity not justified)")
    out.append("")

    return "\n".join(out)


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--iters", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    scores = _load_scores(args.scores)
    report = _render_report(scores, iters=args.iters, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"[v4_paired_bootstrap] wrote {args.out} "
          f"({sum(1 for _ in report.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
