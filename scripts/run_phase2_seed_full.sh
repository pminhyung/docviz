#!/usr/bin/env bash
# Full Phase-2 seed: run all 5 arms (B5,B7,B6-full/−SEF/−VSC) × 100, then
# recover the 3 B6 arms + score. One self-contained script so it survives as a
# single harness-managed background job (inline nohup children get orphaned).
# Usage: scripts/run_phase2_seed_full.sh <seed>
set -uo pipefail
cd "$(dirname "$0")/.."
SEED="${1:-43}"
RUNNER=data/queries/loong_phase2_working_runner.jsonl
BUNDLES=data/bundles/loong_phase2.json

echo "=== [$SEED] launch B5 + B7 + B6 arms ==="
python scripts/run_s1_baseline.py --dataset $RUNNER --bundles $BUNDLES \
  --out data/phase2_b5_s${SEED}/batch_0.jsonl > /tmp/b5_s${SEED}.log 2>&1 &
P_B5=$!
python scripts/run_s7_selfrefine.py --dataset $RUNNER --bundles $BUNDLES \
  --out data/phase2_b7_s${SEED}/batch_0.jsonl --iters 2 > /tmp/b7_s${SEED}.log 2>&1 &
P_B7=$!
bash scripts/run_phase2_b6_arms.sh 100 ${SEED} phase2 > /tmp/b6arms_s${SEED}.log 2>&1 &
P_B6=$!

echo "=== [$SEED] wait for all arms (B5=$P_B5 B7=$P_B7 B6=$P_B6) ==="
wait $P_B5 $P_B7 $P_B6
echo "=== [$SEED] all arms done; counts ==="
for d in b5 b7 full nosef novsc; do
  echo "  phase2_${d}_s${SEED}: $(wc -l < data/phase2_${d}_s${SEED}/batch_0.jsonl 2>/dev/null || echo 0)"
done

echo "=== [$SEED] recover + score ==="
bash scripts/score_phase2_seed.sh ${SEED}
echo "=== [$SEED] DONE ==="
