"""Per-task document cache for docqa_tools.

Populated by ``parse_web_and_doc`` after parsing + IR registration (or after
rehydrating the chunks from IR if the fid was already indexed). Read by
``list_documents``, ``get_document_chunks``, and ``ReadFullDocument``.

Scope: keyed by (task_id, fid). TTL eviction matches _reference_id.
Persists only within the lifetime of a single user turn — for cross-turn
persistence, callers rely on the IR service (which holds the actual
indexed content).

## SHARED LOGIC

This file is kept byte-identical on the ``master`` and ``sft-gen-ir-shim``
branches — including the ir-shim-only ``doc_to_page_dicts`` helper at
the bottom, which is dead code on master but stays in place so the file
diff between branches is zero. When you edit anything here, mirror the
change to the other branch. The cross-branch sync table lives in
``exaone/docqa_tools/_policy.md``.

## Cache shape

Documents are stored as a list of ``CachedChunk(text, html, page)`` —
not a 1-page-per-text dict. IR's add/search wire is chunk-based: one
page may carry several chunks (cf. ``meta_data.chunk_to_page``), and
the rehydrate-from-IR path receives one row per chunk. Keeping chunk
granularity end-to-end avoids merging-then-splitting noise.

Consumer tools fold chunks back into per-page views when needed:

- ``get_document_chunks(<fid>-<page>)``: collect chunks where
  ``chunk.page == page``, join with ``\\n\\n``.
- ``ReadFullDocument``: sort all chunks by ``(0, int(page))`` for digit
  pages and ``(1, page)`` for named labels, then join.

## Document flow policy (background)

See ``exaone/docqa_tools/_policy.md``. This cache is shared by both
ir-shim modes:

- ``HERMES_DOC_SOURCE=local`` (Mode A, default): ``_parse_one_shim``
  populates chunks from local pre-parsed JSON. ``doc_search`` uses the
  sft_pipeline selector against these chunks.
- ``HERMES_DOC_SOURCE=remote`` (Mode B): the production flow.
  ``parse_web_and_doc`` probes IR (``search_pass=1``) and rehydrates chunks
  from IR's response when the fid is already indexed; otherwise it
  parses + ``add_doc``. ``doc_search`` ranks by IR's ``score`` field.

The shape and helpers below are identical to master so a single
chunk-level test fixture works on both branches.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List


_TTL_SECONDS = 3600

# Per-process default bucket key. Used when callers omit task_id (e.g. ad-hoc
# dispatch paths). Including pid + uuid prevents distinct deployments and
# distinct workers from sharing each other's cached documents under the bare
# "default" key.
DEFAULT_TASK_ID = f"_anonymous-{os.getpid()}-{uuid.uuid4().hex[:8]}"

_LOCK = threading.Lock()
_STORE: dict[str, dict[str, "CachedDocument"]] = {}
_EXPIRES: dict[str, float] = {}


@dataclass
class CachedChunk:
    """One IR-indexable unit. Mirrors what parser/IR exchange per row.

    Multiple chunks may share the same ``page`` (e.g. a long slide that
    parser split into 3 chunks). ``page`` is kept as a string because IR
    accepts both numeric labels (``"1"``, ``"2"``) and named labels
    (``"cover"``, ``"appendix"``).
    """

    text: str
    html: str
    page: str
    doc_id: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass
class CachedDocument:
    fid: str
    filename: str
    extension: str
    chunks: List[CachedChunk] = field(default_factory=list)
    ir_registered: bool = False
    ir_doc_ids: List[int] = field(default_factory=list)
    user_id: int = 0
    registered_at: float = 0.0
    # Provenance flag — useful for traces and tests.
    # ``"parser"``: chunks came from a fresh parser run.
    # ``"ir"``:     chunks were rehydrated from IR ``find_docs(search_pass=1)``.
    # ``"shim"``:   chunks came from the local pre-parsed JSON corpus
    #               (ir-shim Mode A only — production never sees this).
    source: str = "parser"

    @property
    def pages(self) -> List[str]:
        """Distinct page labels present in the chunks, in first-seen order."""
        seen: List[str] = []
        for c in self.chunks:
            if c.page not in seen:
                seen.append(c.page)
        return seen

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def char_count(self) -> int:
        return sum(c.char_count for c in self.chunks)

    def chunks_on_page(self, page: str) -> List[CachedChunk]:
        target = str(page)
        return [c for c in self.chunks if c.page == target]

    def page_summary(self) -> Dict[str, int]:
        """Per-page char count, summed across chunks of that page."""
        totals: Dict[str, int] = {}
        for c in self.chunks:
            totals[c.page] = totals.get(c.page, 0) + c.char_count
        return totals


def _gc_expired_locked() -> None:
    now = time.time()
    stale = [tid for tid, exp in _EXPIRES.items() if exp < now]
    for tid in stale:
        _STORE.pop(tid, None)
        _EXPIRES.pop(tid, None)


def _touch_task_locked(task_id: str) -> None:
    _EXPIRES[task_id] = time.time() + _TTL_SECONDS


def put_document(*, task_id: str, doc: CachedDocument) -> None:
    """Insert or overwrite a cached document for this task."""
    with _LOCK:
        _gc_expired_locked()
        bucket = _STORE.setdefault(task_id, {})
        bucket[doc.fid] = doc
        _touch_task_locked(task_id)


def get_document(*, task_id: str, fid: str) -> CachedDocument | None:
    with _LOCK:
        _gc_expired_locked()
        bucket = _STORE.get(task_id) or {}
        return bucket.get(fid)


def list_documents(*, task_id: str) -> List[CachedDocument]:
    with _LOCK:
        _gc_expired_locked()
        bucket = _STORE.get(task_id) or {}
        return list(bucket.values())


def reset_task(task_id: str) -> None:
    """Drop all cached documents for the task. Mostly for tests."""
    with _LOCK:
        _STORE.pop(task_id, None)
        _EXPIRES.pop(task_id, None)


# ─── rehydrate from IR ──────────────────────────────────────────────────────

def rehydrate_from_ir_hits(
    *,
    fid: str,
    hits: Iterable[Dict[str, Any]],
    filename_fallback: str = "",
    extension_fallback: str = "",
    user_id: int = 0,
) -> CachedDocument:
    """Build a ``CachedDocument`` from IR ``search_fid`` hits.

    Used by ``parse_web_and_doc`` when an ``search_pass=1`` probe shows the fid
    is already indexed — IR's hits carry per-chunk text/html plus the
    document title, so we can populate the cache without ever calling
    the parser again. See ``_policy.md`` "Cache shape" and the
    production flow description.

    Each hit is expected to have the lgair IR shape:

        {
            "fid": "...", "doc_id": "...", "page_number": "1",
            "title": "...", "doc_type": "pptx",
            "context": "<list-parsed text>",
            "html_context": "<html-parsed text>",
            "score": 0.99, "rank": 1,
            "meta_data": {...},
        }
    """
    import json as _json

    def _decode_if_jsoned(value: Any) -> str:
        """parsing_tools.handle_parse_web_and_doc wraps context/html_context with
        ``json.dumps`` before send_to_add_doc, so IR stores e.g.
        ``"Hello \\"world\\""`` literally. Undo that on rehydrate so
        downstream tools see plain text, not escaped JSON."""
        if not isinstance(value, str) or not value:
            return value or ""
        s = value.lstrip()
        if not s or s[0] not in ('"', "[", "{"):
            return value
        try:
            decoded = _json.loads(value)
        except Exception:
            return value
        if isinstance(decoded, str):
            return decoded
        if isinstance(decoded, list):
            return "\n\n".join(str(x) for x in decoded)
        return value

    def _first_non_none(*keys: str) -> Any:
        # IR sometimes uses integer 0 as a valid page label — must not
        # treat it as falsy. Walk the keys explicitly.
        for k in keys:
            v = hit.get(k)
            if v is not None:
                return v
        return None

    chunks: List[CachedChunk] = []
    title = filename_fallback
    extension = extension_fallback
    ir_doc_ids: List[int] = []
    for hit in hits:
        text_raw = _first_non_none("context", "text") or ""
        html_raw = _first_non_none("html_context", "html") or text_raw
        text = _decode_if_jsoned(text_raw)
        html = _decode_if_jsoned(html_raw)
        page_val = _first_non_none("page_number", "page", "slide_num")
        page = "" if page_val is None else str(page_val)
        doc_id = hit.get("doc_id")
        if hit.get("title"):
            title = hit["title"]
        if hit.get("doc_type"):
            extension = hit["doc_type"]
        chunks.append(
            CachedChunk(
                text=text if isinstance(text, str) else str(text),
                html=html if isinstance(html, str) else str(html),
                page=page,
                doc_id=str(doc_id) if doc_id is not None else None,
            )
        )
        if isinstance(doc_id, int):
            ir_doc_ids.append(doc_id)
        else:
            try:
                ir_doc_ids.append(int(doc_id))
            except (TypeError, ValueError):
                pass
    return CachedDocument(
        fid=str(fid),
        filename=title or "",
        extension=(extension or "").lower(),
        chunks=chunks,
        ir_registered=True,
        ir_doc_ids=ir_doc_ids,
        user_id=user_id,
        registered_at=time.time(),
        source="ir",
    )


# ─── sft_pipeline selector adapter (ir-shim Mode A only) ────────────────────

def doc_to_page_dicts(doc: CachedDocument) -> List[dict]:
    """Convert a CachedDocument to the sft_pipeline selector page-dict format.

    Each page (one or more chunks joined with ``\\n\\n``) becomes
    ``{"Index", "page", "filename", "content"}``. Used by
    ``handle_doc_search`` under Mode A (``HERMES_DOC_SOURCE=local``).
    Production master does not call this helper.
    """
    pages_in_order = sorted(
        doc.pages,
        key=lambda p: (0, int(p)) if p.isdigit() else (1, p),
    )
    out: List[dict] = []
    for idx, page in enumerate(pages_in_order, start=1):
        content = "\n\n".join(c.text for c in doc.chunks_on_page(page) if c.text)
        out.append({
            "Index": idx,
            "page": int(page) if page.isdigit() else page,
            "filename": doc.filename,
            "content": content,
        })
    return out
