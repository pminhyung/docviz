#!/usr/bin/env python3
"""Sample 30 viz for human spot validation (Week 0 §7, Option A).

Design choices:
  - 15 S1 + 15 S4 (balanced strategy split for paired comparison).
  - Within each strategy, source proportional to the 60-record pool:
    5 hotpotqa + 5 multinews + 3 arxiv + 2 10k = 15 each.
  - Within each (strategy, source) cell, pick records at evenly-spaced
    indices of the cell sorted by judge `overall`. This guarantees the
    sample spans the score range so Spearman r vs. human has signal at
    both ends; otherwise the 0.95-1.00 cluster (36% of all records) would
    dominate a uniform random sample and flatten correlation.
  - No judge scores in the rater-facing CSV — preserves blinding so the
    correlation we compute later isn't anchored.
  - sample_keys.json keeps the (query_id, strategy) keys + judge scores
    for merge after ratings are filled in.

Usage:
    python -m code.judge.sample_for_human
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[2]
JUDGE_PATH = REPO_ROOT / "outputs" / "prototype" / "judge_scores" / "all.json"
VIZ_PATH = REPO_ROOT / "outputs" / "prototype" / "viz" / "all.json"
BUNDLES_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "all.json"
OUT_DIR = REPO_ROOT / "outputs" / "prototype" / "human_ratings"
TEMPLATE_PATH = OUT_DIR / "template.csv"
KEYS_PATH = OUT_DIR / "sample_keys.json"


# 30 sample plan: per-strategy share of each source
PER_STRAT_PLAN = {"hotpotqa": 5, "multinews": 5, "arxiv": 3, "10k": 2}
SEED = 42


def _spread_indices(n_total: int, n_pick: int) -> List[int]:
    """Return n_pick evenly-spaced indices in [0, n_total-1]."""
    if n_pick >= n_total:
        return list(range(n_total))
    step = (n_total - 1) / (n_pick - 1) if n_pick > 1 else 0
    return [round(i * step) for i in range(n_pick)]


def _sample_cell(records: List[Dict[str, Any]], n_pick: int) -> List[Dict[str, Any]]:
    """Pick n_pick records spread across overall score within a cell."""
    if not records:
        return []
    rs = sorted(records, key=lambda r: (r.get("overall") or 0.0))
    idxs = _spread_indices(len(rs), n_pick)
    return [rs[i] for i in idxs]


def _truncate(s: str, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + "...(truncated)"


def _format_source_brief(bundle, char_cap: int = 800) -> str:
    """Compact per-doc summary for the rater. Plain text, no JSON noise."""
    parts = []
    for d in bundle.docs:
        body = (d.content or "")[:char_cap]
        parts.append(f"[{d.title}]\n{body}")
    return "\n\n---\n\n".join(parts)


def main() -> int:
    from code.utils.bundle_io import read_bundles_json

    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", default=str(JUDGE_PATH))
    ap.add_argument("--viz", default=str(VIZ_PATH))
    ap.add_argument("--bundles", default=str(BUNDLES_PATH))
    ap.add_argument("--out", default=str(TEMPLATE_PATH))
    ap.add_argument("--keys-out", default=str(KEYS_PATH))
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    judge = json.loads(Path(args.judge).read_text(encoding="utf-8"))
    viz_records = json.loads(Path(args.viz).read_text(encoding="utf-8"))
    viz_by_key = {(r["query_id"], r["strategy"]): r for r in viz_records}
    bundles = {b.bundle_id: b for b in read_bundles_json(args.bundles)}
    print(f"[sample] loaded {len(judge)} judged records, "
          f"{len(viz_by_key)} viz records, {len(bundles)} bundles")

    random.seed(args.seed)
    sample: List[Dict[str, Any]] = []
    for strategy in ("S1_Direct", "S4_Agentic"):
        for source, n_pick in PER_STRAT_PLAN.items():
            cell = [r for r in judge
                    if r["strategy"] == strategy and r["source"] == source]
            picked = _sample_cell(cell, n_pick)
            for r in picked:
                sample.append(r)
            print(f"  cell {strategy:<12s} {source:<10s}: pool={len(cell):>2d} → picked={len(picked)} "
                  f"overall=[{min(r['overall'] for r in picked):.2f}, {max(r['overall'] for r in picked):.2f}]")

    # Shuffle so raters don't see strategy patterns in rating order
    random.shuffle(sample)
    print(f"[sample] total: {len(sample)} records")

    out_dir = Path(args.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Rater-facing CSV — no judge scores, no axis_scores, no overall.
    cols = [
        "rating_id", "query_id", "strategy_blind",
        "query_type", "query", "viz_type", "viz_dsl",
        "source_brief",
        "rater_id",          # rater fills (e.g., "self" or "colleague")
        "faith_score",       # rater fills: 0 / 0.5 / 1
        "coverage_score",    # rater fills
        "type_score",        # rater fills
        "notes",
    ]
    keys: List[Dict[str, Any]] = []
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(cols)
        for i, r in enumerate(sample):
            bundle = bundles[r["bundle_id"]]
            viz = viz_by_key[(r["query_id"], r["strategy"])]
            # Strategy is blinded as A/B (not S1/S4) to avoid rater bias toward agent.
            blind = "A" if r["strategy"] == "S1_Direct" else "B"
            row = [
                f"R{i:02d}",
                r["query_id"],
                blind,
                r["query_type"],
                viz["query"],
                r["viz_type"],
                _truncate(viz["viz_dsl"], 2500),
                _truncate(_format_source_brief(bundle), 4000),
                "", "", "", "", "",
            ]
            w.writerow(row)
            keys.append({
                "rating_id": f"R{i:02d}",
                "query_id": r["query_id"],
                "strategy": r["strategy"],
                "strategy_blind": blind,
                "judge_overall": r["overall"],
                "judge_axis_scores": r["axis_scores"],
            })

    Path(args.keys_out).write_text(
        json.dumps(keys, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"[sample] wrote {args.out} (rater-facing) + {args.keys_out} (keys+judge)")
    print()
    print("Next step: each rater duplicates the CSV, fills rater_id +")
    print("faith_score + coverage_score + type_score (0 / 0.5 / 1), saves as e.g.")
    print("  outputs/prototype/human_ratings/ratings_self.csv")
    print("  outputs/prototype/human_ratings/ratings_colleague.csv")
    print("Then run:")
    print("  python -m code.judge.analyze_correlation")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
