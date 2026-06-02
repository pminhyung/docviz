"""docviz v0.4.1 §8.1 — Gold construction dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, Any


@dataclass
class EvidenceSpan:
    id: str               # "{doc_id}#{chunk_id}#{start}-{end}"
    doc_id: str
    chunk_id: str
    text: str             # verbatim span text (anchors for embedding match)
    span_start: int
    span_end: int


@dataclass
class GoldFact:
    id: str
    statement: str        # normalized declarative sentence
    supporting_evidence_ids: list[str]  # ≥ 1 required
    is_distractor: bool = False
    confidence: float = 0.5  # 0.5 LLM-only, 1.0 after human verify


@dataclass
class Cell:
    row: str
    col: str
    value: Any


@dataclass
class Series:
    label: str
    values: list[Any]


@dataclass
class GoldTable:
    id: str
    intent_id: str
    chart_type: Literal["bar", "line", "grouped_bar", "pie", "scatter"]
    columns: list[str]
    series: list[Series]
    cells: list[Cell]
    evidence_ids: list[str]


@dataclass
class Node:
    id: str
    label: str


@dataclass
class Edge:
    src: str
    dst: str
    label: str = ""
    relation: str = "->"


@dataclass
class GoldGraph:
    id: str
    intent_id: str
    diagram_type: Literal["flowchart", "timeline", "mindmap",
                          "sequenceDiagram", "classDiagram"]
    nodes: list[Node]
    edges: list[Edge]
    evidence_ids: list[str]


@dataclass
class GoldContradiction:    # Type E queries only
    id: str
    claim_a: str
    claim_b: str
    supported_side: Literal["a", "b"]
    evidence_ids_a: list[str]
    evidence_ids_b: list[str]


@dataclass
class Gold:
    qid: str
    evidence: list[EvidenceSpan] = field(default_factory=list)
    facts: list[GoldFact] = field(default_factory=list)
    tables: list[GoldTable] = field(default_factory=list)
    graphs: list[GoldGraph] = field(default_factory=list)
    contradictions: list[GoldContradiction] = field(default_factory=list)
    intents: list[dict] = field(default_factory=list)
    extractor_provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
