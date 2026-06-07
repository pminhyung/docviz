"""Canonical Visual Spec — v0.4.3 paper §4.5(a).

TMG emits a canonical spec (not free-form DSL); VSC converts it deterministically
to DSL (to_dsl), validates the contract (validator), and repairs once on failure
(repair). Two spec families:

  ChartSpec   — viz_type, axis labels, datapoints[(series, category, value, unit,
                source_eid)]. Covers chartjs_bar/line/grouped_bar/pie/scatter.
  DiagramSpec — viz_type, nodes[(id, label, source_eid)],
                edges[(from_id, to_id, rel_label, source_eid)]. Covers
                mermaid_flowchart/timeline/mindmap/sequenceDiagram/classDiagram.

`parse_spec(dict)` builds the right family from a TMG JSON object.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

CHART_TYPES = frozenset({
    "chartjs_bar", "chartjs_line", "chartjs_grouped_bar",
    "chartjs_pie", "chartjs_scatter",
})
DIAGRAM_TYPES = frozenset({
    "mermaid_flowchart", "mermaid_timeline", "mermaid_mindmap",
    "mermaid_sequenceDiagram", "mermaid_classDiagram",
})
VIZ_TYPE_POOL = CHART_TYPES | DIAGRAM_TYPES


@dataclass
class DataPoint:
    series: str
    category: str
    value: Optional[float]
    unit: Optional[str] = None
    source_eid: Optional[str] = None


@dataclass
class ChartSpec:
    viz_type: str
    x_label: str = ""
    y_label: str = ""
    datapoints: list[DataPoint] = field(default_factory=list)
    title: str = ""

    kind = "chart"

    def source_eids(self) -> list[str]:
        return [dp.source_eid for dp in self.datapoints if dp.source_eid]

    def categories(self) -> list[str]:
        """Ordered unique categories (chart x-axis labels)."""
        seen: dict[str, None] = {}
        for dp in self.datapoints:
            seen.setdefault(dp.category, None)
        return list(seen)

    def series_names(self) -> list[str]:
        seen: dict[str, None] = {}
        for dp in self.datapoints:
            seen.setdefault(dp.series, None)
        return list(seen)


@dataclass
class Node:
    id: str
    label: str
    source_eid: Optional[str] = None


@dataclass
class Edge:
    from_id: str
    to_id: str
    rel_label: str = ""
    source_eid: Optional[str] = None


@dataclass
class DiagramSpec:
    viz_type: str
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    title: str = ""

    kind = "diagram"

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}

    def source_eids(self) -> list[str]:
        out = [n.source_eid for n in self.nodes if n.source_eid]
        out += [e.source_eid for e in self.edges if e.source_eid]
        return out


VisualSpec = Union[ChartSpec, DiagramSpec]


def parse_spec(obj: dict[str, Any]) -> VisualSpec:
    """Build a ChartSpec or DiagramSpec from a TMG JSON object.

    Raises ValueError if viz_type is missing/unknown so the caller can route it
    to an R4 (unsupported marker) violation rather than crash.
    """
    viz_type = obj.get("viz_type", "")
    if viz_type in CHART_TYPES:
        dps = [
            DataPoint(
                series=str(d.get("series", "series")),
                category=str(d.get("category", "")),
                value=_as_float(d.get("value")),
                unit=d.get("unit"),
                source_eid=d.get("source_eid"),
            )
            for d in (obj.get("datapoints") or [])
        ]
        return ChartSpec(
            viz_type=viz_type,
            x_label=str(obj.get("x_label", "")),
            y_label=str(obj.get("y_label", "")),
            datapoints=dps,
            title=str(obj.get("title", "")),
        )
    if viz_type in DIAGRAM_TYPES:
        nodes = [
            Node(id=str(n.get("id", "")), label=str(n.get("label", n.get("id", ""))),
                 source_eid=n.get("source_eid"))
            for n in (obj.get("nodes") or [])
        ]
        edges = [
            Edge(from_id=str(e.get("from", e.get("from_id", ""))),
                 to_id=str(e.get("to", e.get("to_id", ""))),
                 rel_label=str(e.get("rel_label", e.get("label", ""))),
                 source_eid=e.get("source_eid"))
            for e in (obj.get("edges") or [])
        ]
        return DiagramSpec(viz_type=viz_type, nodes=nodes, edges=edges,
                           title=str(obj.get("title", "")))
    raise ValueError(f"unknown viz_type: {viz_type!r}")


def _as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None
