# GPT VL Reasoner Example

## Overview

Use OpenAI GPT-4o as the VL reasoning model.
No custom tools — uses built-in tools only (search, ReadFullDocument, ReadFullText, GetPage).

## Prerequisites

- OpenAI API key (`gpt-4o` access)
- Running Document Agent V2 API server
- Document with page images (for VL features)

## Quick Start

### Run E2E test (sandbox, no API key)

```bash
DOC_AGENT_V2_SANDBOX=1 python run_e2e_test.py
```

### Run client (requires OpenAI API key)

```bash
python run_client.py \
    --api-key sk-proj-YOUR_OPENAI_KEY \
    --doc-json /path/to/document.json \
    --image-dir /path/to/images/ \
    --query "What are the main findings?"
```

## Configuration

| Parameter | Value |
|-----------|-------|
| `reasoner_type` | `"vl"` |
| `reasoner_model_name` | `"gpt-4o"` |
| `reasoner_api_key` | OpenAI API key |
| Base URL | Auto-detected: `https://api.openai.com/v1` (prefix `gpt-`) |

## Notes

- Model router auto-detects `gpt-` prefix and routes to OpenAI API
- VL mode enables image processing in tool outputs
- Training data is generated in the same format regardless of model provider
