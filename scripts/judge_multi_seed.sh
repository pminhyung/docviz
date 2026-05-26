#!/usr/bin/env bash
set -euo pipefail
cd /ex_disk2/mhpark/poc/docviz

SEED="${1:?seed required (e.g. 43)}"
DIR="outputs/multi_seed/seed${SEED}"
[ -f "$DIR/viz/all.json" ] || { echo "viz missing: $DIR/viz/all.json"; exit 1; }

mkdir -p "$DIR/judge_scores"

python -m code.judge.run_judge \
    --viz "$DIR/viz/all.json" \
    --bundles data/prototype/bundles/all.json \
    --out "$DIR/judge_scores/all.json" \
    --checklist-cache outputs/prototype/judge_scores/checklists.json \
    --raw "$DIR/judge_scores/raw.jsonl" \
    --score-workers 16 \
    --checklist-workers 6

python3 - <<PY
import json, statistics
from collections import defaultdict
new = json.load(open("$DIR/judge_scores/all.json"))
prod = json.load(open("outputs/prototype/judge_scores/all.json"))
new_idx = {(r['query_id'], r['strategy']): r['overall'] for r in new}
prod_idx = {(r['query_id'], r['strategy']): r['overall'] for r in prod}
strats = sorted(set(r['strategy'] for r in new))
print()
print("=== seed42 (production) vs seed${SEED} per-strategy mean overall ===")
print(f"{'strategy':<28s} {'seed42':>8s} {'seed'+str(${SEED}):>8s} {'delta':>8s}  {'std':>8s}")
print("-"*72)
for s in strats:
    qids = [k[0] for k in new_idx if k[1]==s]
    n = len(qids)
    m42 = sum(prod_idx.get((q,s),0) for q in qids)/n
    mxx = sum(new_idx.get((q,s),0) for q in qids)/n
    delta = mxx - m42
    std2 = statistics.stdev([m42, mxx])
    print(f"{s:<28s} {m42:>8.4f} {mxx:>8.4f} {delta:>+8.4f}  {std2:>8.4f}")
PY
