"""
E2E Test Helpers — Shared verification functions for example E2E tests.

Used by:
- examples/tool_vl/run_e2e_test.py
- examples/tool_llm/run_e2e_test.py
- examples/tool_image_only/run_e2e_test.py
- examples/reasoner_vl_gpt/run_e2e_test.py
- examples/reasoner_vl_novita/run_e2e_test.py
- tests/integration/test_case_examples_e2e.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure parent is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.core.prompt_compiler import CompiledPrompt
from agent.core.tool_registry import ToolRegistry
from agent.core.sandbox import set_sandbox_mode, is_sandbox_mode
from agent.run_agent_v2 import AgentV2Runner
from agent.export.training_jsonl import (
    convert_base_train_sample_v1,
    convert_base_train_sample,
    TrainingJSONLExporter,
)


# ──── Minimal demo document for sandbox tests ────

DEMO_DOC = {
    "1": "# Demo Document\n\nPage 1: Introduction to the demo system. Key features include multi-step reasoning, tool invocation, and training data export.",
    "2": "# Details\n\nPage 2: The system supports document search, ReadFullDocument, and custom tools for extensibility.",
    "3": "# Summary\n\nPage 3: Sandbox mode allows end-to-end testing without external API calls.",
}


def _create_demo_doc_json() -> str:
    """Create a temporary demo document JSON file. Caller must clean up."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="demo_doc_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(DEMO_DOC, f, ensure_ascii=False)
    return path


def run_e2e(
    custom_tools_path: Optional[str] = None,
    custom_rules: Optional[str] = None,
    reasoner_type: str = "llm",
    reasoner_model_name: Optional[str] = None,
    reasoner_api_key: Optional[str] = None,
    extraction_api_key: Optional[str] = None,
    user_query: str = "What are the main topics in this document?",
    lang: str = "en",
) -> Tuple[Dict[str, Any], Dict[str, Any], CompiledPrompt]:
    """
    Run a full E2E and return (result_dict, train_sample, compiled_prompt).

    Respects the current sandbox mode setting from DOC_AGENT_V2_SANDBOX env var.
    In API mode, auto-resolves reasoner_api_key and extraction_api_key from
    OPENAI_API_KEY / NOVITA_API_KEY based on reasoner_model_name.
    """
    # Auto-resolve API keys when not in sandbox mode
    if not is_sandbox_mode():
        # Resolve effective model name (mirrors model_router defaults)
        effective_model = reasoner_model_name
        if effective_model is None:
            effective_model = (
                "qwen/qwen2.5-vl-72b-instruct" if reasoner_type == "vl"
                else "gpt-5.2"
            )
        if not reasoner_api_key:
            if effective_model == "qwen_onpremise":
                reasoner_api_key = "EMPTY"
            elif effective_model.startswith("gpt-"):
                reasoner_api_key = os.environ.get("OPENAI_API_KEY", "")
            else:
                reasoner_api_key = os.environ.get("NOVITA_API_KEY", "")
        # GPT reasoner → extraction models (qwen3) need Novita key
        if not extraction_api_key and effective_model.startswith("gpt-"):
            extraction_api_key = os.environ.get("NOVITA_API_KEY", "")

    doc_path = _create_demo_doc_json()

    try:
        # Load custom tools if provided
        custom_tools_for_prompt = None
        tool_registry = None
        if custom_tools_path:
            tool_registry = ToolRegistry()
            loaded_names = tool_registry.load_from_file(custom_tools_path)
            custom_tools_for_prompt = tool_registry.get_tools_for_prompt()
            print(f"[E2E] Loaded custom tools: {loaded_names}")

        language = "KOREAN" if lang == "ko" else "ENGLISH"

        runner = AgentV2Runner(
            language=language,
            single_doc=True,
            n_steps_max=10,
            verbose=False,
            custom_tools=custom_tools_for_prompt,
            custom_rules=custom_rules,
            tool_registry=tool_registry,
            reasoner_type=reasoner_type,
            reasoner_model_name=reasoner_model_name,
            reasoner_api_key=reasoner_api_key,
            extraction_api_key=extraction_api_key,
        )

        runner.setup()
        compiled_prompt = runner.compiled_prompt

        multi_docs, filenames, doc_contexts = runner.load_documents(doc_json_path=doc_path)

        session, train_sample = runner.run_single_query(
            user_query=user_query,
            multi_docs=multi_docs,
            filenames=filenames,
            doc_contexts=doc_contexts,
        )

        trace_data = runner.trace_collector.export_session(session, redact=True)

        tools_used = []
        for step in trace_data.get("steps", []):
            if step.get("step_type") == "tool_invoke" and step.get("action"):
                tools_used.append(step["action"])

        result = {
            "final_answer": "",
            "success": trace_data.get("success", False),
            "num_steps": len(trace_data.get("steps", [])),
            "total_tokens": trace_data.get("total_tokens", 0),
            "session_id": trace_data.get("session_id", ""),
            "tools_used": tools_used,
        }

        for step in reversed(trace_data.get("steps", [])):
            if step.get("final_answer"):
                result["final_answer"] = step["final_answer"]
                break

        mode = "sandbox" if is_sandbox_mode() else "API"
        print(f"[E2E] Done ({mode}): success={result['success']}, steps={result['num_steps']}")
        return result, train_sample, compiled_prompt

    finally:
        if os.path.exists(doc_path):
            os.unlink(doc_path)


def run_sandbox_e2e(
    custom_tools_path: Optional[str] = None,
    custom_rules: Optional[str] = None,
    reasoner_type: str = "llm",
    reasoner_model_name: Optional[str] = None,
    user_query: str = "What are the main topics in this document?",
    lang: str = "en",
) -> Tuple[Dict[str, Any], Dict[str, Any], CompiledPrompt]:
    """Backward-compatible wrapper: forces sandbox mode, then calls run_e2e()."""
    set_sandbox_mode(True)
    os.environ["DOC_AGENT_V2_SANDBOX"] = "1"
    return run_e2e(
        custom_tools_path=custom_tools_path,
        custom_rules=custom_rules,
        reasoner_type=reasoner_type,
        reasoner_model_name=reasoner_model_name,
        user_query=user_query,
        lang=lang,
    )


def verify_train_sample(train_sample: Dict[str, Any]) -> List[str]:
    """Verify required keys and structure in train_sample."""
    errors = []
    required_keys = ["df_idx", "user_query", "filenames", "reasoning", "readfulldocument", "readfulltext", "doc_step"]

    for key in required_keys:
        if key not in train_sample:
            errors.append(f"Missing required key: {key}")

    if "reasoning" in train_sample:
        if not isinstance(train_sample["reasoning"], list):
            errors.append("reasoning must be a list")
        elif len(train_sample["reasoning"]) == 0:
            errors.append("reasoning is empty — no reasoning turns recorded")

    if "doc_step" in train_sample:
        if not isinstance(train_sample["doc_step"], list):
            errors.append("doc_step must be a list")

    return errors


def verify_prompt_compilation(
    compiled_prompt: CompiledPrompt,
    custom_rules: Optional[str],
    lang: str,
) -> List[str]:
    """Verify prompt compilation: custom_rules injection, language patch."""
    errors = []

    if not compiled_prompt.runtime_prompt:
        errors.append("runtime_prompt is empty")

    if not compiled_prompt.prompt_hash:
        errors.append("prompt_hash is empty")

    # Check custom rules injection
    if custom_rules:
        if custom_rules.split("\n")[0].lstrip("- ") not in compiled_prompt.runtime_prompt:
            # Check by content, not exact match (may be renumbered)
            first_rule_content = custom_rules.split("\n")[0].lstrip("- ").strip()
            if first_rule_content and first_rule_content not in compiled_prompt.runtime_prompt:
                errors.append(f"Custom rule not found in runtime_prompt: {first_rule_content[:50]}")

    return errors


def save_and_verify_jsonl(
    train_sample: Dict[str, Any],
    output_path: str,
    version: str = "v1",
    train_system_prompt: str = "test training prompt",
) -> List[str]:
    """Save train_sample as JSONL, reload, verify roundtrip."""
    errors = []

    try:
        if version == "v1":
            converted = convert_base_train_sample_v1(train_sample, train_system_prompt)
        else:
            converted = convert_base_train_sample(
                train_sample, train_system_prompt,
                runtime_prompt_hash="test_hash",
            ).to_dict()

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(converted, ensure_ascii=False) + "\n")

        # Reload and verify
        with open(output_path, "r", encoding="utf-8") as f:
            loaded = json.loads(f.readline())

        required_keys = ["df_idx", "user_query", "filenames", "reasoning"]
        for key in required_keys:
            if key not in loaded:
                errors.append(f"JSONL missing key after roundtrip: {key}")

        if version == "v1":
            if "train_system_prompt" not in loaded:
                errors.append("v1 JSONL missing train_system_prompt")
            if "version" in loaded:
                errors.append("v1 JSONL should not have 'version' key")

    except Exception as e:
        errors.append(f"JSONL roundtrip failed: {e}")

    return errors


def verify_custom_tool_auto_recorded(
    train_sample: Dict[str, Any],
    tool_name: str,
) -> List[str]:
    """Verify that a custom tool was auto-recorded in train_sample."""
    errors = []

    key = tool_name.lower()
    if key not in train_sample:
        errors.append(f"Custom tool '{tool_name}' not found in train_sample (expected key: {key})")
        return errors

    entries = train_sample[key]
    if not isinstance(entries, list) or len(entries) == 0:
        errors.append(f"Custom tool '{key}' has no recorded entries")
        return errors

    first_entry = entries[0]
    if not isinstance(first_entry, list) or len(first_entry) < 2:
        errors.append(f"Custom tool '{key}' entry should be list of [user_msg, assistant_msg, ...]")

    return errors
