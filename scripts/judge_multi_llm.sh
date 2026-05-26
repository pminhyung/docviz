#!/usr/bin/env bash
# Judge a multi-LLM viz dir with scope-v3 protocol (re-using cached
# checklists from production). Usage:
#   bash scripts/judge_multi_llm.sh <dir_name>
# e.g.:
#   bash scripts/judge_multi_llm.sh deepseek
#   bash scripts/judge_multi_llm.sh gemma3
#   bash scripts/judge_multi_llm.sh sonnet
# Outputs:
#   outputs/multi_llm/$1/judge_scores/all.json
#   outputs/multi_llm/$1/judge_scores/raw.jsonl
set -euo pipefail
cd /ex_disk2/mhpark/poc/docviz

NAME="${1:?dir name required (deepseek|gemma3|sonnet)}"
DIR="outputs/multi_llm/$NAME"
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

# Summary
python3 - <<PY
import json
from collections import defaultdict
data = json.load(open("$DIR/judge_scores/all.json"))
by_s = defaultdict(list)
for r in data:
    by_s[r['strategy']].append(r['overall'])
print()
print(f"=== $NAME — per-strategy mean overall (n={len(data)//max(1,len(by_s))} per strategy) ===")
ranks = sorted(((s, sum(v)/len(v)) for s, v in by_s.items()), key=lambda x:-x[1])
for s, m in ranks:
    print(f"  {s:<24s}  {m:.4f}")
PY
