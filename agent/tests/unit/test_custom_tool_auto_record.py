"""
Unit tests for custom tool auto-recording.

Tests:
- builder records custom tool
- builder records builtin tool (unchanged)
- is_custom_tool() classification
- v1 format: 7 keys + train_system_prompt + custom keys
- v1 has train_system_prompt
- v1 reasoning has CHATEXAONE prefix
- v2 format: v1 + metadata fields
"""
import json
import os
import pytest

os.environ["DOC_AGENT_V2_SANDBOX"] = "1"

from agent.domain.training.builder import TrainingSampleBuilder
from agent.domain.reasoning.events import ToolExtractionCompleted
from agent.core.tool_registry import ToolRegistry
from agent.export.training_jsonl import (
    convert_base_train_sample_v1,
    convert_base_train_sample,
    CHATEXAONE_SYSTEM_PREFIX,
)


class TestBuilderRecordsCustomTool:
    """builder가 커스텀 Tool 기록"""

    def test_builder_records_custom_tool(self):
        builder = TrainingSampleBuilder("test query", ["doc.json"])
        builder.record_extraction(ToolExtractionCompleted(
            tool_name="analyze_page_image",
            messages=[{"role": "user", "content": "analyze page 1"}],
            result="VL analysis result",
        ))
        sample = builder.build()

        assert "analyze_page_image" in sample
        assert len(sample["analyze_page_image"]) == 1
        entry = sample["analyze_page_image"][0]
        assert entry[0]["role"] == "user"
        assert entry[0]["content"] == "analyze page 1"
        assert entry[0]["loss_masking"] is True
        assert entry[1]["role"] == "assistant"
        assert entry[1]["content"] == "VL analysis result"
        assert entry[1]["loss_masking"] is False


class TestBuilderRecordsBuiltinTool:
    """기존 builtin Tool 기록 유지"""

    def test_builder_records_builtin_tool(self):
        builder = TrainingSampleBuilder("test query", ["doc.json"])
        builder.record_extraction(ToolExtractionCompleted(
            tool_name="ReadFullDocument",
            messages=[{"role": "user", "content": "read doc 1"}],
            result="Document content here",
        ))
        sample = builder.build()

        assert "readfulldocument" in sample
        assert len(sample["readfulldocument"]) == 1
        entry = sample["readfulldocument"][0]
        assert entry[0]["content"] == "read doc 1"
        assert entry[1]["content"] == "Document content here"

    def test_builder_records_readfulltext(self):
        builder = TrainingSampleBuilder("test query", ["doc.json"])
        builder.record_extraction(ToolExtractionCompleted(
            tool_name="ReadFullText",
            messages=[{"role": "user", "content": "read text"}],
            result="Text content here",
        ))
        sample = builder.build()

        assert "readfulltext" in sample
        assert len(sample["readfulltext"]) == 1


class TestIsCustomTool:
    """is_custom_tool() 분류 정확성"""

    def test_is_custom_tool(self):
        registry = ToolRegistry(include_builtin=True)

        # Builtin tools are NOT custom
        assert registry.is_custom_tool("search") is False
        assert registry.is_custom_tool("ReadFullDocument") is False
        assert registry.is_custom_tool("ReadFullText") is False
        assert registry.is_custom_tool("GetPage") is False

        # Unregistered tool is not custom (not in registry)
        assert registry.is_custom_tool("nonexistent") is False

    def test_custom_tool_after_registration(self):
        """After loading a custom tool, is_custom_tool returns True."""
        registry = ToolRegistry(include_builtin=True)

        # Create a minimal tool class
        class FakeTool:
            name = "my_custom_tool"
            description = "A test tool"
            parameters = {"type": "object", "properties": {}}
            tool_type = "inference"
            def execute(self, args, context):
                return "result"

        registry.register(FakeTool())
        assert registry.is_custom_tool("my_custom_tool") is True
        assert registry.is_custom_tool("search") is False


class TestV1Format:
    """v1: 7키 + train_system_prompt + 커스텀키"""

    def _make_base_sample(self):
        return {
            "df_idx": 0,
            "user_query": "test query",
            "filenames": ["doc.json"],
            "reasoning": [[
                {"role": "system", "content": "runtime prompt...", "loss_masking": True},
                {"role": "user", "content": "question", "loss_masking": True},
                {"role": "assistant", "content": "answer", "loss_masking": False},
            ]],
            "readfulldocument": [],
            "readfulltext": [],
            "doc_step": [
                {"role": "user", "content": "summarize", "loss_masking": True},
                {"role": "assistant", "content": "summary", "loss_masking": False},
            ],
            "analyze_page_image": [[
                {"role": "user", "content": "analyze args", "loss_masking": True},
                {"role": "assistant", "content": "vl result", "loss_masking": False},
            ]],
        }

    def test_v1_format_default(self):
        base = self._make_base_sample()
        result = convert_base_train_sample_v1(base, "training system prompt")

        # 7 base keys + train_system_prompt + custom key
        assert "df_idx" in result
        assert "user_query" in result
        assert "filenames" in result
        assert "reasoning" in result
        assert "readfulldocument" in result
        assert "readfulltext" in result
        assert "doc_step" in result
        assert "train_system_prompt" in result
        assert "analyze_page_image" in result

        # No v2 metadata
        assert "version" not in result
        assert "runtime_prompt_hash" not in result
        assert "session_id" not in result
        assert "timestamp" not in result

    def test_v1_has_train_system_prompt(self):
        base = self._make_base_sample()
        result = convert_base_train_sample_v1(base, "my training prompt")
        assert result["train_system_prompt"] == "my training prompt"

    def test_v1_chatexaone_in_reasoning(self):
        base = self._make_base_sample()
        result = convert_base_train_sample_v1(base, "my training prompt")

        # reasoning system turn should have CHATEXAONE prefix + train_system_prompt
        system_turn = result["reasoning"][0][0]
        assert system_turn["role"] == "system"
        assert "ChatEXAONE" in system_turn["content"]
        assert "my training prompt" in system_turn["content"]

    def test_v1_chatexaone_in_doc_step(self):
        base = self._make_base_sample()
        result = convert_base_train_sample_v1(base, "my training prompt")

        # doc_step should have chatexaone system turn prepended
        assert result["doc_step"][0]["role"] == "system"
        assert "ChatEXAONE" in result["doc_step"][0]["content"]

    def test_v1_chatexaone_in_custom_tool(self):
        base = self._make_base_sample()
        result = convert_base_train_sample_v1(base, "my training prompt")

        # custom tool key should have chatexaone system turn
        custom_entries = result["analyze_page_image"]
        assert len(custom_entries) == 1
        first_entry = custom_entries[0]
        assert first_entry[0]["role"] == "system"
        assert "ChatEXAONE" in first_entry[0]["content"]


class TestV2Format:
    """v2: v1 + 메타데이터 필드"""

    def test_v2_format_admin(self):
        base = {
            "df_idx": 0,
            "user_query": "test",
            "filenames": ["doc.json"],
            "reasoning": [],
            "readfulldocument": [],
            "readfulltext": [],
            "doc_step": [],
        }
        result = convert_base_train_sample(
            base, "training prompt",
            runtime_prompt_hash="abc123",
            language="ENGLISH",
        )
        d = result.to_dict()

        # v2 should have all v1 keys + metadata
        assert "version" in d
        assert "runtime_prompt_hash" in d
        assert "session_id" in d
        assert "language" in d
        assert "timestamp" in d
        assert "train_system_prompt" in d
        assert d["runtime_prompt_hash"] == "abc123"
