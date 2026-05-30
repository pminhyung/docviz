"""Async client for the sft_pipeline selector (Format B).

Wire format matches ``sft_pipeline/context/topk_retrieval.py::_call_selector_format_b``:

    POST <SELECTOR_URL>
    {
      "inputs": [{
        "question": <query>,
        "queries": [<query>],
        "evidences": [<json-encoded {"page": N, "context": [<text>], "type": "doc"}>, ...]
      }],
      "params": {"inputs_format": "json"}
    }

The response wraps the per-evidence scores under
``outputs[0]`` (one extra list nesting in some variants). Scores line up
positionally with the input evidences, so this client ranks pages by
score and returns ``[(page_dict, score), ...]`` sorted high→low. The
caller (handle_doc_search shim) applies its own ``top_n`` cap.

Environment:
    EXAONE_SELECTOR_URL — selector endpoint (default gw-qa).
    EXAONE_SELECTOR_MAX_INFLIGHT — backpressure cap (default 8).
    EXAONE_SELECTOR_TIMEOUT_SEC — total request timeout (default 60).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


_DEFAULT_SELECTOR_URL = "http://gw-qa.lgair.net/api/lang/chat-exaone-selector/base"
_MAX_RETRIES = 2
_INITIAL_RETRY_DELAY = 1.0
_RETRIABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def _get_selector_url() -> str:
    return os.getenv("EXAONE_SELECTOR_URL", _DEFAULT_SELECTOR_URL)


def _get_timeout() -> float:
    try:
        return float(os.getenv("EXAONE_SELECTOR_TIMEOUT_SEC", "60"))
    except ValueError:
        return 60.0


def _get_max_inflight() -> int:
    try:
        return max(1, int(os.getenv("EXAONE_SELECTOR_MAX_INFLIGHT", "8")))
    except ValueError:
        return 8


_SEMAPHORE: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(_get_max_inflight())
    return _SEMAPHORE


def _build_evidences(pages: List[Dict[str, Any]]) -> List[str]:
    """Serialize pages into the evidence string list the selector expects."""
    evidences: List[str] = []
    for i, page in enumerate(pages):
        content = str(page.get("content") or page.get("text") or "").strip()
        if not content:
            content = json.dumps(page, ensure_ascii=False)
        evidences.append(json.dumps(
            {
                "page": page.get("page", i + 1),
                "context": [content],
                "type": "doc",
            },
            ensure_ascii=False,
        ))
    return evidences


def _parse_scores(payload: Dict[str, Any], n_pages: int) -> List[float]:
    """Extract per-evidence scores from the selector response.

    The response shape varies — ``outputs[0]`` may be a flat list of
    ``{score, ...}`` dicts or one extra layer of nesting. Scores line up
    positionally with the input evidences. Missing entries score 0.
    """
    outputs = payload.get("outputs") or []
    if not outputs:
        return [0.0] * n_pages
    flat = outputs[0]
    if flat and isinstance(flat[0], list):
        flat = flat[0]
    scores = [0.0] * n_pages
    for idx, item in enumerate(flat):
        if idx >= n_pages:
            break
        if not isinstance(item, dict):
            continue
        try:
            scores[idx] = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            scores[idx] = 0.0
    return scores


async def rank_pages(
    *,
    query: str,
    pages: List[Dict[str, Any]],
    client: Optional[httpx.AsyncClient] = None,
) -> List[Tuple[Dict[str, Any], float]]:
    """POST one (query, doc-pages) tuple to the selector and rank pages.

    Returns ``[(page_dict, score), ...]`` sorted by score descending.
    On total failure (network error, all retries exhausted, malformed
    response) returns the input pages in original order with score 0 —
    callers downstream can still surface them as "unranked".
    """
    if not pages:
        return []

    body = {
        "inputs": [
            {
                "question": query,
                "queries": [query],
                "evidences": _build_evidences(pages),
            }
        ],
        "params": {"inputs_format": "json"},
    }
    url = _get_selector_url()
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=_get_timeout())

    sem = _get_semaphore()
    retry_delay = _INITIAL_RETRY_DELAY
    last_error: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    try:
        for attempt in range(_MAX_RETRIES):
            async with sem:
                try:
                    resp = await client.post(url, json=body)
                    if resp.status_code == 200:
                        payload = resp.json()
                        break
                    last_error = f"HTTP {resp.status_code}"
                    if resp.status_code not in _RETRIABLE_STATUSES:
                        logger.warning(
                            "selector non-retriable status %s (url=%s)",
                            resp.status_code, url,
                        )
                        break
                    logger.warning(
                        "selector attempt %d/%d retriable status %s",
                        attempt + 1, _MAX_RETRIES, resp.status_code,
                    )
                except httpx.HTTPError as exc:
                    last_error = f"network_error: {exc}"
                    logger.warning(
                        "selector attempt %d/%d network error: %s",
                        attempt + 1, _MAX_RETRIES, str(exc)[:120],
                    )
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30.0)
    finally:
        if owns_client:
            await client.aclose()

    if payload is None:
        logger.warning(
            "selector rank failed after %d attempts: %s (returning unranked pages)",
            _MAX_RETRIES, last_error,
        )
        return [(p, 0.0) for p in pages]

    scores = _parse_scores(payload, len(pages))
    ranked = sorted(zip(pages, scores), key=lambda x: x[1], reverse=True)
    return ranked
