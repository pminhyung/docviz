#!/bin/bash
#
# Document Agent V2 - One Command Demo
#
# This script runs the complete Document Agent V2 pipeline in SANDBOX MODE
# without requiring any external API keys.
#
# What it does:
#   1. Starts the API server in background (sandbox mode)
#   2. Checks /health endpoint
#   3. Runs a query via /v2/run
#   4. Saves response to demo_response.json
#   5. Validates the trace via /v2/validate
#   6. Exports training JSONL
#   7. Prints PASS/FAIL summary
#
# Usage:
#   cd examples
#   ./demo_one_command.sh
#
# Requirements:
#   - Python 3.8+
#   - pip install fastapi uvicorn pydantic requests
#   - jq (optional, for pretty printing)

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
DOC_AGENT_DIR="$(dirname "$SCRIPT_DIR")"
PORT="${DEMO_PORT:-8765}"
BASE_URL="http://localhost:${PORT}"
DEMO_DOC="${SCRIPT_DIR}/demo_document.json"
OUTPUT_DIR="${SCRIPT_DIR}/demo_output"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Output files
RESPONSE_FILE="${OUTPUT_DIR}/demo_response.json"
TRACE_FILE="${OUTPUT_DIR}/demo_trace.json"
TRAIN_FILE="${OUTPUT_DIR}/demo_train.jsonl"
VALIDATION_FILE="${OUTPUT_DIR}/demo_validation.json"
SERVER_LOG="${OUTPUT_DIR}/server.log"

# Track test results
TESTS_PASSED=0
TESTS_FAILED=0

print_header() {
    echo ""
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_step() {
    echo -e "${YELLOW}>>> $1${NC}"
}

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

cleanup() {
    print_step "Cleaning up..."
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        print_info "Server stopped (PID: $SERVER_PID)"
    fi
}

trap cleanup EXIT

# ===========================================================================
# Start Demo
# ===========================================================================

print_header "Document Agent V2 - One Command Demo (SANDBOX MODE)"

echo ""
echo "This demo runs the COMPLETE pipeline WITHOUT external API keys."
echo "All LLM responses are deterministic stubs for reproducible testing."
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Check for required commands
print_step "Checking requirements..."

if ! command -v python &> /dev/null; then
    print_fail "Python not found. Please install Python 3.8+"
    exit 1
fi
print_pass "Python found: $(python --version)"

python -c "import fastapi, uvicorn, pydantic, requests" 2>/dev/null || {
    print_info "Installing required packages..."
    pip install fastapi uvicorn pydantic requests -q
}
print_pass "Required Python packages available"

# Check demo document exists
if [ ! -f "$DEMO_DOC" ]; then
    print_fail "Demo document not found: $DEMO_DOC"
    exit 1
fi
print_pass "Demo document found: $DEMO_DOC"

# ===========================================================================
# Step 1: Start Server in Sandbox Mode
# ===========================================================================

print_header "Step 1: Starting API Server (Sandbox Mode)"

# Set sandbox mode
export DOC_AGENT_V2_SANDBOX=1
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"

print_info "DOC_AGENT_V2_SANDBOX=1"
print_info "Starting uvicorn on port $PORT..."

# Start server in background
cd "$PROJECT_ROOT"
python -m uvicorn agent.api.server:app \
    --host 127.0.0.1 \
    --port "$PORT" \
    --log-level warning \
    > "$SERVER_LOG" 2>&1 &

SERVER_PID=$!
print_info "Server PID: $SERVER_PID"

# Wait for server to start
print_step "Waiting for server to be ready..."
MAX_WAIT=30
WAIT_COUNT=0
while ! curl -s "$BASE_URL/health" > /dev/null 2>&1; do
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
    if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
        print_fail "Server failed to start within ${MAX_WAIT}s"
        cat "$SERVER_LOG"
        exit 1
    fi
done

print_pass "Server started successfully"

# ===========================================================================
# Step 2: Health Check
# ===========================================================================

print_header "Step 2: Health Check"

HEALTH_RESPONSE=$(curl -s "$BASE_URL/health")
echo "$HEALTH_RESPONSE" | python -m json.tool 2>/dev/null || echo "$HEALTH_RESPONSE"

# Verify sandbox mode is enabled
if echo "$HEALTH_RESPONSE" | grep -q '"sandbox_mode":true\|"sandbox_mode": true'; then
    print_pass "Sandbox mode confirmed"
else
    print_fail "Sandbox mode not enabled in health response"
fi

if echo "$HEALTH_RESPONSE" | grep -q '"status":"healthy"\|"status": "healthy"'; then
    print_pass "Health check passed"
else
    print_fail "Health check failed"
fi

# ===========================================================================
# Step 3: Run Agent Query
# ===========================================================================

print_header "Step 3: Running Agent Query"

USER_QUERY="What are the main features of the Document Agent system?"

print_info "Document: $DEMO_DOC"
print_info "Query: $USER_QUERY"
print_step "Sending request to /v2/run..."

RUN_RESPONSE=$(curl -s -X POST "$BASE_URL/v2/run" \
    -H "Content-Type: application/json" \
    -d "{
        \"doc_json_path\": \"$DEMO_DOC\",
        \"user_query\": \"$USER_QUERY\",
        \"lang\": \"ENGLISH\",
        \"n_steps_max\": 10,
        \"return_trace\": true,
        \"return_train_sample\": true
    }")

# Save response
echo "$RUN_RESPONSE" > "$RESPONSE_FILE"
print_info "Response saved to: $RESPONSE_FILE"

# Extract and display final answer
FINAL_ANSWER=$(echo "$RUN_RESPONSE" | python -c "import sys, json; data=json.load(sys.stdin); print(data.get('final_answer', 'NO ANSWER'))" 2>/dev/null || echo "PARSE_ERROR")

echo ""
echo -e "${GREEN}--- Final Answer ---${NC}"
echo "$FINAL_ANSWER" | head -20
echo ""

# Check for success
if echo "$RUN_RESPONSE" | grep -q '"success":true\|"success": true'; then
    print_pass "Agent run completed successfully"
else
    print_fail "Agent run failed"
    echo "Full response:"
    echo "$RUN_RESPONSE" | python -m json.tool 2>/dev/null || echo "$RUN_RESPONSE"
fi

# Check for final answer
if [ "$FINAL_ANSWER" != "NO ANSWER" ] && [ "$FINAL_ANSWER" != "PARSE_ERROR" ]; then
    print_pass "Final answer generated"
else
    print_fail "No final answer in response"
fi

# Extract and save trace
print_step "Extracting trace..."
echo "$RUN_RESPONSE" | python -c "
import sys, json
data = json.load(sys.stdin)
trace = data.get('trace', {})
print(json.dumps(trace, indent=2, ensure_ascii=False))
" > "$TRACE_FILE" 2>/dev/null

if [ -s "$TRACE_FILE" ]; then
    print_pass "Trace saved to: $TRACE_FILE"
else
    print_fail "Failed to extract trace"
fi

# Extract and save train_sample
print_step "Extracting train_sample..."
echo "$RUN_RESPONSE" | python -c "
import sys, json
data = json.load(sys.stdin)
sample = data.get('train_sample', {})
# Write as JSONL (one line)
print(json.dumps(sample, ensure_ascii=False))
" > "$TRAIN_FILE" 2>/dev/null

if [ -s "$TRAIN_FILE" ]; then
    print_pass "Training JSONL saved to: $TRAIN_FILE"

    # Verify train_sample has required fields
    REQUIRED_FIELDS=("df_idx" "user_query" "filenames" "reasoning" "readfulldocument" "readfulltext" "doc_step")
    MISSING_FIELDS=""
    for field in "${REQUIRED_FIELDS[@]}"; do
        if ! grep -q "\"$field\"" "$TRAIN_FILE"; then
            MISSING_FIELDS="$MISSING_FIELDS $field"
        fi
    done

    if [ -z "$MISSING_FIELDS" ]; then
        print_pass "train_sample has all required fields"
    else
        print_fail "train_sample missing fields:$MISSING_FIELDS"
    fi
else
    print_fail "Failed to extract train_sample"
fi

# ===========================================================================
# Step 4: Validate Trace
# ===========================================================================

print_header "Step 4: Validating Trace"

# Read trace and validate
TRACE_CONTENT=$(cat "$TRACE_FILE")

VALIDATION_RESPONSE=$(curl -s -X POST "$BASE_URL/v2/validate" \
    -H "Content-Type: application/json" \
    -d "{
        \"trace\": $TRACE_CONTENT,
        \"language\": \"ENGLISH\",
        \"has_documents\": true
    }")

# Save validation response
echo "$VALIDATION_RESPONSE" > "$VALIDATION_FILE"
echo "$VALIDATION_RESPONSE" | python -m json.tool 2>/dev/null || echo "$VALIDATION_RESPONSE"

print_info "Validation saved to: $VALIDATION_FILE"

# Check validation result
if echo "$VALIDATION_RESPONSE" | grep -q '"ok":true\|"ok": true'; then
    print_pass "Trace validation passed"
else
    print_fail "Trace validation failed"
fi

# Extract stats
STEPS_COUNT=$(echo "$VALIDATION_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin).get('stats', {}).get('steps_count', 0))" 2>/dev/null || echo "0")
TOOL_COUNT=$(echo "$VALIDATION_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin).get('stats', {}).get('tool_invoke_count', 0))" 2>/dev/null || echo "0")
CITATION_COUNT=$(echo "$VALIDATION_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin).get('stats', {}).get('citation_count', 0))" 2>/dev/null || echo "0")

print_info "Stats: steps=$STEPS_COUNT, tools=$TOOL_COUNT, citations=$CITATION_COUNT"

if [ "$STEPS_COUNT" -gt 0 ]; then
    print_pass "Trace has $STEPS_COUNT steps"
else
    print_fail "Trace has no steps"
fi

# ===========================================================================
# Step 5: Verify Outputs
# ===========================================================================

print_header "Step 5: Verifying Output Files"

# Check all output files exist and are non-empty
OUTPUT_FILES=(
    "$RESPONSE_FILE:demo_response.json"
    "$TRACE_FILE:demo_trace.json"
    "$TRAIN_FILE:demo_train.jsonl"
    "$VALIDATION_FILE:demo_validation.json"
)

for file_spec in "${OUTPUT_FILES[@]}"; do
    file_path="${file_spec%%:*}"
    file_name="${file_spec##*:}"

    if [ -s "$file_path" ]; then
        size=$(wc -c < "$file_path" | tr -d ' ')
        print_pass "$file_name exists (${size} bytes)"
    else
        print_fail "$file_name is missing or empty"
    fi
done

# ===========================================================================
# Final Summary
# ===========================================================================

print_header "Demo Summary"

echo ""
echo "Output files created in: $OUTPUT_DIR"
echo ""
ls -la "$OUTPUT_DIR"
echo ""

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))

if [ $TESTS_FAILED -eq 0 ]; then
    echo ""
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}  DEMO PASSED: All $TOTAL_TESTS tests passed!${NC}"
    echo -e "${GREEN}============================================================${NC}"
    echo ""
    echo "The full Document Agent V2 pipeline ran successfully in sandbox mode:"
    echo "  - API server started without API keys"
    echo "  - Health check confirmed sandbox mode"
    echo "  - Agent processed query with tool invocations"
    echo "  - Final answer generated with citations"
    echo "  - Trace exported and validated"
    echo "  - Training JSONL exported with all required fields"
    echo ""
    exit 0
else
    echo ""
    echo -e "${RED}============================================================${NC}"
    echo -e "${RED}  DEMO FAILED: $TESTS_FAILED of $TOTAL_TESTS tests failed${NC}"
    echo -e "${RED}============================================================${NC}"
    echo ""
    echo "Check the output files and server log for details:"
    echo "  Server log: $SERVER_LOG"
    echo ""
    exit 1
fi
