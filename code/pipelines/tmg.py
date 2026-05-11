"""Pillar 2 — Type-aware Multi-Viz Generation (TMG).

Implements PAPER_MASTER_SPEC §3.2: a query-type → viz-type router that
injects a type-specific one-shot example into the agent's prompt so the
generator emits a well-formed DSL of the right kind.

Design notes:
  - The recommended viz_type per query type follows §3.2 Mapping table.
    A SECONDARY option is also exposed so the agent can deviate when the
    primary type is a poor fit (e.g., temporal with 1 time point — pick
    chartjs_line over mermaid_timeline).
  - One-shot examples are written in OUR paper schema (the 6-value enum
    of viz_type + Chart.js JSON / Mermaid markdown for viz_dsl) so the
    parser hits `_extract_dsl_block` strategy 1 fast-path.
  - Adapted from agent/examples/diagram/diagram_tools.py's DIAGRAM_EXAMPLES
    + CHART_DSL_EXAMPLES; reformatted for our schema instead of the
    sidecar's chart:bar YAML.
  - When TMG is disabled (no query_type passed), the prompt falls back to
    the no-TMG dsl_output_rule already in run_paper_default — that is
    spec §11.4 "−TMG" ablation cell.
"""
from __future__ import annotations

from typing import Dict, List, Tuple


# ── Mapping (§3.2) ─────────────────────────────────────────────────────────


# query_type → (primary_viz_type, secondary_viz_type)
TYPE_TO_VIZ: Dict[str, Tuple[str, str]] = {
    "quantitative":  ("chartjs_bar",         "chartjs_line"),
    "relational":    ("mermaid_flowchart",   "mermaid_mindmap"),
    "temporal":      ("mermaid_timeline",    "chartjs_line"),
    "hierarchical":  ("mermaid_mindmap",     "mermaid_flowchart"),
    "comparative":   ("chartjs_grouped_bar", "mermaid_flowchart"),
}

# Tip text per type — 1 line of generation guidance, no example.
TYPE_TIP: Dict[str, str] = {
    "quantitative": (
        "Extract concrete numbers from the source. Pair categories on x with "
        "numeric series on y. Never fabricate values."
    ),
    "relational": (
        "Use named entities from the source as nodes; use linking verbs from "
        "the source as edge labels. 5-10 nodes is ideal."
    ),
    "temporal": (
        "Order events chronologically. Use the dates that appear in the "
        "source, with a brief one-line description per event."
    ),
    "hierarchical": (
        "Use a 2-3 level mindmap rooted at the central topic from the query. "
        "Each child is a category from the source; grandchildren are "
        "concrete instances."
    ),
    "comparative": (
        "Pick 2-4 entities and 3-6 comparison axes from the source. Each "
        "dataset = one entity; labels = the axes."
    ),
}


# ── One-shot examples in paper schema ──────────────────────────────────────


# Each example is the EXACT JSON object the agent's final_answer should be:
#   {"viz_type": "...", "viz_dsl": "..."}
# (strings — viz_dsl is a single string holding the raw DSL.)

ONE_SHOT_BY_VIZ_TYPE: Dict[str, str] = {
    "chartjs_bar": (
        '{"viz_type": "chartjs_bar",'
        ' "viz_dsl": "{\\"type\\":\\"bar\\",'
        '\\"data\\":{\\"labels\\":[\\"Q1\\",\\"Q2\\",\\"Q3\\",\\"Q4\\"],'
        '\\"datasets\\":[{\\"label\\":\\"Revenue ($B)\\",'
        '\\"data\\":[12.5,14.3,16.8,18.1]}]}}"}'
    ),
    "chartjs_line": (
        '{"viz_type": "chartjs_line",'
        ' "viz_dsl": "{\\"type\\":\\"line\\",'
        '\\"data\\":{\\"labels\\":[\\"2020\\",\\"2021\\",\\"2022\\",\\"2023\\",\\"2024\\"],'
        '\\"datasets\\":[{\\"label\\":\\"Active Users (M)\\",'
        '\\"data\\":[1.2,3.5,8.1,15.0,24.7]}]}}"}'
    ),
    "chartjs_grouped_bar": (
        '{"viz_type": "chartjs_grouped_bar",'
        ' "viz_dsl": "{\\"type\\":\\"bar\\",'
        '\\"data\\":{\\"labels\\":[\\"Speed\\",\\"Accuracy\\",\\"Cost\\"],'
        '\\"datasets\\":['
        '{\\"label\\":\\"Model A\\",\\"data\\":[8.0,9.2,3.5]},'
        '{\\"label\\":\\"Model B\\",\\"data\\":[6.1,7.8,8.4]}]}}"}'
    ),
    "mermaid_flowchart": (
        '{"viz_type": "mermaid_flowchart",'
        ' "viz_dsl": "graph LR\\n'
        '    A[Founder] -->|founded| B[Acme Corp]\\n'
        '    B -->|acquired| C[Beta Labs]\\n'
        '    C -->|hired| D[Engineer X]\\n'
        '    A -->|advised| C"}'
    ),
    "mermaid_timeline": (
        '{"viz_type": "mermaid_timeline",'
        ' "viz_dsl": "timeline\\n'
        '    title Acme Corp Milestones\\n'
        '    2018 : Founded by Alice and Bob\\n'
        '    2020 : Series A — $20M\\n'
        '    2022 : Acquired Beta Labs\\n'
        '    2024 : IPO at $1.4B valuation"}'
    ),
    "mermaid_mindmap": (
        '{"viz_type": "mermaid_mindmap",'
        ' "viz_dsl": "mindmap\\n'
        '  root((NLP Methods))\\n'
        '    Supervised\\n'
        '      Classification\\n'
        '      Sequence Labeling\\n'
        '    Self-supervised\\n'
        '      Masked LM\\n'
        '      Contrastive\\n'
        '    RL-based\\n'
        '      RLHF\\n'
        '      DPO"}'
    ),
}


# ── Rule builder ───────────────────────────────────────────────────────────


def _viz_options(query_type: str) -> List[str]:
    primary, secondary = TYPE_TO_VIZ[query_type]
    out = [primary]
    if secondary != primary:
        out.append(secondary)
    return out


def build_tmg_rule(query_type: str, *, include_one_shot: bool = True) -> str:
    """Return a custom_rules block that routes the agent for this query type.

    Appended to run_paper_default's existing rules. Must NOT contradict
    the dsl_output_rule (final_answer = single JSON, viz_type ∈ enum).

    `include_one_shot` toggles the reference-output line:
      - True  → V0 mode (current placeholder one-shot from
                ONE_SHOT_BY_VIZ_TYPE[primary])
      - False → V1 mode (rule routing + tip only, no example) — mentor
                risk #1 baseline; isolates the value of the one-shot
                independently from the routing decision.
    """
    if query_type not in TYPE_TO_VIZ:
        # Unknown type — emit a no-op block so the agent falls back to the
        # generic prompt (spec §11.4 −TMG behaviour).
        return ""

    primary, secondary = TYPE_TO_VIZ[query_type]
    options = _viz_options(query_type)
    options_str = ", ".join(f'"{o}"' for o in options)
    tip = TYPE_TIP[query_type]

    parts = [
        "",
        "TMG ROUTING (DocViz-Agent Pillar 2 — type-aware):",
        f"- The user query is type **{query_type}**.",
        f"- Recommended viz_type: **{primary}**. Secondary acceptable: {secondary}.",
        f"- Restrict viz_type to: {options_str} unless the source content "
        f"truly fits a different enum value.",
        f"- Generation tip for {query_type}: {tip}",
    ]
    if include_one_shot:
        one_shot = ONE_SHOT_BY_VIZ_TYPE[primary]
        parts.append(
            "- Reference output for this type — match the schema exactly, "
            "not the content:"
        )
        parts.append(f"  {one_shot}")
    return "\n".join(parts)


def primary_viz_type(query_type: str) -> str:
    return TYPE_TO_VIZ.get(query_type, ("mermaid_flowchart", ""))[0]


# ── V4 — agent inference + tool-call exposure rule ────────────────────────


# Used by S4AgenticTMG(mode="v4_pool" | "v4_consolidated"). The agent sees
# the 10-type pool with use-case hints, and is instructed to call the
# generate_viz tool (loaded from code/agent_tools/generate_viz.py via
# custom_tools_path) rather than emit DSL directly.
V4_POOL_EXPOSURE_RULE = (
    "- **TMG (Pillar 2 — Type-aware Multi-Viz Generation)**: For any "
    "request that asks for a visualization, diagram, chart, mindmap, "
    "or similar visual artifact of the document content, you MUST "
    "invoke the `generate_viz` action tool to produce the DSL. The "
    "`viz_type` argument MUST be one of "
    "{chartjs_bar, chartjs_line, chartjs_grouped_bar, chartjs_pie, "
    "chartjs_scatter, mermaid_flowchart, mermaid_timeline, "
    "mermaid_mindmap, mermaid_sequenceDiagram, mermaid_classDiagram}; "
    "choose it based on the user query type AND the source content "
    "structure (e.g., qualitative cross-entity comparison → "
    "`mermaid_mindmap` rather than `chartjs_grouped_bar`). Pass "
    "`content_brief` as a detailed natural-language description that "
    "names the entities, dates, numbers, quantities, relationships, "
    "and any quotes from the source documents that the visualization "
    "must include — `generate_viz` does not see the documents, only "
    "this brief.\n"
    "- **`generate_viz` final_answer format**: When you have invoked "
    "`generate_viz` and received its result, your `<final_answer>` "
    "MUST be EXACTLY the JSON string returned by `generate_viz`, "
    "verbatim and unmodified. Do not write the DSL yourself, do not "
    "summarize the result in prose, and do not wrap the JSON with "
    "extra text or markdown fences. If you produce `<final_answer>` "
    "without first invoking `generate_viz`, the response is invalid."
)
