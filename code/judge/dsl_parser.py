"""Lightweight DSL → struct parser for the checklist judge.

The judge prompt benefits from a structured view of the viz alongside the
raw DSL — the LLM evaluator can reference node/edge counts, axis labels,
dataset values, etc. without having to re-parse the DSL itself.

We keep this dependency-free (no mermaid CLI, no chart.js). For Mermaid
we extract node identifiers + labels + edges with light regex; for
Chart.js we json.loads and pull (type, labels, datasets).

Returns a dict with at least:
  - kind:   "mermaid" | "chartjs" | "unknown"
  - summary: human-readable one-line shape description
  - nodes / edges (mermaid) OR type / labels / datasets (chartjs)
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List


_MERMAID_HEADER_RE = re.compile(
    r"^\s*(graph|flowchart|sequenceDiagram|stateDiagram(?:-v2)?|classDiagram|"
    r"erDiagram|gantt|mindmap|timeline|journey|pie|gitGraph)\b",
    re.MULTILINE,
)
# id[label]  /  id(label)  /  id{label}  — basic Mermaid node syntaxes
_MERMAID_NODE_RE = re.compile(r"\b([A-Za-z_][\w]*)\s*[\[\(\{]\s*\"?([^\"\]\)\}]*?)\"?\s*[\]\)\}]")
_MERMAID_EDGE_RE = re.compile(r"\b([A-Za-z_][\w]*)\s*-{1,3}>(?:\|[^|]*\|)?\s*([A-Za-z_][\w]*)")
# mindmap nodes are indented `text` lines under `mindmap` header
_MINDMAP_LINE_RE = re.compile(r"^(\s+)(.+?)\s*$", re.MULTILINE)


def parse_mermaid(dsl: str) -> Dict[str, Any]:
    head = _MERMAID_HEADER_RE.search(dsl)
    kind = head.group(1) if head else "unknown_mermaid"
    nodes_raw = _MERMAID_NODE_RE.findall(dsl)
    edges = _MERMAID_EDGE_RE.findall(dsl)
    # Dedupe preserving order
    seen: Dict[str, str] = {}
    for nid, label in nodes_raw:
        if nid not in seen:
            seen[nid] = label.strip()
    nodes = [{"id": nid, "label": lbl} for nid, lbl in seen.items()]

    out: Dict[str, Any] = {
        "kind": "mermaid",
        "header": kind,
        "nodes": nodes,
        "n_nodes": len(nodes),
        "edges": [{"src": s, "dst": d} for s, d in edges],
        "n_edges": len(edges),
    }

    if kind in {"mindmap", "timeline"}:
        # Indented hierarchy — also list non-blank lines for the prompt.
        lines = [ln.rstrip() for ln in dsl.splitlines() if ln.strip()]
        out["lines"] = lines[:60]   # cap to keep prompt bounded
        out["n_lines"] = len(lines)

    out["summary"] = (
        f"mermaid_{kind}: {out['n_nodes']} nodes, {out['n_edges']} edges"
    )
    return out


def parse_chartjs(dsl: str) -> Dict[str, Any]:
    try:
        spec = json.loads(dsl)
    except json.JSONDecodeError as e:
        return {"kind": "chartjs", "parse_error": str(e), "summary": "chartjs: parse_fail"}
    if not isinstance(spec, dict):
        return {"kind": "chartjs", "parse_error": "top level not an object",
                "summary": "chartjs: not_object"}

    t = spec.get("type", "")
    data = spec.get("data") or {}
    labels = data.get("labels") or []
    datasets_raw = data.get("datasets") or []

    datasets: List[Dict[str, Any]] = []
    for ds in datasets_raw:
        if not isinstance(ds, dict):
            continue
        datasets.append({
            "label": ds.get("label", ""),
            "data": ds.get("data") or [],
            "n_points": len(ds.get("data") or []),
        })

    return {
        "kind": "chartjs",
        "type": t,
        "labels": labels,
        "n_labels": len(labels),
        "datasets": datasets,
        "n_datasets": len(datasets),
        "summary": (
            f"chartjs_{t}: {len(labels)} x-labels, "
            f"{len(datasets)} datasets, "
            f"{sum(d['n_points'] for d in datasets)} total points"
        ),
    }


def parse_viz(viz_type: str, viz_dsl: str) -> Dict[str, Any]:
    if not viz_dsl:
        return {"kind": "unknown", "summary": "empty_dsl"}
    if viz_type.startswith("mermaid"):
        return parse_mermaid(viz_dsl)
    if viz_type.startswith("chartjs"):
        return parse_chartjs(viz_dsl)
    return {"kind": "unknown", "viz_type": viz_type,
            "summary": f"unknown_viz_type:{viz_type}"}
