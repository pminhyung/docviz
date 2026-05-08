#!/bin/bash
#
# agent API Server Startup Script
#
# Usage:
#   ./agent/run_server.sh [--port PORT] [--host HOST] [--workers N]
#
# Examples:
#   ./agent/run_server.sh                    # Default: 0.0.0.0:9024
#   ./agent/run_server.sh --port 8080        # Custom port
#   ./agent/run_server.sh --workers 4        # Multiple workers
#
export NOVITA_API_KEY="sk_QraO23nzwfMM_gIC7y-3o-aByS4iORJrObdlrGxyrcQ"
set -e

# Default values
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-9024}"
WORKERS="${WORKERS:-1}"
LOG_LEVEL="${LOG_LEVEL:-info}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        --workers|-w)
            WORKERS="$2"
            shift 2
            ;;
        --log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --host HOST       Bind host (default: 0.0.0.0)"
            echo "  --port, -p PORT   Bind port (default: 9024)"
            echo "  --workers, -w N   Number of workers (default: 1)"
            echo "  --log-level LEVEL Log level (default: info)"
            echo "  --help, -h        Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Change to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "============================================================"
echo "agent API Server"
echo "============================================================"
echo "Host: $HOST"
echo "Port: $PORT"
echo "Workers: $WORKERS"
echo "Log Level: $LOG_LEVEL"
echo "Project Root: $PROJECT_ROOT"
echo "============================================================"

# Run uvicorn
exec uvicorn agent.api.server:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL"
