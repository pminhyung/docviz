"""Verbatim prompts for VisuBench viz redesign (v3, 2026-04-09).

Source of truth (byte-exact):
  - Guide 1 §2.2  → SUBTYPE_ASSIGNMENT_PROMPT
  - Guide 1 §3.1  → CHART_QUERY_PROMPT + qc_chart_query()
  - Guide 1 §3.2  → DIAGRAM_QUERY_PROMPT
  - Guide 1 §3.3  → generate_mindmap_query()
  - Guide 1 §5    → SYSTEM_PROMPT_CHART / SYSTEM_PROMPT_DIAGRAM / SYSTEM_PROMPT_MINDMAP

Preserved copies for drift-check:
  /ex_disk2/mhpark/poc/visubench/research_memory/10-steps/v3_query_format_redesign.md
  /home/poc/.claude/projects/-ex-disk2-mhpark-poc-visubench/memory/project_viz_redesign_guides_v2.md

DO NOT paraphrase or reformat. Any edit is a bug.
"""

# ── Guide 1 §2.2 — SUBTYPE_ASSIGNMENT_PROMPT (verbatim) ──────────────────────

SUBTYPE_ASSIGNMENT_PROMPT = """You are assigning visualization subtypes to a document for a benchmark
that evaluates LLM visualization generation quality.

Read the document excerpt below. For each of CHART and DIAGRAM, select the
subtype that is MOST NATURALLY suited to visualizing this document's content.

CHART subtypes (output as Vega-Lite):
- bar: numerical comparisons across categories
- line: trends over time or sequences
- pie: proportional composition
- scatter: correlation between two variables
- combo: two related metrics with different scales
- area: cumulative trends or stacked compositions
- radar: multi-dimensional comparison (3+ attributes)
- doughnut: proportional data with emphasis on specific segments

DIAGRAM subtypes (output as Mermaid):
- flowchart: step-by-step processes, decision flows
- sequenceDiagram: temporal interactions between entities
- classDiagram: hierarchical structures, class relationships
- stateDiagram: state transitions, lifecycle stages
- erDiagram: entity relationships, data models
- gantt: project timelines, scheduling
- sankey: flow/distribution between categories

Rules:
- Choose based on what DATA or PROCESSES the document actually contains
- If the document has financial/statistical tables → prefer bar/line/pie
- If the document describes workflows or procedures → prefer flowchart/sequence
- If no subtype fits well, choose the closest reasonable option

Document excerpt (first 1500 chars):
{doc_excerpt}

Document language: {doc_language}
Document domain: {doc_domain}

Output (JSON only, no explanation):
{{"chart_subtype": "...", "diagram_subtype": "...",
 "chart_reason": "one sentence why",
 "diagram_reason": "one sentence why"}}"""


# ── Guide 1 §3.1 Step 2 — CHART_QUERY_PROMPT (verbatim) ──────────────────────

CHART_QUERY_PROMPT = """You are writing a natural user query for a chart generation task.

The user has a document and wants to create a specific chart. Write the query
as if a real user is asking — natural, concise, 1-2 sentences.

Rules:
1. REFERENCE the data by topic/location in the document (e.g., "the revenue
   comparison in Section 3", "the patient statistics from Table 2")
2. SPECIFY the chart type: {chart_type_name}
3. If applicable, mention the key data fields: {x_field}, {y_field}
4. Do NOT include actual data values — the model must extract from the document
5. Write in {document_language}
6. SPECIFY output format: "Generate as a Vega-Lite JSON specification"

Document excerpt (first 500 chars): {doc_excerpt}
Chart type: {chart_type_name}
X field: {x_field}
Y field: {y_field}
Color/series field: {color_field}

Generate the query:"""


# ── Guide 1 §3.2 — DIAGRAM_QUERY_PROMPT (verbatim) ───────────────────────────

DIAGRAM_QUERY_PROMPT = """You are writing a natural user query for a diagram generation task.

The user has a document and wants to create a {diagram_subtype} diagram.
Write the query as a real user would — natural, concise, 1-2 sentences.

Rules:
1. SPECIFY the diagram type: {diagram_subtype}
2. REFERENCE the specific process, structure, or relationship in the document
   to visualize (e.g., "the approval workflow in Section 2", "the entity
   relationships described in the data model section")
3. Do NOT specify exact nodes, edges, or labels — the model determines these
4. Write in {document_language}
5. SPECIFY output format: "Generate as Mermaid syntax"

Document excerpt (first 1000 chars): {doc_excerpt}
Assigned subtype: {diagram_subtype}
Assignment reason: {diagram_reason}

Generate the query:"""


# ── Guide 1 §3.3 — generate_mindmap_query (verbatim) ─────────────────────────

def generate_mindmap_query(doc_language: str) -> str:
    queries = {
        "ko": "이 문서의 핵심 내용을 마인드맵으로 정리해주세요. "
              "모든 레이블은 문서와 동일한 언어로 작성하세요. "
              "Mermaid mindmap 문법으로 출력하세요.",
        "en": "Organize the key content of this document as a mindmap. "
              "Generate ALL labels in the SAME language as the document. "
              "Generate as Mermaid mindmap syntax.",
    }
    return queries.get(doc_language,
        f"Organize the key content of this document as a mindmap. "
        f"Generate ALL labels in {doc_language}. Generate as Mermaid mindmap syntax.")


# ── Guide 1 §5 — System prompts (verbatim, one-shot examples included) ──────

SYSTEM_PROMPT_CHART = """You are a data visualization assistant.
Given a document and a user query, generate a Vega-Lite JSON specification
that visualizes the requested data from the document.

Output ONLY the Vega-Lite JSON — no explanation, no markdown fences.

Example output format:
{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "mark": "bar",
  "encoding": {
    "x": {"field": "category", "type": "nominal"},
    "y": {"field": "value", "type": "quantitative"}
  },
  "data": {"values": [{"category": "A", "value": 10}, ...]}
}

Generate ALL text labels in the SAME language as the input document."""


SYSTEM_PROMPT_DIAGRAM = """You are a diagram generation assistant.
Given a document and a user query, generate Mermaid syntax that
visualizes the requested structure from the document.

Output ONLY the Mermaid code — no explanation, no markdown fences.

Example (flowchart):
flowchart TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Action 1]
    B -->|No| D[Action 2]

Generate ALL labels in the SAME language as the input document."""


SYSTEM_PROMPT_MINDMAP = """You are a document summarization assistant.
Given a document and a user query, generate a Mermaid mindmap that
organizes the key content hierarchically.

Output ONLY the Mermaid mindmap code — no explanation, no markdown fences.

Example:
mindmap
  root((Document Title))
    Topic A
      Detail 1
      Detail 2
    Topic B
      Detail 3

Generate ALL labels in the SAME language as the input document."""


# ── Guide 1 §3.1 Step 3 — qc_chart_query (verbatim logic) ───────────────────
# Argument renamed gold_vl → chart_spec per Resolved decision #16 (real-world
# flow). Detection logic unchanged.

def qc_chart_query(query: str, chart_spec: dict) -> dict:
    """Return {'pass': bool, 'issues': list[str]} for a chart query.

    Checks:
      1. LEAKED_VALUE   — any numeric value from chart_spec['data']['values']
                          appearing literally in the query
      2. MISSING_FORMAT — "vega-lite" or "vegalite" not mentioned
      3. MISSING_CHART_TYPE — no bar/line/pie/scatter/area/radar/doughnut/combo
    """
    issues = []
    data = chart_spec.get("data", {}) if isinstance(chart_spec, dict) else {}
    if isinstance(data, dict) and "values" in data:
        for row in data["values"]:
            if not isinstance(row, dict):
                continue
            for val in row.values():
                if isinstance(val, (int, float)) and str(val) in query:
                    issues.append(f"LEAKED_VALUE: {val}")
    # 2. format indicator
    q_lower = query.lower()
    if "vega-lite" not in q_lower and "vegalite" not in q_lower:
        issues.append("MISSING_FORMAT: Vega-Lite not mentioned")
    # 3. chart type keyword
    chart_keywords = ["bar", "line", "pie", "scatter",
                      "area", "radar", "doughnut", "combo"]
    if not any(kw in q_lower for kw in chart_keywords):
        issues.append("MISSING_CHART_TYPE")
    return {"pass": len(issues) == 0, "issues": issues}


__all__ = [
    "SUBTYPE_ASSIGNMENT_PROMPT",
    "CHART_QUERY_PROMPT",
    "DIAGRAM_QUERY_PROMPT",
    "generate_mindmap_query",
    "SYSTEM_PROMPT_CHART",
    "SYSTEM_PROMPT_DIAGRAM",
    "SYSTEM_PROMPT_MINDMAP",
    "qc_chart_query",
]
