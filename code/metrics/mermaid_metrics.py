"""Mermaid DSL parser → NormalizedGraph (v0.4.1 §7.2, §9.3).

P0 pilot uses this regex-based parser. Production hardening (P1/P4) will
swap in `code/judge/_vendor/diagrameval_parser.py` (vendored from
DiagramEval upstream, Apache-2) for richer subdiagram coverage. The shapes
agree so the metric code in P4 is parser-agnostic.

Supported mermaid kinds for P0:
    flowchart / graph    nodes + directed edges + optional edge labels
    timeline             title + sections + dated items
    mindmap              hierarchical text tree
    sequenceDiagram      participants + messages (degenerate node/edge form)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass(frozen=True)
class Node:
    id: str
    label: str


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    label: str = ""        # label on the arrow (`-->|label|`)
    relation: str = "->"   # arrow style (-->, ==>, -.->,  -->|`)


@dataclass(frozen=True)
class NormalizedGraph:
    kind: str              # mermaid_flowchart / mermaid_timeline / …
    nodes: List[Node]
    edges: List[Edge]
    extra_lines: List[str] = field(default_factory=list)
    # hierarchical content for timeline/mindmap where node/edge form is
    # degenerate (lines preserve the human-readable hierarchy)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "n_nodes": len(self.nodes),
            "n_edges": len(self.edges),
            "n_extra_lines": len(self.extra_lines),
        }


_HEADER_RE = re.compile(
    r"^\s*(graph|flowchart|sequenceDiagram|stateDiagram(?:-v2)?|classDiagram|"
    r"erDiagram|gantt|mindmap|timeline|journey|pie|gitGraph)\b",
    re.MULTILINE,
)
# id[label] | id(label) | id{label} | id((label))
_NODE_RE = re.compile(
    r"\b([A-Za-z_][\w]*)\s*[\[\(\{]+\s*\"?([^\"\]\)\}]*?)\"?\s*[\]\)\}]+"
)
# `A --> B` or `A --|label|--> B` or `A ==> B`
_EDGE_RE = re.compile(
    r"\b([A-Za-z_][\w]*)\s*"
    r"(-{1,3}>|={1,3}>|-\.->|--?\|[^|]*\|-{1,3}>)\s*"
    r"([A-Za-z_][\w]*)"
)
_EDGE_LABEL_RE = re.compile(r"\|([^|]+)\|")


def _detect_kind(dsl_code: str) -> str:
    m = _HEADER_RE.search(dsl_code)
    if m:
        head = m.group(1)
        return f"mermaid_{head}"
    return "mermaid_unknown"


def _extract_nodes_edges(dsl_code: str) -> tuple[List[Node], List[Edge]]:
    seen_nodes: dict[str, str] = {}
    for nid, label in _NODE_RE.findall(dsl_code):
        if nid not in seen_nodes:
            seen_nodes[nid] = label.strip()

    edges: List[Edge] = []
    for src, arrow, dst in _EDGE_RE.findall(dsl_code):
        # Promote referenced ids to nodes even if never declared with []/()
        for ref in (src, dst):
            if ref not in seen_nodes:
                seen_nodes[ref] = ""
        label = ""
        lm = _EDGE_LABEL_RE.search(arrow)
        if lm:
            label = lm.group(1).strip()
        edges.append(Edge(src=src, dst=dst, label=label, relation=arrow.strip()))

    nodes = [Node(id=nid, label=lbl) for nid, lbl in seen_nodes.items()]
    return nodes, edges


def parse_mermaid_to_graph(dsl_code: str) -> Optional[NormalizedGraph]:
    """Deterministic Mermaid DSL → NormalizedGraph. Returns None on empty/blank."""
    if not dsl_code or not dsl_code.strip():
        return None

    kind = _detect_kind(dsl_code)
    nodes, edges = _extract_nodes_edges(dsl_code)

    # For hierarchical diagrams without explicit node syntax, fall back to
    # line-by-line preservation so downstream metrics can still recover the
    # textual content for evidence_f1.
    extra_lines: List[str] = []
    if kind in {"mermaid_timeline", "mermaid_mindmap"} and len(nodes) == 0:
        extra_lines = [ln.rstrip() for ln in dsl_code.splitlines() if ln.strip()]
        extra_lines = extra_lines[:200]  # cap so metric prompts stay bounded

    # Mermaid syntax errors: zero nodes + zero extra_lines and unknown header
    # is the conservative "definitely failed" signal.
    if (
        kind == "mermaid_unknown"
        and not nodes
        and not edges
        and not extra_lines
    ):
        return None

    return NormalizedGraph(
        kind=kind,
        nodes=nodes,
        edges=edges,
        extra_lines=extra_lines,
    )
