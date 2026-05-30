#!/usr/bin/env bash
# Launch local multi-host vLLM for gemma3 (OpenAI-compatible API).
#
# Backbone-swap usage (cross-backbone SOTA verification): once these servers
# are up, set GEMMA3_HOSTS env to point at them and run our normal pipelines.
# For direct-call baselines (S1, S7) use:
#   GEMMA3_HOSTS="localhost:9401,localhost:9402" \
#     python -m code.scripts.run_backbone_baselines --backbone gemma3 ...
# For agent-server-backed B6, restart the agent server with:
#   QWEN_HOSTS="localhost:9401,localhost:9402" \
#   QWEN3_MODEL_ID="gemma-3-27b-it" \
#   DOCVIZ_VLLM_MODEL="gemma-3-27b-it" \
#     uvicorn agent.api.server:app --host 0.0.0.0 --port 9037 --workers N
#
# Model variants:
#   - VARIANT=27b (default, ~50GB fp16, needs 2+ GPUs via tensor-parallel)
#   - VARIANT=4b  (~8GB, fits on a single GPU with room)
#
# Usage:
#   bash scripts/launch_gemma3.sh             # default: 1 host on port 9401, 27b
#   N_HOSTS=2 VARIANT=27b bash scripts/launch_gemma3.sh
#   N_HOSTS=4 VARIANT=4b GPU_LIST="2,3,4,5" bash scripts/launch_gemma3.sh
#
# Cleanup:
#   bash scripts/launch_gemma3.sh stop

set -uo pipefail

REPO="/ex_disk2/mhpark/poc/docviz"
LOG_DIR="/tmp/gemma3_logs"
PID_DIR="/tmp/gemma3_pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

VARIANT="${VARIANT:-27b}"
MODEL_BASE="/ex_disk2/mhpark/poc/chartvr/models"
case "$VARIANT" in
  27b)    MODEL_PATH="$MODEL_BASE/gemma3-27b-it";   MODEL_ID="gemma-3-27b-it";   TP=${TP:-2} ;;
  4b)     MODEL_PATH="$MODEL_BASE/gemma3-4b-it";    MODEL_ID="gemma-3-4b-it";    TP=${TP:-1} ;;
  4-31b)  MODEL_PATH="$MODEL_BASE/gemma-4-31B-it";  MODEL_ID="gemma-4-31b-it";   TP=${TP:-4}
          # Gemma4 requires vllm>=0.19 with transformers>=5.9 (model_type=gemma4).
          # gemma4_vllm_env has vllm 0.19 + torch 2.10+cu128 + transformers 5.9
          # (works on driver 535.x via CUDA 12.8 forward-compat).
          VLLM_BIN="${VLLM_BIN:-/ex_disk2/mhpark/poc/gemma4_vllm_env/bin/vllm}"
          ;;
  *) echo "Unknown VARIANT=$VARIANT (expect 27b | 4b | 4-31b)"; exit 1 ;;
esac

# Default vllm binary: nightly env (works for gemma3). Gemma4 overrides above.
VLLM_BIN="${VLLM_BIN:-/opt/conda/bin/vllm}"
[ -x "$VLLM_BIN" ] || VLLM_BIN="/ex_disk2/mhpark/poc/vllm_nightly_env/bin/vllm"

N_HOSTS="${N_HOSTS:-1}"
PORT_START="${PORT_START:-9401}"
GPU_LIST="${GPU_LIST:-}"  # e.g., "0,1,2,3" — N_HOSTS * TP gpus needed; if empty auto-pick from free
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.85}"

# ── stop ────────────────────────────────────────────────────────────────────
if [ "${1:-}" = "stop" ]; then
  echo "[gemma3] stopping all gemma3 vllm hosts"
  for pidfile in "$PID_DIR"/gemma3_*.pid; do
    [ -f "$pidfile" ] || continue
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" && echo "  killed PID=$pid ($(basename "$pidfile" .pid))"
    fi
    rm -f "$pidfile"
  done
  exit 0
fi

# ── start ───────────────────────────────────────────────────────────────────
[ -d "$MODEL_PATH" ] || { echo "model path missing: $MODEL_PATH"; exit 1; }
[ -x "$VLLM_BIN" ] || { echo "vllm binary missing: $VLLM_BIN"; exit 1; }

# Auto-pick free GPUs if GPU_LIST not given
if [ -z "$GPU_LIST" ]; then
  REQUIRED_GPUS=$(( N_HOSTS * TP ))
  GPU_LIST=$(nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits \
             | sort -t, -k2 -nr | head -n "$REQUIRED_GPUS" | awk -F, '{print $1}' | paste -sd ,)
  echo "[gemma3] auto-picked GPUs: $GPU_LIST"
fi

IFS=',' read -ra GPU_ARR <<< "$GPU_LIST"
[ ${#GPU_ARR[@]} -ge $((N_HOSTS * TP)) ] || { echo "need $((N_HOSTS*TP)) GPUs, got ${#GPU_ARR[@]}"; exit 1; }

HOSTS=""
for ((i=0; i<N_HOSTS; i++)); do
  port=$((PORT_START + i))
  gpu_slice=""
  for ((j=0; j<TP; j++)); do
    idx=$((i * TP + j))
    [ -n "$gpu_slice" ] && gpu_slice="$gpu_slice,"
    gpu_slice="$gpu_slice${GPU_ARR[$idx]}"
  done

  log="$LOG_DIR/host_${port}.log"
  pidf="$PID_DIR/gemma3_${port}.pid"
  echo "[gemma3] launching host port=$port gpus=$gpu_slice TP=$TP"
  # Gemma4 is multimodal — needs larger max-num-batched-tokens (default 2048
  # is below per-MM-item budget). Gemma3 + others fine at default.
  EXTRA_FLAGS=""
  if [[ "$VARIANT" == 4-* ]]; then
    EXTRA_FLAGS="--max-num-batched-tokens 8192"
  fi
  CUDA_VISIBLE_DEVICES="$gpu_slice" nohup "$VLLM_BIN" serve "$MODEL_PATH" \
    --served-model-name "$MODEL_ID" \
    --port "$port" \
    --host 0.0.0.0 \
    --tensor-parallel-size "$TP" \
    --gpu-memory-utilization "$GPU_MEM_UTIL" \
    --max-model-len "$MAX_MODEL_LEN" \
    --dtype bfloat16 \
    $EXTRA_FLAGS \
    > "$log" 2>&1 &
  pid=$!
  echo "$pid" > "$pidf"
  disown $pid 2>/dev/null
  echo "  PID=$pid  log=$log"
  HOSTS="${HOSTS:+$HOSTS,}localhost:$port"
done

echo ""
echo "[gemma3] N_HOSTS=$N_HOSTS variant=$VARIANT model_id=$MODEL_ID"
echo "[gemma3] hosts: $HOSTS"
echo "[gemma3] wait ~60s for vLLM startup, then check health:"
echo "  for p in \$(seq $PORT_START $((PORT_START+N_HOSTS-1))); do curl -s http://localhost:\$p/v1/models | head -c 200; echo; done"
echo ""
echo "[gemma3] use in pipelines:"
echo "  export GEMMA3_HOSTS=\"$HOSTS\""
echo "  export GEMMA3_MODEL=\"$MODEL_ID\""
