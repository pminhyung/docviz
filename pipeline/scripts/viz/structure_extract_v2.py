"""D11 — Structure extractor v2 (Vega-Lite + Mermaid family).

Replaces `extract_chart_structure(chart_dsl)` in scripts/utils/structure_extraction.py
for the Vega-Lite case. Mermaid diagram / mindmap parsing still reuses the
existing extractors (they already parse `mindmap` / `flowchart` / etc.).

Output schema remains compatible with `eval/metrics/structural.py` (NodeF1,
TED, EdgeF1) — each structure dict carries `node_labels`, `stats`, and for
charts additionally `series`, `x_labels`, `x_field`, `y_field`, `mark`,
`data_values`.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Union

from scripts.utils.structure_extraction import (
    extract_mindmap_structure,
    extract_mermaid_structure,
)


def _ensure_dict(vl: Union[str, dict]) -> Optional[dict]:
    if isinstance(vl, dict):
        return vl
    if not isinstance(vl, str):
        return None
    try:
        return json.loads(vl)
    except Exception:
        # try to find a JSON object anywhere in the text
        m = re.search(r"\{.*\}", vl, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def _get_encoding(spec: dict) -> dict:
    """Return the first encoding dict found in a Vega-Lite spec.

    Handles top-level `encoding`, `layer[*].encoding`, and simple composite forms.
    """
    if isinstance(spec.get("encoding"), dict):
        return spec["encoding"]
    for key in ("layer", "vconcat", "hconcat"):
        arr = spec.get(key)
        if isinstance(arr, list):
            for item in arr:
                if isinstance(item, dict) and isinstance(item.get("encoding"), dict):
                    return item["encoding"]
    return {}


def _get_mark_name(spec: dict) -> str:
    mk = spec.get("mark")
    if isinstance(mk, str):
        return mk
    if isinstance(mk, dict) and "type" in mk:
        return str(mk["type"])
    for key in ("layer", "vconcat", "hconcat"):
        arr = spec.get(key)
        if isinstance(arr, list):
            for item in arr:
                if isinstance(item, dict) and item.get("mark"):
                    sub = item["mark"]
                    return sub if isinstance(sub, str) else str(sub.get("type", ""))
    return ""


def _get_data_values(spec: dict) -> List[dict]:
    data = spec.get("data") or {}
    if isinstance(data, dict):
        vals = data.get("values")
        if isinstance(vals, list):
            return [v for v in vals if isinstance(v, dict)]
    for key in ("layer", "vconcat", "hconcat"):
        arr = spec.get(key)
        if isinstance(arr, list):
            for item in arr:
                if isinstance(item, dict):
                    d = item.get("data") or {}
                    if isinstance(d, dict) and isinstance(d.get("values"), list):
                        return [v for v in d["values"] if isinstance(v, dict)]
    return []


def _strip_dsl_comment(line: str) -> str:
    idx = line.find("%%")
    return line[:idx].rstrip() if idx >= 0 else line.rstrip()


def _split_list_items(body: str) -> List[str]:
    """Split a bracketed list body by commas, respecting quotes."""
    items: List[str] = []
    buf = ""
    quote: Optional[str] = None
    for ch in body:
        if quote:
            if ch == quote:
                quote = None
            else:
                buf += ch
            continue
        if ch in ("'", '"'):
            quote = ch
            continue
        if ch == ",":
            items.append(buf.strip())
            buf = ""
            continue
        buf += ch
    if buf.strip():
        items.append(buf.strip())
    # drop surrounding quotes on each item if any slipped through
    cleaned = []
    for it in items:
        s = it.strip()
        if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
            s = s[1:-1]
        cleaned.append(s)
    return cleaned


def _parse_bracket_list(text: str) -> List[str]:
    """Given `[a, b, 'c, d']` return ['a','b','c, d']. Returns [] if malformed."""
    s = text.strip()
    if not s.startswith("["):
        return []
    depth = 0
    end = -1
    for i, ch in enumerate(s):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return []
    return _split_list_items(s[1:end])


def _parse_chart_dsl(text: str) -> Optional[dict]:
    """Parse Mistral-style chart DSL into raw components.

    Returns {chart_type, title, x_labels, series: {name: [floats]}} or None.
    """
    if not isinstance(text, str):
        return None
    lines = [_strip_dsl_comment(ln) for ln in text.strip().splitlines()]
    if not lines or not lines[0].lower().startswith("chart:"):
        return None

    chart_type = lines[0].split(":", 1)[1].strip()
    title = ""
    x_labels: List[str] = []
    series: Dict[str, List[float]] = {}

    in_series = False
    i = 1
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        i += 1
        if not stripped:
            continue
        low = stripped.lower()
        if low.startswith("title:"):
            title = stripped.split(":", 1)[1].strip()
            in_series = False
            continue
        if low.startswith("x:"):
            body = stripped.split(":", 1)[1].strip()
            x_labels = _parse_bracket_list(body)
            in_series = False
            continue
        if low == "series:" or low.startswith("series:"):
            in_series = True
            tail = stripped.split(":", 1)[1].strip()
            if tail:  # inline series not expected, but handle
                continue
            continue
        if in_series and ":" in stripped:
            name, rest = stripped.split(":", 1)
            vals_raw = _parse_bracket_list(rest.strip())
            nums: List[float] = []
            for v in vals_raw:
                try:
                    nums.append(float(v))
                except (TypeError, ValueError):
                    continue
            if nums:
                series[name.strip()] = nums
    return {
        "chart_type": chart_type,
        "title": title,
        "x_labels": x_labels,
        "series": series,
    }


def _dsl_to_structure(dsl: dict, gold_hint: Optional[dict] = None) -> dict:
    """Convert parsed DSL to the extract_vegalite_structure output schema.

    Uses gold_hint {x_field, y_field, color_field} so data_accuracy_vegalite's
    fuzzy field-name match succeeds; falls back to generic names.
    """
    chart_type = dsl.get("chart_type", "")
    title = dsl.get("title", "")
    x_labels: List[str] = dsl.get("x_labels", []) or []
    series: Dict[str, List[float]] = dsl.get("series", {}) or {}

    hint = gold_hint or {}
    x_field = (hint.get("x_field") or "").strip() or "x"
    y_field = (hint.get("y_field") or "").strip() or "y"
    color_field = (hint.get("color_field") or "").strip() or None
    if color_field is None and len(series) > 1:
        color_field = "series"

    data_values: List[dict] = []
    if color_field:
        for sname, vals in series.items():
            for idx, v in enumerate(vals):
                if idx >= len(x_labels):
                    break
                data_values.append({
                    x_field: x_labels[idx],
                    color_field: sname,
                    y_field: v,
                })
    else:
        for sname, vals in series.items():
            for idx, v in enumerate(vals):
                if idx >= len(x_labels):
                    break
                data_values.append({x_field: x_labels[idx], y_field: v})
            break  # single-series only

    node_labels = set()
    node_labels.update(x_labels)
    node_labels.update(series.keys())
    if title:
        node_labels.add(title)
    if x_field:
        node_labels.add(x_field)
    if y_field:
        node_labels.add(y_field)

    return {
        "chart_type": chart_type,
        "mark": chart_type,
        "title": title,
        "x_field": x_field,
        "y_field": y_field,
        "color_field": color_field,
        "x_labels": x_labels,
        "series": series,
        "data_values": data_values,
        "node_labels": node_labels,
        "stats": {
            "num_series": len(series),
            "num_categories": len(x_labels),
            "num_rows": len(data_values),
        },
        "source_format": "dsl",
    }


def extract_vegalite_structure(vl: Union[str, dict],
                               gold_hint: Optional[dict] = None) -> dict:
    """Parse a Vega-Lite spec into the same schema the legacy extractor produced.

    Returns:
      {
        "chart_type": str  (mark name),
        "mark": str,
        "title": str,
        "x_field": str,  "y_field": str,  "color_field": str|None,
        "x_labels": [str],                     (unique x values encountered)
        "series": {series_name: [float]},      (grouped by color_field when present)
        "data_values": list[dict],             (raw row-of-values, for DataAcc)
        "node_labels": set[str],               (for NodeF1)
        "stats": {"num_series": int, "num_categories": int, "num_rows": int}
      }
    """
    spec = _ensure_dict(vl) or {}
    if not spec:
        dsl = _parse_chart_dsl(vl if isinstance(vl, str) else "")
        if dsl is not None:
            return _dsl_to_structure(dsl, gold_hint)
    mark = _get_mark_name(spec)
    enc = _get_encoding(spec)

    def _field(key: str) -> str:
        d = enc.get(key) or {}
        if isinstance(d, dict):
            return str(d.get("field", "")) if d.get("field") is not None else ""
        return ""

    # For most marks x/y are primary. For arc (pie/doughnut) the fields are
    # theta/color; map those into x/y conceptually so downstream DataAcc
    # can still compare values.
    x_field = _field("x")
    y_field = _field("y")
    color_field = _field("color") or None
    if not y_field and _field("theta"):
        y_field = _field("theta")
    if not x_field and color_field:
        x_field = color_field
        color_field = None

    title_raw = spec.get("title", "")
    if isinstance(title_raw, dict):
        title = str(title_raw.get("text", ""))
    else:
        title = str(title_raw or "")

    rows = _get_data_values(spec)

    # Build series grouped by color_field (if any)
    x_labels_seen: List[str] = []
    seen_x = set()
    series: Dict[str, List[float]] = {}

    def _to_float(val):
        try:
            if isinstance(val, bool):
                return None
            return float(val)
        except (TypeError, ValueError):
            return None

    for row in rows:
        xv = row.get(x_field)
        xv_str = "" if xv is None else str(xv)
        if xv_str and xv_str not in seen_x:
            seen_x.add(xv_str)
            x_labels_seen.append(xv_str)
        yv = _to_float(row.get(y_field))
        if yv is None:
            continue
        sname = y_field or "value"
        if color_field and color_field in row:
            sname = str(row[color_field])
        series.setdefault(sname, []).append(yv)

    node_labels = set()
    node_labels.update(x_labels_seen)
    node_labels.update(series.keys())
    if title:
        node_labels.add(title)
    if x_field:
        node_labels.add(x_field)
    if y_field:
        node_labels.add(y_field)

    return {
        "chart_type": mark,
        "mark": mark,
        "title": title,
        "x_field": x_field,
        "y_field": y_field,
        "color_field": color_field,
        "x_labels": x_labels_seen,
        "series": series,
        "data_values": rows,
        "node_labels": node_labels,
        "stats": {
            "num_series": len(series),
            "num_categories": len(x_labels_seen),
            "num_rows": len(rows),
        },
    }


def extract_structure_v2(source_text: str, viz_type: str,
                         subtype: str = "",
                         gold_hint: Optional[dict] = None) -> dict:
    """Unified v2 extractor. Chart → Vega-Lite parser; diagram/mindmap → reuse."""
    if viz_type == "chart":
        return extract_vegalite_structure(source_text, gold_hint=gold_hint)
    if viz_type == "mindmap":
        return extract_mindmap_structure(source_text)
    if viz_type == "diagram":
        return extract_mermaid_structure(source_text, subtype or "flowchart")
    raise ValueError(f"unknown viz_type: {viz_type}")
