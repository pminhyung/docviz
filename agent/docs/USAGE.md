# Document Agent V2 - API Usage Guide

Client-facing guide for using the Document Agent V2 API.

## Table of Contents

1. [No-Keys Quickstart (Sandbox Mode)](#no-keys-quickstart-sandbox-mode)
2. [Quick Start (Production)](#quick-start-production)
3. [Health Check](#health-check)
4. [API Endpoints](#api-endpoints)
   - [GET /health](#get-health)
   - [POST /v2/run](#post-v2run)
   - [POST /v2/finalize_session](#post-v2finalize_session)
   - [POST /v2/validate](#post-v2validate)
5. [Session Workflow (Batch Training Data)](#session-workflow-batch-training-data)
6. [Custom Tools](#custom-tools)
7. [Reasoner Configuration](#reasoner-configuration)
8. [Document JSON Format](#document-json-format)
9. [Override Patch Usage](#override-patch-usage)
10. [Output Explanation](#output-explanation)
11. [Security Notes](#security-notes)
12. [Troubleshooting](#troubleshooting)

---

## No-Keys Quickstart (Sandbox Mode)

**Run the complete Document Agent V2 pipeline WITHOUT any API keys.**

Sandbox mode uses deterministic stub responses, allowing you to:
- Test the full pipeline end-to-end
- Verify trace/JSONL exports work correctly
- Demo the system to teammates
- Run CI/CD tests without API costs

### One-Command Demo

```bash
cd examples/
./demo_one_command.sh
```

This script will:
1. Start the API server in sandbox mode (no API keys needed)
2. Run a health check
3. Execute a sample query
4. Save all outputs to `demo_output/`
5. Print PASS/FAIL summary

### Manual Sandbox Mode

```bash
# Enable sandbox mode
export DOC_AGENT_V2_SANDBOX=1

# Start server (no API keys needed)
cd /path/to/doc_deep_v2
python -m agent.api.server
# → http://0.0.0.0:9024

# In another terminal:
curl http://localhost:9024/health
# {"status":"healthy","version":"2.0.0","models_available":true,"sandbox_mode":true}
```

> **Note:** `reasoner_api_key` is required even in sandbox mode. Use a dummy value like `"sandbox"`.

| Component | Production Mode | Sandbox Mode |
|-----------|----------------|--------------|
| LLM Calls | Real API (requires keys) | Deterministic stubs |
| Document Loading | From files | From files (normal) |
| Tool Execution | Real search/extraction | Stub results |
| Trace Export | Normal | Normal |
| Training JSONL | Normal | Normal |

---

## Quick Start (Production)

### 1. Start the Server

```bash
cd /path/to/doc_deep_v2
python -m agent.api.server
# → Uvicorn running on http://0.0.0.0:9024
```

### 2. Verify Server is Running

```bash
curl http://localhost:9024/health
```

Expected:
```json
{"status": "healthy", "version": "2.0.0", "models_available": true, "sandbox_mode": false}
```

### 3. Run a Query

```bash
curl -X POST http://localhost:9024/v2/run \
  -H "Content-Type: application/json" \
  -d '{
    "doc_json_path": "/path/to/document.json",
    "user_query": "Summarize this document",
    "reasoner_api_key": "your-openai-api-key"
  }'
```

> **Note:** `reasoner_api_key` is **required** for every request. The default model is `gpt-5.2` (OpenAI), so pass an OpenAI API key unless you override `reasoner_model_name`.

### 4. Python Client Example

```python
import requests

resp = requests.post("http://localhost:9024/v2/run", json={
    "doc_json_path": "/path/to/document.json",
    "user_query": "What are the key findings?",
    "reasoner_api_key": "your-openai-api-key",
    "return_train_sample": True,
})

data = resp.json()
print(data["final_answer"])
print(f"Steps: {data['num_steps']}, Tokens: {data['total_tokens']}")
```

---

## Health Check

After starting the server, always verify connectivity before sending queries.

### Request

```bash
curl http://localhost:9024/health
```

### Response

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "models_available": true,
  "sandbox_mode": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"healthy"` if server is running |
| `version` | string | API version (e.g., `"2.0.0"`) |
| `models_available` | boolean | Whether LLM API keys are configured on the server |
| `sandbox_mode` | boolean | Whether sandbox mode is enabled (`DOC_AGENT_V2_SANDBOX=1`) |

### Checklist

1. **`status: "healthy"`** — Server is running and ready
2. **`models_available: true`** — Model configurations are loaded (always true; API keys are provided per-request)
3. **`sandbox_mode`** — Check if running in sandbox mode (deterministic stubs, no real API calls)

### Connection Failure

If the health check fails:

```bash
# Check if server is running
lsof -i :9024

# Check server logs
# (look for startup errors in the terminal where the server was started)

# Restart the server
python -m agent.api.server
```

---

## API Endpoints

### GET /health

Health check endpoint (see [Health Check](#health-check) above).

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"healthy"` |
| `version` | string | API version (e.g., `"2.0.0"`) |
| `models_available` | boolean | Whether any LLM API keys are configured on server |
| `sandbox_mode` | boolean | Whether sandbox mode is enabled |

---

### POST /v2/run

Run the document agent for a single query.

#### Request Fields

**Required:**

| Field | Type | Description |
|-------|------|-------------|
| `doc_json_path` | string | Path to document JSON file |
| `user_query` | string | Question to answer |
| `reasoner_api_key` | string | API key for the reasoning model (**required**). OpenAI key for `gpt-*` models, Novita key for others. |

**Optional — Document:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `doc_json_path_2` | string | null | Second document path (multi-doc mode) |
| `doc_image_dir` | string | null | Image directory for VL tools |
| `single_doc` | boolean | true | Single document mode |
| `lang` | string | `"en"` | Output language: `"en"` or `"ko"` |

**Optional — Reasoner:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `reasoner_type` | string | `"llm"` | `"llm"` (text-only) or `"vl"` (vision-language) |
| `reasoner_model_name` | string | `"gpt-5.2"` | Model name (see [Reasoner Configuration](#reasoner-configuration)) |
| `reasoner_base_url` | string | null | Override base URL (e.g., local vLLM: `"http://localhost:8000/v1"`) |
| `reasoner_model_max_length` | integer | null | Override max output tokens for reasoner. null uses model default (gpt-5.2: 32768, Novita: 16384). |

**Optional — Custom Tools:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `custom_tools_path` | string | null | Path to `.py` file with custom tool classes |
| `custom_rules` | string | null | Extra rules for the agent (e.g., `"- Use analyze_chart tool"`) |
| `tool_secrets` | object | null | Secret values for custom tools (e.g., `{"api_key": "sk_xxx"}`) |

**Optional — Session & Output:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `session_id` | string | null | Session ID for accumulating training samples |
| `n_steps_max` | integer | 20 | Maximum agent steps (1–100) |
| `return_trace` | boolean | false | Include reasoning trace in response |
| `return_train_sample` | boolean | false | Include training sample in response |
| `train_sample_version` | string | `"v1"` | Training data format: `"v1"` (default) or `"v2"` (admin) |
| `override_patch_path` | string | null | Path to YAML override patch file |

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Whether agent completed successfully |
| `final_answer` | string | The agent's final answer |
| `num_steps` | integer | Number of agent steps taken |
| `total_tokens` | integer | Total tokens used |
| `total_duration_seconds` | float | Total execution time in seconds |
| `steps_reasoning` | array | List of reasoning steps |
| `inputs_used` | integer | Count of documents used |
| `warnings` | array | Validation warnings |
| `session_id` | string | Unique request session ID |
| `error` | string \| null | Error message if `success=false` |
| `train_sample` | object \| null | Training sample (if `return_train_sample=true`) |
| `trace` | object \| null | Full trace (if `return_trace=true`) |
| `accumulation_session_id` | string \| null | Session ID if accumulating |
| `session_sample_count` | integer \| null | Current sample count in session |

#### Example — Basic Query (default gpt-5.2)

```bash
curl -X POST http://localhost:9024/v2/run \
  -H "Content-Type: application/json" \
  -d '{
    "doc_json_path": "/data/report.json",
    "user_query": "What are the key findings?",
    "reasoner_api_key": "your-openai-key",
    "lang": "en",
    "return_train_sample": true
  }'
```

#### Example — VL + Custom Tools + Session (Novita)

```bash
curl -X POST http://localhost:9024/v2/run \
  -H "Content-Type: application/json" \
  -d '{
    "doc_json_path": "/data/docai/report.json",
    "doc_image_dir": "/data/docai/images/report/",
    "user_query": "Analyze the chart on page 3",
    "reasoner_type": "vl",
    "reasoner_model_name": "qwen/qwen2.5-vl-72b-instruct",
    "reasoner_api_key": "your-novita-key",
    "reasoner_model_max_length": 16384,
    "custom_tools_path": "/path/to/vl_tools.py",
    "custom_rules": "- Use analyze_page_image for chart analysis",
    "tool_secrets": {"external_api_key": "sk_xxx"},
    "session_id": "batch_001",
    "return_train_sample": true
  }'
```

---

### POST /v2/finalize_session

Finalize a session and upload accumulated training samples to GCS.

Call this after sending multiple `/v2/run` requests with the same `session_id`.

#### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | Yes | Session ID to finalize |

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | The finalized session ID |
| `sample_count` | integer | Total training samples |
| `gcs_path` | string | GCS path where JSONL was uploaded |
| `success` | boolean | Whether finalization succeeded |
| `error` | string \| null | Error message if failed |

#### Example

```bash
# After multiple /v2/run calls with session_id="batch_001"
curl -X POST http://localhost:9024/v2/finalize_session \
  -H "Content-Type: application/json" \
  -d '{"session_id": "batch_001"}'
```

Response:
```json
{
  "session_id": "batch_001",
  "sample_count": 50,
  "gcs_path": "gs://mhpark_bucket/reasoning_api_output/batch_001/20260227_train.jsonl",
  "success": true
}
```

---

### POST /v2/validate

Validate a trace or raw LLM output.

#### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `trace` | object | One of trace/raw_output | Trace to validate |
| `raw_output` | string | One of trace/raw_output | Raw LLM text to validate |
| `constraints` | object | No | Validation constraints |
| `language` | string | No | `"ENGLISH"` or `"KOREAN"` |
| `has_documents` | boolean | No | Whether docs were provided (default: true) |

**Constraints Object:**

| Field | Type | Description |
|-------|------|-------------|
| `max_steps` | integer | Maximum allowed steps |
| `required_tools` | array | Tools that must be used |
| `min_citations` | integer | Minimum required citations |

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | True if no errors |
| `errors` | array | Validation errors |
| `warnings` | array | Validation warnings |
| `stats` | object | `{steps_count, tool_invoke_count, citation_count}` |

---

## Session Workflow (Batch Training Data)

Use sessions to accumulate training samples from multiple queries, then upload to GCS as a single JSONL file.

### Flow

```
1. /v2/run  (session_id="my_batch") → sample #1 saved locally
2. /v2/run  (session_id="my_batch") → sample #2 appended
3. /v2/run  (session_id="my_batch") → sample #3 appended
4. /v2/finalize_session              → JSONL uploaded to GCS
```

### Python Example

```python
import requests

API = "http://localhost:9024"
SESSION = "experiment_20260227"

# Run multiple queries with the same session_id
queries = [
    "Summarize the key findings",
    "What methodology was used?",
    "List the main conclusions",
]

for query in queries:
    resp = requests.post(f"{API}/v2/run", json={
        "doc_json_path": "/data/report.json",
        "user_query": query,
        "reasoner_api_key": "your-openai-key",
        "session_id": SESSION,
    })
    data = resp.json()
    print(f"[{data['success']}] {query[:40]}... → samples: {data['session_sample_count']}")

# Finalize: upload to GCS
result = requests.post(f"{API}/v2/finalize_session", json={
    "session_id": SESSION,
}).json()

print(f"Uploaded {result['sample_count']} samples → {result['gcs_path']}")
```

### Local Storage

Before finalization, samples are stored locally at:

```
/tmp/docviz_agent_sessions/{session_id}/train.jsonl
```

After `finalize_session`, local files are cleaned up.

### JSONL Format (v1, default)

Each line in the JSONL contains:

| Field | Type | Description |
|-------|------|-------------|
| `df_idx` | int | Dataset index |
| `user_query` | string | Original query |
| `filenames` | array | Document filenames |
| `reasoning` | array | Reasoning conversation turns |
| `readfulldocument` | array | Full document read conversations |
| `readfulltext` | array | Text extraction conversations |
| `doc_step` | array | Document summary conversations |
| `train_system_prompt` | string | System prompt for training |
| *(custom keys)* | array | Any custom tool training data |

---

## Custom Tools

Add custom tools by writing a `.py` file and passing its path in the request.

See [CUSTOM_TOOLS.md](CUSTOM_TOOLS.md) for the full guide.

### Quick Summary

```python
# my_tools.py
import json

class AnalyzeChartTool:
    name = "analyze_chart"
    description = "Analyze a chart image on a specific page"
    parameters = {
        "type": "object",
        "properties": {
            "page_number": {"type": "integer", "description": "Page number"}
        },
        "required": ["page_number"]
    }
    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        page_num = args["page_number"]
        # Use context services: call_llm, call_vl, search_documents, record_training
        result = context["call_llm"](
            messages=[{"role": "user", "content": f"Analyze page {page_num}"}],
        )
        return result
```

Pass in request:
```json
{
  "custom_tools_path": "/path/to/my_tools.py",
  "custom_rules": "- Use analyze_chart for chart analysis",
  "tool_secrets": {"external_api_key": "sk_xxx"}
}
```

### `tool_secrets`

Pass secrets your custom tools need (API keys, DB credentials, etc.) via `tool_secrets`. These are accessible in the tool as `context["tool_secrets"]` and are NOT logged by the server.

---

## Reasoner Configuration

The `reasoner_type` and `reasoner_model_name` control the reasoning model.

### Default Model

| Field | Default Value |
|-------|---------------|
| `reasoner_model_name` | `gpt-5.2` (OpenAI) |
| `reasoner_type` | `llm` (text-only) |
| `reasoner_model_max_length` | null (auto: gpt-5.2 → 32768, Novita → 16384) |

> The default model is `gpt-5.2` via OpenAI API. Pass an OpenAI API key as `reasoner_api_key`.
> To use Novita models, explicitly set `reasoner_model_name` (e.g., `qwen/qwen3-235b-a22b-instruct-2507`).

### Model Routing

| Model Name Pattern | Provider | Base URL |
|--------------------|----------|----------|
| `gpt-*` (e.g., `gpt-4o`) | OpenAI | `https://api.openai.com/v1` |
| `local/*` (e.g., `local/qwen3`) | Local vLLM | `$VLLM_BASE_URL` or `http://localhost:8000/v1` |
| Everything else | Novita AI | `https://api.novita.ai/v3/openai` |

### Examples

```python
# Default (gpt-5.2 via OpenAI)
{"reasoner_api_key": "sk-proj-your-openai-key"}

# OpenAI GPT-4o (different model)
{"reasoner_model_name": "gpt-4o", "reasoner_api_key": "sk-proj-..."}

# Novita qwen3-235b LLM
{"reasoner_model_name": "qwen/qwen3-235b-a22b-instruct-2507", "reasoner_api_key": "your-novita-key"}

# Novita VL mode (must specify model since default is LLM)
{"reasoner_type": "vl", "reasoner_model_name": "qwen/qwen2.5-vl-72b-instruct", "reasoner_api_key": "your-novita-key"}

# Custom max_length
{"reasoner_api_key": "sk-proj-...", "reasoner_model_max_length": 16384}

# Local vLLM
{"reasoner_model_name": "local/qwen3", "reasoner_base_url": "http://localhost:8000/v1", "reasoner_api_key": "dummy"}
```

### VL Mode Image Flow

When `reasoner_type: "vl"`, tool outputs containing `image_paths` are automatically base64-encoded and included as multimodal messages in the next reasoning call:

```
Tool Output: {"result": "...", "image_paths": ["/path/to/chart.png"]}
     ↓
System: Base64 encode image → multimodal message
     ↓
Next Reasoning Call: text + image content
```

---

## Document JSON Format

### Format 1: Dictionary

Page numbers as string keys:

```json
{
  "1": "Content of page 1...",
  "2": "Content of page 2..."
}
```

### Format 2: DocAI

```json
{
  "id": "uuid",
  "outputs": [{
    "file_name": "report.pdf",
    "html_parsed": {
      "1": ["Page 1 text..."],
      "2": ["Page 2 text..."]
    }
  }]
}
```

### Format 3: Array

```json
[
  {"page": 1, "content": "Content of page 1..."},
  {"page": 2, "content": "Content of page 2..."}
]
```

The loader auto-detects the format.

### Multi-Document Mode

```json
{
  "doc_json_path": "/path/to/doc1.json",
  "doc_json_path_2": "/path/to/doc2.json",
  "single_doc": false
}
```

---

## Override Patch Usage

Override patches customize agent behavior without modifying core code.

### Patch File Format

```yaml
meta:
  owner: your_team_name
  version: 1.0.0

patches:
  RULES_BLOCK:
    action: replace
    content: |
      ## Custom Rules
      1. Always cite sources
      2. Use formal language
```

### Patchable Blocks

| Block ID | Action | Description |
|----------|--------|-------------|
| `RULES_BLOCK` | replace | Agent behavior rules |
| `TOOLS_SEARCH` | append | Search tool instructions |
| `TOOLS_DOCUMENT` | append | Document tool instructions |
| `TOOLS_PAGE` | append | Page tool instructions |
| `TOOLS_TEXT` | append | Text tool instructions |

---

## Output Explanation

### steps_reasoning

Each step:

| Field | Description |
|-------|-------------|
| `step_number` | Sequential step number (1, 2, 3...) |
| `step_type` | `doc_summary`, `tool_invoke`, or `final_answer` |
| `step_name` | Human-readable step description |
| `action` | Tool action taken (`{name, arguments}`) |
| `duration` | Step duration in seconds |

### Validation Warnings

| Warning | Meaning |
|---------|---------|
| No document action found | Agent answered without reading documents |
| Hangul ratio check | Language mismatch detected |
| Missing polite endings | Korean response lacks formal speech |

---

## Security Notes

### API Key Handling

**Reasoner API keys** (`reasoner_api_key`) are passed per-request in the request body. This is by design — the server acts as a stateless proxy and does not store API keys.

**Custom tool secrets** (`tool_secrets`) are also passed per-request and are NOT logged by the server.

### System Prompt Protection

The API NEVER returns runtime system prompts in responses:
- Trace data: prompts replaced with `__SYSTEM_PROMPT_REDACTED__`
- train_sample: system messages redacted
- Only the `train_system_prompt` field (in session JSONL) contains the training-safe prompt

### File Path Access

The API accepts file paths as parameters. In production:
- Validate paths on your infrastructure
- Consider restricting accessible directories
- Use absolute paths

### Recommendations

1. Run behind a reverse proxy (nginx, traefik)
2. Implement authentication for production
3. Set appropriate CORS origins
4. Monitor token usage via response `total_tokens`
5. Rate limit requests

---

## Troubleshooting

### Server Won't Start

```bash
# Check port availability
lsof -i :9024

# Verify imports
python -c "from agent.api.server import app"

# Install dependencies
pip install fastapi uvicorn pydantic openai pyyaml
```

### Model Errors

**max_tokens exceeded:**
```
BadRequestError: max_tokens (current value: ...) must be between 0 and 16384
```
- The server uses `max_tokens=16384` for Novita/OpenAI models. If you see this error, ensure you're running the latest server code.

**Model not found:**
```
MODEL_NOT_FOUND: model: qwen/xxx not found
```
- Check the model name is valid on Novita (`https://api.novita.ai/v3/openai/models`) or OpenAI.
- Default model: `gpt-5.2` (OpenAI). For Novita VL, use e.g., `qwen/qwen2.5-vl-72b-instruct`

**API key error:**
- Default model is `gpt-5.2`: pass your **OpenAI** API key as `reasoner_api_key`
- For Novita models (e.g., `qwen3-235b`): pass your **Novita** API key
- `reasoner_api_key` is **required** for every request (including sandbox mode)

### VL Mode Issues

1. Verify `reasoner_type: "vl"` is set
2. Check tool output contains `image_paths` key
3. Ensure image paths are absolute and files exist
4. Check image format is PNG or JPEG
5. `doc_image_dir` must be an existing directory

### Document Loading Errors

```bash
# Verify file exists
ls -la /path/to/document.json

# Validate JSON
python -m json.tool /path/to/document.json
```

### Session Issues

**Session not found on finalize:**
- Ensure the same server instance handled both `/v2/run` and `/v2/finalize_session` calls
- Sessions are stored in memory + `/tmp/docviz_agent_sessions/` — restarting the server clears in-memory state

**GCS upload failed:**
- Requires `gsutil` installed and authenticated (`gcloud auth login`)
- Local JSONL is preserved if GCS upload fails
