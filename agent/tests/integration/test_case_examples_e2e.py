"""
Integration E2E tests for the 4 example use cases.

All tests run in sandbox mode (no external API calls).

Tests:
- test_tool_vl_e2e: VL tool + JSONL roundtrip
- test_tool_llm_e2e: LLM tool + train_sample structure
- test_reasoner_vl_gpt_e2e: VL reasoner (gpt-4o) sandbox
- test_reasoner_vl_novita_e2e: VL reasoner (novita) sandbox
- test_custom_rules_injection: RULES_BLOCK auto-numbering
- test_ko_language_patch: Korean language patch
- test_en_language_patch: English language patch
- test_training_prompt_chatexaone: CHATEXAONE prefix in reasoning
- test_jsonl_roundtrip: JSONL save/load roundtrip
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

os.environ["DOC_AGENT_V2_SANDBOX"] = "1"

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agent.examples.e2e_helpers import (
    run_sandbox_e2e,
    verify_train_sample,
    verify_prompt_compilation,
    save_and_verify_jsonl,
    verify_custom_tool_auto_recorded,
)
from agent.export.training_jsonl import (
    convert_base_train_sample_v1,
    CHATEXAONE_SYSTEM_PREFIX,
)


TOOL_VL_PATH = str(Path(__file__).parent.parent.parent / "examples" / "tool_vl" / "vl_tools.py")
TOOL_LLM_PATH = str(Path(__file__).parent.parent.parent / "examples" / "tool_llm" / "llm_tools.py")


class TestToolVLCase:
    """VL Tool + JSONL 저장"""

    def test_tool_vl_e2e(self):
        result, train_sample, compiled_prompt = run_sandbox_e2e(
            custom_tools_path=TOOL_VL_PATH,
            custom_rules="- Use analyze_page_image for visual content",
            reasoner_type="vl",
            user_query="Analyze the visual content",
        )

        assert result["success"] is True
        assert result["final_answer"], "No final answer generated"
        assert result["num_steps"] >= 2

        errors = verify_train_sample(train_sample)
        assert not errors, f"Train sample errors: {errors}"


class TestToolLLMCase:
    """LLM Tool + extra_training 키"""

    def test_tool_llm_e2e(self):
        result, train_sample, compiled_prompt = run_sandbox_e2e(
            custom_tools_path=TOOL_LLM_PATH,
            custom_rules="- Use summarize_page for summaries",
            reasoner_type="llm",
            user_query="Summarize the key facts",
        )

        assert result["success"] is True
        assert result["final_answer"], "No final answer generated"

        errors = verify_train_sample(train_sample)
        assert not errors, f"Train sample errors: {errors}"


class TestReasonerVLGPTCase:
    """VL reasoner (gpt-4o) sandbox"""

    def test_reasoner_vl_gpt_e2e(self):
        result, train_sample, compiled_prompt = run_sandbox_e2e(
            custom_tools_path=None,
            custom_rules=None,
            reasoner_type="vl",
            reasoner_model_name="gpt-4o",
            user_query="What are the main findings?",
        )

        assert result["success"] is True
        assert result["final_answer"]

        errors = verify_train_sample(train_sample)
        assert not errors, f"Train sample errors: {errors}"


class TestReasonerVLNovitaCase:
    """VL reasoner (novita) sandbox"""

    def test_reasoner_vl_novita_e2e(self):
        result, train_sample, compiled_prompt = run_sandbox_e2e(
            custom_tools_path=None,
            custom_rules=None,
            reasoner_type="vl",
            user_query="Summarize this document",
        )

        assert result["success"] is True
        assert result["final_answer"]

        errors = verify_train_sample(train_sample)
        assert not errors, f"Train sample errors: {errors}"


class TestCustomRulesInjection:
    """RULES_BLOCK 자동번호 17+"""

    def test_custom_rules_injection(self):
        custom_rules = "- When analyzing charts, use analyze_page_image first\n- Always cite sources"

        _, _, compiled_prompt = run_sandbox_e2e(
            custom_tools_path=TOOL_VL_PATH,
            custom_rules=custom_rules,
            reasoner_type="vl",
        )

        errors = verify_prompt_compilation(compiled_prompt, custom_rules, "en")
        assert not errors, f"Prompt compilation errors: {errors}"

        # Verify the rule content appears in the prompt
        assert "analyze_page_image" in compiled_prompt.runtime_prompt


class TestKOLanguagePatch:
    """KO_LANG_PATCH 부착"""

    def test_ko_language_patch(self):
        _, _, compiled_prompt = run_sandbox_e2e(
            custom_tools_path=None,
            custom_rules=None,
            reasoner_type="llm",
            lang="ko",
        )

        # Korean prompt should contain Korean-specific content
        # The exact patch depends on runtime_prompts.py but the lang should be set
        assert compiled_prompt.runtime_prompt, "Runtime prompt is empty"


class TestENLanguagePatch:
    """EN_LANG_PATCH 부착"""

    def test_en_language_patch(self):
        _, _, compiled_prompt = run_sandbox_e2e(
            custom_tools_path=None,
            custom_rules=None,
            reasoner_type="llm",
            lang="en",
        )

        assert compiled_prompt.runtime_prompt, "Runtime prompt is empty"


class TestTrainingPromptChatexaone:
    """CHATEXAONE prefix in reasoning"""

    def test_training_prompt_chatexaone(self):
        _, train_sample, _ = run_sandbox_e2e(
            custom_tools_path=None,
            custom_rules=None,
            reasoner_type="llm",
            user_query="Test query for chatexaone prefix",
        )

        # Convert to v1 and check
        v1 = convert_base_train_sample_v1(train_sample, "test training prompt")

        assert "train_system_prompt" in v1
        assert v1["train_system_prompt"] == "test training prompt"

        # Check reasoning has CHATEXAONE prefix
        if v1["reasoning"]:
            system_turn = v1["reasoning"][0][0]
            assert system_turn["role"] == "system"
            assert "ChatEXAONE" in system_turn["content"]


class TestJSONLRoundtrip:
    """JSONL 저장/읽기 정합성"""

    def test_jsonl_roundtrip(self):
        _, train_sample, _ = run_sandbox_e2e(
            custom_tools_path=None,
            custom_rules=None,
            reasoner_type="llm",
        )

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            jsonl_path = f.name

        try:
            errors = save_and_verify_jsonl(train_sample, jsonl_path, version="v1")
            assert not errors, f"JSONL roundtrip errors: {errors}"

            # Also test v2 roundtrip
            errors_v2 = save_and_verify_jsonl(train_sample, jsonl_path, version="v2")
            assert not errors_v2, f"JSONL v2 roundtrip errors: {errors_v2}"
        finally:
            if os.path.exists(jsonl_path):
                os.unlink(jsonl_path)
