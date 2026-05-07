#!/usr/bin/env bash
# D14 watchdog — polls nvidia-smi until an allowed GPU has ≥15 GB free,
# then runs the three comparison models sequentially (start server, infer,
# stop server). Intended to run unattended overnight.
#
# Logs:
#   logs/d14_watchdog.log   — this script's own output
#   logs/vllm_{model}_{port}.log — per-server logs
#   logs/d14_{model}.log    — per-model inference progress
set -u
cd /ex_disk2/mhpark/poc/visubench

LOG=logs/d14_watchdog.log
mkdir -p logs
echo "[$(date)] d14_watchdog started" >> "$LOG"

CHARTVR_MODELS=/ex_disk2/mhpark/poc/chartvr/models
# (model_id, checkpoint_dir, gpu_id, port, tp)
MODELS=(
  "qwen9b ${CHARTVR_MODELS}/qwen3.5-9b 10 8100 1"
  "gpt_oss_20b ${CHARTVR_MODELS}/gpt-oss-20b 11 8101 1"
  "gemma3_4b ${CHARTVR_MODELS}/gemma3-4b-it 12 8102 1"
)

wait_for_gpu() {
  local gpu="$1"
  while true; do
    local free=$(nvidia-smi --id="$gpu" --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1)
    if [ -z "$free" ]; then free=0; fi
    if [ "$free" -ge 15000 ]; then
      echo "[$(date)] GPU $gpu has ${free} MiB free — proceeding" >> "$LOG"
      return 0
    fi
    echo "[$(date)] GPU $gpu only ${free} MiB free, sleeping 600s" >> "$LOG"
    sleep 600
  done
}

run_one_model() {
  local spec="$1"
  read -r MID MPATH GPU PORT TP <<< "$spec"
  echo "[$(date)] === D14 model $MID on GPU $GPU port $PORT ===" >> "$LOG"

  wait_for_gpu "$GPU"

  bash scripts/viz/start_vllm_model.sh "$MPATH" "$GPU" "$PORT" "$TP" >> "$LOG" 2>&1
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "[$(date)] start_vllm_model failed for $MID (rc=$rc); will retry this model" >> "$LOG"
    return 1
  fi

  echo "[$(date)] running inference for $MID" >> "$LOG"
  python -u -m scripts.viz.model_inference --model "$MID" --workers 6 \
    > logs/d14_${MID}.log 2>&1
  rc=$?
  echo "[$(date)] inference for $MID returned rc=$rc" >> "$LOG"

  local PIDF=$(ls logs/vllm_*_${PORT}.pid 2>/dev/null | head -1)
  if [ -n "$PIDF" ] && [ -f "$PIDF" ]; then
    local PID=$(cat "$PIDF")
    echo "[$(date)] stopping server pid=$PID" >> "$LOG"
    kill "$PID" 2>/dev/null || true
    sleep 3
    kill -9 "$PID" 2>/dev/null || true
    rm -f "$PIDF"
  fi

  return $rc
}

# Per-model retry loop: any transient start failure (bad env, GPU
# reclaimed, etc.) sleeps 600s and tries again. Only a clean rc=0 from
# inference marks the model as done.
for spec in "${MODELS[@]}"; do
  attempt=1
  while true; do
    if run_one_model "$spec"; then
      break
    fi
    echo "[$(date)] model attempt $attempt failed; retry in 600s" >> "$LOG"
    attempt=$((attempt + 1))
    if [ "$attempt" -gt 6 ]; then
      echo "[$(date)] model exhausted 6 attempts; moving on" >> "$LOG"
      break
    fi
    sleep 600
  done
done

echo "[$(date)] d14_watchdog finished" >> "$LOG"

# After D14 finishes, kick off downstream.
echo "[$(date)] extracting structures for model_outputs" >> "$LOG"
python -m scripts.viz.batch_extract_structures >> "$LOG" 2>&1

echo "[$(date)] running step4 structural metrics (D15)" >> "$LOG"
python -m scripts.step4_structural_metrics >> "$LOG" 2>&1

echo "[$(date)] running step5 VLM judge (D16)" >> "$LOG"
python -m scripts.step5_vlm_judge --all --parallel 8 >> "$LOG" 2>&1 || \
  python -m scripts.step5_vlm_judge --all >> "$LOG" 2>&1

echo "[$(date)] running step6 aggregate (D17)" >> "$LOG"
python -m scripts.step6_aggregate >> "$LOG" 2>&1

echo "[$(date)] d14 → d17 watchdog chain complete" >> "$LOG"
