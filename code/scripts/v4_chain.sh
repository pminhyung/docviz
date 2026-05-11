#!/usr/bin/env bash
# V4 chain-runner — unattended sequential execution of:
#   wait V1 → V4_pool → V4_consolidated → judge → analysis
#
# V1 PID is hardcoded as the first arg (default 3423847 — the alive
# V1 batch process). Override on command line if relaunched.
#
# Each step's log goes to /tmp/v4_logs/{step}.log. Final analysis
# output: docs/analysis/v4_paired_results.md.
#
# Usage:
#   nohup bash code/scripts/v4_chain.sh [V1_PID] > /tmp/v4_logs/chain.log 2>&1 &

set -u
V1_PID=${1:-3423847}
LOGDIR=/tmp/v4_logs
mkdir -p "$LOGDIR"

VLLM_BASE=http://10.1.211.148:8000/v1
# host round-robin via QWEN_HOSTS — see s4_agentic_tmg._next_reasoner_url
COMMON_ENV="QWEN_BASE_URL=$VLLM_BASE DOCVIZ_VLLM_BASE_URL=$VLLM_BASE QWEN_HOSTS=10.1.211.148:8000,10.1.211.163:8000,10.1.211.164:8000,10.1.211.165:8000,10.1.211.166:8000,10.1.211.167:8000,10.1.211.168:8000,10.1.211.169:8000,10.1.211.170:8000 DOCVIZ_HOST_MODE=single PYTHONUNBUFFERED=1"

stamp() { date '+%Y-%m-%d %H:%M:%S'; }

log() { echo "[chain $(stamp)] $*"; }

run_step() {
  local label=$1
  local logfile=$2
  shift 2
  log "▶ $label"
  log "   cmd: $*"
  log "   log: $logfile"
  if eval "$@" > "$logfile" 2>&1; then
    log "✓ $label OK (exit 0)"
    return 0
  else
    local rc=$?
    log "✗ $label FAILED (exit $rc) — chain halted"
    return $rc
  fi
}

# ── Step 0 — wait for V1 ─────────────────────────────────────────────────
log "waiting for V1 batch PID=$V1_PID"
while ps -p "$V1_PID" > /dev/null 2>&1; do
  sleep 30
done
log "V1 finished"

# Brief pause to flush
sleep 5

# ── Step 1 — V4_consolidated full batch (priority per user 2026-05-10) ──
run_step "V4_consolidated full batch (60 records)" \
  "$LOGDIR/v4_cons.log" \
  "$COMMON_ENV python -m code.run_prototype --strategies S4_TMGv4_consolidated --s4-workers 1" \
  || exit 1

# ── Step 2 — INTERMEDIATE judge (V1 + V4_consolidated only) ─────────────
# run_judge picks up un-judged (query_id, strategy) pairs idempotently.
run_step "INTERMEDIATE judge (V1 + V4_consolidated)" \
  "$LOGDIR/judge_intermediate.log" \
  "$COMMON_ENV python -m code.judge.run_judge" \
  || exit 1

# ── Step 3 — INTERMEDIATE paired bootstrap analysis ─────────────────────
# Writes docs/analysis/v4_paired_results.md. V4_pool comparisons skip
# because V4_pool not yet measured; V4_consolidated comparisons populated.
run_step "INTERMEDIATE analysis (V4_consolidated + V1 + V0/S4 only)" \
  "$LOGDIR/analysis_intermediate.log" \
  "python -m code.analysis.v4_paired_bootstrap --out docs/analysis/v4_paired_results_intermediate.md" \
  || exit 1

log "=== INTERMEDIATE PHASE DONE — V4_consolidated results ready ==="
log "docs/analysis/v4_paired_results_intermediate.md"

# ── Step 4 — V4_pool full batch ──────────────────────────────────────────
run_step "V4_pool full batch (60 records)" \
  "$LOGDIR/v4_pool.log" \
  "$COMMON_ENV python -m code.run_prototype --strategies S4_TMGv4_pool --s4-workers 1" \
  || exit 1

# ── Step 5 — FINAL judge (adds V4_pool) ─────────────────────────────────
run_step "FINAL judge (adds V4_pool)" \
  "$LOGDIR/judge_final.log" \
  "$COMMON_ENV python -m code.judge.run_judge" \
  || exit 1

# ── Step 6 — FINAL paired bootstrap analysis ────────────────────────────
run_step "FINAL analysis (all 6 strategies including V4_pool)" \
  "$LOGDIR/analysis_final.log" \
  "python -m code.analysis.v4_paired_bootstrap --out docs/analysis/v4_paired_results.md" \
  || exit 1

log "=== ALL STEPS DONE ==="
log "intermediate: docs/analysis/v4_paired_results_intermediate.md"
log "final: docs/analysis/v4_paired_results.md"
