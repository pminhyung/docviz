"""Dump the actual compiled V4 reasoning prompt the Qwen3-8B agent sees.

Reproduces the prompt-compilation pipeline of `agent.run_agent_v2.AgentV2Runner.setup()`:
  1. ToolRegistry loads builtin tools + generate_viz custom tool
  2. PromptCompiler.compile(tools=..., custom_rules=V4_POOL_EXPOSURE_RULE)
  3. assemble_runtime_prompt + FINAL_ANSWER_PATCH + EN_LANG_PATCH

Output: markdown file with full runtime_prompt + section dividers + each block's
position so the user can edit specific sections directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make project root importable
REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from agent.core.prompt_compiler import (
    PromptCompiler,
    FINAL_ANSWER_PATCH,
    EN_LANG_PATCH,
    KO_LANG_PATCH,
)
from agent.core.tool_registry import ToolRegistry
from code.pipelines.tmg import V4_POOL_EXPOSURE_RULE


def main() -> int:
    # 1. Load tools exactly as the agent server does
    tool_registry = ToolRegistry(include_builtin=True)
    tool_registry.load_from_file(
        str(REPO / "code" / "agent_tools" / "generate_viz.py"),
        allow_override=True,
    )
    all_tools = tool_registry.get_tools_for_prompt()
    print(f"[dump] tools loaded: {[t['name'] for t in all_tools]}")

    # 2. Compile prompt with V4 rule injection (English, no override patch)
    compiler = PromptCompiler(language="ENGLISH")
    compiled = compiler.compile(
        tools=all_tools,
        custom_rules=V4_POOL_EXPOSURE_RULE,
        lang="en",
    )
    print(f"[dump] pack_id={compiled.prompt_pack_id} hash={compiled.prompt_hash}")
    print(f"[dump] runtime_prompt total chars: {len(compiled.runtime_prompt)}")

    # 3. Write markdown — split into source-traceable sections so user can
    # locate which file to edit. Custom rules (V4) come from
    # code/pipelines/tmg.py:V4_POOL_EXPOSURE_RULE. Builtin blocks come from
    # agent/config/runtime_prompts.py. Tool defs come from each tool class.
    out_path = REPO / "docs" / "active" / "tracks" / "feat-source-loaders" / "v4_compiled_prompt.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sections = []
    sections.append(
        "# V4_consolidated — compiled runtime prompt (agent system message)\n\n"
        "This is the **exact system prompt** the Qwen3.5-397B reasoner sees on every "
        "reasoning turn for `S4_AgenticTMGv4_consolidated` (B6 / B6_NoCIS, same prompt — "
        "NoCIS only flips `skip_doc_step=True`, which suppresses the Step-1 doc-summary "
        "*content* but does not modify this prompt).\n\n"
        f"- **pack_id**: `{compiled.prompt_pack_id}`\n"
        f"- **prompt_hash**: `{compiled.prompt_hash}`\n"
        f"- **total chars**: `{len(compiled.runtime_prompt)}`\n"
        f"- **compiled by**: `code/scripts/dump_v4_prompt.py`\n\n"
        "---\n\n"
        "## Edit-source reference\n\n"
        "| section in prompt | source file | how to edit |\n"
        "|---|---|---|\n"
        "| numbered rules 1–16 (RULES_BLOCK) | `agent/config/runtime_prompts.py` | edit the `RULES_BLOCK` content; or override via patch YAML |\n"
        "| numbered rules 17–18 (V4 custom rules) | `code/pipelines/tmg.py:V4_POOL_EXPOSURE_RULE` (line 193+) | edit Python string literal directly |\n"
        "| TOOLS_GENERATE_VIZ block | `code/agent_tools/generate_viz.py` (`description` + `parameters` class attrs) | edit class attrs in tool file |\n"
        "| TOOLS_SEARCH / TOOLS_READFULLDOCUMENT / etc | `agent/sidecars/...` builtin tool classes | edit `description`/`parameters` |\n"
        "| FINAL_ANSWER_PATCH (terse-output directive at end) | `agent/core/prompt_compiler.py:FINAL_ANSWER_PATCH` (line 45) | edit string literal |\n"
        "| EN_LANG_PATCH (language directive) | `agent/core/prompt_compiler.py:EN_LANG_PATCH` (line 33) | edit string literal |\n\n"
        "After editing, restart the agent server (port 9037) — prompt is compiled at server startup, not per-request:\n"
        "```bash\n"
        "kill 4116271  # current SOTA server PID\n"
        "DOCVIZ_HOST_MODE=multi QWEN_HOSTS=10.1.211.147:8000,10.1.211.148:8000,10.1.211.163:8000,10.1.211.164:8000,10.1.211.165:8000,10.1.211.166:8000 \\\n"
        "  /opt/conda/bin/uvicorn agent.api.server:app --host 0.0.0.0 --port 9037 --workers 4 --log-level info \\\n"
        "  > /tmp/v04_logs/sota_agent_server.log 2>&1 &\n"
        "```\n\n"
        "---\n\n"
        "## COMPILED PROMPT (verbatim — what the model receives)\n\n"
        "```\n"
        f"{compiled.runtime_prompt}\n"
        "```\n"
    )

    # Also dump V4 custom rule alone for quick visual comparison
    sections.append(
        "---\n\n"
        "## V4_POOL_EXPOSURE_RULE — isolated (the two paragraphs the user flagged)\n\n"
        "Source: `code/pipelines/tmg.py:193-240`. This is exactly the string passed as "
        "`custom_rules` and injected into RULES_BLOCK as rules 17 and 18.\n\n"
        "```\n"
        f"{V4_POOL_EXPOSURE_RULE}\n"
        "```\n\n"
        "---\n\n"
        "## FINAL_ANSWER_PATCH — appended after all blocks\n\n"
        "Source: `agent/core/prompt_compiler.py:45`.\n\n"
        "```\n"
        f"{FINAL_ANSWER_PATCH}\n"
        "```\n\n"
        "---\n\n"
        "## EN_LANG_PATCH — appended last\n\n"
        "Source: `agent/core/prompt_compiler.py:33`.\n\n"
        "```\n"
        f"{EN_LANG_PATCH}\n"
        "```\n"
    )

    out_path.write_text("".join(sections), encoding="utf-8")
    print(f"\n[dump] wrote {out_path}")
    print(f"[dump] absolute path: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
