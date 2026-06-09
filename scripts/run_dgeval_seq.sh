#!/usr/bin/env bash
# DiagramEval node/path — SEQUENTIAL (one arm at a time, workers=4) with chromium
# cleanup between arms. Slow but reliable: concurrency clogged the vLLM vision
# scheduler and accumulated chromium zombies → hangs. Resumes (skips existing).
set -uo pipefail
cd "$(dirname "$0")/.."
G=data/gold/loong_phase2_working.jsonl
R=outputs/v0.5_harness

clean() { pkill -9 -f "mmdc" 2>/dev/null || true; pkill -9 -f "chrome" 2>/dev/null || true; sleep 2; }

clean
for seed in 42 43 44; do
  for arm in full nosef novsc b5 b7; do
    out=$R/dgeval_${arm}_s${seed}.json
    [ -f "$out" ] && { echo "skip $arm s$seed"; continue; }
    echo "=== $arm s$seed ($(date +%H:%M)) ==="
    if [ "$arm" = "b5" ] || [ "$arm" = "b7" ]; then
      python -u code/judge/diagrameval_score.py --baseline-traj data/phase2_${arm}_s${seed} \
        --gold $G --out "$out" --workers 4 > /tmp/dge_${arm}_s${seed}.log 2>&1 || true
    else
      python -u code/judge/diagrameval_score.py --recovered $R/rec_${arm}_s${seed}.json \
        --gold $G --out "$out" --workers 4 > /tmp/dge_${arm}_s${seed}.log 2>&1 || true
    fi
    clean
    echo "done $arm s$seed → $(grep -aoE 'done: ok [0-9]+/[0-9]+.*' /tmp/dge_${arm}_s${seed}.log 2>/dev/null | tail -1)"
  done
done
echo "=== ALL done; aggregate ==="
python code/judge/aggregate_dgeval.py
