#!/usr/bin/env python3
"""
LLM Custom Tool E2E Test (sandbox mode).

Verifies:
- LLM tool registration and prompt injection
- Sandbox execution with custom tools
- Custom tool auto-recording in train_sample
- JSONL save/load roundtrip

Usage:
    DOC_AGENT_V2_SANDBOX=1 python run_e2e_test.py
"""
import os
import sys
from pathlib import Path

os.environ["DOC_AGENT_V2_SANDBOX"] = "1"

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agent.examples.e2e_helpers import (
    run_sandbox_e2e,
    verify_train_sample,
    verify_prompt_compilation,
    save_and_verify_jsonl,
)


def main():
    tools_path = str(Path(__file__).parent / "llm_tools.py")
    custom_rules = "- Use summarize_page for page summaries"

    print("[E2E] Running LLM tool sandbox test...")
    result, train_sample, compiled_prompt = run_sandbox_e2e(
        custom_tools_path=tools_path,
        custom_rules=custom_rules,
        reasoner_type="llm",
        user_query="Summarize the key facts in this document",
        lang="en",
    )

    errors = []
    errors.extend(verify_train_sample(train_sample))
    errors.extend(verify_prompt_compilation(compiled_prompt, custom_rules, "en"))

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
        print(f"\n[PASS] LLM tool E2E test passed!")
        print(f"  train_sample keys: {sorted(train_sample.keys())}")
        sys.exit(0)


if __name__ == "__main__":
    main()
