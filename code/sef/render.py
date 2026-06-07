"""SEF → agent-readable chunks — v0.4.3 §4.2 (B6 input representation).

The B6 (full) arm retrieves the SEF *structured* representation instead of raw
markdown; the −SEF arm retrieves plain markdown. This module serializes a SEF
document into searchable chunks (one per evidence-bearing block) that:

  - carry the structured claim (type, normalized value+unit, time anchor),
  - are labeled with the block/claim eid so the agent's citations resolve to
    real SEF ids (SAO / R5 grounding),
  - end with a doc-level viz-affordance summary so TMG can see which blocks
    suit which output structure.

`sef_to_chunks(sef)` returns list[str]; `sef_to_parsed_doc(sef, ...)` wraps them
in the parsed-root JSON shape the docqa cache consumes.
"""
from __future__ import annotations

from typing import Any

from .schema import SEF, Block


def _render_block(doc_id: str, blk: Block) -> str:
    """One searchable chunk = the block's FULL text + its SEF annotations.

    SEF is a superset of the full parse (paper App. A: every block carries
    text_md / text_html), not a claims-only digest — so doc_search and
    get_document_chunks retrieve the same content they would on the markdown
    root, while B6 additionally sees the structured annotations + eids.
    """
    sect = blk.claim_units[0].section_path if blk.claim_units else ""
    head = f"[{doc_id}#{blk.bid}" + (f" · {sect}" if sect else "") + "]"
    lines = [head]
    # full block text (this is what preserves complete retrieval)
    if blk.text_md:
        lines.append(blk.text_md)
    elif blk.text_html:
        lines.append(blk.text_html)
    # structured annotations (the SEF advantage) appended after the text
    for cu in blk.claim_units:
        vals = ", ".join(
            f"{v.normalized_value:g}{(' ' + v.unit) if v.unit else ''}"
            if v.normalized_value is not None else v.raw
            for v in cu.values
        )
        t = "; ".join(t.normalized or t.raw for t in cu.time_anchors)
        ents = ", ".join(e.canonical or e.surface for e in cu.entities[:4])
        meta = " | ".join(p for p in (
            f"type={cu.claim_type}",
            f"values={vals}" if vals else "",
            f"time={t}" if t else "",
            f"entities={ents}" if ents else "",
        ) if p)
        lines.append(f"  - {cu.claim_text}")
        # doc-namespaced eid — must match the R5 SEF dir (build_phase2_sef.py)
        lines.append(f"    ↳ {meta}  (eid: {doc_id}#{cu.cuid})")
    if blk.table_parsed and blk.table_parsed.headers:
        lines.append(f"  [table] headers: {', '.join(blk.table_parsed.headers)} "
                     f"({len(blk.table_parsed.rows)} rows)  (eid: {doc_id}#{blk.bid})")
    return "\n".join(lines)


def sef_to_chunks(sef: SEF) -> list[str]:
    # EVERY block contributes a chunk (full text preserved) — claim-bearing
    # blocks additionally carry structured annotations + eids.
    chunks: list[str] = []
    for blk in sef.blocks:
        if blk.text_md or blk.text_html or blk.claim_units:
            chunks.append(_render_block(sef.doc_id, blk))
    # doc-level affordance summary (one chunk) so TMG sees output-structure cues
    if sef.viz_affordance_index:
        aff = "; ".join(
            f"{k}: {len(v)} block(s)" for k, v in sef.viz_affordance_index.items())
        chunks.append(f"[{sef.doc_id} · viz-affordance] {aff}")
    return chunks or [f"[{sef.doc_id}] (no structured claims extracted)"]


def sef_to_parsed_doc(sef: SEF, *, filename: str) -> dict[str, Any]:
    """Wrap SEF chunks in the parsed-root JSON shape (mirrors the markdown root:
    outputs[0].html_parsed = {page: [chunks]})."""
    return {
        "id": sef.doc_id,
        "outputs": [{
            "file_name": filename,
            "html_parsed": {"1": sef_to_chunks(sef)},
            "list_parsed": {},
            "version": "docviz-sef-1.0",
        }],
        "params": {
            "source": sef.doc_meta.get("domain", ""),
            "title": sef.doc_meta.get("title", ""),
            "representation": "sef",
        },
    }
