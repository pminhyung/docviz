"""D24 v3 — Hungarian re-balance with v3 rare-feasibility supplement.

Reads:
- data/viz/_subtype_rankings_v2.jsonl  (v2 full-rank + feasibility)
- data/viz/_rare_feasibility_v3.jsonl   (v3 supplement, rare-only)

Builds a UNION feasibility matrix (v2 ∪ v3 for the 4 rare types) and
runs Hungarian assignment again. v2 feasibility for non-rare types
(bar/line/pie/scatter) is preserved verbatim.

Cost is taken from v2 rank for v2-feasible cells, and synthesized
(rank=2, "good fit") for v3-only-feasible cells so the solver prefers
them when quotas demand.

Outputs:
- data/viz/_subtype_assignment_v3.jsonl
    {doc_id, chart_subtype_v2, chart_subtype_v3, swap, unassigned}
    where chart_subtype_v2 is read from corpus.jsonl (current state =
    after v2 balance writeback) and swap = (v3 != v2).
- docs/d24_subtype_balance_v3_report.md

Run:
    python -m scripts.viz.balance_chart_subtypes_v3 [--target auto|...]
"""
import argparse
import collections
import json
import os
import sys
from datetime import datetime

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from scripts.config import CHART_SUBTYPES

RANKINGS_V2 = os.path.join(ROOT, "data", "viz", "_subtype_rankings_v2.jsonl")
RARE_V3 = os.path.join(ROOT, "data", "viz", "_rare_feasibility_v3.jsonl")
CORPUS = os.path.join(ROOT, "data", "documents", "corpus.jsonl")
OUT = os.path.join(ROOT, "data", "viz", "_subtype_assignment_v3.jsonl")
REPORT = os.path.join(ROOT, "docs", "d24_subtype_balance_v3_report.md")

INFEASIBLE_PENALTY = 1000
RARE_TYPES = ["combo", "area", "radar", "doughnut"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="auto")
    args = ap.parse_args()

    if not os.path.exists(RANKINGS_V2):
        print(f"[balance-v3] missing {RANKINGS_V2}"); sys.exit(1)
    if not os.path.exists(RARE_V3):
        print(f"[balance-v3] missing {RARE_V3} — run boost_rare_subtypes first")
        sys.exit(1)

    v2_rows = [json.loads(l) for l in open(RANKINGS_V2) if l.strip()]
    v3_rows = {r["doc_id"]: r for r in (json.loads(l) for l in open(RARE_V3))}
    doc_ids = [r["doc_id"] for r in v2_rows]
    n_docs = len(doc_ids)
    subtypes = list(CHART_SUBTYPES)
    n_sub = len(subtypes)

    cost = np.full((n_docs, n_sub), INFEASIBLE_PENALTY, dtype=np.float64)
    feasible = np.zeros((n_docs, n_sub), dtype=bool)

    # 1. Seed from v2 rankings
    for i, r in enumerate(v2_rows):
        for entry in r.get("chart_rankings", []):
            st = entry.get("subtype")
            if st not in subtypes:
                continue
            j = subtypes.index(st)
            if entry.get("feasible"):
                feasible[i, j] = True
                try:
                    cost[i, j] = float(entry.get("rank", 8))
                except (TypeError, ValueError):
                    cost[i, j] = 8.0

    # 2. Apply v3 union for rare types only
    v3_added = 0
    for i, doc_id in enumerate(doc_ids):
        v3 = v3_rows.get(doc_id, {}).get("rare", {})
        for st in RARE_TYPES:
            j = subtypes.index(st)
            if v3.get(st, {}).get("feasible") and not feasible[i, j]:
                feasible[i, j] = True
                cost[i, j] = 2.0  # synthetic "good fit"
                v3_added += 1

    print(f"[balance-v3] v3 supplement added {v3_added} new (doc, rare-type) "
           "feasibility cells")

    supply = feasible.sum(axis=0)
    print(f"\n[balance-v3] feasibility supply per subtype (v2 ∪ v3):")
    for st, s in zip(subtypes, supply):
        print(f"  {st:9s}: {int(s)}")

    # Targets (auto = even split capped by supply)
    if args.target == "auto":
        even = n_docs // n_sub
        targets = [min(int(s), even) for s in supply]
        remaining = n_docs - sum(targets)
        capacity = [int(s) - t for s, t in zip(supply, targets)]
        order = sorted(range(n_sub), key=lambda j: -capacity[j])
        idx_iter = iter(order)
        while remaining > 0:
            try:
                j = next(idx_iter)
            except StopIteration:
                capacity = [int(supply[j]) - targets[j] for j in range(n_sub)]
                order = sorted(range(n_sub), key=lambda j: -capacity[j])
                if all(c <= 0 for c in capacity):
                    print(f"[balance-v3] WARN: cannot place {remaining} docs")
                    break
                idx_iter = iter(order)
                j = next(idx_iter)
            if targets[j] < int(supply[j]):
                targets[j] += 1
                remaining -= 1
    else:
        targets = [0] * n_sub
        for kv in args.target.split(","):
            k, v = kv.split("=")
            targets[subtypes.index(k.strip())] = int(v)

    print(f"\n[balance-v3] target quotas:")
    for st, t in zip(subtypes, targets):
        print(f"  {st:9s}: {t}")

    # Hungarian
    slots = []
    for j, t in enumerate(targets):
        slots.extend([j] * t)
    n_slots = len(slots)
    expanded = np.zeros((n_docs, n_slots), dtype=np.float64)
    for k, j in enumerate(slots):
        expanded[:, k] = cost[:, j]
    if n_docs > n_slots:
        pad = n_docs - n_slots
        expanded = np.hstack([expanded,
                              np.full((n_docs, pad), INFEASIBLE_PENALTY)])
        slots = slots + [-1] * pad

    from scipy.optimize import linear_sum_assignment
    row_ind, col_ind = linear_sum_assignment(expanded)

    # corpus current state = chart_subtype_v2 result
    current = {}
    with open(CORPUS) as f:
        for line in f:
            d = json.loads(line)
            current[d["doc_id"]] = d.get("chart_subtype", "?")

    assignments = []
    final_dist = collections.Counter()
    swap_count = 0
    unassigned = 0
    for i, k in zip(row_ind, col_ind):
        j = slots[k]
        doc_id = doc_ids[i]
        v2_st = current.get(doc_id, "?")
        if j == -1 or expanded[i, k] >= INFEASIBLE_PENALTY:
            assignments.append({"doc_id": doc_id,
                                  "chart_subtype_v2": v2_st,
                                  "chart_subtype_v3": None,
                                  "swap": False, "unassigned": True})
            unassigned += 1
            continue
        v3_st = subtypes[j]
        final_dist[v3_st] += 1
        swap = (v3_st != v2_st)
        if swap:
            swap_count += 1
        assignments.append({"doc_id": doc_id, "chart_subtype_v2": v2_st,
                              "chart_subtype_v3": v3_st, "swap": swap,
                              "unassigned": False})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for a in assignments:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")

    before_v2 = collections.Counter(current[d] for d in doc_ids)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(f"# D24 v3 Chart Subtype Balance Report\n\n")
        f.write(f"> Generated: {datetime.utcnow().isoformat()} UTC\n")
        f.write(f"> Inputs: {RANKINGS_V2} (v2) + {RARE_V3} (v3 supplement)\n")
        f.write(f"> v3 added {v3_added} new feasibility cells\n\n")
        f.write(f"## Before (v2) vs After (v3)\n\n")
        f.write(f"| subtype | feasibility supply (v2∪v3) | v2 (current) | v3 (after) | target |\n")
        f.write(f"|---|---:|---:|---:|---:|\n")
        for st, t in zip(subtypes, targets):
            f.write(f"| {st} | {int(supply[subtypes.index(st)])} | "
                     f"{before_v2[st]} | {final_dist[st]} | {t} |\n")
        f.write(f"\n**Swaps**: {swap_count} / {n_docs} docs change subtype.\n")
        f.write(f"**Unassigned**: {unassigned}.\n")

    print(f"\n[balance-v3] wrote {OUT}")
    print(f"[balance-v3] wrote {REPORT}")
    print(f"[balance-v3] swaps: {swap_count} / {n_docs}, unassigned: {unassigned}")
    print(f"\n[balance-v3] before(v2) vs after(v3):")
    for st in subtypes:
        print(f"  {st:9s}: {before_v2[st]:3d} → {final_dist[st]:3d}  "
               f"(target {targets[subtypes.index(st)]})")


if __name__ == "__main__":
    main()
