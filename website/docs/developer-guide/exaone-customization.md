---
sidebar_position: 5
title: "EXAONE Customization"
description: "Where EXAONE customization lives and what to check before making code changes"
---

# EXAONE Customization

This fork includes local EXAONE-specific customization under `exaone/`.

## Start Here

- Read `exaone/USAGE.md` before making EXAONE-related code changes.
- Use `exaone/USAGE.md` as the source of truth for setup, runtime flags, and environment expectations in this fork.

## Runtime Model (Current Design)

- EXAONE path targets stateless per-request behavior: each request builds a new `ExaoneAgent`.
- `qa_mode` and `toolset` are resolved in `ExaoneAgent.__init__()`, then tool availability is finalized before `run_conversation()`.
- `qa_mode` and `toolset` are mutually exclusive. Passing both raises `ValueError`.
- Prompt assembly uses identity/style/tool-list blocks from `exaone/system_prompt.py`.

## How `qa_mode` Works

Source of truth: `exaone/qa_modes.py`

`QA_MODES` maps mode name to:

- `toolset`: allowed tool name(s), or `"all"`
- `identity_name`: file under `exaone/prompts/identities/`
- `style_name`: file under `exaone/prompts/style/`

At runtime:

1. `validate_exclusive_modes(toolset, qa_mode)` enforces mutual exclusion.
2. `resolve_qa_mode()` validates mode name.
3. `validate_qa_mode_prompt_files()` checks required identity/style files.
4. `ExaoneAgent` selects tools from `mode_config.toolset`.
5. Tool-list prompt is composed from active tools:
   - `exaone/prompts/tools/base_prompt.txt`
   - `exaone/prompts/tools/<tool_name>.txt` for each selected tool

## Adding a New `qa_mode`

1. Add entry in `exaone/qa_modes.py` under `QA_MODES`.
2. Add prompt files:
   - `exaone/prompts/identities/<name>.txt`
   - `exaone/prompts/style/<name>.txt`
3. Ensure `toolset` values are valid registered tool names (or `"all"`).
4. If using strict tool-list composition (current default), add tool prompt files:
   - `exaone/prompts/tools/<tool_name>.txt`
5. Update `exaone/USAGE.md` mode examples and API usage docs.

If identity/style files are missing, startup will fail with `RuntimeError`.

## Tool Definition: What To Add

Source of truth: `exaone/tools.py`

MCP tools are registered into custom toolset `exaone-tools` via `register_exaone_tools()`.

When adding a tool source:

1. Add/adjust server in `_MCP_SERVERS`:
   - SSE form: `"server_name": "http://host:port/sse"`
   - stdio form: command/args/env config object
2. Keep env-dependent values in `env_from` where possible.
3. Ensure the MCP server actually exposes tools at runtime.
4. Add matching prompt descriptions in `exaone/prompts/tools/`.

`register_exaone_tools()` is idempotent and called before `super().__init__()` in `ExaoneAgent`.

## Tool Name and Toolset Semantics

Tool names follow Hermes registry naming:

- `mcp_{server_name}_{tool_name}`

Examples:

- `mcp_brave_search_brave_web_search`
- `mcp_code_exec_execute`

Current Exaone behavior:

- `enabled_toolsets` is fixed to `["exaone-tools"]`.
- Per-request selection is by **tool name list**, not legacy group aliases.
- `toolset=None` or `"all"` means all tools registered under `exaone-tools`.
- Unknown tool names raise `ValueError` with available tool names.

## Prompt Files to Keep in Sync

- `exaone/prompts/identities/<name>.txt`
- `exaone/prompts/style/<name>.txt`
- `exaone/prompts/tools/base_prompt.txt`
- `exaone/prompts/tools/<tool_name>.txt`
- optional MCP style snippets: `exaone/prompts/mcp_servers/<server_id>/style.txt`

With strict composition enabled, missing required prompt files fail fast.

## Pre-Change Checklist

Before code changes (edits/updates), if a task mentions EXAONE, API-server behavior, or custom gateway runtime, verify the following in order:

1. Open `exaone/USAGE.md` first.
2. Apply instructions from that file before changing runtime/config code.
3. Keep `AGENTS.md` and `exaone/USAGE.md` aligned when customizing behavior further.

## Scope

The `exaone/` directory is fork-specific. Changes there may not apply to upstream Hermes defaults.
