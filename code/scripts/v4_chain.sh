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

VLLM_BASE=http://localhost:9102/v1
# 9102+9103 round-robin via QWEN36_27B_PORTS — see s4_agentic_tmg._next_reasoner_url
COMMON_ENV="QWEN36_27B_BASE_URL=$VLLM_BASE DOCVIZ_VLLM_BASE_URL=$VLLM_BASE QWEN36_27B_PORTS=9102,9103 PYTHONUNBUFFERED=1"

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

# ── Step 1 — V4_pool full batch ──────────────────────────────────────────
run_step "V4_pool full batch (60 records)" \
  "$LOGDIR/v4_pool.log" \
  "$COMMON_ENV python -m code.run_prototype --strategies S4_TMGv4_pool --s4-workers 2" \
  || exit 1

# ── Step 2 — V4_consolidated full batch ──────────────────────────────────
run_step "V4_consolidated full batch (60 records)" \
  "$LOGDIR/v4_cons.log" \
  "$COMMON_ENV python -m code.run_prototype --strategies S4_TMGv4_consolidated --s4-workers 2" \
  || exit 1

# ── Step 3 — judge new records ───────────────────────────────────────────
# run_judge picks up un-judged (query_id, strategy) pairs from viz/all.json
# and writes/updates outputs/prototype/judge_scores/all.json.
run_step "judge run for V1 + V4_pool + V4_consolidated" \
  "$LOGDIR/judge.log" \
  "$COMMON_ENV python -m code.judge.run_judge" \
  || exit 1

# ── Step 4 — paired bootstrap analysis ───────────────────────────────────
run_step "v4_paired_bootstrap analysis" \
  "$LOGDIR/analysis.log" \
  "python -m code.analysis.v4_paired_bootstrap" \
  || exit 1

log "=== ALL STEPS DONE ==="
log "v4_paired_results.md written to docs/analysis/"
