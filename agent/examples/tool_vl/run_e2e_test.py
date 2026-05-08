#!/usr/bin/env python3
"""
VL Custom Tool E2E Test.

Verifies:
- VL tool registration and prompt injection
- Execution with custom tools (API or sandbox)
- Custom tool auto-recording in train_sample
- JSONL save/load roundtrip

Usage:
    # API mode (default — uses qwen_onpremise, no API key needed)
    python run_e2e_test.py

    # Sandbox mode (no keys needed)
    DOC_AGENT_V2_SANDBOX=1 python run_e2e_test.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agent.core.sandbox import is_sandbox_mode
from agent.examples.e2e_helpers import (
    run_e2e,
    verify_train_sample,
    verify_prompt_compilation,
    save_and_verify_jsonl,
    verify_custom_tool_auto_recorded,
)


def main():
    tools_path = str(Path(__file__).parent / "vl_tools.py")
    custom_rules = "- When analyzing visual content, use analyze_page_image tool"

    mode = "sandbox" if is_sandbox_mode() else "API"
    print(f"[E2E] Running VL tool test ({mode})...")
    result, train_sample, compiled_prompt = run_e2e(
        custom_tools_path=tools_path,
        custom_rules=custom_rules,
        reasoner_type="vl",
        reasoner_model_name="qwen_onpremise",
        user_query="Analyze the charts in this document",
        lang="en",
    )

    errors = []

    # Verify basic train_sample structure
    errors.extend(verify_train_sample(train_sample))

    # Verify prompt compilation
    errors.extend(verify_prompt_compilation(compiled_prompt, custom_rules, "en"))

    # Verify JSONL roundtrip
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        jsonl_path = f.name
    try:
        errors.extend(save_and_verify_jsonl(train_sample, jsonl_path))
    finally:
        if os.path.exists(jsonl_path):
            os.unlink(jsonl_path)

    if errors:
        print(f"\n[FAIL] {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"\n[PASS] VL tool E2E test passed!")
        print(f"  tools used: {result['tools_used']}")
        print(f"  final_answer: {result['final_answer'][:200]}...")
        print(f"  train_sample keys: {sorted(train_sample.keys())}")
        print(f"  prompt pack_id: {compiled_prompt.prompt_pack_id}")
        sys.exit(0)


if __name__ == "__main__":
    main()
