"""Integration tests for extraction event flow (Phase 3).

Tests the full flow:
1. builtin tool appends to _extraction_sink (instead of mutating train_sample)
2. caller harvests sink and converts to ToolExtractionCompleted events
3. builder.record_extraction() records the event
4. convert_base_train_sample() inserts CHATEXAONE prefix
"""

import json
import pytest
from unittest.mock import MagicMock

from agent.core.builtin_tools import ReadFullDocumentTool, ReadFullTextTool
from agent.core.tool_actions import ToolContext
from agent.domain.training.builder import TrainingSampleBuilder
from agent.domain.reasoning.events import ToolExtractionCompleted
from agent.export.training_jsonl import (
    convert_base_train_sample,
    CHATEXAONE_SYSTEM_PREFIX,
)


def _make_mock_router():
    """Create a mock router that returns a predetermined extraction result."""
    mock_router = MagicMock()
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Extracted document content here."
    mock_client.chat.completions.create.return_value = mock_response
    mock_router.get_proxy_client.return_value = mock_client
    return mock_router


class TestExtractionSinkFlow:
    """Test that builtin tools use _extraction_sink instead of direct mutation."""

    def test_readfulldocument_uses_sink(self):
        """ReadFullDocumentTool should append to _extraction_sink, not train_sample."""
        router = _make_mock_router()
        extraction_sink = []
        train_sample = {
            "reasoning": [], "readfulldocument": [], "readfulltext": [], "doc_step": [],
        }

        ctx = ToolContext(
            user_query="What is in the doc?",
            filenames=["test.pdf"],
            multi_docs=[[{"content": "Test content", "page": 1}]],
            image_dir=None,
            language="en",
            current_step=2,
            model_router=router,
            train_sample=train_sample,
            _extraction_sink=extraction_sink,
        )
        ctx_dict = ctx.to_dict()

        tool = ReadFullDocumentTool()
        result = tool.execute({"document_number": [1], "goal": "test"}, ctx_dict)

        # sink should have one entry
        assert len(extraction_sink) == 1
        assert extraction_sink[0]["tool_name"] == "ReadFullDocument"
        assert "messages" in extraction_sink[0]
        assert extraction_sink[0]["result"] == "Extracted document content here."

        # train_sample should NOT be mutated directly
        assert len(train_sample["readfulldocument"]) == 0

    def test_readfulltext_uses_sink(self):
        """ReadFullTextTool should append to _extraction_sink, not train_sample."""
        router = _make_mock_router()

        # Mock web client
        from agent.core.web_search_client import WebSearchClient
        web_client = WebSearchClient()
        web_client._page_cache = {"https://example.com": "Page content"}

        extraction_sink = []
        search_pages = [
            {"Index": 1, "url": "https://example.com", "site_name": "Example"},
        ]
        train_sample = {
            "reasoning": [], "readfulldocument": [], "readfulltext": [], "doc_step": [],
        }

        ctx = ToolContext(
            user_query="What does the page say?",
            filenames=["test.pdf"],
            multi_docs=[[{"content": "Test", "page": 1}]],
            image_dir=None,
            language="en",
            current_step=3,
            model_router=router,
            web_search_client=web_client,
            train_sample=train_sample,
            search_pages=search_pages,
            _extraction_sink=extraction_sink,
        )
        ctx_dict = ctx.to_dict()

        tool = ReadFullTextTool()
        result = tool.execute({"index": [1], "goal": "test"}, ctx_dict)

        # sink should have one entry
        assert len(extraction_sink) == 1
        assert extraction_sink[0]["tool_name"] == "ReadFullText"

        # train_sample should NOT be mutated directly
        assert len(train_sample["readfulltext"]) == 0

    def test_no_sink_no_error(self):
        """When _extraction_sink is None, tool should still work (backward compat)."""
        router = _make_mock_router()

        ctx = ToolContext(
            user_query="What?",
            filenames=["test.pdf"],
            multi_docs=[[{"content": "Test", "page": 1}]],
            image_dir=None,
            language="en",
            current_step=2,
            model_router=router,
            train_sample=None,
            _extraction_sink=None,
        )
        ctx_dict = ctx.to_dict()

        tool = ReadFullDocumentTool()
        result = tool.execute({"document_number": [1]}, ctx_dict)

        assert isinstance(result, str)
        assert len(result) > 0


class TestSinkToBuilderEvent:
    """Test converting sink entries to builder events."""

    def test_sink_to_builder_readfulldocument(self):
        """Sink entries should be convertible to ToolExtractionCompleted events."""
        builder = TrainingSampleBuilder(
            user_query="test query",
            filenames=["doc.pdf"],
        )

        # Simulate what _execute_tool does after tool execution
        sink_entry = {
            "tool_name": "ReadFullDocument",
            "messages": [{"role": "user", "content": "Extract from doc"}],
            "result": "Extracted content",
        }

        event = ToolExtractionCompleted(
            tool_name=sink_entry["tool_name"],
            messages=sink_entry["messages"],
            result=sink_entry["result"],
        )
        builder.record_extraction(event)

        sample = builder.build()
        assert len(sample["readfulldocument"]) == 1
        entry = sample["readfulldocument"][0]
        assert entry[0]["role"] == "user"
        assert entry[0]["loss_masking"] is True
        assert entry[1]["role"] == "assistant"
        assert entry[1]["content"] == "Extracted content"

    def test_full_e2e_with_chatexaone_prefix(self):
        """Full E2E: sink -> builder -> convert_base_train_sample -> CHATEXAONE prefix."""
        builder = TrainingSampleBuilder(
            user_query="test",
            filenames=["f.pdf"],
        )

        # Record extraction via sink pattern
        event = ToolExtractionCompleted(
            tool_name="ReadFullDocument",
            messages=[{"role": "user", "content": "Read all"}],
            result="Document summary",
        )
        builder.record_extraction(event)

        sample = builder.build()

        # Convert to v2 format
        v2 = convert_base_train_sample(
            base_train_sample=sample,
            train_system_prompt="You are a helpful agent.",
            runtime_prompt_hash="abc123",
        )

        # Verify CHATEXAONE prefix is inserted in readfulldocument
        assert len(v2.readfulldocument) == 1
        entry = v2.readfulldocument[0]
        # First turn should be system with CHATEXAONE prefix
        assert entry[0]["role"] == "system"
        assert entry[0]["content"].startswith(CHATEXAONE_SYSTEM_PREFIX.rstrip())
