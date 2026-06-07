#!/usr/bin/env bash
# Phase-2 B6 arms — full / −SEF / −VSC. Encodes the v0.4.3 input×variant matrix:
#   full : SEF root   + VSC on        (DOCVIZ_VARIANT=full,  SEF_DIR set)
#   nosef: markdown   + VSC on        (DOCVIZ_VARIANT=nosef, SEF_DIR unset → plain md input)
#   novsc: SEF root   + direct-DSL    (DOCVIZ_VARIANT=novsc, SEF_DIR set)
# Baselines B5/B7 are separate scripts (run_s1_baseline.py / run_s7_selfrefine.py).
#
# Usage: scripts/run_phase2_b6_arms.sh <n_samples> <seed> <out_tag>
set -uo pipefail
cd "$(dirname "$0")/.."

N="${1:-3}"; SEED="${2:-42}"; TAG="${3:-pf}"
RUNNER=data/queries/loong_phase2_working_runner.jsonl
MD_ROOT=outputs/v0.5_harness/loong_docai_phase2
SEF_ROOT=outputs/v0.5_harness/loong_docai_phase2_sef
SEF_DIR=outputs/v0.5_harness/phase2_sef
HOSTS=configs/hosts-eval-qwen.yaml
COMMON="HERMES_EXAONE_AGENT=1 HERMES_DOC_SOURCE=local EXAONE_DISABLE_RFD=1 DOCVIZ_SYNTH_MODEL=Qwen3.5-397B-A17B-FP8"

run_arm () {  # name root variant sef_dir
  local name="$1" root="$2" variant="$3" sef="$4"
  local rn="${TAG}_${name}_s${SEED}"
  echo "▶ arm=$name root=$(basename $root) variant=$variant sef_dir=${sef:-none} run=$rn"
  env $COMMON \
    EXAONE_PARSED_ROOT="$root" DOCVIZ_VARIANT="$variant" \
    ${sef:+DOCVIZ_SEF_DIR=$sef} \
    DOCVIZ_VIZ_SIDECAR_DIR="/tmp/${rn}_viz" \
    python exaone/batch_runner_pool.py --dataset_file="$RUNNER" \
      --batch_size="$N" --max_samples="$N" --run_name="$rn" \
      --host_config="$HOSTS" --max_turns=10 > "/tmp/${rn}.log" 2>&1
  echo "  done: data/${rn}/  (log /tmp/${rn}.log)"
}

run_arm full  "$SEF_ROOT" full  "$SEF_DIR"
run_arm nosef "$MD_ROOT"  nosef ""
run_arm novsc "$SEF_ROOT" novsc "$SEF_DIR"
echo "all B6 arms done for seed $SEED"
