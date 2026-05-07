"""Extract structural representations from visualization source texts.

For each viz type, converts the post-processed source text into a
normalized structure JSON suitable for metric computation.
"""
import json
import re
from typing import Optional

from examples.diagram.diagram_tools import (
    _parse_markdown_to_nodes,
    _postprocess_mindmap_markdown,
)


# ── Mindmap Structure Extraction ───────────────────────────────────────────

# Mermaid mindmap label shapes, ordered by specificity
_MINDMAP_SHAPE_PATTERNS = [
    # root((Label)) or node((Label)) — cloud/circle
    (re.compile(r'^([A-Za-z_][\w]*)?\(\((.+)\)\)\s*$'), "double_paren"),
    # ["Label"] or ["Label with (parens) and stuff"]
    (re.compile(r'^\[\s*"(.+)"\s*\]\s*$'), "square_quoted"),
    # [Label] (no quotes)
    (re.compile(r'^\[\s*(.+?)\s*\]\s*$'), "square"),
    # (Label) — round
    (re.compile(r'^\(\s*(.+?)\s*\)\s*$'), "round"),
    # {Label} — diamond
    (re.compile(r'^\{\s*(.+?)\s*\}\s*$'), "diamond"),
]

_CITE_RE = re.compile(r'\[\d+\]')


def _strip_shape(raw: str) -> tuple[str, str]:
    """Return (label, shape) for a single mindmap line's content.

    Handles Mermaid mindmap node shape syntax. Falls back to plain text.
    """
    s = raw.strip()
    if not s:
        return "", "empty"
    for pat, shape in _MINDMAP_SHAPE_PATTERNS:
        m = pat.match(s)
        if m:
            # For double_paren the label is in group(2)
            label = m.group(2) if shape == "double_paren" else m.group(1)
            return label.strip(), shape
    return s, "text"


def _parse_mermaid_mindmap(text: str) -> tuple[list, list]:
    """Indent-based Mermaid mindmap parser.

    Input format (Mermaid mindmap syntax):
        mindmap
          root((Title))
            Theme A
              Subtopic 1
              ["Subtopic 2"]
            ["Theme B"]
              Leaf

    Builds a flat node list + parent→child edge list by tracking an
    indentation stack. Compatible with 2-space or 4-space indentation
    and mixed widths (normalized by leading-whitespace count).
    """
    lines = text.splitlines()
    nodes: list = []
    edges: list = []
    # Stack of (indent_width, node_id) from ancestor to current
    stack: list[tuple[int, str]] = []

    # Skip leading `mindmap` header and blank lines
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped:
            idx += 1
            continue
        if stripped.lower() == "mindmap":
            idx += 1
            continue
        break

    counter = 0
    root_found = False

    def _alloc_id(label: str) -> str:
        nonlocal counter
        counter += 1
        return f"n{counter}"

    for line in lines[idx:]:
        if not line.strip():
            continue
        # Skip mermaid directives/comments mid-file
        s = line.strip()
        if s.startswith("%%") or s.startswith("mindmap"):
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        # Extract the visible content; may be a shape+label or plain text
        label, shape = _strip_shape(s)
        if not label:
            continue

        # First node becomes root
        if not root_found:
            node_id = "root"
            root_found = True
            nodes.append({
                "id": node_id,
                "label": label,
                "type": "root",
                "shape": shape,
                "children": [],
            })
            stack = [(indent, node_id)]
            continue

        # Pop stack until we find a strictly-lesser indent (parent)
        while stack and stack[-1][0] >= indent:
            stack.pop()

        if not stack:
            # Orphan — attach under root if present
            parent_id = nodes[0]["id"] if nodes else None
        else:
            parent_id = stack[-1][1]

        node_id = _alloc_id(label)
        depth = len(stack)  # 0 = theme (child of root), >0 = deeper
        node_type = "theme" if depth == 1 else ("topic" if depth == 2 else "leaf")
        nodes.append({
            "id": node_id,
            "label": label,
            "type": node_type,
            "shape": shape,
            "children": [],
        })
        edges.append({
            "source": parent_id,
            "target": node_id,
            "relationship": "parent",
        })
        # Record child id on parent entry
        for n in nodes:
            if n["id"] == parent_id:
                n["children"].append(node_id)
                break
        stack.append((indent, node_id))

    return nodes, edges


def extract_mindmap_structure(markdown_text: str) -> dict:
    """Extract tree structure from a mindmap source.

    Supports two input shapes:
      1. Mermaid mindmap syntax (default for gold + model outputs in v2+):
         `mindmap\n  root((Title))\n    child1\n    ["child2"]\n...`
         → parsed via indent-based `_parse_mermaid_mindmap`.
      2. Legacy `## Section` bullet markdown (kept for backward compat)
         → parsed via `_parse_markdown_to_nodes` (diagram_tools path).

    Returns:
        {
            "nodes": [{"id": str, "label": str, "type": str, "children": [str]}],
            "edges": [{"source": str, "target": str, "relationship": str}],
            "node_labels": set of cleaned labels (for F1 matching),
            "tree": {"label": str, "children": [...]},  # nested tree form
            "stats": {"num_themes": int, "num_nodes": int, "max_depth": int, "num_edges": int}
        }
    """
    # Detect format: Mermaid mindmap starts with `mindmap` header or
    # contains `root((...))`, never has `## ` section headers.
    is_mermaid = (
        re.search(r'^\s*mindmap\s*$', markdown_text, re.MULTILINE) is not None
        or re.search(r'\broot\(\(.+?\)\)', markdown_text) is not None
    )
    has_sections = re.search(r'^##\s+', markdown_text, re.MULTILINE) is not None

    if is_mermaid and not has_sections:
        nodes, edges = _parse_mermaid_mindmap(markdown_text)
    else:
        processed = _postprocess_mindmap_markdown(markdown_text)
        nodes, edges = _parse_markdown_to_nodes(processed)
        # Markdown parser builds children arrays but only creates edges from
        # explicit cross-reference sections; generate parent→child edges from
        # the hierarchy so structural metrics have parity with the Mermaid path.
        if not edges:
            for node in nodes:
                for child_id in node.get("children", []):
                    edges.append({
                        "source": node["id"],
                        "target": child_id,
                        "relationship": "parent",
                    })

    # Extract clean labels (strip citations [N]) from every non-root node
    node_labels = set()
    for n in nodes:
        if n.get("type") in ("topic", "leaf", "visual", "theme"):
            clean = _CITE_RE.sub("", n.get("label", "")).strip()
            if clean and len(clean) >= 2:
                node_labels.add(clean)

    # Build nested tree
    node_map = {n["id"]: n for n in nodes}
    tree = _build_nested_tree(node_map, "root")

    # Stats
    num_themes = sum(1 for n in nodes if n.get("type") == "theme")
    max_depth = _calc_max_depth(tree)

    return {
        "nodes": nodes,
        "edges": edges,
        "node_labels": node_labels,
        "tree": tree,
        "stats": {
            "num_themes": num_themes,
            "num_nodes": len(nodes),
            "max_depth": max_depth,
            "num_edges": len(edges),
        },
    }


def _build_nested_tree(node_map: dict, root_id: str) -> dict:
    """Convert flat node list to nested tree dict."""
    node = node_map.get(root_id)
    if not node:
        return {"label": root_id, "children": []}
    children = []
    for cid in node.get("children", []):
        children.append(_build_nested_tree(node_map, cid))
    return {"label": node.get("label", ""), "children": children}


def _calc_max_depth(tree: dict, depth: int = 0) -> int:
    """Calculate maximum depth of a nested tree."""
    if not tree.get("children"):
        return depth
    return max(_calc_max_depth(c, depth + 1) for c in tree["children"])


# ── Mermaid Diagram Structure Extraction ───────────────────────────────────

# Regex patterns for common mermaid node/edge syntax
_NODE_PATTERNS = [
    re.compile(r'(\w+)\[([^\]]+)\]'),           # A[Label]
    re.compile(r'(\w+)\(([^)]+)\)'),             # A(Label)
    re.compile(r'(\w+)\{([^}]+)\}'),             # A{Label}
    re.compile(r'(\w+)\[\[([^\]]+)\]\]'),        # A[[Label]]
    re.compile(r'(\w+)\(\(([^)]+)\)\)'),         # A((Label))
    re.compile(r'(\w+)>([^\]]+)\]'),             # A>Label]
]

_EDGE_PATTERNS = [
    # A --> B, A -->|label| B, A -- text --> B
    re.compile(r'(\w+)\s*--+>?\|?([^|]*?)\|?\s*(\w+)'),
    # A -.-> B (dotted)
    re.compile(r'(\w+)\s*-\.->?\s*(\w+)'),
    # A ==> B (thick)
    re.compile(r'(\w+)\s*==+>\s*(\w+)'),
    # classDiagram: A --|> B (inheritance), A --* B (composition),
    # A --o B (aggregation), A ..> B (dependency), A ..|> B (realization)
    re.compile(r'(\w+)\s*(?:--|\.\.)\|?[>o*]?\s*(\w+)'),
]


def extract_mermaid_structure(mermaid_source: str, diagram_type: str = "flowchart") -> dict:
    """Extract nodes and edges from mermaid source code.

    Returns:
        {
            "nodes": [{"id": str, "label": str}],
            "edges": [{"source": str, "target": str, "label": str}],
            "node_labels": set of labels,
            "stats": {"num_nodes": int, "num_edges": int}
        }
    """
    nodes = {}  # id -> label
    edges = []

    # Extract nodes
    for pattern in _NODE_PATTERNS:
        for match in pattern.finditer(mermaid_source):
            nid = match.group(1)
            label = match.group(2).strip()
            if nid not in nodes and label and len(label) >= 2:
                nodes[nid] = label

    # classDiagram: `class Foo { ... }` or `class Foo` declarations
    for m in re.finditer(r'^\s*class\s+([A-Za-z_][\w]*)\b', mermaid_source,
                          re.MULTILINE):
        nid = m.group(1)
        if nid not in nodes:
            nodes[nid] = nid

    # stateDiagram: `state FooBar` or state-transition ids
    for m in re.finditer(r'^\s*state\s+([A-Za-z_][\w]*)\b', mermaid_source,
                          re.MULTILINE):
        nid = m.group(1)
        if nid not in nodes:
            nodes[nid] = nid

    # Extract edges
    seen_edges = set()
    for pattern in _EDGE_PATTERNS:
        for match in pattern.finditer(mermaid_source):
            groups = match.groups()
            if len(groups) >= 3:
                src, label, tgt = groups[0], groups[1].strip(), groups[2]
            elif len(groups) == 2:
                src, tgt = groups[0], groups[1]
                label = ""
            else:
                continue
            edge_key = (src, tgt)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append({"source": src, "target": tgt, "label": label})

    # Special handling for sequence diagrams
    if diagram_type == "sequenceDiagram":
        seq_nodes, seq_edges = _parse_sequence_diagram(mermaid_source)
        nodes.update(seq_nodes)
        for e in seq_edges:
            key = (e["source"], e["target"])
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append(e)

    node_list = [{"id": nid, "label": label} for nid, label in nodes.items()]
    node_labels = set(nodes.values())

    return {
        "nodes": node_list,
        "edges": edges,
        "node_labels": node_labels,
        "stats": {"num_nodes": len(node_list), "num_edges": len(edges)},
    }


def _parse_sequence_diagram(source: str) -> tuple[dict, list]:
    """Parse sequence diagram participants and messages."""
    nodes = {}
    edges = []

    # participant A as Alice
    for m in re.finditer(r'participant\s+(\w+)(?:\s+as\s+(.+))?', source):
        nid = m.group(1)
        label = (m.group(2) or nid).strip()
        nodes[nid] = label

    # A ->> B: message
    for m in re.finditer(r'(\w+)\s*->>?\+?\s*(\w+)\s*:\s*(.+)', source):
        edges.append({
            "source": m.group(1),
            "target": m.group(2),
            "label": m.group(3).strip(),
        })

    return nodes, edges


# ── Chart DSL Structure Extraction ─────────────────────────────────────────

def extract_chart_structure(chart_dsl: str) -> dict:
    """Parse Chart DSL into structured data.

    Returns:
        {
            "chart_type": str,
            "title": str,
            "x_labels": [str],
            "series": {"name": [float]},
            "node_labels": set (series names + x labels for F1),
            "stats": {"num_series": int, "num_categories": int}
        }
    """
    chart_type = ""
    title = ""
    x_labels = []
    series = {}

    lines = chart_dsl.strip().split("\n")
    current_section = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue

        if stripped.startswith("chart:"):
            chart_type = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("title:"):
            title = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("x:"):
            x_str = stripped.split(":", 1)[1].strip()
            x_labels = _parse_list(x_str)
        elif stripped.startswith("series:"):
            current_section = "series"
        elif stripped.startswith("stages:"):
            current_section = "stages"
        elif stripped.startswith("data:"):
            current_section = "data"
        elif current_section in ("series", "stages"):
            # "  SeriesName: [v1, v2, v3]" or "  StageName: value"
            m = re.match(r'\s+(.+?):\s*(.+)', line)
            if m:
                name = m.group(1).strip()
                val_str = m.group(2).strip()
                values = _parse_values(val_str)
                series[name] = values
        elif re.match(r'(?:bar|line)\s+\S+\s+(.+?):\s*\[(.+?)\]', stripped):
            # combo chart: "bar y-left Revenue: [1257, 1665]"
            m = re.match(r'(?:bar|line)\s+\S+\s+(.+?):\s*\[(.+?)\]', stripped)
            if m:
                name = m.group(1).strip()
                values = _parse_values(f"[{m.group(2)}]")
                series[name] = values

    # Build node_labels for F1 matching
    node_labels = set()
    node_labels.update(x_labels)
    node_labels.update(series.keys())
    if title:
        node_labels.add(title)

    return {
        "chart_type": chart_type,
        "title": title,
        "x_labels": x_labels,
        "series": series,
        "node_labels": node_labels,
        "stats": {"num_series": len(series), "num_categories": len(x_labels)},
    }


def _parse_list(s: str) -> list[str]:
    """Parse [a, b, c] into list of strings."""
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    return [x.strip().strip('"').strip("'") for x in s.split(",") if x.strip()]


def _parse_values(s: str) -> list[float]:
    """Parse [1, 2, 3] or single value into list of floats."""
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
        parts = s.split(",")
        result = []
        for p in parts:
            p = p.strip()
            try:
                result.append(float(p))
            except ValueError:
                pass
        return result
    else:
        try:
            return [float(s)]
        except ValueError:
            return []


# ── Unified Extraction Interface ───────────────────────────────────────────

def extract_structure(source_text: str, viz_type: str,
                      subtype: str = "") -> dict:
    """Extract structure from source text based on viz type.

    Args:
        source_text: Raw or post-processed source text
        viz_type: "mindmap", "diagram", or "chart"
        subtype: Specific type (e.g., "flowchart", "bar")

    Returns:
        Normalized structure dict with node_labels and stats
    """
    if viz_type == "mindmap":
        return extract_mindmap_structure(source_text)
    elif viz_type == "diagram":
        return extract_mermaid_structure(source_text, subtype)
    elif viz_type == "chart":
        return extract_chart_structure(source_text)
    else:
        raise ValueError(f"Unknown viz_type: {viz_type}")
