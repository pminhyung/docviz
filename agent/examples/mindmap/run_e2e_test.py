#!/usr/bin/env python3
"""
Mindmap Custom Tool E2E Test.

Verifies:
- Mindmap tool registration and prompt injection
- Execution with custom tools (API or sandbox)
- Custom tool auto-recording in train_sample
- JSONL save/load roundtrip

Usage:
    # API mode (default — requires reasoner API key in env)
    set -a; source .env; set +a
    python -m agent.examples.mindmap.run_e2e_test

    # Sandbox mode (no keys needed)
    DOC_AGENT_V2_SANDBOX=1 python -m agent.examples.mindmap.run_e2e_test
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
)


def main():
    tools_path = str(Path(__file__).parent / "mindmap_tools.py")
    custom_rules = (
        "- Use generate_mindmap to create an interactive mindmap from the document\n"
        "- The mindmap should capture the main themes, topics, and supporting facts\n"
        "- Include cross-reference links between related topics"
    )

    # Use qwen_onpremise if available
    qwen_host = os.environ.get("QWEN_ONPREMISE_HOST", "10.1.211.148")
    qwen_port = os.environ.get("QWEN_ONPREMISE_PORT", "8000")
    qwen_model = os.environ.get("QWEN_ONPREMISE_MODEL", "Qwen3.5-397B-A17B-FP8")

    mode = "sandbox" if is_sandbox_mode() else "API"
    print(f"[E2E] Running Mindmap tool test ({mode})...")

    kwargs = dict(
        custom_tools_path=tools_path,
        custom_rules=custom_rules,
        reasoner_type="llm",
        user_query="이 문서의 핵심 내용을 마인드맵으로 정리해주세요",
        lang="ko",
    )

    # Use qwen_onpremise for API mode
    if not is_sandbox_mode():
        kwargs.update(
            reasoner_model_name=qwen_model,
            reasoner_api_key="EMPTY",
            reasoner_base_url=f"http://{qwen_host}:{qwen_port}/v1",
        )

    result, train_sample, compiled_prompt = run_e2e(**kwargs)

    errors = []
    errors.extend(verify_train_sample(train_sample))
    errors.extend(verify_prompt_compilation(compiled_prompt, custom_rules, "ko"))

    # Verify mindmap tool appears in compiled prompt
    if "generate_mindmap" not in (compiled_prompt.runtime_prompt or ""):
        errors.append("generate_mindmap not found in compiled prompt")

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
        print(f"\n[PASS] Mindmap tool E2E test passed!")
        print(f"  tools used: {result['tools_used']}")
        print(f"  final_answer: {result['final_answer'][:200]}...")
        print(f"  train_sample keys: {sorted(train_sample.keys())}")
        sys.exit(0)


if __name__ == "__main__":
    main()
