#!/usr/bin/env bash
# D14 — Start a single vLLM server for a comparison model on a specified GPU.
# Usage: start_vllm_model.sh <model_path> <gpu_id> <port> [tp_size] [extra_args]
#
# Examples:
#   start_vllm_model.sh "$MODELS_ROOT/qwen3.5-9b" 10 8100 1
#   start_vllm_model.sh "$MODELS_ROOT/gpt-oss-20b" 11 8101 1
#
# Env: DOCVIZ_LOGS_DIR (default: <repo>/logs), VLLM_PYTHON (default:
# /ex_disk2/mhpark/poc/vllm_nightly_env/bin/python).
#
# Logs to $DOCVIZ_LOGS_DIR/vllm_$(basename model)_$port.log. PID file written
# to $DOCVIZ_LOGS_DIR/vllm_$(basename model)_$port.pid. Waits until /v1/models
# is reachable or exits non-zero after 10 minutes.

set -e
MODEL_PATH="$1"
GPU_ID="$2"
PORT="$3"
TP="${4:-1}"
shift 4 || true
EXTRA="$@"

if [ -z "$MODEL_PATH" ] || [ -z "$GPU_ID" ] || [ -z "$PORT" ]; then
  echo "usage: $0 <model_path> <gpu_id> <port> [tp_size] [extra args]"
  exit 2
fi

NAME=$(basename "$MODEL_PATH")
# Resolve repo root: this script lives at <repo>/pipeline/scripts/viz/.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCVIZ_ROOT="${DOCVIZ_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
LOGS_DIR="${DOCVIZ_LOGS_DIR:-$DOCVIZ_ROOT/logs}"
LOG="$LOGS_DIR/vllm_${NAME}_${PORT}.log"
PIDF="$LOGS_DIR/vllm_${NAME}_${PORT}.pid"
mkdir -p "$LOGS_DIR"

# Use the vLLM nightly env python that has vllm installed. The system
# `python` resolves to /opt/conda/bin/python which does NOT have vllm.
VLLM_PY="${VLLM_PYTHON:-/ex_disk2/mhpark/poc/vllm_nightly_env/bin/python}"
if [ ! -x "$VLLM_PY" ]; then
  echo "[start_vllm] FATAL: $VLLM_PY not found"
  exit 3
fi

if curl -s -m 2 http://localhost:${PORT}/v1/models >/dev/null 2>&1; then
  echo "[start_vllm] server already up on port $PORT"
  exit 0
fi

export CUDA_VISIBLE_DEVICES="$GPU_ID"
export VLLM_WORKER_MULTIPROC_METHOD=spawn
echo "[start_vllm] launching $NAME on GPU $GPU_ID port $PORT tp=$TP"

nohup "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_PATH" \
  --served-model-name "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --tensor-parallel-size "$TP" \
  --gpu-memory-utilization 0.82 \
  --max-model-len 32768 \
  --dtype auto \
  --trust-remote-code \
  $EXTRA \
  > "$LOG" 2>&1 &

PID=$!
echo $PID > "$PIDF"
echo "[start_vllm] pid=$PID log=$LOG"

# Health-check loop, up to 10 minutes
for i in $(seq 1 120); do
  sleep 5
  if curl -s -m 2 http://localhost:${PORT}/v1/models >/dev/null 2>&1; then
    echo "[start_vllm] ready on port $PORT after ${i}×5s"
    exit 0
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "[start_vllm] process died; tail log:"
    tail -40 "$LOG"
    exit 1
  fi
done

echo "[start_vllm] timeout; killing $PID"
kill "$PID" 2>/dev/null || true
tail -40 "$LOG"
exit 1
