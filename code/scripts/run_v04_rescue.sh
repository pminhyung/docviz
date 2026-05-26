#!/usr/bin/env bash
# v0.4 rescue-path full benchmark — B6_NoCIS (Fix #1) + sidecar rescue (Fix #2).
#
# Goal: reach SOTA on v0.4 by eliminating tool-invocation failures that
# accounted for 86% of the seed42 B6_Full vs S7_SelfRefine gap.
#
# Stages:
#   2r. B6_NoCIS (with rescue) × seeds 42, 43, 44
#   6r. judge scope-v3 4-axis on all 3 seeds (re-uses checklist cache)
#   7r. aggregate vs baselines from v0.4
#
# Prereq: SOTA agent server on port 9037, multi-host Qwen vLLM cluster up.

set -uo pipefail

export DOCVIZ_AGENT_URL="http://localhost:9037"
export DOCVIZ_HOST_MODE="multi"
export QWEN_HOSTS="10.1.211.147:8000,10.1.211.148:8000,10.1.211.163:8000,10.1.211.164:8000,10.1.211.165:8000,10.1.211.166:8000"
export QWEN_BASE_URL="http://10.1.211.147:8000/v1"
export QWEN_MODEL="Qwen3.5-397B-A17B-FP8"
export DOCVIZ_VIZ_SIDECAR_DIR=/tmp/v4_viz_outputs
export PYTHONUNBUFFERED=1

REPO="/ex_disk2/mhpark/poc/docviz"
cd "$REPO"

OUT_BASE="$REPO/outputs/v0.4_rescue"
LOG_DIR="/tmp/v04_rescue_logs"
mkdir -p "$OUT_BASE/viz" "$OUT_BASE/judge" "$OUT_BASE/reports" "$LOG_DIR"

# Pre-warm checklist cache from v0.4 (300 records already cached).
if [ ! -f "$OUT_BASE/judge/checklists.json" ] && [ -f "$REPO/outputs/v0.4/judge/checklists.json" ]; then
  cp "$REPO/outputs/v0.4/judge/checklists.json" "$OUT_BASE/judge/checklists.json"
fi

STAGE="${1:-all}"
stamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[v04_rescue $(stamp)] $*"; }

stage_2r() {
  log "Stage 2r — B6_NoCIS (rescue) × seeds 42, 43, 44"
  for SEED in 42 43 44; do
    log "  seed=$SEED"
    QWEN_SEED=$SEED python -m code.run_prototype \
      --strategies B6_NoCIS \
      --bundles data/prototype/bundles/all.json \
      --queries data/prototype/queries/all.json \
      --out "$OUT_BASE/viz/b6_nocis_seed${SEED}.json" \
      --raw "$OUT_BASE/viz/b6_nocis_seed${SEED}.raw.jsonl" \
      --s4-workers 6 \
      --force \
      2>&1 | tee "$LOG_DIR/2r_b6_nocis_seed${SEED}.log"
  done
}

stage_6r() {
  log "Stage 6r — judge scope-v3 on all 3 seeds"
  for SEED in 42 43 44; do
    if [ -f "$OUT_BASE/viz/b6_nocis_seed${SEED}.json" ]; then
      python -m code.judge.run_judge \
        --viz "$OUT_BASE/viz/b6_nocis_seed${SEED}.json" \
        --bundles data/prototype/bundles/all.json \
        --out "$OUT_BASE/judge/b6_nocis_seed${SEED}.json" \
        --checklist-cache "$OUT_BASE/judge/checklists.json" \
        --raw "$OUT_BASE/judge/b6_nocis_seed${SEED}.raw.jsonl" \
        --checklist-workers 6 --score-workers 6 \
        2>&1 | tee "$LOG_DIR/6r_judge_seed${SEED}.log"
    fi
  done
}

stage_7r() {
  log "Stage 7r — aggregate vs v0.4 baselines"
  python3 -m code.scripts.aggregate_rescue \
    --rescue-judge-dir "$OUT_BASE/judge" \
    --baselines-judge "$REPO/outputs/v0.4/judge/baselines.json" \
    --out "$OUT_BASE/reports/v04_rescue_summary.md" \
    2>&1 | tee "$LOG_DIR/7r_aggregate.log" || log "  [WARN] aggregator not implemented"
}

case "$STAGE" in
  2r) stage_2r ;;
  6r) stage_6r ;;
  7r) stage_7r ;;
  all)
    stage_2r
    stage_6r
    stage_7r
    ;;
  *) log "unknown stage: $STAGE"; exit 1 ;;
esac

log "rescue pipeline stage=$STAGE complete"
