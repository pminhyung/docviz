#!/usr/bin/env bash
# Stop one or more Qwen vLLM servers launched by launch_qwen_vllm.sh.
#
# Usage:
#   ./scripts/viz/stop_qwen_vllm.sh <port> [<port> ...]
#
# Strategy:
# 1. If logs/vllm_*_${port}.pid exists, kill that PID (and its process group).
# 2. Fallback: lsof -ti :PORT | xargs kill.
# 3. Wait briefly, force kill (-9) if needed.
# 4. Verify: lsof -i :PORT must return nothing.

set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <port> [<port> ...]" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOG_DIR="$ROOT/logs"

stop_port() {
    local PORT="$1"
    echo "[stop] port=$PORT"

    # 1) Try every PID file matching this port
    local matched=0
    for pidfile in "$LOG_DIR"/vllm_*_"${PORT}".pid; do
        [ -f "$pidfile" ] || continue
        local pid
        pid="$(cat "$pidfile" 2>/dev/null || true)"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "  killing PID $pid (from $pidfile)"
            # Kill the process group (setsid → pgid == pid)
            kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
            matched=1
        fi
        rm -f "$pidfile"
    done

    # 2) Fallback: any listener on PORT
    local lsof_pids
    lsof_pids=$(lsof -ti ":${PORT}" -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "$lsof_pids" ]; then
        echo "  killing lsof listeners: $lsof_pids"
        echo "$lsof_pids" | xargs -r kill -TERM 2>/dev/null || true
        matched=1
    fi

    # 3) Wait, then escalate
    sleep 4
    lsof_pids=$(lsof -ti ":${PORT}" -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "$lsof_pids" ]; then
        echo "  still up; SIGKILL: $lsof_pids"
        echo "$lsof_pids" | xargs -r kill -9 2>/dev/null || true
        sleep 2
    fi

    # 4) Verify
    if lsof -i ":${PORT}" -sTCP:LISTEN -t > /dev/null 2>&1; then
        echo "[stop] FAIL: port $PORT still bound" >&2
        return 1
    fi
    if [ "$matched" -eq 0 ]; then
        echo "[stop] (nothing was running on $PORT)"
    else
        echo "[stop] OK: port $PORT free"
    fi
    return 0
}

rc=0
for p in "$@"; do
    stop_port "$p" || rc=1
done

echo
echo "=== nvidia-smi (GPU 8-15 should drop to ~0 MiB) ==="
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader \
    | awk -F',' '$1+0 >= 8 && $1+0 <= 15' || true

exit $rc
