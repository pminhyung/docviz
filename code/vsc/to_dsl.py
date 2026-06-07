"""Deterministic canonical-spec → DSL conversion — v0.4.3 paper §4.5(b).

No LLM. Because conversion is rule-based, the "spec is correct but the DSL
emission is malformed" failure mode is structurally eliminated: a dimension-
consistent ChartSpec always yields a dimension-consistent Chart.js object, and a
DiagramSpec with declared nodes always yields edges that reference real nodes.
"""
from __future__ import annotations

import json

from .spec import ChartSpec, DiagramSpec, VisualSpec


def spec_to_dsl(spec: VisualSpec) -> str:
    if isinstance(spec, ChartSpec):
        return chart_to_chartjs(spec)
    if isinstance(spec, DiagramSpec):
        return diagram_to_mermaid(spec)
    raise TypeError(f"unsupported spec: {type(spec).__name__}")


# --- charts ---------------------------------------------------------------

def chart_to_chartjs(spec: ChartSpec) -> str:
    """Emit a Chart.js JSON object. Datasets are aligned to the shared label
    axis; a (series, category) absent from the spec is filled with null so
    `labels.length == dataset.data.length` holds for every dataset (R2)."""
    base = spec.viz_type.removeprefix("chartjs_")
    chart_type = "bar" if base == "grouped_bar" else base
    labels = spec.categories()
    index = {(dp.series, dp.category): dp.value for dp in spec.datapoints}

    if base == "scatter":
        # scatter: one dataset per series, points are {x: i, y: value}
        datasets = []
        for s in spec.series_names():
            pts = [{"x": i, "y": index.get((s, c))} for i, c in enumerate(labels)]
            datasets.append({"label": s, "data": pts})
    elif base == "pie":
        # pie: single dataset over categories (first series only)
        s0 = spec.series_names()[0] if spec.series_names() else "series"
        datasets = [{"label": s0,
                     "data": [index.get((s0, c)) for c in labels]}]
    else:
        datasets = [
            {"label": s, "data": [index.get((s, c)) for c in labels]}
            for s in spec.series_names()
        ]

    obj = {"type": chart_type, "data": {"labels": labels, "datasets": datasets}}
    if spec.title:
        obj["options"] = {"plugins": {"title": {"display": True, "text": spec.title}}}
    return json.dumps(obj, ensure_ascii=False)


# --- diagrams -------------------------------------------------------------

def _san(node_id: str) -> str:
    """Mermaid-safe node id: alnum + underscore."""
    s = "".join(ch if ch.isalnum() else "_" for ch in (node_id or "n"))
    if not s or not (s[0].isalpha() or s[0] == "_"):
        s = "n" + s
    return s


def _q(label: str) -> str:
    """Quote a label body for mermaid (downgrade inner quotes)."""
    return label.replace('"', "'").replace("\n", " ").strip()


def diagram_to_mermaid(spec: DiagramSpec) -> str:
    base = spec.viz_type.removeprefix("mermaid_")
    if base == "flowchart":
        return _flowchart(spec)
    if base == "timeline":
        return _timeline(spec)
    if base == "mindmap":
        return _mindmap(spec)
    if base == "sequenceDiagram":
        return _sequence(spec)
    if base == "classDiagram":
        return _classdiagram(spec)
    # should be unreachable (R4 catches unknown), keep a safe stub
    return f"flowchart TD\n    {_san('n')}[\"{_q(spec.title or 'node')}\"]\n"


def _flowchart(spec: DiagramSpec) -> str:
    lines = ["flowchart TD"]
    for n in spec.nodes:
        lines.append(f'    {_san(n.id)}["{_q(n.label)}"]')
    for e in spec.edges:
        if e.rel_label:
            lines.append(f'    {_san(e.from_id)} -->|"{_q(e.rel_label)}"| {_san(e.to_id)}')
        else:
            lines.append(f"    {_san(e.from_id)} --> {_san(e.to_id)}")
    return "\n".join(lines) + "\n"


def _timeline(spec: DiagramSpec) -> str:
    lines = ["timeline"]
    if spec.title:
        lines.append(f"    title {_q(spec.title)}")
    # node label = period header, outgoing edges = events under it
    out: dict[str, list[str]] = {n.id: [] for n in spec.nodes}
    id_label = {n.id: n.label for n in spec.nodes}
    for e in spec.edges:
        out.setdefault(e.from_id, []).append(id_label.get(e.to_id, e.to_id))
    for n in spec.nodes:
        events = out.get(n.id) or []
        if events:
            lines.append(f"    {_q(n.label)} : " + " : ".join(_q(ev) for ev in events))
        else:
            lines.append(f"    {_q(n.label)}")
    return "\n".join(lines) + "\n"


def _mindmap(spec: DiagramSpec) -> str:
    lines = ["mindmap"]
    # root = node with no incoming edge (fallback: first node)
    targets = {e.to_id for e in spec.edges}
    roots = [n for n in spec.nodes if n.id not in targets] or spec.nodes[:1]
    children: dict[str, list[str]] = {}
    for e in spec.edges:
        children.setdefault(e.from_id, []).append(e.to_id)
    id_label = {n.id: n.label for n in spec.nodes}
    root = roots[0]
    lines.append(f"  root(({_q(root.label)}))")
    seen = {root.id}

    def walk(nid: str, depth: int):
        for c in children.get(nid, []):
            if c in seen:
                continue
            seen.add(c)
            lines.append("  " * (depth + 1) + _q(id_label.get(c, c)))
            walk(c, depth + 1)
    walk(root.id, 1)
    # orphan nodes attach to root level
    for n in spec.nodes:
        if n.id not in seen:
            lines.append("    " + _q(n.label))
    return "\n".join(lines) + "\n"


def _sequence(spec: DiagramSpec) -> str:
    lines = ["sequenceDiagram"]
    for n in spec.nodes:
        lines.append(f"    participant {_san(n.id)} as {_q(n.label)}")
    for e in spec.edges:
        msg = _q(e.rel_label) or "message"
        lines.append(f"    {_san(e.from_id)}->>{_san(e.to_id)}: {msg}")
    return "\n".join(lines) + "\n"


def _classdiagram(spec: DiagramSpec) -> str:
    lines = ["classDiagram"]
    for n in spec.nodes:
        lines.append(f"    class {_san(n.id)}")
        if n.label and _san(n.id) != n.label:
            lines.append(f'    {_san(n.id)} : {_q(n.label)}')
    for e in spec.edges:
        rel = _q(e.rel_label)
        if rel:
            lines.append(f"    {_san(e.from_id)} --> {_san(e.to_id)} : {rel}")
        else:
            lines.append(f"    {_san(e.from_id)} --> {_san(e.to_id)}")
    return "\n".join(lines) + "\n"
