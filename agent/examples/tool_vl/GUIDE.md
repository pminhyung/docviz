# VL (Vision-Language) Custom Tool Example

## Overview

This example demonstrates how to use custom VL tools with the Document Agent V2 pipeline.
VL tools use `context["call_vl"]` to call a Vision-Language model for image analysis.

## Prerequisites

- Running Document Agent V2 API server
- API key (OpenAI for default `gpt-5.2` model, or Novita for `qwen2.5-vl-72b`)
- Document with page images (`doc_image_dir`)

## Tools Provided

| Tool | Description |
|------|-------------|
| `analyze_page_image` | Analyze visual elements in page images (charts, tables, diagrams) |
| `extract_table` | Extract structured table data as JSON |
| `compare_page_images` | Compare visual elements across multiple pages |

## Quick Start

### 1. Start the API server

```bash
./run_server.sh
```

### 2. Run the client

```bash
python run_client.py \
    --api-key YOUR_OPENAI_API_KEY \
    --doc-json /path/to/document.json \
    --image-dir /path/to/images/ \
    --query "Analyze the chart on page 3"
```

### 3. Run E2E test (sandbox mode, no API key needed)

```bash
DOC_AGENT_V2_SANDBOX=1 python run_e2e_test.py
```

## Auto-Recording

Custom tool executions are **automatically recorded** in training samples.
You do NOT need to call `context["record_training"]` manually.

The pipeline records `train_sample["analyze_page_image"]`, `train_sample["extract_table"]`, etc.
with `[{role: "user", content: args_json}, {role: "assistant", content: result}]`.

Manual `record_training()` calls are still supported for additional custom training data.

## Custom Rules

Pass `custom_rules` to inject additional rules into the runtime prompt:

```json
{
    "custom_rules": "- When the user asks about charts, use analyze_page_image first\n- For tables, use extract_table tool"
}
```
