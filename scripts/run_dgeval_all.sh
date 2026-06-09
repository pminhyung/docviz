#!/usr/bin/env bash
# Real DiagramEval (Qwen-VL) node/path for all 5 arms × 3 seeds = 15 jobs,
# 3 concurrent (bounded so the 7-host pool isn't oversubscribed). One
# harness-managed background job.
set -uo pipefail
cd "$(dirname "$0")/.."
G=data/gold/loong_phase2_working.jsonl
R=outputs/v0.5_harness

run() {  # arm seed
  local arm=$1 seed=$2 out=$R/dgeval_${1}_s${2}.json
  [ -f "$out" ] && { echo "skip $out (exists)"; return; }
  if [ "$arm" = "b5" ] || [ "$arm" = "b7" ]; then
    python code/judge/diagrameval_score.py --baseline-traj data/phase2_${arm}_s${seed} \
      --gold $G --out "$out" --workers 10 > /tmp/dge_${arm}_s${seed}.log 2>&1
  else
    python code/judge/diagrameval_score.py --recovered $R/rec_${arm}_s${seed}.json \
      --gold $G --out "$out" --workers 10 > /tmp/dge_${arm}_s${seed}.log 2>&1
  fi
  echo "done $arm s$seed"
}

for seed in 42 43 44; do
  for arm in full nosef novsc b5 b7; do
    run "$arm" "$seed" &
    while [ "$(jobs -r | wc -l)" -ge 3 ]; do wait -n; done
  done
done
wait
echo "=== all 15 done; aggregate ==="
python code/judge/aggregate_dgeval.py
