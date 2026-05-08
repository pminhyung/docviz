"""
Selector Client — Format B with round-robin load balancing

Ported from: sft_pipeline/scripts/test_selector_call.py
Provides document page selection via the selector service.

Rate limiting / backpressure ported from:
    sft_pipeline/multi_turn/adapter/outbound/selector_client.py

Load balancing:
    Round-robin between gw-dev and gw-qa (stg) endpoints.
    On retriable failure, next attempt uses the other URL.

Usage:
    client = SelectorClient(select_num=8)
    top_pages = client.select(query="...", pages=[{Index, filename, page, content}, ...])
"""

import json
import logging
import os
import random
import threading
import time
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────
SELECTOR_URLS = [
    os.environ.get(
        "SELECTOR_URL_1",
        "http://gw-qa.lgair.net/api/lang/chat-exaone-selector/base",
    ),
    os.environ.get(
        "SELECTOR_URL_2",
        "http://gw-dev.lgair.net/api/lang/chat-exaone-selector/base",
    ),
]
# Legacy env var override — single URL disables load balancing
_legacy_url = os.environ.get("GW_STG_SELECTOR_URL")
if _legacy_url:
    SELECTOR_URLS = [_legacy_url]

DEFAULT_SELECT_NUM = 8

# Round-robin counter (atomic via threading lock)
_URL_COUNTER_LOCK = threading.Lock()
_url_counter = 0


def _next_url() -> str:
    """Return the next selector URL in round-robin order."""
    global _url_counter
    with _URL_COUNTER_LOCK:
        url = SELECTOR_URLS[_url_counter % len(SELECTOR_URLS)]
        _url_counter += 1
    return url


# ── Tuning constants (env-overridable) ────────────────────────
def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


MAX_INFLIGHT = _env_int("SELECTOR_MAX_INFLIGHT", 48)
CONNECT_TIMEOUT = _env_float("SELECTOR_CONNECT_TIMEOUT_SEC", 3.0, 0.1)
READ_TIMEOUT = _env_float("SELECTOR_READ_TIMEOUT_SEC", 30.0, 0.1)
TOTAL_BUDGET = _env_float("SELECTOR_TOTAL_BUDGET_SEC", 180.0, 0.5)
MAX_RETRIES = _env_int("SELECTOR_MAX_RETRIES", 50, 0)
RETRY_BASE_DELAY = _env_float("SELECTOR_RETRY_BASE_DELAY_SEC", 3.0)
RETRY_JITTER = _env_float("SELECTOR_RETRY_JITTER_SEC", 0.3)

RETRIABLE_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})

# ── Concurrency control ──────────────────────────────────────
_SEMAPHORE = threading.BoundedSemaphore(MAX_INFLIGHT)
_SESSION_LOCAL = threading.local()


def _get_session() -> requests.Session:
    """Thread-local requests.Session with connection pooling."""
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        pool = max(16, MAX_INFLIGHT * 2)
        adapter = HTTPAdapter(pool_connections=pool, pool_maxsize=pool, max_retries=0)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _SESSION_LOCAL.session = session
    return session


# ── Core functions ────────────────────────────────────────────

def parse_context_text(text: str) -> list:
    """Apply lgair 3-step json.loads parsing to convert text -> context list.

    Replicates context_adapter.py:_parse_context_text():
    1. json.loads(text) -> use as-is if list/dict
    2. json.loads("{" + text + "}") -> list(values())[0]
    3. fallback: [text]
    """
    if not text:
        return [text]

    # Step 1: direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        return [parsed]
    except (json.JSONDecodeError, TypeError):
        pass

    # Step 2: wrap with braces
    try:
        wrapped = json.loads("{" + text + "}", strict=False)
        if isinstance(wrapped, dict) and wrapped:
            first_val = list(wrapped.values())[0]
            if isinstance(first_val, list):
                return first_val
            return [first_val]
    except (json.JSONDecodeError, TypeError):
        pass

    # Step 3: plain text fallback
    return [text]


def pages_to_evidences(pages: List[Dict]) -> List[Dict]:
    """Convert page dicts to selector evidence format.

    Each page's content goes through parse_context_text().
    Uses the original page number from the page dict (1-based fallback).
    Output: [{"page": original_page_num, "context": [...], "type": "doc"}, ...]
    """
    evidences: List[Dict] = []
    for idx, page in enumerate(pages):
        if not isinstance(page, dict):
            continue
        text = page.get("content", page.get("context", page.get("html_context", "")))
        if text is None:
            text = ""
        text = str(text)
        context = parse_context_text(text)
        evidences.append({
            "page": page.get("page", idx + 1),
            "context": context,
            "type": "doc",
        })
    return evidences


def call_selector(
    query: str,
    evidences: List[Dict],
    url: Optional[str] = None,
    timeout: float = READ_TIMEOUT,
    max_retries: int = MAX_RETRIES,
) -> Optional[Dict]:
    """Call selector with Format B payload, round-robin LB, semaphore guard, and retry.

    Each retry attempt rotates to the next URL in SELECTOR_URLS.
    Concurrency is bounded by SELECTOR_MAX_INFLIGHT (default 48).
    Total wall-clock time is bounded by SELECTOR_TOTAL_BUDGET_SEC (default 120s).

    Returns:
        Raw JSON response dict, or None on failure.
    """
    payload = {
        "inputs": [{
            "question": query,
            "queries": [query],
            "evidences": [json.dumps(e, ensure_ascii=False) for e in evidences],
        }],
        "params": {"inputs_format": "json"},
    }

    start = time.monotonic()
    session = _get_session()
    max_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None
    last_status: Optional[int] = None
    last_url: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        elapsed = time.monotonic() - start
        remaining = TOTAL_BUDGET - elapsed
        if remaining <= 0:
            break

        # Round-robin URL selection (or fixed url if explicitly provided)
        current_url = url if url else _next_url()
        last_url = current_url

        _SEMAPHORE.acquire()
        try:
            req_timeout = (
                CONNECT_TIMEOUT,
                min(timeout, max(0.1, remaining)),
            )
            resp = session.post(
                current_url,
                json=payload,
                timeout=req_timeout,
            )
            last_status = resp.status_code

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code in RETRIABLE_HTTP:
                last_error = RuntimeError(
                    f"selector retriable status={resp.status_code}"
                )
            else:
                logger.warning(
                    "Selector non-retriable status=%s url=%s",
                    resp.status_code, current_url,
                )
                return None

        except requests.exceptions.RequestException as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc
        finally:
            _SEMAPHORE.release()

        if attempt >= max_attempts:
            break

        elapsed = time.monotonic() - start
        remaining = TOTAL_BUDGET - elapsed
        if remaining <= 0:
            break

        jitter = random.uniform(0.0, RETRY_JITTER)
        sleep_sec = min(RETRY_BASE_DELAY + jitter, max(0.0, remaining))
        if sleep_sec > 0:
            time.sleep(sleep_sec)

    logger.warning(
        "Selector call failed: urls=%s last_url=%s attempts=%s status=%s error=%s",
        SELECTOR_URLS, last_url, max_attempts, last_status, last_error,
    )
    return None


def parse_selector_outputs(raw: Dict) -> Optional[List[Dict]]:
    """Extract flat score list from response.

    Handles double/triple nesting: outputs[0] -> flat list of score dicts.
    """
    outputs = raw.get("outputs")
    if not outputs or not isinstance(outputs, list):
        logger.warning("Selector response missing 'outputs' key")
        return None

    first = outputs[0]

    # nested list: [[{...}, ...]]
    if isinstance(first, list) and first and isinstance(first[0], list):
        first = first[0]

    if isinstance(first, list):
        return first

    logger.warning("Unexpected outputs[0] type: %s", type(first))
    return None


def select_top_k(
    pages: List[Dict],
    scores: List[Dict],
    select_num: int = DEFAULT_SELECT_NUM,
    min_score: float = 0.0,
) -> List[Dict]:
    """Score descending sort -> top-k page dicts.

    Output: [{Index, filename, page, content}, ...]
    """
    if not scores:
        return []

    scored: List[tuple] = []
    for idx, item in enumerate(scores):
        if not isinstance(item, dict):
            continue
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        if 0 <= idx < len(pages):
            scored.append((idx, score))

    if not scored:
        return []

    scored.sort(key=lambda x: x[1], reverse=True)

    selected: List[Dict] = []
    for page_idx, score in scored:
        if score <= min_score and min_score > 0:
            continue
        page = pages[page_idx]
        selected.append({
            "Index": len(selected) + 1,
            "filename": page.get("filename", ""),
            "page": page.get("page", page.get("Index", page_idx)),
            "content": page.get("content", ""),
        })
        if len(selected) >= select_num:
            break

    return selected


# ── Client class ──────────────────────────────────────────────

class SelectorClient:
    """End-to-end selector client: pages -> evidences -> call -> parse -> top-k.

    Usage:
        client = SelectorClient()
        results = client.select("LG전자 매출", pages)
    """

    def __init__(
        self,
        url: Optional[str] = None,
        select_num: int = DEFAULT_SELECT_NUM,
    ):
        self.url = url  # None = use round-robin load balancing
        self.select_num = select_num

    def select(
        self,
        query: str,
        pages: List[Dict],
        reasoning: str = "",
    ) -> List[Dict]:
        """End-to-end: pages -> evidences -> call -> parse -> top-k.

        Args:
            query: Search query string
            pages: List of page dicts with content field
            reasoning: Current reasoning context (unused by selector, kept for interface compat)

        Returns:
            List of selected page dicts [{Index, filename, page, content}, ...]
        """
        evidences = pages_to_evidences(pages)
        if not evidences:
            return []

        raw = call_selector(query, evidences, url=self.url)
        if raw is None:
            return []

        scores = parse_selector_outputs(raw)
        if scores is None:
            return []

        return select_top_k(pages, scores, select_num=self.select_num)

    def select_for_doc(
        self,
        query: str,
        reasoning: str,
        multi_docs: List[List[Dict]],
        doc_id: int,
        filenames: List[str],
    ) -> List[Dict]:
        """Compatibility wrapper matching the old selector_fn signature.

        Args:
            query: Search query
            reasoning: Current reasoning (passed through)
            multi_docs: All documents' page lists
            doc_id: 1-indexed document number
            filenames: Document filenames

        Returns:
            Selected pages with filename set
        """
        if not (0 < doc_id <= len(multi_docs)):
            return []

        pages = multi_docs[doc_id - 1]
        results = self.select(query, pages, reasoning=reasoning)

        # Ensure filename is set
        filename = filenames[doc_id - 1] if doc_id <= len(filenames) else f"Document{doc_id}"
        for r in results:
            if not r.get("filename"):
                r["filename"] = filename

        return results
