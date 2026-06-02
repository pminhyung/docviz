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


# ── §9.3 evaluate_mermaid — Graph Edge F1 + Node F1 + relation_hallu ──────


def _node_sim(a: str, b: str, threshold: float = 0.6) -> bool:
    """Lightweight token-overlap node similarity (production = SentenceTransformer)."""
    if not a or not b:
        return False
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta or not tb:
        return False
    j = len(ta & tb) / max(len(ta | tb), 1)
    return j >= threshold


def _edge_sim(pe, ge, threshold: float = 0.6) -> bool:
    """Edges match if both endpoints' labels are similar AND edge label aligns."""
    pe_src = pe.get("src", "") if isinstance(pe, dict) else pe.src
    pe_dst = pe.get("dst", "") if isinstance(pe, dict) else pe.dst
    pe_lbl = pe.get("label", "") if isinstance(pe, dict) else pe.label
    ge_src = ge.get("src", "") if isinstance(ge, dict) else ge.src
    ge_dst = ge.get("dst", "") if isinstance(ge, dict) else ge.dst
    ge_lbl = ge.get("label", "") if isinstance(ge, dict) else ge.label
    src_match = _node_sim(pe_src, ge_src, threshold)
    dst_match = _node_sim(pe_dst, ge_dst, threshold)
    if not src_match or not dst_match:
        return False
    if ge_lbl and pe_lbl:
        return _node_sim(pe_lbl, ge_lbl, threshold=0.4) or pe_lbl.lower() == ge_lbl.lower()
    return True   # untyped edges match if endpoints match


def evaluate_mermaid(artifact: dict, gold_graph: dict) -> dict:
    """Mermaid eval against a gold_graph dict (§9.3).

    Returns: {diagram_type_acc, node_p, node_r, node_f1, edge_p, edge_r,
              edge_f1, relation_hallucination_rate, parse_failed}
    """
    dsl = artifact.get("dsl_code") or artifact.get("viz_dsl", "")
    g = parse_mermaid_to_graph(dsl)
    if g is None or g.kind == "mermaid_unknown":
        return {
            "diagram_type_acc": 0.0, "node_p": 0.0, "node_r": 0.0, "node_f1": 0.0,
            "edge_p": 0.0, "edge_r": 0.0, "edge_f1": 0.0,
            "relation_hallucination_rate": 1.0, "parse_failed": True,
        }

    gold_type = (gold_graph.get("diagram_type") or "").lower()
    pred_type = g.kind.replace("mermaid_", "").lower()
    type_acc = float(pred_type == gold_type) if gold_type else 0.0

    pred_nodes = [{"id": n.id, "label": n.label or n.id} for n in g.nodes]
    pred_edges = [{"src": e.src, "dst": e.dst, "label": e.label,
                   "relation": e.relation} for e in g.edges]
    gold_nodes = list(gold_graph.get("nodes", []))
    gold_edges = list(gold_graph.get("edges", []))

    # Node F1.
    matched_pred = set()
    matched_gold = set()
    for i, pn in enumerate(pred_nodes):
        for j, gn in enumerate(gold_nodes):
            if j in matched_gold:
                continue
            pl = pn["label"] if isinstance(pn, dict) else pn.label
            gl = gn.get("label", "") if isinstance(gn, dict) else gn.label
            if _node_sim(pl, gl):
                matched_pred.add(i)
                matched_gold.add(j)
                break
    np_, ng_ = len(pred_nodes), len(gold_nodes)
    node_p = len(matched_pred) / np_ if np_ else 0.0
    node_r = len(matched_gold) / ng_ if ng_ else 0.0
    node_f1 = 2 * node_p * node_r / (node_p + node_r) if (node_p + node_r) else 0.0

    # Edge F1.
    matched_pe = set()
    matched_ge = set()
    for i, pe in enumerate(pred_edges):
        for j, ge in enumerate(gold_edges):
            if j in matched_ge:
                continue
            if _edge_sim(pe, ge):
                matched_pe.add(i)
                matched_ge.add(j)
                break
    pe_n, ge_n = len(pred_edges), len(gold_edges)
    edge_p = len(matched_pe) / pe_n if pe_n else 0.0
    edge_r = len(matched_ge) / ge_n if ge_n else 0.0
    edge_f1 = 2 * edge_p * edge_r / (edge_p + edge_r) if (edge_p + edge_r) else 0.0
    relation_hallu = max(0, pe_n - len(matched_pe)) / max(pe_n, 1)

    return {
        "diagram_type_acc": type_acc,
        "node_p": node_p, "node_r": node_r, "node_f1": node_f1,
        "edge_p": edge_p, "edge_r": edge_r, "edge_f1": edge_f1,
        "relation_hallucination_rate": relation_hallu,
        "parse_failed": False,
    }
