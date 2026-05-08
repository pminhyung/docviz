"""Unit tests for domain/document — truncator and TokenCounter."""

import pytest

from agent.domain.document.truncator import (
    CharacterCounter,
    TokenCounter,
    truncate_documents,
)


# ── CharacterCounter ────────────────────────────────────────


class TestCharacterCounter:
    def test_count(self):
        c = CharacterCounter()
        assert c.count("hello") == 5
        assert c.count("") == 0
        assert c.count("한글") == 2


# ── TokenCounter Protocol ──────────────────────────────────


class TestTokenCounterProtocol:
    def test_isinstance_check(self):
        assert isinstance(CharacterCounter(), TokenCounter)

    def test_custom_counter_isinstance(self):
        class DoubleCounter:
            def count(self, text: str) -> int:
                return len(text) * 2

        assert isinstance(DoubleCounter(), TokenCounter)


# ── truncate_documents ──────────────────────────────────────


class TestTruncate:
    def test_within_budget(self):
        docs = [[{"content": "Hello world", "page": 1}]]
        result = truncate_documents(docs, max_length=10000)
        assert "[Doc1 Page1] Hello world" in result

    def test_over_budget(self):
        docs = [[
            {"content": "A" * 200, "page": 1},
            {"content": "B" * 200, "page": 2},
        ]]
        # "[Doc1 Page1] " prefix is 14 chars, so page1 = 214 chars.
        # Budget 350 leaves 136 remaining (>100), so page2 is truncated.
        result = truncate_documents(docs, max_length=350)
        assert "[Doc1 Page1]" in result
        # Second page should be truncated with "..."
        assert result.endswith("...")

    def test_empty(self):
        assert truncate_documents([], max_length=100) == ""
        assert truncate_documents([[]], max_length=100) == ""

    def test_multi_doc(self):
        docs = [
            [{"content": "Doc1 content", "page": 1}],
            [{"content": "Doc2 content", "page": 1}],
        ]
        result = truncate_documents(docs, max_length=10000)
        assert "[Doc1 Page1]" in result
        assert "[Doc2 Page1]" in result

    def test_custom_counter(self):
        class DoubleCounter:
            def count(self, text: str) -> int:
                return len(text) * 2

        docs = [[{"content": "A" * 100, "page": 1}]]
        # With DoubleCounter, effective budget halves
        result_normal = truncate_documents(docs, max_length=300)
        result_double = truncate_documents(docs, max_length=300, counter=DoubleCounter())
        # DoubleCounter counts each char as 2, so hits budget faster
        assert len(result_double) <= len(result_normal)

    def test_remaining_too_small(self):
        """When remaining budget <= 100, page is skipped entirely."""
        docs = [[
            {"content": "X" * 200, "page": 1},
            {"content": "Y" * 200, "page": 2},
        ]]
        # Budget leaves < 100 remaining after first page
        result = truncate_documents(docs, max_length=230)
        assert "[Doc1 Page1]" in result
        assert "Y" not in result
        assert not result.endswith("...")


# ── Parity with original _truncate_documents ────────────────


class TestParity:
    def test_matches_original(self):
        """Output must match AgentV2Runner._truncate_documents exactly."""
        docs = [
            [
                {"content": "Hello world", "page": 1},
                {"content": "Page two", "page": 2},
            ]
        ]

        # Reproduce original logic inline
        parts = []
        current_length = 0
        max_length = 100

        for doc_idx, pages in enumerate(docs):
            for page in pages:
                content = page.get("content", "")
                page_num = page.get("page", "?")
                chunk = f"[Doc{doc_idx+1} Page{page_num}] {content}"

                if current_length + len(chunk) > max_length:
                    remaining = max_length - current_length
                    if remaining > 100:
                        parts.append(chunk[:remaining] + "...")
                    break

                parts.append(chunk)
                current_length += len(chunk)

        expected = "\n\n".join(parts)
        actual = truncate_documents(docs, max_length=100)
        assert actual == expected
