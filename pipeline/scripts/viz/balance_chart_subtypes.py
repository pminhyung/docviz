"""D24 §2 — Hungarian-style balanced assignment of chart subtypes.

Reads `data/viz/_subtype_rankings_v2.jsonl` (full-rank + feasibility per
doc per subtype, produced by rank_subtypes_v2.py) and assigns each doc
to ONE chart subtype such that:

- The corpus-wide subtype distribution is as balanced as feasibility
  supply allows.
- A doc is only assigned to a subtype that the LLM flagged feasible=true
  for that doc.
- Among feasible subtypes, the assignment minimises sum of ranks
  (lower rank = better fit).

Solver: scipy.optimize.linear_sum_assignment on a duplicated cost matrix
that encodes per-subtype quotas. Where exact balance is infeasible due
to supply gaps, the solver fills as evenly as possible and reports the
shortfall.

Inputs / outputs
----------------
in : data/viz/_subtype_rankings_v2.jsonl
out: data/viz/_subtype_assignment_v2.jsonl
     {doc_id, chart_subtype_v1, chart_subtype_v2, swap}
log: docs/d24_subtype_balance_report.md
     (per-subtype before/after, supply, and swap count)

Run:
    python -m scripts.viz.balance_chart_subtypes
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

RANKINGS = os.path.join(ROOT, "data", "viz", "_subtype_rankings_v2.jsonl")
CORPUS = os.path.join(ROOT, "data", "documents", "corpus.jsonl")
OUT = os.path.join(ROOT, "data", "viz", "_subtype_assignment_v2.jsonl")
REPORT = os.path.join(ROOT, "docs", "d24_subtype_balance_report.md")
INFEASIBLE_PENALTY = 1000  # huge cost so solver never picks infeasible


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=str, default="auto",
                     help="auto = floor(N/8) per subtype with supply cap; "
                          "or comma list bar=70,line=70,...")
    args = ap.parse_args()

    if not os.path.exists(RANKINGS):
        print(f"[balance] missing {RANKINGS}"); sys.exit(1)

    # Load rankings
    rows = [json.loads(l) for l in open(RANKINGS) if l.strip()]
    doc_ids = [r["doc_id"] for r in rows]
    n_docs = len(doc_ids)
    subtypes = list(CHART_SUBTYPES)  # 8
    n_sub = len(subtypes)

    # cost[i, j] = rank for doc_i, subtype_j  (1-best, 8-worst)
    # If infeasible, cost = INFEASIBLE_PENALTY
    cost = np.full((n_docs, n_sub), INFEASIBLE_PENALTY, dtype=np.float64)
    feasible = np.zeros((n_docs, n_sub), dtype=bool)
    for i, r in enumerate(rows):
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

    supply = feasible.sum(axis=0)  # per-subtype number of feasible docs
    print(f"[balance] N docs={n_docs}, subtypes={subtypes}")
    print("[balance] feasibility supply per subtype:")
    for st, s in zip(subtypes, supply):
        print(f"  {st:9s}: {int(s)}")

    # Decide target quotas
    if args.target == "auto":
        # Even split with cap = supply for any subtype with too few
        even = n_docs // n_sub
        targets = [min(int(s), even) for s in supply]
        # The shortfall (n_docs - sum(targets)) must be redistributed to
        # subtypes that still have remaining supply.
        remaining = n_docs - sum(targets)
        # Sort subtypes by surplus capacity (supply - target), descending
        capacity = [int(s) - t for s, t in zip(supply, targets)]
        order = sorted(range(n_sub), key=lambda j: -capacity[j])
        idx_iter = iter(order)
        while remaining > 0:
            try:
                j = next(idx_iter)
            except StopIteration:
                # restart loop if any capacity remains
                capacity = [int(supply[j]) - targets[j] for j in range(n_sub)]
                order = sorted(range(n_sub), key=lambda j: -capacity[j])
                if all(c <= 0 for c in capacity):
                    print(f"[balance] WARN: cannot place {remaining} docs "
                           "(no feasible subtype remaining)")
                    break
                idx_iter = iter(order)
                j = next(idx_iter)
            if targets[j] < int(supply[j]):
                targets[j] += 1
                remaining -= 1
    else:
        # Parse explicit "bar=70,line=70,..."
        targets = [0] * n_sub
        for kv in args.target.split(","):
            k, v = kv.split("=")
            targets[subtypes.index(k.strip())] = int(v)
    print("[balance] target quotas:")
    for st, t in zip(subtypes, targets):
        print(f"  {st:9s}: {t}")
    if sum(targets) > n_docs:
        print(f"[balance] WARN: targets sum {sum(targets)} > N {n_docs}; "
               "trimming via solver")

    # Build expanded cost matrix: rows = docs (n_docs), cols = "slots"
    # where slot j_k corresponds to subtype j's k-th opening. Total cols
    # = sum(targets). Rectangular Hungarian (scipy linear_sum_assignment
    # supports rectangular: docs >= slots OK).
    slots = []
    for j, t in enumerate(targets):
        slots.extend([j] * t)
    n_slots = len(slots)
    if n_slots == 0:
        print("[balance] FATAL: no slots")
        sys.exit(1)
    expanded = np.zeros((n_docs, n_slots), dtype=np.float64)
    for k, j in enumerate(slots):
        expanded[:, k] = cost[:, j]

    # If n_docs > n_slots, pad with dummy slots so every doc is assigned.
    # Dummy slots have cost = INFEASIBLE_PENALTY (only used if real slots
    # are exhausted) and we record the assignment as "unassigned".
    if n_docs > n_slots:
        pad = n_docs - n_slots
        expanded = np.hstack([expanded,
                              np.full((n_docs, pad), INFEASIBLE_PENALTY)])
        slots = slots + [-1] * pad

    from scipy.optimize import linear_sum_assignment
    row_ind, col_ind = linear_sum_assignment(expanded)

    # Build assignment results
    assignments = []
    final_dist = collections.Counter()
    swap_count = 0
    unassigned = 0

    # Load doc_id → original chart_subtype map from corpus
    orig = {}
    with open(CORPUS) as f:
        for line in f:
            d = json.loads(line)
            orig[d["doc_id"]] = d.get("chart_subtype", "?")

    for i, k in zip(row_ind, col_ind):
        j = slots[k]
        doc_id = doc_ids[i]
        old = orig.get(doc_id, "?")
        if j == -1 or expanded[i, k] >= INFEASIBLE_PENALTY:
            assignments.append({"doc_id": doc_id,
                                  "chart_subtype_v1": old,
                                  "chart_subtype_v2": None,
                                  "swap": False, "unassigned": True})
            unassigned += 1
            continue
        new_st = subtypes[j]
        final_dist[new_st] += 1
        swap = (new_st != old)
        if swap:
            swap_count += 1
        assignments.append({"doc_id": doc_id, "chart_subtype_v1": old,
                              "chart_subtype_v2": new_st, "swap": swap,
                              "unassigned": False})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for a in assignments:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")

    # Report
    before = collections.Counter(orig[d] for d in doc_ids)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(f"# D24 Chart Subtype Balance Report\n\n")
        f.write(f"> Generated: {datetime.utcnow().isoformat()} UTC\n")
        f.write(f"> Inputs: {RANKINGS} (N={n_docs})\n\n")
        f.write(f"## Before vs After\n\n")
        f.write(f"| subtype | feasibility supply | v1 (before) | v2 (after) | target |\n")
        f.write(f"|---|---:|---:|---:|---:|\n")
        for st, t in zip(subtypes, targets):
            f.write(f"| {st} | {int(supply[subtypes.index(st)])} | "
                     f"{before[st]} | {final_dist[st]} | {t} |\n")
        f.write(f"\n**Swaps**: {swap_count} / {n_docs} docs change subtype.\n")
        f.write(f"**Unassigned** (no feasible slot): {unassigned}.\n")
    print(f"[balance] wrote {OUT}")
    print(f"[balance] wrote {REPORT}")
    print(f"[balance] swaps: {swap_count} / {n_docs}, unassigned: {unassigned}")
    print("[balance] before vs after:")
    for st in subtypes:
        print(f"  {st:9s}: {before[st]:3d} → {final_dist[st]:3d}  "
               f"(target {targets[subtypes.index(st)]})")


if __name__ == "__main__":
    main()
