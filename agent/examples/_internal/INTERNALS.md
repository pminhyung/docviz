# Internal Architecture Guide

## PromptCompiler

- **Block structure**: RUNTIME_PROMPT_BLOCKS = [TOOLS_BLOCK, RULES_BLOCK, EXAMPLES_BLOCK, ...]
- **YAML patch**: `override_patch_path` loads YAML and applies key-by-key override
- **custom_rules**: Injected into RULES_BLOCK with automatic numbering starting at 17+
- **Language patch**: `lang="ko"` adds KO_LANG_PATCH; `lang="en"` adds EN_LANG_PATCH

## ModelRouter

- **Provider auto-detection** (`_resolve_base_url`):
  - Prefix `gpt-` → `https://api.openai.com/v1`
  - Otherwise → Novita `https://api.novita.ai/v3/openai`
  - `reasoner_base_url` → explicit override (e.g., local vLLM `http://localhost:8000/v1`)
- **create_reasoning_client**: Returns proxy client or sandbox client based on mode

## TrainingSample Formats

### v1 (default)
```
df_idx, user_query, filenames,
reasoning, readfulldocument, readfulltext, doc_step,
train_system_prompt,
+ custom tool keys (auto-recorded)
```
- CHATEXAONE prefix applied to all conversation system turns
- reasoning system content = `CHATEXAONE_SYSTEM_PREFIX + train_system_prompt`

### v2 (admin)
v1 + metadata:
```
version, runtime_prompt_hash, override_hash,
session_id, language, trace_summary, timestamp, metadata
```
Activate: `train_sample_version: "v2"` in RunRequestV2.

## Custom Tool Auto-Recording

1. `_execute_tool()` in `run_agent_v2.py` detects `is_custom_tool(name)`
2. After execution, auto-appends to `extraction_sink`:
   `{"tool_name": name, "messages": [{"role": "user", "content": args_json}], "result": result}`
3. `builder.record_extraction()` processes all tool keys (no longer restricted to builtin)
4. `train_sample["tool_name"]` gets `[[{role, content, loss_masking}, ...]]`
5. In sandbox mode, custom tools also get auto-recorded with stub responses

## Sandbox Mode

- `DOC_AGENT_V2_SANDBOX=1` or `set_sandbox_mode(True)`
- Deterministic responses: doc_summary → tool_invoke (search) → final_answer
- No external API calls needed
- All tools return stub data

## Session Accumulation → GCS

1. Client sends `session_id` in each `/v2/run` request
2. `session_manager.append_sample()` accumulates JSONL samples
3. `/v2/finalize_session` → writes local JSONL → uploads to GCS
4. GCS path: `gs://mhpark_bucket/reasoning_api_output/{session_id}/train.jsonl`

## extra_training Key Preservation

- Custom tools calling `context["record_training"](key, conversations)` create `extra_training` keys
- `training_jsonl.py` expands `extra_training` dict into top-level keys in JSONL
- `TrainingSample.from_dict()` detects unknown list-valued keys → `extra_training`
- Auto-recorded custom tool keys are handled the same way
