"""
Web Search Client — Manager primary + SerpAPI fallback

Ported from:
- sft_pipeline/scripts/test_web_search_call.py (Manager + SerpAPI calls)
- sft_pipeline/core/web_search.py (WebSearchClient, cache, jina_read_page)

Provides web search with URL->snippet cache for ReadFullText integration.

Usage:
    client = WebSearchClient(manager_url="http://gw-qa...", serpapi_key="...")
    passages = client.search_web("NVIDIA earnings 2025")
    # ReadFullText can now read cached pages:
    page = client.jina_read_page("https://...")
"""

import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────
DEFAULT_MANAGER_URL = os.environ.get(
    "MANAGER_WEB_SEARCH_URL",
    "http://gw-qa.lgair.net/api/lang/chat-exaone/base",
)
DEFAULT_WEBSEARCH_API_BASE = os.environ.get(
    "WEBSEARCH_API_BASE", "http://localhost:9025"
).rstrip("/")
DEFAULT_WEBSEARCH_ENGINE = os.environ.get("WEBSEARCH_ENGINE", "bing")
DEFAULT_SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "").strip()
DEFAULT_SEARCH_NUM = 10
MAX_CONTENT_LENGTH = 35000


# ── Data models ──────────────────────────────────────────────

@dataclass
class PageContent:
    """Result of reading a single page."""
    url: str
    content: str
    success: bool
    error: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────

def _is_korean(text: str) -> bool:
    """Detect Korean characters in text."""
    return bool(re.search(r"[가-힣]+", text or ""))


# ── Client class ─────────────────────────────────────────────

class WebSearchClient:
    """Manager primary + SerpAPI fallback, with URL->snippet cache for ReadFullText.

    Usage:
        client = WebSearchClient()
        passages = client.search_web("query")  # Manager -> SerpAPI fallback
        pages = client.read_multiple_pages(["https://..."])  # Cache-backed
    """

    def __init__(
        self,
        manager_url: str = DEFAULT_MANAGER_URL,
        serpapi_key: str = DEFAULT_SERPAPI_KEY,
        api_base: str = DEFAULT_WEBSEARCH_API_BASE,
        engine: str = DEFAULT_WEBSEARCH_ENGINE,
        max_content_length: int = MAX_CONTENT_LENGTH,
    ):
        self.manager_url = manager_url
        self.serpapi_key = serpapi_key
        self.api_base = api_base
        self.engine = engine
        self.max_content_length = max_content_length

        # Thread-safe URL -> snippet cache (for ReadFullText)
        self._page_cache: Dict[str, str] = {}
        self._cache_lock = threading.Lock()

    # ══════════════════════════════════════════════════════════
    #  Manager (primary)
    # ══════════════════════════════════════════════════════════

    def _call_manager(
        self,
        query: str,
        timeout: int = 60,
    ) -> Tuple[int, Optional[Dict]]:
        """Multipart POST to gw-qa manager.

        Returns:
            (http_status, result_dict) where result_dict has 'llm.tool' with search results.
        """
        header = {"X-request-id": "llm-agent squad"}
        inputs = bytes("dummy", "utf-8")
        data = {
            "inputs_format": "bytes",
            "task_types": "e2e",
            "temperature": 1.5,
            "output_len": 1500,
            "topk": 1,
            "topp": 1.0,
            "repetition_penalty": 1.0,
            "beam_width": 1,
            "inputs": [
                {
                    "query": query,
                    "session_id": 1,
                    "user_id": "1111111",
                    "q_id": 1,
                    "user_history": [],
                    "f_id": [-1],
                    "file_name": [""],
                    "document_file_ids": [],
                    "public_document_file_ids": [],
                    "debug_mode": 2,
                    "search_mode": {"deep_dive": False, "focus": ["General"]},
                }
            ],
        }
        files = [("inputs", ("dummy", inputs))]
        my_data = {"params": json.dumps(data, ensure_ascii=False).encode("utf-8")}

        resp = requests.post(
            url=self.manager_url,
            headers=header,
            files=files,
            data=my_data,
            stream=False,
            timeout=timeout,
        )
        raw_bytes = resp.content
        parsed = json.loads(raw_bytes.decode("utf-8", errors="replace"))

        result_dict: Dict = {}
        if resp.status_code == 200 and "outputs" in parsed and parsed["outputs"]:
            out_item = parsed["outputs"][0]
            if isinstance(out_item, str):
                out_item = json.loads(out_item)
            main_paragraph = out_item.get("main_paragraph", "")
            result_dict = eval(str(main_paragraph))  # noqa: S307 - legacy format

        return resp.status_code, result_dict

    def _parse_manager_results(
        self,
        result_dict: Dict,
    ) -> List[Dict]:
        """Parse manager result_dict into passage dicts.

        result_dict.get("llm", {}).get("tool", "") -> json.loads -> .get("검색결과", [])
        Each item -> {Index, site_name, snippet, url}
        """
        tool_context = result_dict.get("llm", {}).get("tool", "")
        if not tool_context:
            return []

        try:
            json_loaded = json.loads(tool_context)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse manager tool context as JSON")
            return []

        items = json_loaded.get("검색결과", [])
        if not items:
            return []

        passages: List[Dict] = []
        for idx, item in enumerate(items, start=1):
            content = (item.get("내용", "") or "")[:self.max_content_length]
            site_name = item.get("사이트명", "Unknown")
            url = item.get("link", "") or item.get("url", "") or f"web-result-{idx}"
            passages.append({
                "Index": idx,
                "site_name": site_name,
                "snippet": content,
                "url": url,
            })
        return passages

    def _search_via_manager(
        self,
        query: str,
        max_retries: int = 3,
    ) -> List[Dict]:
        """Retry-wrapped manager search.

        Returns:
            List of passage dicts [{Index, site_name, snippet, url}, ...]
        """
        for attempt in range(max_retries):
            try:
                status, result = self._call_manager(query)
                passages = self._parse_manager_results(result)
                if passages:
                    return passages
                logger.warning(
                    "Manager attempt %d/%d: no passages parsed (status=%s)",
                    attempt + 1, max_retries, status,
                )
            except Exception as e:
                logger.warning(
                    "Manager web search attempt %d/%d failed: %s",
                    attempt + 1, max_retries, e,
                )
            if attempt < max_retries - 1:
                time.sleep((attempt + 1) * 2)
        return []

    # ══════════════════════════════════════════════════════════
    #  SerpAPI (fallback)
    # ══════════════════════════════════════════════════════════

    def _call_serpapi(
        self,
        query: str,
        search_num: int = DEFAULT_SEARCH_NUM,
    ) -> Optional[Dict]:
        """POST {api_base}/websearch_api_key/batch.

        Returns:
            Raw JSON response dict, or None on failure.
        """
        if not self.serpapi_key:
            logger.warning("SerpAPI key not configured, skipping SerpAPI search")
            return None

        url = f"{self.api_base}/websearch_api_key/batch"
        lang = "ko" if _is_korean(query) else "en-US"
        payload = {
            "query": [query],
            "search_num": search_num,
            "engine": self.engine,
            "serpapi_api_key": self.serpapi_key,
            "lang": lang,
            "snippet_only": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code != 200:
                body = (resp.text or "")[:500].replace("\n", " ")
                logger.warning(
                    "SerpAPI gateway failed: status=%s body=%s", resp.status_code, body
                )
                return None
            return resp.json()
        except Exception as e:
            logger.warning("SerpAPI gateway error: %s", e)
            return None

    def _parse_serpapi(self, raw: Dict) -> List[Dict]:
        """Parse gateway response into passage dicts.

        Supports both:
        - {"result": {"results": [...]}}
        - {"result": [{"results": [...]}]}

        Each item: {사이트명, 내용, link} -> {Index, site_name, snippet, url}
        """
        result_obj = raw.get("result", {})
        if isinstance(result_obj, list):
            if not result_obj:
                return []
            result_obj = result_obj[0]

        rows = result_obj.get("results", []) if isinstance(result_obj, dict) else []
        passages: List[Dict] = []
        for idx, res in enumerate(rows, start=1):
            site_name = res.get("사이트명", "Unknown")
            content = (res.get("내용", "") or "")[:self.max_content_length]
            link = res.get("link", "")
            passages.append({
                "Index": idx,
                "site_name": site_name,
                "snippet": content,
                "url": link,
            })
        return passages

    # ══════════════════════════════════════════════════════════
    #  Public API
    # ══════════════════════════════════════════════════════════

    def search_web(self, query: str, count: int = 10) -> List[Dict]:
        """Manager -> SerpAPI fallback. Results: [{Index, site_name, snippet, url}, ...]

        Also populates the internal cache for ReadFullText integration.
        """
        # 1) Manager primary
        passages = self._search_via_manager(query)

        # 2) SerpAPI fallback
        if not passages and self.serpapi_key:
            raw = self._call_serpapi(query, search_num=count)
            if raw:
                passages = self._parse_serpapi(raw)

        # 3) Cache injection (for ReadFullText)
        self._populate_cache(passages)

        return passages[:count]

    def _populate_cache(self, passages: List[Dict]) -> int:
        """Inject passage url->snippet pairs into internal cache.

        This makes ReadFullText -> jina_read_page(url) -> cache hit work.

        Returns:
            Number of entries injected.
        """
        injected = 0
        for p in passages:
            url = p.get("url", "")
            snippet = p.get("snippet", "")
            if url and snippet:
                with self._cache_lock:
                    self._page_cache[url] = snippet
                injected += 1
        return injected

    def jina_read_page(self, url: str) -> PageContent:
        """Read a page, checking cache first.

        Returns cached content from search_web() if available.
        """
        with self._cache_lock:
            cached = self._page_cache.get(url)
        if cached is not None:
            return PageContent(url=url, content=cached, success=True)
        return PageContent(url=url, content="", success=False, error="Not cached")

    def read_multiple_pages(
        self,
        urls: List[str],
        parallel: bool = True,
    ) -> List[PageContent]:
        """Read multiple pages, using cache where available.

        Args:
            urls: List of URLs to read
            parallel: Whether to read in parallel (only matters for non-cached)

        Returns:
            List of PageContent results
        """
        if not parallel or len(urls) <= 1:
            return [self.jina_read_page(url) for url in urls]

        results: List[PageContent] = [None] * len(urls)  # type: ignore
        with ThreadPoolExecutor(max_workers=min(len(urls), 5)) as executor:
            future_to_idx = {
                executor.submit(self.jina_read_page, url): i
                for i, url in enumerate(urls)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = PageContent(
                        url=urls[idx], content="", success=False, error=str(e)
                    )

        return results

    # ── Cache management ─────────────────────────────────────

    def get_cached_content(self, url: str) -> Optional[str]:
        """Get cached content for a URL."""
        with self._cache_lock:
            return self._page_cache.get(url)

    def is_cached(self, url: str) -> bool:
        """Check if URL content is cached."""
        with self._cache_lock:
            return url in self._page_cache

    def clear_cache(self) -> None:
        """Clear the page cache."""
        with self._cache_lock:
            self._page_cache.clear()

    @property
    def cache_size(self) -> int:
        """Get number of cached pages."""
        with self._cache_lock:
            return len(self._page_cache)
