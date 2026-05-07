#!/usr/bin/env bash
# Preflight a vLLM endpoint: /v1/models reachable + small chat completion works.
#
# Usage:
#   ./scripts/viz/preflight_vllm.sh <url> [<url> ...]
#   ./scripts/viz/preflight_vllm.sh http://localhost:9200/v1 http://localhost:9201/v1
#
# Exits non-zero if ANY url fails.

set -uo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <url> [<url> ...]" >&2
    exit 1
fi

check_url() {
    local URL="$1"
    echo "[preflight] $URL"

    # 1) /v1/models
    local body
    body="$(curl -sf -m 10 "${URL%/}/models" || true)"
    if [ -z "$body" ]; then
        echo "  FAIL: ${URL%/}/models unreachable"
        return 1
    fi
    local model_id
    model_id="$(echo "$body" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["data"][0]["id"])' 2>/dev/null || true)"
    if [ -z "$model_id" ]; then
        echo "  FAIL: /models response missing data[0].id"
        echo "  body: ${body:0:200}"
        return 1
    fi
    echo "  models OK: $model_id"

    # 2) 5-token chat completion
    local resp
    resp="$(curl -sf -m 30 -X POST "${URL%/}/chat/completions" \
        -H 'Content-Type: application/json' \
        -d "$(python3 -c "
import json
print(json.dumps({
    'model': '$model_id',
    'messages': [{'role':'user','content':'Reply with the single word: OK'}],
    'max_tokens': 5,
    'temperature': 0
}))
")" || true)"
    if [ -z "$resp" ]; then
        echo "  FAIL: chat/completions returned empty"
        return 1
    fi
    local content
    content="$(echo "$resp" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["choices"][0]["message"]["content"])' 2>/dev/null || true)"
    if [ -z "$content" ]; then
        echo "  FAIL: chat response missing content"
        echo "  body: ${resp:0:200}"
        return 1
    fi
    echo "  chat OK: ${content:0:60}"
    return 0
}

rc=0
for u in "$@"; do
    check_url "$u" || rc=1
done

if [ $rc -eq 0 ]; then
    echo "[preflight] ALL PASS"
else
    echo "[preflight] FAIL"
fi
exit $rc
