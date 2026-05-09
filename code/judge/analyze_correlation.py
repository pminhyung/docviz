#!/usr/bin/env python3
"""Judge ↔ Human correlation + inter-rater agreement (Week 0 §7.4 / §1.2).

Reads:
  outputs/prototype/human_ratings/ratings_*.csv   (one per rater)
  outputs/prototype/human_ratings/sample_keys.json  (judge anchor scores)

Reports:
  - Spearman r per axis: mean(rater) vs judge_axis_score        (target ≥ 0.5)
  - Per-rater Spearman r per axis (sanity, in case one rater is noisy)
  - Cohen's κ (linear-weighted) between every pair of raters per axis
                                                                  (target ≥ 0.5)
  - Largest judge↔human disagreements (top 5 by |Δ|) — for W0_REPORT.

Spec reference: PAPER_MASTER_SPEC §10.5 Layer 2 anchor (r ≥ 0.65 minimum,
≥ 0.5 acceptable for prototype Go/No-Go per QG-MDV §1.2).
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
RATINGS_GLOB = REPO_ROOT / "outputs" / "prototype" / "human_ratings" / "ratings_*.csv"
KEYS_PATH = REPO_ROOT / "outputs" / "prototype" / "human_ratings" / "sample_keys.json"


AXES = ("faithfulness", "coverage", "type_appropriateness")
COL_BY_AXIS = {
    "faithfulness": "faith_score",
    "coverage": "coverage_score",
    "type_appropriateness": "type_score",
}


# ── Stats (no scipy/sklearn dependency) ───────────────────────────────────


def _rank(xs: List[float]) -> List[float]:
    """Average-rank to handle ties (matches scipy.stats.rankdata 'average')."""
    n = len(xs)
    order = sorted(range(n), key=lambda i: xs[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1   # 1-based average
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def spearman(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    return _pearson(_rank(xs), _rank(ys))


def cohen_kappa_linear(xs: List[float], ys: List[float],
                       categories=(0.0, 0.5, 1.0)) -> Optional[float]:
    """Linear-weighted Cohen's κ for ordinal categories."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    cats = list(categories)
    k = len(cats)
    idx = {c: i for i, c in enumerate(cats)}
    obs = [[0] * k for _ in range(k)]
    for x, y in zip(xs, ys):
        if x not in idx or y not in idx:
            continue
        obs[idx[x]][idx[y]] += 1
    n = sum(sum(r) for r in obs)
    if n == 0:
        return None
    row_marg = [sum(r) for r in obs]
    col_marg = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    # Linear weights: 1 - |i - j| / (k - 1)
    def w(i, j): return 1.0 - abs(i - j) / (k - 1)
    p_o = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k)) / n
    p_e = sum(w(i, j) * row_marg[i] * col_marg[j] for i in range(k) for j in range(k)) / (n * n)
    if p_e >= 1.0:
        return None
    return (p_o - p_e) / (1 - p_e)


# ── IO ───────────────────────────────────────────────────────────────────


def _coerce_score(s: str) -> Optional[float]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if v not in (0.0, 0.5, 1.0):
        # Snap close values (some raters might type "0.50")
        return min((0.0, 0.5, 1.0), key=lambda c: abs(c - v))
    return v


def _load_ratings_csv(path: Path) -> Dict[str, Dict[str, Optional[float]]]:
    """Return {rating_id: {axis: score, "rater_id": "..."}}."""
    out: Dict[str, Dict[str, Optional[float]]] = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = (row.get("rating_id") or "").strip()
            if not rid:
                continue
            entry = {ax: _coerce_score(row.get(COL_BY_AXIS[ax], "")) for ax in AXES}
            entry["rater_id"] = (row.get("rater_id") or path.stem.replace("ratings_", "")).strip()
            out[rid] = entry
    return out


# ── Analysis ─────────────────────────────────────────────────────────────


def _aggregate_human(per_rater: List[Dict[str, Dict[str, Any]]],
                     ax: str) -> Dict[str, Optional[float]]:
    """Mean-axis-score per rating_id, ignoring missing scores."""
    agg: Dict[str, Optional[float]] = {}
    keys = set()
    for r in per_rater:
        keys.update(r.keys())
    for rid in keys:
        vals = [r[rid].get(ax) for r in per_rater
                if rid in r and r[rid].get(ax) is not None]
        agg[rid] = (sum(vals) / len(vals)) if vals else None
    return agg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratings-glob", default=str(RATINGS_GLOB))
    ap.add_argument("--keys", default=str(KEYS_PATH))
    args = ap.parse_args()

    rating_paths = sorted(glob.glob(args.ratings_glob))
    if not rating_paths:
        print(f"[analyze] no ratings files matched {args.ratings_glob}")
        print("Each rater should produce ratings_<name>.csv from template.csv.")
        return 1
    print(f"[analyze] found {len(rating_paths)} rater files: "
          f"{[Path(p).name for p in rating_paths]}")

    per_rater = [_load_ratings_csv(Path(p)) for p in rating_paths]
    rater_names = [next(iter(r.values()), {}).get("rater_id", Path(p).stem)
                   for p, r in zip(rating_paths, per_rater)]

    keys = json.loads(Path(args.keys).read_text(encoding="utf-8"))
    keys_by_id = {k["rating_id"]: k for k in keys}

    # ── Per-axis Spearman vs judge ──
    print("\n=== Spearman r per axis (mean human ↔ judge) ===")
    print(f"{'axis':<22s} {'n':>3s} {'r':>7s}   per-rater r")
    rows: List[Dict[str, Any]] = []
    for ax in AXES:
        human_agg = _aggregate_human(per_rater, ax)
        xs, ys = [], []
        per_rater_corr: List[Optional[float]] = []
        # mean human vs judge
        for rid, hv in human_agg.items():
            if hv is None or rid not in keys_by_id:
                continue
            jv = keys_by_id[rid]["judge_axis_scores"].get(ax)
            if jv is None:
                continue
            xs.append(hv)
            ys.append(jv)
        r = spearman(xs, ys)
        # per-rater
        per_rater_str_parts = []
        for rmap, name in zip(per_rater, rater_names):
            xs_p, ys_p = [], []
            for rid, e in rmap.items():
                v = e.get(ax)
                if v is None or rid not in keys_by_id:
                    continue
                jv = keys_by_id[rid]["judge_axis_scores"].get(ax)
                if jv is None:
                    continue
                xs_p.append(v)
                ys_p.append(jv)
            r_p = spearman(xs_p, ys_p)
            per_rater_corr.append(r_p)
            per_rater_str_parts.append(f"{name}={r_p:.3f}" if r_p is not None else f"{name}=n/a")
        per_rater_str = "  ".join(per_rater_str_parts)
        rstr = f"{r:.3f}" if r is not None else "n/a"
        print(f"{ax:<22s} {len(xs):>3d} {rstr:>7s}   {per_rater_str}")
        rows.append({"axis": ax, "n": len(xs), "spearman_r": r,
                     "per_rater": dict(zip(rater_names, per_rater_corr))})

    # ── Inter-rater Cohen's κ (pairwise) ──
    print("\n=== Cohen's κ (linear-weighted) — inter-rater per axis ===")
    if len(per_rater) < 2:
        print("  (need ≥2 raters)")
    else:
        for i in range(len(per_rater)):
            for j in range(i + 1, len(per_rater)):
                a, b = rater_names[i], rater_names[j]
                print(f"\n  pair: {a} ↔ {b}")
                for ax in AXES:
                    xs = [per_rater[i][rid].get(ax) for rid in per_rater[i]
                          if rid in per_rater[j]
                          and per_rater[i][rid].get(ax) is not None
                          and per_rater[j][rid].get(ax) is not None]
                    ys = [per_rater[j][rid].get(ax) for rid in per_rater[i]
                          if rid in per_rater[j]
                          and per_rater[i][rid].get(ax) is not None
                          and per_rater[j][rid].get(ax) is not None]
                    k = cohen_kappa_linear(xs, ys)
                    kstr = f"{k:.3f}" if k is not None else "n/a"
                    print(f"    {ax:<22s} n={len(xs):>3d}  κ={kstr}")

    # ── Largest disagreements ──
    print("\n=== Top 5 largest |judge − mean_human| disagreements (overall) ===")
    deltas = []
    for rid, key in keys_by_id.items():
        # average across axes for "overall human"
        humans = []
        for ax in AXES:
            for rmap in per_rater:
                v = rmap.get(rid, {}).get(ax)
                if v is not None:
                    humans.append(v)
        if not humans or key["judge_overall"] is None:
            continue
        mh = sum(humans) / len(humans)
        deltas.append((rid, mh, key["judge_overall"], abs(mh - key["judge_overall"]),
                       key["query_id"], key["strategy"]))
    deltas.sort(key=lambda x: -x[3])
    print(f"  {'rid':<5s} {'qid':<28s} {'strat':<11s} {'human':>6s} {'judge':>6s} {'|Δ|':>6s}")
    for rid, mh, j, d, qid, strat in deltas[:5]:
        print(f"  {rid:<5s} {qid:<28s} {strat:<11s} {mh:>6.2f} {j:>6.2f} {d:>6.2f}")

    # ── §1.2 gate ──
    print("\n=== Week 0 §1.2 Judge gate ===")
    n_pass = sum(1 for row in rows if row["spearman_r"] is not None and row["spearman_r"] >= 0.5)
    print(f"  axes meeting r ≥ 0.5: {n_pass} / {len(AXES)}")
    print(f"  GO branch requires ≥ 2 of 3 axes — {'PASS' if n_pass >= 2 else 'FAIL'}")
    return 0 if n_pass >= 2 else 0   # don't fail CI; this is a report


if __name__ == "__main__":
    sys.exit(main())
