"""Per-task attachment table for the SFT batch flow.

The agent never sees raw file paths in its prompt — only ``[1] basename``
entries from a synthetic "Attached documents" block. When it issues
``parse_web_and_doc(document_idx=[1,2])`` the handler resolves each idx back
to the real ``file_path`` via this table.

Lifetime: keyed by task_id, TTL-evicted like ``_doc_cache``. Each batch
prompt gets its own task_id, so attachments cannot leak across rows.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


_TTL_SECONDS = 3600

_LOCK = threading.Lock()
_STORE: dict[str, dict[int, "Attachment"]] = {}
_FID_BY_IDX: dict[str, dict[int, str]] = {}  # (task_id, idx) -> fid (set by parse_web_and_doc)
_IDX_BY_FID: dict[str, dict[str, int]] = {}  # (task_id, fid) -> idx (reverse lookup)
_EXPIRES: dict[str, float] = {}


@dataclass(frozen=True)
class Attachment:
    """One attached document the model can reference by ``idx``."""

    idx: int
    file_path: str   # absolute or shim-resolvable path; never shown to the model
    filename: str    # basename — what the model sees in the prompt


def _gc_expired_locked() -> None:
    now = time.time()
    stale = [tid for tid, exp in _EXPIRES.items() if exp < now]
    for tid in stale:
        _STORE.pop(tid, None)
        _FID_BY_IDX.pop(tid, None)
        _IDX_BY_FID.pop(tid, None)
        _EXPIRES.pop(tid, None)


def _touch_locked(task_id: str) -> None:
    _EXPIRES[task_id] = time.time() + _TTL_SECONDS


def register_attachments(*, task_id: str, entries: List[Attachment]) -> None:
    """Replace this task's attachment table."""
    with _LOCK:
        _gc_expired_locked()
        _STORE[task_id] = {a.idx: a for a in entries}
        _touch_locked(task_id)


def list_attachments(*, task_id: str) -> List[Attachment]:
    """Return all attachments for this task, ordered by idx."""
    with _LOCK:
        _gc_expired_locked()
        bucket = _STORE.get(task_id) or {}
        return [bucket[i] for i in sorted(bucket.keys())]


def lookup_attachment(*, task_id: str, idx: int) -> Optional[Attachment]:
    """Return the attachment with the given idx, or None if unknown."""
    with _LOCK:
        _gc_expired_locked()
        bucket = _STORE.get(task_id) or {}
        return bucket.get(int(idx))


def reset_task(task_id: str) -> None:
    """Drop attachments for the task (tests/cleanup)."""
    with _LOCK:
        _STORE.pop(task_id, None)
        _FID_BY_IDX.pop(tid := task_id, None)
        _IDX_BY_FID.pop(tid, None)
        _EXPIRES.pop(task_id, None)


def set_fid(*, task_id: str, idx: int, fid: str) -> None:
    """Record the idx <-> fid mapping after parse_web_and_doc resolves the document.

    Idempotent: re-registering the same (idx, fid) pair is a no-op.
    """
    with _LOCK:
        _gc_expired_locked()
        _FID_BY_IDX.setdefault(task_id, {})[int(idx)] = str(fid)
        _IDX_BY_FID.setdefault(task_id, {})[str(fid)] = int(idx)
        _touch_locked(task_id)


def get_fid_by_idx(*, task_id: str, idx: int) -> Optional[str]:
    """Return fid for an attachment idx, or None if not parsed yet."""
    with _LOCK:
        _gc_expired_locked()
        return (_FID_BY_IDX.get(task_id) or {}).get(int(idx))


def get_idx_by_fid(*, task_id: str, fid: str) -> Optional[int]:
    """Return attachment idx for a fid, or None if fid is unknown."""
    with _LOCK:
        _gc_expired_locked()
        return (_IDX_BY_FID.get(task_id) or {}).get(str(fid))


def render_attachments_block(attachments: List[Attachment]) -> str:
    """Render the user-visible '[Attached documents]' block.

    The agent sees basenames only — never file_path.
    """
    if not attachments:
        return ""
    lines = ["[Attached documents]"]
    for a in attachments:
        lines.append(f"[{a.idx}] {a.filename}")
    return "\n".join(lines)
