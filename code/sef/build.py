"""SEF builders — v0.4.3 plan §3 (sec:dotsmocr, sec:sef-build).

Two entry points sharing the claim/normalize/affordance logic:

  build_sef_from_markdown(doc, ...)   Loong / MultiHop-RAG path (no dots.mocr).
                                      Picture/SVG steps are skipped; markdown
                                      tables populate table_parsed.
  build_sef_from_dotsmocr(pages, ...) PDF path (Phase-3). Consumes dots.mocr
                                      page JSON (bbox+category+text) and the
                                      dots.mocr-svg outputs. SVG quality check
                                      and data-table extraction live in
                                      picture.py (built when the PDF path lands).

Both produce the Appendix-A SEF dataclass.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .schema import (
    SEF, Block, CrossRef, TableParsed, AFFORDANCE_KEYS,
)
from .claim_units import extract_claim_units

# --- markdown segmentation ------------------------------------------------
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# sections that carry no visualizable real-world claims — citation lists,
# acknowledgments. Their integers (volumes, years, page ranges) are noise.
_NOCLAIM_SECTION = re.compile(
    r"\b(references?|bibliography|acknowledge?ments?|appendix\s+citations)\b",
    re.IGNORECASE)
# a line that is itself a bibliographic citation, e.g. "[3] A. Author, ..., 2019."
_CITATION_LINE = re.compile(r"^\s*\[\d+\]\s+\w|\b\d{3,4}\s*\(\d{4}\)")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?[\s:]*-{2,}[\s:|-]*\|?\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")

# cross-ref mentions in body text
_XREF = re.compile(r"\b(Figure|Fig\.?|Table|Section|Sec\.?)\s+(\d+(?:\.\d+)*)",
                   re.IGNORECASE)
# caption/label that *defines* a figure/table number, e.g. "Table 1: ..."
_LABEL = re.compile(r"^\s*(Figure|Fig\.?|Table)\s+(\d+)\b", re.IGNORECASE)


def _bid(reading_order: int) -> str:
    return f"B{reading_order:04d}"


def _parse_md_table(lines: list[str]) -> Optional[TableParsed]:
    """Parse a GitHub-flavored markdown table block into headers+rows+units."""
    rows = [ln for ln in lines if _TABLE_ROW.match(ln)]
    if len(rows) < 2:
        return None
    def cells(ln: str) -> list[str]:
        return [c.strip() for c in ln.strip().strip("|").split("|")]
    headers = cells(rows[0])
    body = [cells(r) for r in rows[2:]] if _TABLE_SEP.match(rows[1]) else [cells(r) for r in rows[1:]]
    # units from header parens: "Revenue (B USD)" -> {Revenue: "B USD"}
    units: dict[str, str] = {}
    clean_headers: list[str] = []
    for h in headers:
        m = re.match(r"(.*?)\s*\(([^)]+)\)\s*$", h)
        if m:
            clean_headers.append(m.group(1).strip())
            units[m.group(1).strip()] = m.group(2).strip()
        else:
            clean_headers.append(h)
    return TableParsed(headers=clean_headers, rows=body, units=units)


def _segment_markdown(content: str) -> list[dict[str, Any]]:
    """Yield raw segments: {category, text, section_path}. reading order = list order."""
    lines = (content or "").splitlines()
    segs: list[dict[str, Any]] = []
    section_stack: list[str] = []
    para: list[str] = []
    i = 0

    def flush_para():
        nonlocal para
        if para:
            txt = "\n".join(para).strip()
            if txt:
                cat = "List-item" if all(_LIST_ITEM.match(p) for p in para if p.strip()) else "Text"
                segs.append({"category": cat, "text": txt,
                             "section_path": " / ".join(section_stack)})
            para = []

    while i < len(lines):
        ln = lines[i]
        if (m := _HEADING.match(ln)):
            flush_para()
            level = len(m.group(1)); title = m.group(2).strip()
            section_stack = section_stack[: level - 1] + [title]
            cat = "Title" if level == 1 else "Section-header"
            segs.append({"category": cat, "text": title,
                         "section_path": " / ".join(section_stack)})
            i += 1
            continue
        if _TABLE_ROW.match(ln):
            flush_para()
            tbl_lines = []
            while i < len(lines) and _TABLE_ROW.match(lines[i]):
                tbl_lines.append(lines[i]); i += 1
            segs.append({"category": "Table", "text": "\n".join(tbl_lines),
                         "section_path": " / ".join(section_stack),
                         "_table_lines": tbl_lines})
            continue
        if not ln.strip():
            flush_para()
            i += 1
            continue
        para.append(ln); i += 1
    flush_para()
    return segs


def _build_cross_refs(blocks: list[Block]) -> list[CrossRef]:
    """Resolve 'Figure N' / 'Table N' mentions to labeled blocks (best effort)."""
    label_to_bid: dict[str, str] = {}
    for blk in blocks:
        head = (blk.text_md or blk.text_html or "")[:40]
        if (m := _LABEL.match(head)):
            key = f"{m.group(1).lower().rstrip('.')}:{m.group(2)}"
            key = key.replace("fig:", "figure:")
            label_to_bid[key] = blk.bid
    refs: list[CrossRef] = []
    seen: set[tuple[str, str]] = set()
    for blk in blocks:
        for m in _XREF.finditer(blk.text_md or ""):
            kind = m.group(1).lower().rstrip(".").replace("fig", "figure")
            kind = "figure" if kind.startswith("figure") else ("table" if kind.startswith("table") else "section")
            if kind == "section":
                continue
            key = f"{kind}:{m.group(2)}"
            to_bid = label_to_bid.get(key)
            if not to_bid or to_bid == blk.bid:
                continue
            pair = (blk.bid, to_bid)
            if pair in seen:
                continue
            seen.add(pair)
            refs.append(CrossRef(from_bid=blk.bid, to_bid=to_bid,
                                 rel="visualizes_data_supporting"))
    return refs


# claim_type / block -> affordance key (deterministic; plan §3.5 step h)
_CLAIM_AFFORD = {
    "numeric_trend": ["numeric_trend"],
    "ranking": ["ranking"],
    "categorical": ["categorical_comparison"],
    "temporal_event": ["temporal_event"],
}
_CHART_AFFORD = {
    "bar": "categorical_comparison", "grouped_bar": "categorical_comparison",
    "line": "numeric_trend", "pie": "part_to_whole", "scatter": "correlation",
}


def _build_affordance_index(blocks: list[Block]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {k: [] for k in AFFORDANCE_KEYS}
    for blk in blocks:
        for cu in blk.claim_units:
            for key in _CLAIM_AFFORD.get(cu.claim_type, []):
                idx[key].append(cu.cuid)
            if cu.claim_type == "numeric_value":
                pct = any(v.unit == "%" for v in cu.values)
                idx["part_to_whole" if pct else "categorical_comparison"].append(cu.cuid)
        if blk.category == "Table" and blk.table_parsed:
            idx["categorical_comparison"].append(blk.bid)
            if len(blk.table_parsed.headers) >= 3:
                idx["correlation"].append(blk.bid)
        if blk.picture_meta and blk.picture_meta.chart_subtype_inferred:
            key = _CHART_AFFORD.get(blk.picture_meta.chart_subtype_inferred)
            if key:
                idx[key].append(blk.bid)
    return {k: v for k, v in idx.items() if v}


def build_sef_from_markdown(doc: dict[str, Any], *,
                            domain: str = "", language: str = "en",
                            synonyms: Optional[dict[str, str]] = None) -> SEF:
    """Build SEF from a Loong-style doc {doc_id, title, content(markdown)}."""
    doc_id = str(doc.get("doc_id") or doc.get("id") or "doc")
    content = doc.get("content") or doc.get("text") or ""
    segs = _segment_markdown(content)

    blocks: list[Block] = []
    for ro, seg in enumerate(segs):
        bid = _bid(ro)
        blk = Block(bid=bid, page=0, bbox=None, category=seg["category"],
                    reading_order=ro)
        if seg["category"] == "Table":
            blk.text_html = seg["text"]
            blk.table_parsed = _parse_md_table(seg.get("_table_lines", []))
        else:
            blk.text_md = seg["text"]
            claimable = (
                seg["category"] in ("Text", "List-item", "Caption", "Footnote")
                and not _NOCLAIM_SECTION.search(seg["section_path"])
                and not _CITATION_LINE.search(seg["text"][:60])
            )
            if claimable:
                blk.claim_units = extract_claim_units(
                    seg["text"], bid=bid, section_path=seg["section_path"],
                    synonyms=synonyms)
        blocks.append(blk)

    sef = SEF(
        doc_id=doc_id,
        source_format="markdown_v1.0",
        doc_meta={"title": doc.get("title", ""), "page_count": 0,
                  "domain": domain, "language": language},
        blocks=blocks,
        cross_refs=_build_cross_refs(blocks),
        viz_affordance_index=_build_affordance_index(blocks),
        extraction_quality="full",
    )
    return sef


def build_sef_for_bundle(bundle: dict[str, Any], *, domain: str = "",
                         synonyms: Optional[dict[str, str]] = None) -> list[SEF]:
    """Build one SEF per doc in a Loong bundle {bundle_id, docs:[...]}."""
    return [build_sef_from_markdown(d, domain=domain, synonyms=synonyms)
            for d in bundle.get("docs", [])]
