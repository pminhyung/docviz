"""Unit tests for SelectorClient."""

import json
import threading
import time
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from agent.core.selector_client import (
    SelectorClient,
    SELECTOR_URLS,
    _next_url,
    parse_context_text,
    pages_to_evidences,
    call_selector,
    parse_selector_outputs,
    select_top_k,
)


# ── Fixtures ─────────────────────────────────────────────────

SAMPLE_PAGES = [
    {"Index": 1, "filename": "report.pdf", "page": 1, "content": "Revenue was $10B in 2024."},
    {"Index": 2, "filename": "report.pdf", "page": 2, "content": "Operating profit reached $1.5B."},
    {"Index": 3, "filename": "report.pdf", "page": 3, "content": "R&D spending was $500M."},
    {"Index": 4, "filename": "report.pdf", "page": 4, "content": "Market share grew 5%."},
    {"Index": 5, "filename": "report.pdf", "page": 5, "content": "Employee count: 50,000."},
]

SAMPLE_SCORES = [
    {"score": 0.9},    # idx 0 → pages[0]
    {"score": 0.85},   # idx 1 → pages[1]
    {"score": 0.7},    # idx 2 → pages[2]
    {"score": 0.5},    # idx 3 → pages[3]
    {"score": 0.3},    # idx 4 → pages[4]
]


# ── parse_context_text ───────────────────────────────────────

class TestParseContextText:
    def test_empty_string(self):
        assert parse_context_text("") == [""]

    def test_plain_text(self):
        result = parse_context_text("Hello world")
        assert result == ["Hello world"]

    def test_json_list(self):
        result = parse_context_text('["a", "b", "c"]')
        assert result == ["a", "b", "c"]

    def test_json_dict(self):
        result = parse_context_text('{"key": "val"}')
        assert result == [{"key": "val"}]

    def test_wrapped_brace_parsing(self):
        result = parse_context_text('"key": ["a", "b"]')
        assert result == ["a", "b"]


# ── pages_to_evidences ───────────────────────────────────────

class TestPagesToEvidences:
    def test_basic_conversion(self):
        evidences = pages_to_evidences(SAMPLE_PAGES)
        assert len(evidences) == 5
        assert evidences[0]["page"] == 1  # original page number from SAMPLE_PAGES
        assert evidences[0]["type"] == "doc"
        assert isinstance(evidences[0]["context"], list)

    def test_empty_pages(self):
        assert pages_to_evidences([]) == []

    def test_skips_non_dict(self):
        pages = [SAMPLE_PAGES[0], "not a dict", SAMPLE_PAGES[1]]
        evidences = pages_to_evidences(pages)
        assert len(evidences) == 2

    def test_missing_content(self):
        pages = [{"filename": "test.pdf", "page": 1}]
        evidences = pages_to_evidences(pages)
        assert len(evidences) == 1
        assert evidences[0]["context"] == [""]

    def test_content_key_fallback(self):
        """Should try 'content', 'context', 'html_context' keys."""
        pages = [{"context": "from context key"}]
        evidences = pages_to_evidences(pages)
        assert "from context key" in evidences[0]["context"]


# ── parse_selector_outputs ───────────────────────────────────

class TestParseSelectorOutputs:
    def test_flat_list(self):
        raw = {"outputs": [SAMPLE_SCORES]}
        result = parse_selector_outputs(raw)
        assert result == SAMPLE_SCORES

    def test_nested_list(self):
        raw = {"outputs": [[SAMPLE_SCORES]]}
        result = parse_selector_outputs(raw)
        assert result == SAMPLE_SCORES

    def test_missing_outputs(self):
        assert parse_selector_outputs({}) is None
        assert parse_selector_outputs({"outputs": []}) is None

    def test_non_list_first(self):
        raw = {"outputs": ["not a list"]}
        assert parse_selector_outputs(raw) is None


# ── select_top_k ─────────────────────────────────────────────

class TestSelectTopK:
    def test_basic_top_k(self):
        result = select_top_k(SAMPLE_PAGES, SAMPLE_SCORES, select_num=3)
        assert len(result) == 3
        # Verify descending score order (position-based: idx 0=0.9, idx 1=0.85, idx 2=0.7)
        assert result[0]["page"] == 1  # score 0.9, idx 0 -> pages[0] -> page 1
        assert result[1]["page"] == 2  # score 0.85, idx 1 -> pages[1] -> page 2
        assert result[2]["page"] == 3  # score 0.7, idx 2 -> pages[2] -> page 3

    def test_reindex(self):
        result = select_top_k(SAMPLE_PAGES, SAMPLE_SCORES, select_num=3)
        assert result[0]["Index"] == 1
        assert result[1]["Index"] == 2
        assert result[2]["Index"] == 3

    def test_has_required_keys(self):
        result = select_top_k(SAMPLE_PAGES, SAMPLE_SCORES, select_num=2)
        required = {"Index", "filename", "page", "content"}
        for item in result:
            assert required.issubset(set(item.keys()))

    def test_empty_scores(self):
        assert select_top_k(SAMPLE_PAGES, []) == []

    def test_min_score_filter(self):
        result = select_top_k(SAMPLE_PAGES, SAMPLE_SCORES, select_num=10, min_score=0.6)
        # Only scores > 0.6: 0.9 (idx 0), 0.85 (idx 1), 0.7 (idx 2)
        assert len(result) == 3

    def test_select_num_limit(self):
        result = select_top_k(SAMPLE_PAGES, SAMPLE_SCORES, select_num=1)
        assert len(result) == 1

    def test_overflow_scores_ignored(self):
        """Scores beyond pages length are ignored (position-based)."""
        pages = [SAMPLE_PAGES[0]]  # only 1 page
        scores = [{"score": 0.9}, {"score": 0.8}, {"score": 0.7}]  # 3 scores
        result = select_top_k(pages, scores, select_num=5)
        assert len(result) == 1  # Only idx 0 is valid


# ── call_selector (mocked) ───────────────────────────────────

class TestCallSelector:
    @patch("agent.core.selector_client._get_session")
    def test_success(self, mock_get_session):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"outputs": [SAMPLE_SCORES]}
        mock_session.post.return_value = mock_resp
        mock_get_session.return_value = mock_session

        result = call_selector("test query", [{"page": 0, "context": ["text"], "type": "doc"}])
        assert result == {"outputs": [SAMPLE_SCORES]}

    @patch("agent.core.selector_client._get_session")
    def test_non_retriable_failure(self, mock_get_session):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_session.post.return_value = mock_resp
        mock_get_session.return_value = mock_session

        result = call_selector("test", [{"page": 0, "context": ["t"], "type": "doc"}], max_retries=1)
        assert result is None

    @patch("agent.core.selector_client._get_session")
    def test_connection_error(self, mock_get_session):
        import requests as req
        mock_session = MagicMock()
        mock_session.post.side_effect = req.exceptions.ConnectionError("Connection refused")
        mock_get_session.return_value = mock_session

        result = call_selector("test", [{"page": 0, "context": ["t"], "type": "doc"}], max_retries=1)
        assert result is None

    @patch("agent.core.selector_client._get_session")
    def test_retriable_status_retries(self, mock_get_session):
        """500 should be retried up to max_retries."""
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_session.post.return_value = mock_resp
        mock_get_session.return_value = mock_session

        result = call_selector(
            "test", [{"page": 0, "context": ["t"], "type": "doc"}],
            max_retries=3,
        )
        assert result is None
        # 3 retries -> max_retries+1 = 4 attempts
        assert mock_session.post.call_count == 4

    @patch("agent.core.selector_client._get_session")
    def test_retry_then_success(self, mock_get_session):
        """First call 500, second call 200 -> success."""
        mock_session = MagicMock()
        fail_resp = MagicMock()
        fail_resp.status_code = 500
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"outputs": [SAMPLE_SCORES]}
        mock_session.post.side_effect = [fail_resp, ok_resp]
        mock_get_session.return_value = mock_session

        result = call_selector(
            "test", [{"page": 0, "context": ["t"], "type": "doc"}],
            max_retries=3,
        )
        assert result == {"outputs": [SAMPLE_SCORES]}
        assert mock_session.post.call_count == 2

    @patch("agent.core.selector_client.TOTAL_BUDGET", 0.0)
    @patch("agent.core.selector_client._get_session")
    def test_total_budget_exceeded(self, mock_get_session):
        """Should stop retrying when total budget is exhausted."""
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_session.post.return_value = mock_resp
        mock_get_session.return_value = mock_session

        result = call_selector(
            "test", [{"page": 0, "context": ["t"], "type": "doc"}],
            max_retries=8,
        )
        assert result is None
        # With 0 budget, should not even make a single call
        assert mock_session.post.call_count == 0


# ── Round-robin load balancing ─────────────────────────────────

class TestRoundRobinLB:
    def test_next_url_rotates(self):
        """_next_url should cycle through SELECTOR_URLS."""
        urls = [_next_url() for _ in range(len(SELECTOR_URLS) * 2)]
        # Each URL should appear at least once
        for u in SELECTOR_URLS:
            assert u in urls

    def test_selector_urls_no_gw_stg(self):
        """Default SELECTOR_URLS should NOT contain gw-stg."""
        for u in SELECTOR_URLS:
            assert "gw-stg" not in u, f"gw-stg found in SELECTOR_URLS: {u}"

    def test_selector_urls_contains_expected(self):
        """Default SELECTOR_URLS should contain gw-qa and gw-dev."""
        all_urls = " ".join(SELECTOR_URLS)
        assert "gw-qa" in all_urls
        assert "gw-dev" in all_urls

    @patch("agent.core.selector_client._get_session")
    def test_retry_rotates_urls(self, mock_get_session):
        """On retriable failure, retries should use different URLs."""
        mock_session = MagicMock()
        fail_resp = MagicMock()
        fail_resp.status_code = 500
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"outputs": [SAMPLE_SCORES]}
        mock_session.post.side_effect = [fail_resp, ok_resp]
        mock_get_session.return_value = mock_session

        result = call_selector(
            "test", [{"page": 0, "context": ["t"], "type": "doc"}],
            max_retries=3,
        )
        assert result == {"outputs": [SAMPLE_SCORES]}

        # Two calls should have been made to (potentially) different URLs
        called_urls = [call.args[0] for call in mock_session.post.call_args_list]
        assert len(called_urls) == 2
        # With 2 URLs in pool, consecutive calls should rotate
        if len(SELECTOR_URLS) > 1:
            assert called_urls[0] != called_urls[1]

    @patch("agent.core.selector_client._get_session")
    def test_explicit_url_skips_rotation(self, mock_get_session):
        """When url= is explicitly provided, all retries use that URL."""
        mock_session = MagicMock()
        fail_resp = MagicMock()
        fail_resp.status_code = 500
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"outputs": [SAMPLE_SCORES]}
        mock_session.post.side_effect = [fail_resp, ok_resp]
        mock_get_session.return_value = mock_session

        fixed_url = "http://custom-selector.example.com/base"
        result = call_selector(
            "test", [{"page": 0, "context": ["t"], "type": "doc"}],
            url=fixed_url, max_retries=3,
        )
        assert result == {"outputs": [SAMPLE_SCORES]}

        called_urls = [call.args[0] for call in mock_session.post.call_args_list]
        assert all(u == fixed_url for u in called_urls)


# ── Semaphore backpressure ────────────────────────────────────

class TestSemaphoreBackpressure:
    @patch("agent.core.selector_client._get_session")
    def test_semaphore_released_on_success(self, mock_get_session):
        """Semaphore must be released after successful call."""
        from agent.core.selector_client import _SEMAPHORE, MAX_INFLIGHT

        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"outputs": [SAMPLE_SCORES]}
        mock_session.post.return_value = mock_resp
        mock_get_session.return_value = mock_session

        # Acquire all-but-one slots to detect leak
        held = []
        for _ in range(MAX_INFLIGHT - 1):
            _SEMAPHORE.acquire()
            held.append(True)

        try:
            # This should acquire the last slot and release it
            call_selector("test", [{"page": 0, "context": ["t"], "type": "doc"}])

            # If semaphore was released, we can acquire again
            acquired = _SEMAPHORE.acquire(blocking=False)
            assert acquired, "Semaphore was not released after successful call"
            _SEMAPHORE.release()
        finally:
            for _ in held:
                _SEMAPHORE.release()

    @patch("agent.core.selector_client._get_session")
    def test_semaphore_released_on_exception(self, mock_get_session):
        """Semaphore must be released even when request raises exception."""
        from agent.core.selector_client import _SEMAPHORE, MAX_INFLIGHT
        import requests as req

        mock_session = MagicMock()
        mock_session.post.side_effect = req.exceptions.ConnectionError("fail")
        mock_get_session.return_value = mock_session

        held = []
        for _ in range(MAX_INFLIGHT - 1):
            _SEMAPHORE.acquire()
            held.append(True)

        try:
            call_selector(
                "test", [{"page": 0, "context": ["t"], "type": "doc"}],
                max_retries=1,
            )

            acquired = _SEMAPHORE.acquire(blocking=False)
            assert acquired, "Semaphore was not released after exception"
            _SEMAPHORE.release()
        finally:
            for _ in held:
                _SEMAPHORE.release()


# ── SelectorClient ───────────────────────────────────────────

class TestSelectorClient:
    @patch("agent.core.selector_client.call_selector")
    def test_select_end_to_end(self, mock_call):
        mock_call.return_value = {"outputs": [SAMPLE_SCORES]}

        client = SelectorClient(select_num=3)
        result = client.select("revenue query", SAMPLE_PAGES)

        assert len(result) == 3
        assert result[0]["Index"] == 1

    @patch("agent.core.selector_client.call_selector")
    def test_select_returns_empty_on_failure(self, mock_call):
        mock_call.return_value = None

        client = SelectorClient()
        result = client.select("query", SAMPLE_PAGES)
        assert result == []

    @patch("agent.core.selector_client.call_selector")
    def test_select_for_doc(self, mock_call):
        mock_call.return_value = {"outputs": [SAMPLE_SCORES]}

        client = SelectorClient(select_num=2)
        multi_docs = [SAMPLE_PAGES]
        filenames = ["report.pdf"]

        result = client.select_for_doc(
            query="revenue",
            reasoning="looking for revenue data",
            multi_docs=multi_docs,
            doc_id=1,
            filenames=filenames,
        )

        assert len(result) == 2
        assert all(r["filename"] == "report.pdf" for r in result)

    @patch("agent.core.selector_client.call_selector")
    def test_select_for_doc_invalid_id(self, mock_call):
        client = SelectorClient()
        result = client.select_for_doc("q", "", [[]], 5, ["f1"])
        assert result == []
