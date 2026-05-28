#!/usr/bin/env bash
# Restart the docviz agent server (port 9037) with a chosen backbone.
#
# Usage:
#   bash scripts/restart_agent_server.sh qwen        # Qwen3.5-397B on 8-host pool (147,148,163-168)
#   bash scripts/restart_agent_server.sh deepseek    # DeepSeek-V4-Flash on 169,170
#   bash scripts/restart_agent_server.sh gemma3      # Gemma3 — requires `bash scripts/launch_gemma3.sh` first
#
# The agent server (FastAPI) compiles prompts at startup, so a backbone
# swap requires a full restart. This wrapper:
#   1. Kills any existing uvicorn agent.api.server
#   2. Exports the right env (QWEN_HOSTS / QWEN3_MODEL_ID / DOCVIZ_VLLM_MODEL
#      / DOCVIZ_VIZ_SIDECAR_DIR — note: sidecar dir is shared with
#      orchestrator so the generate_viz tool's output is readable)
#   3. Launches uvicorn with --workers matching host count

set -uo pipefail

BACKBONE="${1:-qwen}"
PORT="${PORT:-9037}"
LOG="/tmp/v04_logs/sota_agent_server.log"
SIDECAR_DIR="${DOCVIZ_VIZ_SIDECAR_DIR:-/tmp/v4_viz_outputs}"
mkdir -p "$(dirname "$LOG")" "$SIDECAR_DIR"

# Clear any conflicting env so model_router resolver picks fresh values
unset QWEN3_BASE_URL QWEN3_BASE_URLS QWEN3_API_KEY

case "$BACKBONE" in
  qwen)
    export QWEN_HOSTS="10.1.211.147:8000,10.1.211.148:8000,10.1.211.163:8000,10.1.211.164:8000,10.1.211.165:8000,10.1.211.166:8000,10.1.211.167:8000,10.1.211.168:8000"
    export QWEN_BASE_URL="http://10.1.211.147:8000/v1"
    export QWEN3_MODEL_ID="Qwen3.5-397B-A17B-FP8"
    export DOCVIZ_VLLM_MODEL="Qwen3.5-397B-A17B-FP8"
    WORKERS="${WORKERS:-8}"
    ;;
  deepseek)
    # only 169 confirmed alive (170 down as of 2026-05-28); update when restored
    export QWEN_HOSTS="${DEEPSEEK_HOSTS:-10.1.211.169:8000,10.1.211.170:8000}"
    export QWEN_BASE_URL="http://10.1.211.169:8000/v1"
    export QWEN3_MODEL_ID="deepseek-v4-flash"
    export DOCVIZ_VLLM_MODEL="deepseek-v4-flash"
    WORKERS="${WORKERS:-2}"
    ;;
  gemma3)
    # Requires `bash scripts/launch_gemma3.sh` to be running first.
    # Default: 1 host on localhost:9401 (gemma3-27b-it). Override via GEMMA3_HOSTS.
    export QWEN_HOSTS="${GEMMA3_HOSTS:-localhost:9401}"
    HOST1="${GEMMA3_HOSTS%%,*}"
    export QWEN_BASE_URL="http://${HOST1}/v1"
    export QWEN3_MODEL_ID="${GEMMA3_MODEL:-gemma-3-27b-it}"
    export DOCVIZ_VLLM_MODEL="${GEMMA3_MODEL:-gemma-3-27b-it}"
    WORKERS="${WORKERS:-2}"
    ;;
  *)
    echo "unknown backbone: $BACKBONE (qwen|deepseek|gemma3)"
    exit 1
    ;;
esac

export DOCVIZ_HOST_MODE="multi"
export DOCVIZ_VIZ_SIDECAR_DIR="$SIDECAR_DIR"

cd /ex_disk2/mhpark/poc/docviz

echo "[restart_agent] killing any running agent.api.server..."
pgrep -f "uvicorn agent.api.server" | xargs -r kill
sleep 5
pgrep -f "uvicorn agent.api.server" >/dev/null && echo "  WARNING: still alive" || echo "  killed"

# Rotate log
[ -f "$LOG" ] && mv "$LOG" "${LOG}.cycle$(date +%s)"

echo "[restart_agent] launching with backbone=$BACKBONE  workers=$WORKERS"
echo "  QWEN_HOSTS=$QWEN_HOSTS"
echo "  QWEN3_MODEL_ID=$QWEN3_MODEL_ID"
echo "  DOCVIZ_VIZ_SIDECAR_DIR=$DOCVIZ_VIZ_SIDECAR_DIR"

nohup /opt/conda/bin/uvicorn agent.api.server:app \
  --host 0.0.0.0 --port "$PORT" --workers "$WORKERS" --log-level info \
  > "$LOG" 2>&1 &
PID=$!
disown
echo "[restart_agent] PID=$PID  log=$LOG"

# Wait for ready
echo -n "[restart_agent] waiting for /health"
for i in $(seq 1 30); do
  sleep 2
  r=$(curl -s -m 3 http://localhost:$PORT/health 2>/dev/null || true)
  if echo "$r" | grep -q "healthy"; then
    echo "  ready ($(echo "$r" | head -c 80))"
    exit 0
  fi
  echo -n "."
done
echo ""
echo "[restart_agent] FAIL: server did not become healthy in 60s; check $LOG"
tail -20 "$LOG"
exit 1
