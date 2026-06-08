#!/usr/bin/env bash
# Run seeds 43 and 44 sequentially (avoids host oversubscription), then
# aggregate 3-seed variance → PHASE2_REPORT. One harness-managed background job.
set -uo pipefail
cd "$(dirname "$0")/.."

for S in 43 44; do
  echo "######## SEED $S ########"
  bash scripts/run_phase2_seed_full.sh $S
done

echo "######## 3-seed aggregate ########"
python code/judge/aggregate_seeds.py \
  --gates outputs/v0.5_harness/PHASE2_GATE_s42.json \
          outputs/v0.5_harness/PHASE2_GATE_s43.json \
          outputs/v0.5_harness/PHASE2_GATE_s44.json \
  --out outputs/v0.5_harness/PHASE2_REPORT.md
echo "######## ALL DONE — PHASE2_REPORT.md ########"
