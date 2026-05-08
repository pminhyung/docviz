#!/bin/bash
#
# Curl Client Examples for Document Agent V2 API
#
# This script demonstrates how to use the Document Agent V2 API with curl.
#
# Prerequisites:
#   1. API server running (see run_server.sh, default port 9024)
#   2. curl and jq installed
#
# Usage:
#   ./client_curl.sh
#   or source individual commands

set -e

# Configuration
BASE_URL="${API_BASE_URL:-http://10.4.43.13:9024}"
DOC_PATH="${DOC_PATH:-/path/to/your/document.json}"
USER_QUERY="${USER_QUERY:-What is the main topic of this document?}"

echo "==================================="
echo "Document Agent V2 API - Curl Examples"
echo "==================================="
echo "Base URL: $BASE_URL"
echo ""

# ============================================================================
# 1. Health Check
# ============================================================================

echo "1. Health Check"
echo "---------------"
echo ""
echo "Request:"
echo "  curl -s ${BASE_URL}/health"
echo ""

if command -v jq &> /dev/null; then
    curl -s "${BASE_URL}/health" | jq .
else
    curl -s "${BASE_URL}/health"
fi

echo ""
echo ""

# ============================================================================
# 2. Run Agent - Basic Request
# ============================================================================

echo "2. Run Agent - Basic Request"
echo "----------------------------"
echo ""
echo "Request:"
cat << 'EOF'
curl -X POST "${BASE_URL}/v2/run" \
  -H "Content-Type: application/json" \
  -d '{
    "doc_json_path": "/path/to/document.json",
    "user_query": "Summarize this document",
    "reasoner_api_key": "your-openai-api-key-here",
    "lang": "ENGLISH"
  }'
EOF
echo ""
echo ""

# Example with actual execution (commented out - uncomment to run)
# curl -s -X POST "${BASE_URL}/v2/run" \
#   -H "Content-Type: application/json" \
#   -d "{
#     \"doc_json_path\": \"${DOC_PATH}\",
#     \"user_query\": \"${USER_QUERY}\",
#     \"lang\": \"ENGLISH\"
#   }" | jq .

# ============================================================================
# 3. Run Agent - Full Request with All Options
# ============================================================================

echo "3. Run Agent - Full Request with Options"
echo "-----------------------------------------"
echo ""
echo "Request:"
cat << 'EOF'
curl -X POST "${BASE_URL}/v2/run" \
  -H "Content-Type: application/json" \
  -d '{
    "doc_json_path": "/path/to/document.json",
    "doc_json_path_2": "/path/to/second_document.json",
    "single_doc": false,
    "lang": "KOREAN",
    "user_query": "두 문서의 주요 차이점은 무엇인가요?",
    "override_patch_path": "/path/to/override.yaml",
    "model_config_path": "/path/to/model_config.yaml",
    "n_steps_max": 30,
    "export_training_jsonl": false,
    "return_trace": true,
    "return_train_sample": true
  }'
EOF
echo ""
echo ""

# ============================================================================
# 4. Validate Trace
# ============================================================================

echo "4. Validate Trace"
echo "-----------------"
echo ""
echo "Request:"
cat << 'EOF'
curl -X POST "${BASE_URL}/v2/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "trace": {
      "session_id": "abc-123",
      "steps": [
        {
          "step_number": 1,
          "step_type": "tool_invoke",
          "action": "ReadFullDocument",
          "action_args": {"document_number": 1}
        },
        {
          "step_number": 2,
          "step_type": "final_answer",
          "final_answer": "The document discusses..."
        }
      ],
      "success": true
    },
    "language": "ENGLISH",
    "has_documents": true
  }'
EOF
echo ""

# Example execution
if command -v jq &> /dev/null; then
    curl -s -X POST "${BASE_URL}/v2/validate" \
      -H "Content-Type: application/json" \
      -d '{
        "trace": {
          "session_id": "test",
          "steps": [
            {"step_number": 1, "step_type": "final_answer", "final_answer": "Test answer"}
          ],
          "success": true
        },
        "language": "ENGLISH",
        "has_documents": true
      }' | jq .
fi
echo ""
echo ""

# ============================================================================
# 5. Validate Raw Output
# ============================================================================

echo "5. Validate Raw Output"
echo "----------------------"
echo ""
echo "Request:"
cat << 'EOF'
curl -X POST "${BASE_URL}/v2/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_output": "<observation>I see the document content.</observation>\n<reasoning>I need to summarize.</reasoning>\n<step_name>Generating answer</step_name>\n<final_answer>The document is about...</final_answer>",
    "language": "ENGLISH",
    "has_documents": true
  }'
EOF
echo ""

# Example execution
if command -v jq &> /dev/null; then
    curl -s -X POST "${BASE_URL}/v2/validate" \
      -H "Content-Type: application/json" \
      -d '{
        "raw_output": "<observation>Test</observation>\n<reasoning>Test reasoning</reasoning>\n<final_answer>Test answer</final_answer>",
        "language": "ENGLISH",
        "has_documents": true
      }' | jq .
fi
echo ""
echo ""

# ============================================================================
# 6. Validate with Constraints
# ============================================================================

echo "6. Validate with Constraints"
echo "----------------------------"
echo ""
echo "Request:"
cat << 'EOF'
curl -X POST "${BASE_URL}/v2/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "trace": {
      "steps": [...],
      "success": true
    },
    "constraints": {
      "max_steps": 10,
      "required_tools": ["search", "ReadFullDocument"],
      "min_citations": 2
    }
  }'
EOF
echo ""
echo ""

# ============================================================================
# Response Field Reference
# ============================================================================

echo "==================================="
echo "Response Field Reference"
echo "==================================="
echo ""
echo "/v2/run Response:"
echo "  final_answer       - The agent's final answer"
echo "  steps_reasoning    - List of reasoning steps"
echo "    step_number      - Sequential step number"
echo "    step_type        - Type of step (reasoning, tool_invoke, final_answer)"
echo "    step_name        - Description of step"
echo "    action           - Tool action taken {name, arguments}"
echo "    duration         - Step duration in seconds"
echo "  inputs_used        - Count of document inputs"
echo "  warnings           - Validation warnings"
echo "  session_id         - Unique session ID"
echo "  total_tokens       - Total tokens used"
echo "  success            - Whether agent completed successfully"
echo "  trace              - Full trace (if return_trace=true)"
echo "  train_sample       - Training sample (if return_train_sample=true)"
echo ""
echo "/v2/validate Response:"
echo "  ok                 - True if no errors"
echo "  errors             - List of validation errors"
echo "  warnings           - List of validation warnings"
echo "  stats              - Statistics"
echo "    steps_count      - Total steps"
echo "    tool_invoke_count - Number of tool invocations"
echo "    citation_count   - Number of [N] citations"
echo ""
echo "/health Response:"
echo "  status             - Server status"
echo "  version            - API version"
echo "  models_available   - Whether model API keys are configured"
echo ""
