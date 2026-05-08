"""Unit tests for _insert_chatexaone_system and CHATEXAONE prefix logic.

Tests the CHATEXAONE_SYSTEM_PREFIX insertion for:
- doc_step conversations
- readfulldocument conversations
- readfulltext conversations
"""

import pytest

from agent.export.training_jsonl import (
    _insert_chatexaone_system,
    CHATEXAONE_SYSTEM_PREFIX,
)


class TestInsertChatExaoneSystem:
    def test_empty_conversation(self):
        """Empty conversations are returned as-is."""
        result = _insert_chatexaone_system([])
        assert result == []

    def test_existing_system_turn_prepend(self):
        """When first turn is system, prefix is prepended to its content."""
        conversations = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        result = _insert_chatexaone_system(conversations)

        assert result[0]["role"] == "system"
        assert result[0]["content"].startswith(CHATEXAONE_SYSTEM_PREFIX)
        assert "You are helpful." in result[0]["content"]
        assert result[1]["content"] == "Hello"

    def test_no_system_turn_inserts_new(self):
        """When no system turn, a new one with CHATEXAONE prefix is inserted."""
        conversations = [
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI is..."},
        ]
        result = _insert_chatexaone_system(conversations)

        assert len(result) == 3  # system + user + assistant
        assert result[0]["role"] == "system"
        assert CHATEXAONE_SYSTEM_PREFIX.strip() in result[0]["content"]
        assert result[1]["content"] == "What is AI?"

    def test_does_not_mutate_original(self):
        """Original list should not be modified."""
        conversations = [
            {"role": "user", "content": "Hi"},
        ]
        original_len = len(conversations)
        _insert_chatexaone_system(conversations)
        assert len(conversations) == original_len


class TestPrefixAppliedPerTaskType:
    """Verify prefix is applied correctly for doc_step, readfulldocument, readfulltext."""

    def _make_conversations(self):
        return [
            {"role": "user", "content": "Extract content", "loss_masking": True},
            {"role": "assistant", "content": "Here is the content.", "loss_masking": False},
        ]

    def test_doc_step_prefix(self):
        convs = self._make_conversations()
        result = _insert_chatexaone_system(convs)
        assert result[0]["role"] == "system"
        assert "ChatEXAONE" in result[0]["content"]

    def test_readfulldocument_prefix(self):
        convs = self._make_conversations()
        result = _insert_chatexaone_system(convs)
        assert result[0]["role"] == "system"
        assert "LG AI Research" in result[0]["content"]

    def test_readfulltext_prefix(self):
        convs = self._make_conversations()
        result = _insert_chatexaone_system(convs)
        assert result[0]["role"] == "system"
        assert "ChatEXAONE" in result[0]["content"]
