"""Hermes-style reference id assignment for docqa_tools results.

Hermes' built-in formatter assigns ``<tcid>.<n>`` ids to web_search/web_extract
output (see exaone/tool_formatting.py). For tools outside that allowlist we
synthesize a Hermes-style id ourselves so the model sees a uniform citation
shape across web and document content.

Format: ``<tool-short>-<task-prefix>.<n>``
    - tool-short: short tool name segment for readability (e.g. ``ds`` for
      docqa search, ``rt`` for ReadFullText, ``dp`` for parse_web_and_doc).
    - task-prefix: first 6 chars of the task_id (or "default" prefix).
    - n: zero-based per (task_id, tool_name) counter.

Same payload key within the same task_id returns the same id — lets
search and follow-up reads reference identical content with one id.

NB: This helper is opt-in. Only modules in exaone/docqa_tools/ and
exaone/parsing_tools/ import it; tools added by other developers to other
groups are unaffected.
"""

from __future__ import annotations

import threading
import time
from typing import Hashable, Tuple


_TTL_SECONDS = 3600

_LOCK = threading.Lock()
_STORE: dict[str, dict[Tuple[str, Hashable], str]] = {}
_COUNTERS: dict[Tuple[str, str], int] = {}
_EXPIRES: dict[str, float] = {}


_TOOL_SHORT = {
    "parse_web_and_doc": "pw",
    "doc_search": "ds",
    "ReadFullDocument": "rd",
    "list_documents": "ld",
    "get_document_chunks": "gc",
}


def _gc_expired_locked() -> None:
    now = time.time()
    stale = [tid for tid, exp in _EXPIRES.items() if exp < now]
    for tid in stale:
        _STORE.pop(tid, None)
        _EXPIRES.pop(tid, None)
        for key in [k for k in _COUNTERS if k[0] == tid]:
            _COUNTERS.pop(key, None)


def _tool_segment(tool_name: str) -> str:
    return _TOOL_SHORT.get(tool_name, "tl")


def _task_prefix(task_id: str) -> str:
    if not task_id:
        return "deflt0"
    cleaned = task_id.replace("-", "")
    return (cleaned + "000000")[:6]


def assign_reference_id(
    *,
    task_id: str,
    tool_name: str,
    payload_key: Tuple[str, Hashable, ...],
) -> str:
    """Return canonical reference id for ``payload_key`` within ``task_id``.

    Same payload within a task returns the same id (dedup). Different tools
    sharing identical payload also share the id — call-sites are responsible
    for choosing a payload_key that is stable across tools when desired.
    """
    short = _tool_segment(tool_name)
    prefix = _task_prefix(task_id)

    with _LOCK:
        _gc_expired_locked()
        bucket = _STORE.setdefault(task_id, {})
        if payload_key in bucket:
            return bucket[payload_key]

        counter_key = (task_id, tool_name)
        n = _COUNTERS.get(counter_key, 0)
        _COUNTERS[counter_key] = n + 1

        ref = f"{short}-{prefix}.{n}"
        bucket[payload_key] = ref
        _EXPIRES[task_id] = time.time() + _TTL_SECONDS
        return ref


def lookup_reference_id(
    *,
    task_id: str,
    payload_key: Tuple[str, Hashable, ...],
) -> str | None:
    """Read-only lookup. Returns None if not present (no allocation)."""
    with _LOCK:
        _gc_expired_locked()
        bucket = _STORE.get(task_id)
        if bucket is None:
            return None
        return bucket.get(payload_key)


def reset_task(task_id: str) -> None:
    """Drop all reference ids for the given task. Mostly for tests."""
    with _LOCK:
        _STORE.pop(task_id, None)
        _EXPIRES.pop(task_id, None)
        for key in [k for k in _COUNTERS if k[0] == task_id]:
            _COUNTERS.pop(key, None)
