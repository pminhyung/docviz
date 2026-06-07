#!/usr/bin/env bash
# Recover the 3 B6 arms (mirroring each variant) + score all 5 arms for one seed.
# Usage: scripts/score_phase2_seed.sh <seed>
set -uo pipefail
cd "$(dirname "$0")/.."

SEED="${1:-42}"
M=Qwen3.5-397B-A17B-FP8
Q=data/queries/loong_phase2_working.jsonl
G=data/gold/loong_phase2_working.jsonl
SEF_DIR=outputs/v0.5_harness/phase2_sef
REC=outputs/v0.5_harness

echo "▶ recover B6 arms (seed $SEED)"
DOCVIZ_VARIANT=full  DOCVIZ_SEF_DIR=$SEF_DIR DOCVIZ_SYNTH_MODEL=$M \
  python code/judge/recover_b6_viz.py --traj data/phase2_full_s${SEED} \
  --queries $Q --out $REC/rec_full_s${SEED}.json --workers 8 2>&1 | grep -E "recovery mode|wrote"
DOCVIZ_VARIANT=nosef DOCVIZ_SYNTH_MODEL=$M \
  python code/judge/recover_b6_viz.py --traj data/phase2_nosef_s${SEED} \
  --queries $Q --out $REC/rec_nosef_s${SEED}.json --workers 8 2>&1 | grep -E "recovery mode|wrote"
DOCVIZ_VARIANT=novsc DOCVIZ_SYNTH_MODEL=$M \
  python code/judge/recover_b6_viz.py --traj data/phase2_novsc_s${SEED} \
  --queries $Q --out $REC/rec_novsc_s${SEED}.json --workers 8 2>&1 | grep -E "recovery mode|wrote"

echo "▶ score all 5 arms (seed $SEED)"
python code/judge/score_phase1.py \
  --b6-traj data/phase2_full_s${SEED} --b6-sidecar /tmp/phase2_full_s${SEED}_viz \
  --b6-recovered $REC/rec_full_s${SEED}.json \
  --b5-traj data/phase2_b5_s${SEED} --b7-traj data/phase2_b7_s${SEED} \
  --b6-nosef-traj data/phase2_nosef_s${SEED} --b6-nosef-recovered $REC/rec_nosef_s${SEED}.json \
  --b6-novsc-traj data/phase2_novsc_s${SEED} --b6-novsc-recovered $REC/rec_novsc_s${SEED}.json \
  --queries $Q --gold $G --clipscore \
  --out $REC/PHASE2_GATE_s${SEED}.json 2>&1 | grep -vE "fal_client|Could not"
echo "▶ wrote $REC/PHASE2_GATE_s${SEED}.json"
