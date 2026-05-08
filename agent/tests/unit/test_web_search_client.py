"""Unit tests for WebSearchClient."""

import json
import pytest
from unittest.mock import patch, MagicMock

from agent.core.web_search_client import (
    WebSearchClient,
    PageContent,
    _is_korean,
)


# ── Fixtures ─────────────────────────────────────────────────

SAMPLE_PASSAGES = [
    {"Index": 1, "site_name": "Example News", "snippet": "Content about revenue growth...", "url": "https://example.com/1"},
    {"Index": 2, "site_name": "Tech Report", "snippet": "Technology trends analysis...", "url": "https://example.com/2"},
    {"Index": 3, "site_name": "Finance", "snippet": "Market analysis for Q4...", "url": "https://example.com/3"},
]

SAMPLE_MANAGER_RESULT = {
    "llm": {
        "tool": json.dumps({
            "검색결과": [
                {"사이트명": "뉴스1", "내용": "LG전자 실적 발표", "link": "https://news.com/1"},
                {"사이트명": "뉴스2", "내용": "삼성전자 전망", "link": "https://news.com/2"},
            ]
        })
    }
}

SAMPLE_SERPAPI_RESPONSE = {
    "result": {
        "results": [
            {"사이트명": "Site A", "내용": "Content A", "link": "https://a.com"},
            {"사이트명": "Site B", "내용": "Content B", "link": "https://b.com"},
        ]
    }
}


# ── _is_korean ───────────────────────────────────────────────

class TestIsKorean:
    def test_korean_text(self):
        assert _is_korean("한국어 텍스트") is True

    def test_english_text(self):
        assert _is_korean("English text") is False

    def test_mixed_text(self):
        assert _is_korean("Hello 세계") is True

    def test_empty(self):
        assert _is_korean("") is False
        assert _is_korean(None) is False


# ── WebSearchClient Cache ────────────────────────────────────

class TestWebSearchClientCache:
    def test_populate_and_read(self):
        client = WebSearchClient()
        injected = client._populate_cache(SAMPLE_PASSAGES)
        assert injected == 3

        # Read from cache
        pc = client.jina_read_page("https://example.com/1")
        assert pc.success is True
        assert pc.content == "Content about revenue growth..."

    def test_cache_miss(self):
        client = WebSearchClient()
        pc = client.jina_read_page("https://nonexistent.com")
        assert pc.success is False
        assert pc.error == "Not cached"

    def test_read_multiple_pages(self):
        client = WebSearchClient()
        client._populate_cache(SAMPLE_PASSAGES)

        urls = ["https://example.com/1", "https://example.com/2", "https://missing.com"]
        results = client.read_multiple_pages(urls, parallel=False)

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is True
        assert results[2].success is False

    def test_cache_management(self):
        client = WebSearchClient()
        client._populate_cache(SAMPLE_PASSAGES)

        assert client.cache_size == 3
        assert client.is_cached("https://example.com/1") is True
        assert client.get_cached_content("https://example.com/1") == "Content about revenue growth..."

        client.clear_cache()
        assert client.cache_size == 0

    def test_populate_skips_empty(self):
        client = WebSearchClient()
        passages = [
            {"Index": 1, "url": "", "snippet": "no url"},
            {"Index": 2, "url": "https://a.com", "snippet": ""},
            {"Index": 3, "url": "https://b.com", "snippet": "has both"},
        ]
        injected = client._populate_cache(passages)
        assert injected == 1  # Only the last one has both url and snippet


# ── Manager parsing ──────────────────────────────────────────

class TestManagerParsing:
    def test_parse_manager_results(self):
        client = WebSearchClient()
        passages = client._parse_manager_results(SAMPLE_MANAGER_RESULT)

        assert len(passages) == 2
        assert passages[0]["site_name"] == "뉴스1"
        assert passages[0]["snippet"] == "LG전자 실적 발표"
        assert passages[0]["url"] == "https://news.com/1"
        assert passages[0]["Index"] == 1

    def test_parse_manager_empty_tool(self):
        client = WebSearchClient()
        result = client._parse_manager_results({"llm": {"tool": ""}})
        assert result == []

    def test_parse_manager_invalid_json(self):
        client = WebSearchClient()
        result = client._parse_manager_results({"llm": {"tool": "not json"}})
        assert result == []


# ── SerpAPI parsing ──────────────────────────────────────────

class TestSerpAPIParsing:
    def test_parse_serpapi_basic(self):
        client = WebSearchClient()
        passages = client._parse_serpapi(SAMPLE_SERPAPI_RESPONSE)

        assert len(passages) == 2
        assert passages[0]["site_name"] == "Site A"
        assert passages[0]["snippet"] == "Content A"
        assert passages[0]["url"] == "https://a.com"

    def test_parse_serpapi_list_format(self):
        """Supports {"result": [{"results": [...]}]} format."""
        client = WebSearchClient()
        raw = {"result": [{"results": [{"사이트명": "X", "내용": "Y", "link": "https://x.com"}]}]}
        passages = client._parse_serpapi(raw)

        assert len(passages) == 1
        assert passages[0]["site_name"] == "X"

    def test_parse_serpapi_empty(self):
        client = WebSearchClient()
        assert client._parse_serpapi({}) == []
        assert client._parse_serpapi({"result": []}) == []


# ── search_web (mocked) ─────────────────────────────────────

class TestSearchWeb:
    @patch.object(WebSearchClient, "_search_via_manager")
    def test_manager_primary(self, mock_manager):
        mock_manager.return_value = SAMPLE_PASSAGES

        client = WebSearchClient()
        results = client.search_web("test query")

        assert len(results) == 3
        assert client.cache_size == 3  # Cache populated
        mock_manager.assert_called_once()

    @patch.object(WebSearchClient, "_call_serpapi")
    @patch.object(WebSearchClient, "_search_via_manager")
    def test_serpapi_fallback(self, mock_manager, mock_serpapi):
        mock_manager.return_value = []  # Manager fails
        mock_serpapi.return_value = SAMPLE_SERPAPI_RESPONSE

        client = WebSearchClient(serpapi_key="test-key")
        results = client.search_web("test query")

        assert len(results) == 2  # SerpAPI results
        mock_manager.assert_called_once()
        mock_serpapi.assert_called_once()

    @patch.object(WebSearchClient, "_search_via_manager")
    def test_no_serpapi_key(self, mock_manager):
        mock_manager.return_value = []

        client = WebSearchClient(serpapi_key="")
        results = client.search_web("test query")

        assert results == []  # Both fail, no serpapi key

    @patch.object(WebSearchClient, "_search_via_manager")
    def test_count_limit(self, mock_manager):
        many_passages = [{"Index": i, "site_name": f"S{i}", "snippet": f"C{i}", "url": f"https://{i}.com"} for i in range(1, 21)]
        mock_manager.return_value = many_passages

        client = WebSearchClient()
        results = client.search_web("test", count=5)

        assert len(results) == 5


# ── Manager call (mocked) ───────────────────────────────────

class TestManagerCall:
    @patch("agent.core.web_search_client.requests.post")
    def test_call_manager_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = json.dumps({
            "outputs": [json.dumps({"main_paragraph": str(SAMPLE_MANAGER_RESULT)})]
        }).encode("utf-8")
        mock_post.return_value = mock_resp

        client = WebSearchClient()
        status, result = client._call_manager("test query")

        assert status == 200

    @patch("agent.core.web_search_client.requests.post")
    def test_search_via_manager_retry(self, mock_post):
        """Should retry on failure."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.content = b'{"error": "internal"}'
        mock_post.return_value = mock_resp

        client = WebSearchClient()
        results = client._search_via_manager("test", max_retries=1)
        assert results == []


# ── SerpAPI call (mocked) ───────────────────────────────────

class TestSerpAPICall:
    @patch("agent.core.web_search_client.requests.post")
    def test_call_serpapi_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_SERPAPI_RESPONSE
        mock_post.return_value = mock_resp

        client = WebSearchClient(serpapi_key="test-key")
        result = client._call_serpapi("test query")

        assert result == SAMPLE_SERPAPI_RESPONSE

    def test_call_serpapi_no_key(self):
        client = WebSearchClient(serpapi_key="")
        result = client._call_serpapi("test query")
        assert result is None

    @patch("agent.core.web_search_client.requests.post")
    def test_call_serpapi_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        client = WebSearchClient(serpapi_key="test-key")
        result = client._call_serpapi("test query")
        assert result is None
