"""Per-task cache of rendered full-page images.

pdf_page_layout (and future PPTX/DOCX/HWPX/XLSX layout tools) rasterize
whole pages and return Index handles. analyze_visual resolves those
handles by reading this cache rather than the parser's cropped-figure
PNG dump — the parser's dump only has positive img_idx values, whereas
layout-tool renders use img_idx == -1.

Lifetime: TTL-evicted per task_id, mirrors _doc_cache / _attachments.
"""

from __future__ import annotations

import threading
import time
from typing import Optional


_TTL_SECONDS = 3600

_LOCK = threading.Lock()
_STORE: dict[str, dict[tuple[str, int], bytes]] = {}
_EXPIRES: dict[str, float] = {}


def _gc_expired_locked() -> None:
    now = time.time()
    stale = [tid for tid, exp in _EXPIRES.items() if exp < now]
    for tid in stale:
        _STORE.pop(tid, None)
        _EXPIRES.pop(tid, None)


def _touch_locked(task_id: str) -> None:
    _EXPIRES[task_id] = time.time() + _TTL_SECONDS


def register_render(
    *, task_id: str, fid: str, page: int, png_bytes: bytes,
) -> None:
    with _LOCK:
        _gc_expired_locked()
        _STORE.setdefault(task_id, {})[(str(fid), int(page))] = png_bytes
        _touch_locked(task_id)


def lookup_render(
    *, task_id: str, fid: str, page: int,
) -> Optional[bytes]:
    with _LOCK:
        _gc_expired_locked()
        return (_STORE.get(task_id) or {}).get((str(fid), int(page)))


def reset_task(task_id: str) -> None:
    with _LOCK:
        _STORE.pop(task_id, None)
        _EXPIRES.pop(task_id, None)
