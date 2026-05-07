#!/usr/bin/env bash
# D14 post-inference chain — waits for all 3 model_inference processes,
# stops the vLLM servers, then runs D15 (step4) → D16 (step5) → D17 (step6).
# Launched after the parallel D14 kickoff on 2026-04-09.
#
# NOTE (docviz): step4/5/6_*.py were NOT imported into docviz (eval-side, out
# of scope for the generation pipeline). This script is left as a reference
# template; rewire to docviz's eval pipeline before reusing.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DOCVIZ_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
LOG="${DOCVIZ_LOGS_DIR:-logs}/d14_chain.log"
mkdir -p "${DOCVIZ_LOGS_DIR:-logs}"
echo "[$(date)] d14_chain started" >> "$LOG"

# Wait for all 3 inference procs to exit (poll their pid files would be
# cleaner; for now poll by name).
while true; do
  running=$(ps -ef | grep "model_inference" | grep -v grep | wc -l)
  if [ "$running" -eq 0 ]; then
    echo "[$(date)] all model_inference procs finished" >> "$LOG"
    break
  fi
  echo "[$(date)] $running model_inference still running" >> "$LOG"
  sleep 300
done

# Stop vLLM servers (GPU 0/1/2).
for port in 8100 8101 8102; do
  pidf=$(ls logs/vllm_*_${port}.pid 2>/dev/null | head -1)
  if [ -n "$pidf" ] && [ -f "$pidf" ]; then
    pid=$(cat "$pidf")
    echo "[$(date)] stopping vllm pid=$pid (port $port)" >> "$LOG"
    kill "$pid" 2>/dev/null || true
    sleep 3
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$pidf"
  fi
done

# Extract structures for model_outputs
echo "[$(date)] batch_extract_structures" >> "$LOG"
python -m scripts.viz.batch_extract_structures >> "$LOG" 2>&1

# D15
echo "[$(date)] running step4 structural metrics (D15)" >> "$LOG"
python -m scripts.step4_structural_metrics >> "$LOG" 2>&1

# D16
echo "[$(date)] running step5 VLM judge (D16)" >> "$LOG"
python -m scripts.step5_vlm_judge --all --parallel 8 >> "$LOG" 2>&1 || \
  python -m scripts.step5_vlm_judge --all >> "$LOG" 2>&1

# D17
echo "[$(date)] running step6 aggregate (D17)" >> "$LOG"
python -m scripts.step6_aggregate >> "$LOG" 2>&1

echo "[$(date)] d14_chain complete" >> "$LOG"
