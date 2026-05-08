# Novita VL Reasoner Example

## Overview

Use Novita AI's Qwen2.5-VL-72B as the VL reasoning model.
No custom tools — uses built-in tools only.

## Prerequisites

- Novita API key
- Running Document Agent V2 API server

## Quick Start

### Run E2E test (sandbox, no API key)

```bash
DOC_AGENT_V2_SANDBOX=1 python run_e2e_test.py
```

### Run client

```bash
python run_client.py \
    --api-key sk_YOUR_NOVITA_KEY \
    --doc-json /path/to/document.json \
    --query "Summarize this document"
```

## Configuration

| Parameter | Value |
|-----------|-------|
| `reasoner_type` | `"vl"` |
| `reasoner_model_name` | `"qwen/qwen2.5-vl-72b-instruct"` |
| `reasoner_api_key` | Novita API key |
| Base URL | Auto-detected: `https://api.novita.ai/v3/openai` |

## Notes

- Explicit model name required since default is now gpt-5.2 (LLM)
- Novita base URL is auto-detected by model_router
- Suitable for production VL workflows with competitive pricing
