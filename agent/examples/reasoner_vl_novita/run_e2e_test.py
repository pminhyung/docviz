#!/usr/bin/env python3
"""
Novita VL Reasoner E2E Test (sandbox mode).

Verifies:
- VL reasoner setup with default Novita model
- Sandbox execution with builtin tools only
- final_answer generation
- Train sample structure

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
    print("[E2E] Running Novita VL reasoner sandbox test...")
    result, train_sample, compiled_prompt = run_sandbox_e2e(
        custom_tools_path=None,
        custom_rules=None,
        reasoner_type="vl",
        reasoner_model_name="qwen/qwen2.5-vl-72b-instruct",  # Novita VL model
        user_query="Summarize this document",
        lang="en",
    )

    errors = []
    errors.extend(verify_train_sample(train_sample))
    errors.extend(verify_prompt_compilation(compiled_prompt, None, "en"))

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
        print(f"\n[PASS] Novita VL reasoner E2E test passed!")
        print(f"  train_sample keys: {sorted(train_sample.keys())}")
        sys.exit(0)


if __name__ == "__main__":
    main()
