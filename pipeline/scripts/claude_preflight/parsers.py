"""Robust output extractors for Claude preflight runs.

Each extractor returns a dict:
    {
        "ok": bool,
        "format": str,      # detected format tag
        "parsed": dict|str, # structured content or cleaned text
        "errors": list[str],
    }

Design goals:
- Tolerate markdown code fences even when the prompt forbids them.
- Try multiple formats for chart (Vega-Lite JSON vs. Chart DSL)
  and mindmap (Mermaid vs. Markdown-outline).
- Surface non-fatal warnings in `errors` without flipping `ok`.
"""
from __future__ import annotations

import json
import re
from typing import Any


_FENCE_RE = re.compile(
    r"^\s*```(?:\w+)?\s*\n(?P<body>.*?)\n```\s*$",
    re.DOTALL,
)


def strip_code_fence(text: str) -> tuple[str, bool]:
    """Remove the outermost ```...``` fence if present.

    Returns (cleaned_text, was_fenced).
    """
    if not text:
        return "", False
    m = _FENCE_RE.match(text.strip())
    if m:
        return m.group("body").strip(), True
    return text.strip(), False


# --------------------------------------------------------------------------
# Chart
# --------------------------------------------------------------------------

_CHART_DSL_HEAD = re.compile(r"^\s*chart\s*:\s*(?P<ctype>[\w_-]+)", re.MULTILINE)


def _parse_chart_dsl(body: str) -> dict[str, Any]:
    """Parse the project's chart DSL into a minimal dict.

    DSL shape:
        chart:bar
        title: Some Title
        x: [a, b, c]
        series:
          Name: [1, 2, 3]
    """
    out: dict[str, Any] = {"chart_type": None, "title": None, "x": [], "series": {}}
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line or line.lstrip().startswith("%%"):
            i += 1
            continue
        m = _CHART_DSL_HEAD.match(line)
        if m:
            out["chart_type"] = m.group("ctype")
            i += 1
            continue
        if line.lower().startswith("title:"):
            out["title"] = line.split(":", 1)[1].strip()
            i += 1
            continue
        if line.lower().startswith("x:"):
            rest = line.split(":", 1)[1].strip()
            out["x"] = [t.strip() for t in rest.strip("[]").split(",") if t.strip()]
            i += 1
            continue
        if line.lower().startswith("series"):
            i += 1
            while i < len(lines):
                sline = lines[i]
                if not sline.strip() or sline.lstrip().startswith("%%"):
                    i += 1
                    continue
                if not (sline.startswith(" ") or sline.startswith("\t")):
                    break
                if ":" in sline:
                    name, vals = sline.split(":", 1)
                    vs = [v.strip() for v in vals.strip().strip("[]").split(",") if v.strip()]
                    out["series"][name.strip()] = vs
                i += 1
            continue
        i += 1
    return out


def extract_chart(text: str) -> dict[str, Any]:
    """Extract chart in either Vega-Lite JSON or Chart DSL form."""
    errors: list[str] = []
    body, fenced = strip_code_fence(text)
    if fenced:
        errors.append("model_added_code_fence")
    body = body.strip()

    # Try Vega-Lite JSON first
    if body.startswith("{"):
        try:
            parsed = json.loads(body)
            mark = parsed.get("mark") or (parsed.get("encoding", {}) or {})
            if parsed.get("$schema") or mark or parsed.get("data"):
                return {
                    "ok": True,
                    "format": "vega-lite",
                    "parsed": parsed,
                    "errors": errors,
                }
            errors.append("json_missing_vega_markers")
        except json.JSONDecodeError as e:
            errors.append(f"json_error: {e.msg}")

    # Try Chart DSL
    if _CHART_DSL_HEAD.search(body):
        dsl = _parse_chart_dsl(body)
        ok = bool(dsl["chart_type"])
        if not ok:
            errors.append("dsl_missing_chart_header")
        if not dsl["series"]:
            errors.append("dsl_missing_series")
        return {
            "ok": ok,
            "format": "chart-dsl",
            "parsed": dsl,
            "errors": errors,
        }

    errors.append("unknown_chart_format")
    return {"ok": False, "format": "unknown", "parsed": body[:200], "errors": errors}


# --------------------------------------------------------------------------
# Diagram (Mermaid)
# --------------------------------------------------------------------------

_MERMAID_DIAGRAM_HEAD = re.compile(
    r"^(?:flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|"
    r"erDiagram|gantt|pie|journey)\b",
    re.MULTILINE,
)


def extract_diagram(text: str) -> dict[str, Any]:
    errors: list[str] = []
    body, fenced = strip_code_fence(text)
    if fenced:
        errors.append("model_added_code_fence")
    m = _MERMAID_DIAGRAM_HEAD.search(body)
    if not m:
        errors.append("no_mermaid_header")
        return {"ok": False, "format": "unknown", "parsed": body[:200], "errors": errors}
    start = m.start()
    source = body[start:].strip()
    if len(source.splitlines()) < 2:
        errors.append("diagram_only_header")
    return {
        "ok": True,
        "format": "mermaid",
        "parsed": {"header": m.group(0), "source": source},
        "errors": errors,
    }


# --------------------------------------------------------------------------
# Mindmap
# --------------------------------------------------------------------------

_MARKDOWN_THEME = re.compile(r"^##\s+.+", re.MULTILINE)
_CITATION = re.compile(r"\[(?:\d+|p\.\d+)\]")


def extract_mindmap(text: str) -> dict[str, Any]:
    errors: list[str] = []
    body, fenced = strip_code_fence(text)
    if fenced:
        errors.append("model_added_code_fence")
    body = body.strip()

    # Mermaid mindmap
    if body.lstrip().lower().startswith("mindmap"):
        lines = [ln for ln in body.splitlines() if ln.strip()]
        node_count = sum(1 for ln in lines if ln.startswith(" ") or ln.startswith("\t"))
        ok = node_count >= 2
        if not ok:
            errors.append("mermaid_mindmap_too_shallow")
        return {
            "ok": ok,
            "format": "mermaid-mindmap",
            "parsed": {"source": body, "node_count": node_count},
            "errors": errors,
        }

    # Markdown outline
    themes = _MARKDOWN_THEME.findall(body)
    if themes:
        citations = _CITATION.findall(body)
        topic_lines = [ln for ln in body.splitlines() if ln.lstrip().startswith("-")]
        ok = len(themes) >= 2 and len(topic_lines) >= 2
        if not ok:
            errors.append("markdown_mindmap_too_shallow")
        if not citations:
            errors.append("markdown_mindmap_missing_citations")
        return {
            "ok": ok,
            "format": "markdown-mindmap",
            "parsed": {
                "theme_count": len(themes),
                "topic_count": len(topic_lines),
                "citation_count": len(citations),
                "source": body,
            },
            "errors": errors,
        }

    errors.append("unknown_mindmap_format")
    return {"ok": False, "format": "unknown", "parsed": body[:200], "errors": errors}


# --------------------------------------------------------------------------
# VLM Judge
# --------------------------------------------------------------------------

_JUDGE_FIELDS = ("faithfulness", "clarity", "overall")
_HUMAN_EVAL_FIELDS = ("struct", "clarity", "faith", "overall")


def extract_human_eval(text: str) -> dict[str, Any]:
    """Extract 4-dim Phase B simulation output (struct/clarity/faith/overall)."""
    errors: list[str] = []
    body, fenced = strip_code_fence(text)
    if fenced:
        errors.append("model_added_code_fence")

    json_match = re.search(
        r"\{[^{}]*?(?:struct|clar|faith|overall)[^{}]*?\}",
        body, re.IGNORECASE | re.DOTALL,
    )
    candidate = json_match.group(0) if json_match else body

    parsed: dict[str, Any] = {}
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            parsed = {k.lower(): v for k, v in obj.items()}
    except Exception:
        errors.append("json_parse_failed")

    # Field-name aliases (be lenient with model output drift)
    alias_map = {
        "structural": "struct", "structure": "struct", "structural_correctness": "struct",
        "faithfulness": "faith",
        "visual_clarity": "clarity",
        "overall_quality": "overall",
    }
    for k, v in list(parsed.items()):
        if k in alias_map and alias_map[k] not in parsed:
            parsed[alias_map[k]] = v

    # Plain-text fallback
    if not all(f in parsed for f in _HUMAN_EVAL_FIELDS):
        for field in _HUMAN_EVAL_FIELDS:
            m = re.search(
                rf'(?:"?{field}\w*"?\s*[:=]\s*)(\d(?:\.\d+)?)',
                body, re.IGNORECASE,
            )
            if m and field not in parsed:
                parsed[field] = float(m.group(1))

    missing = [f for f in _HUMAN_EVAL_FIELDS if f not in parsed]
    if missing:
        errors.append(f"missing_fields:{','.join(missing)}")

    for f in _HUMAN_EVAL_FIELDS:
        if f in parsed:
            try:
                v = float(parsed[f])
                if not (1.0 <= v <= 5.0):
                    errors.append(f"out_of_range_{f}:{v}")
                parsed[f] = max(1.0, min(5.0, v))
            except (TypeError, ValueError):
                errors.append(f"nonnumeric_{f}:{parsed[f]}")
                del parsed[f]

    ok = all(f in parsed for f in _HUMAN_EVAL_FIELDS)
    return {"ok": ok, "format": "human-eval-json", "parsed": parsed, "errors": errors}


def extract_judge(text: str) -> dict[str, Any]:
    """Extract faithfulness/clarity/overall from judge response.

    Strategy:
    1. Parse stripped code fence as JSON.
    2. Regex for '"faithfulness": N' style.
    3. Fallback: 'Faithfulness: N' plain text.
    """
    errors: list[str] = []
    body, fenced = strip_code_fence(text)
    if fenced:
        errors.append("model_added_code_fence")

    # Find first JSON-looking object
    json_match = re.search(r"\{[^{}]*?(?:faith|clar|overall)[^{}]*?\}", body, re.IGNORECASE | re.DOTALL)
    candidate = json_match.group(0) if json_match else body

    parsed: dict[str, Any] = {}
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            parsed = {k.lower(): v for k, v in obj.items()}
    except Exception:
        errors.append("json_parse_failed")

    # Fallback: regex extract numbers
    if not all(f in parsed for f in _JUDGE_FIELDS):
        for field in _JUDGE_FIELDS:
            m = re.search(
                rf'(?:"?{field}"?\s*[:=]\s*)(\d(?:\.\d+)?)',
                body,
                re.IGNORECASE,
            )
            if m and field not in parsed:
                parsed[field] = float(m.group(1))

    missing = [f for f in _JUDGE_FIELDS if f not in parsed]
    if missing:
        errors.append(f"missing_fields:{','.join(missing)}")

    # Coerce to floats and clamp 1-5
    for f in _JUDGE_FIELDS:
        if f in parsed:
            try:
                v = float(parsed[f])
                if not (1.0 <= v <= 5.0):
                    errors.append(f"out_of_range_{f}:{v}")
                parsed[f] = max(1.0, min(5.0, v))
            except (TypeError, ValueError):
                errors.append(f"nonnumeric_{f}:{parsed[f]}")
                del parsed[f]

    ok = all(f in parsed for f in _JUDGE_FIELDS)
    return {"ok": ok, "format": "judge-json", "parsed": parsed, "errors": errors}
