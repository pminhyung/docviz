# LLM Custom Tool Example

## Overview

This example demonstrates custom tools that use `context["call_llm"]` for text-based LLM operations.
No VL model or images required.

## Tools Provided

| Tool | Description |
|------|-------------|
| `summarize_page` | Summarize a specific page using LLM |
| `extract_key_facts` | Extract key facts as structured JSON |

## Quick Start

### Run E2E test (sandbox, no API key)

```bash
DOC_AGENT_V2_SANDBOX=1 python run_e2e_test.py
```

### Run client (requires API key + running server)

```bash
python run_client.py \
    --api-key YOUR_OPENAI_API_KEY \
    --doc-json /path/to/document.json \
    --query "Summarize the key facts in this document"
```

## Auto-Recording

Custom tool results are **automatically recorded** in training samples.
No need to call `context["record_training"]` manually.

For example, after `summarize_page` executes, the pipeline automatically adds:
```json
{"summarize_page": [[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]]}
```
