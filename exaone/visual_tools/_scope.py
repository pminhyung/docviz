"""Scope-item parser for visual_tools.

`get_visuals` and `pdf_page_layout` accept a `scope` list whose items name
a document attachment (and optionally a page) via the same `document_idx`
the agent uses with docqa_tools:

    "1"     → doc only      → all pages of attachment idx=1
    "1@5"   → doc + page    → page 5 of attachment idx=1

`@` was chosen because:
  - attachment idx is just digits — `@` cannot collide with the idx token
  - never appears inside captions/descriptions/titles
  - reads naturally as "doc at page"
  - single ASCII char, single token in tokenizer

The integer is the `document_idx` from the prompt's [Attached documents]
block — the same idx every docqa tool already uses. The handler resolves
idx → fid via exaone.docqa_tools._attachments, identical to doc_search.
"""

from __future__ import annotations

from typing import Iterable, NamedTuple


class ScopeItem(NamedTuple):
    doc_idx: int        # the attachment idx the model sees in [Attached documents]
    page: int | None    # None ⇒ "all pages of doc_idx"


_SEP = "@"


def parse_scope(items: Iterable[str]) -> list[ScopeItem]:
    """Parse raw `scope` input into structured ScopeItem tuples.

    Raises ValueError on malformed items so the handler can surface a
    tool_error to the model (rather than silently dropping bad input).
    """
    out: list[ScopeItem] = []
    for raw in items or []:
        if not isinstance(raw, (str, int)):
            raise ValueError(
                f"scope item must be a string like '1@5' or '1', got "
                f"{type(raw).__name__}"
            )
        s = str(raw).strip()
        if not s:
            continue
        if _SEP in s:
            idx_str, _, page_str = s.partition(_SEP)
            try:
                idx = int(idx_str.strip())
            except ValueError:
                raise ValueError(
                    f"invalid scope item {raw!r}: doc_idx before '@' must be integer"
                )
            try:
                page = int(page_str.strip())
            except ValueError:
                raise ValueError(
                    f"invalid scope item {raw!r}: page after '@' must be integer"
                )
            if page < 1:
                raise ValueError(f"invalid scope item {raw!r}: page must be >= 1")
            if idx < 1:
                raise ValueError(f"invalid scope item {raw!r}: doc_idx must be >= 1")
            out.append(ScopeItem(idx, page))
        else:
            try:
                idx = int(s)
            except ValueError:
                raise ValueError(
                    f"invalid scope item {raw!r}: must be '<doc_idx>' or "
                    f"'<doc_idx>@<page>' with integer doc_idx"
                )
            if idx < 1:
                raise ValueError(f"invalid scope item {raw!r}: doc_idx must be >= 1")
            out.append(ScopeItem(idx, None))
    return out
