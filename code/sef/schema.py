"""SEF (Strategic Evidence Format) schema — v0.4.3 paper Appendix A.

Deterministic structured representation consumed by the DocViz-Agent B6 arm.
Source-agnostic: the same dataclasses serve both the Loong markdown path
(build.build_sef_from_markdown) and the future dots.mocr-JSON / PDF path
(build.build_sef_from_dotsmocr). Picture/Table metadata are populated only on
the dots.mocr path; on the markdown path picture_meta is None and table_parsed
is filled when a markdown table is present.

Block category vocabulary mirrors dots.mocr's layout categories so a markdown
block and a dots.mocr block share one schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# dots.mocr layout categories (paper §6.1). Markdown path uses a subset.
CATEGORIES = (
    "Text", "Title", "Section-header", "Picture", "Table", "Caption",
    "Formula", "Footnote", "List-item", "Page-header", "Page-footer",
)

CLAIM_TYPES = (
    "numeric_value", "numeric_trend", "ranking", "categorical",
    "temporal_event",
)

# viz_affordance_index keys (paper Appendix A).
AFFORDANCE_KEYS = (
    "numeric_trend", "categorical_comparison", "ranking", "part_to_whole",
    "correlation", "hierarchical_structure", "process_flow",
    "temporal_event", "causal_chain",
)


@dataclass
class Entity:
    surface: str
    canonical: Optional[str]
    type: str


@dataclass
class Value:
    raw: str
    normalized_value: Optional[float]
    unit: Optional[str]


@dataclass
class TimeRef:
    raw: str
    normalized: Optional[str]


@dataclass
class ClaimUnit:
    cuid: str
    claim_text: str
    claim_type: str
    entities: list[Entity] = field(default_factory=list)
    values: list[Value] = field(default_factory=list)
    time_anchors: list[TimeRef] = field(default_factory=list)
    section_path: str = ""


@dataclass
class PictureMeta:
    caption_bid: Optional[str] = None
    svg_code: Optional[str] = None
    svg_quality_score: float = 0.0
    visual_type: Optional[str] = None
    chart_subtype_inferred: Optional[str] = None
    extracted_data_table: Optional[list[dict[str, Any]]] = None
    safe_to_use_numerics: bool = False


@dataclass
class TableParsed:
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)


@dataclass
class Block:
    bid: str
    page: int
    bbox: Optional[list[float]]
    category: str
    reading_order: int
    text_md: str = ""
    text_html: str = ""
    claim_units: list[ClaimUnit] = field(default_factory=list)
    picture_meta: Optional[PictureMeta] = None
    table_parsed: Optional[TableParsed] = None


@dataclass
class CrossRef:
    from_bid: str
    to_bid: str
    rel: str


@dataclass
class SEF:
    doc_id: str
    source_format: str
    doc_meta: dict[str, Any]
    blocks: list[Block] = field(default_factory=list)
    cross_refs: list[CrossRef] = field(default_factory=list)
    viz_affordance_index: dict[str, list[str]] = field(default_factory=dict)
    extraction_quality: str = "full"  # full | partial | fallback

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the Appendix-A JSON shape (drops empty Nones cleanly)."""
        d = asdict(self)
        for blk in d["blocks"]:
            if blk["picture_meta"] is None:
                blk.pop("picture_meta")
            if blk["table_parsed"] is None:
                blk.pop("table_parsed")
        return d

    # convenience for VSC R5 (source-ref validity) ------------------------
    def all_eids(self) -> set[str]:
        """Every valid SEF reference id: block bids + claim cuids."""
        eids: set[str] = set()
        for blk in self.blocks:
            eids.add(blk.bid)
            for cu in blk.claim_units:
                eids.add(cu.cuid)
        return eids
