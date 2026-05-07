#!/usr/bin/env bash
# Launch a Qwen vLLM server (text-only).
#
# Mirrors chartvr/scripts/launch_397b_vllm.sh as closely as possible.
# Differences are limited to what the GPU layout / model path forces:
#   - PORT, CUDA_DEVICES, MODEL, SERVED_NAME, MAX_MODEL_LEN are positional/env
#   - LOG_DIR defaults to <repo>/logs (chartvr uses /tmp/vllm_logs)
#   - PID file written so stop_qwen_vllm.sh can reliably terminate
#
# Usage:
#   ./scripts/viz/launch_qwen_vllm.sh <port> <cuda_devices> <model_path> [served_name] [max_model_len]
#
# Examples:
#   ./scripts/viz/launch_qwen_vllm.sh 9200 8,9,10,11 \
#       /ex_disk2/mhpark/poc/chartvr/models/qwen3.6-27b Qwen3.6-27B 4096

set -euo pipefail

PORT="${1:?PORT required (e.g. 9200)}"
CUDA_DEVICES="${2:?CUDA_VISIBLE_DEVICES required (comma-separated)}"
MODEL="${3:?MODEL path required}"
SERVED_NAME="${4:-$(basename "$MODEL")}"
MAX_MODEL_LEN="${5:-4096}"

GPU_UTIL="${GPU_UTIL:-0.90}"
PY="${PY:-/ex_disk2/mhpark/poc/vllm_nightly_env/bin/python}"

# TP = number of CUDA devices
TP=$(echo "$CUDA_DEVICES" | awk -F',' '{print NF}')

# Resolve repo root (this script lives at scripts/viz/)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOG_DIR="${LOG_DIR:-$ROOT/logs}"
mkdir -p "$LOG_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
LOG="$LOG_DIR/vllm_${SERVED_NAME//\//_}_${PORT}_${TS}.log"
PIDFILE="$LOG_DIR/vllm_${SERVED_NAME//\//_}_${PORT}.pid"

# Pre-clean: if anything is bound to the port, refuse (safer than auto-kill)
if lsof -i ":${PORT}" -sTCP:LISTEN -t > /dev/null 2>&1; then
    echo "[launch] ERROR: port ${PORT} already in use." >&2
    lsof -i ":${PORT}" >&2 || true
    exit 1
fi

echo "[launch] port=$PORT gpus=$CUDA_DEVICES TP=$TP max_len=$MAX_MODEL_LEN"
echo "[launch] model=$MODEL"
echo "[launch] served_name=$SERVED_NAME"
echo "[launch] log=$LOG"
echo "[launch] pid file=$PIDFILE"

# Daemonise with setsid + nohup + </dev/null + disown so the server
# survives parent shell exit / claude-code session compaction.
CUDA_VISIBLE_DEVICES="$CUDA_DEVICES" setsid nohup "$PY" -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --served-model-name "$SERVED_NAME" \
    --tensor-parallel-size "$TP" \
    --gpu-memory-utilization "$GPU_UTIL" \
    --max-model-len "$MAX_MODEL_LEN" \
    --port "$PORT" \
    --trust-remote-code \
    --enforce-eager \
    --reasoning-parser qwen3 \
    --generation-config vllm \
    </dev/null > "$LOG" 2>&1 &
LAUNCHED_PID=$!
disown
echo "$LAUNCHED_PID" > "$PIDFILE"

echo "[launch] started. PID=$LAUNCHED_PID (saved to $PIDFILE)"
echo "[launch] health check: curl -s http://localhost:$PORT/v1/models | jq"
echo "[launch] tail log:     tail -f $LOG"
