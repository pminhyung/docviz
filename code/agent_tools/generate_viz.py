"""V4 custom tool — viz_type-aware DSL generator.

This tool is loaded into the vendored agent via `custom_tools_path`. The
agent reasons over the user query and source content, decides which
viz_type from the 6-enum pool best fits, then calls this tool with that
viz_type plus a content brief. The tool internally:

  1. Looks up the type-matched exemplar from the pool sidecar JSON
     (one-shot for V4_pool mode; consolidated single example for
     V4_consolidated mode).
  2. Calls the on-prem Qwen3.6 vLLM endpoint with the exemplar +
     content brief as one-shot prompt.
  3. Returns `{"viz_type": "...", "viz_dsl": "..."}` for the agent to
     embed in `final_answer`.

This realizes PAPER_MASTER_SPEC §3.2 (Provisional, 2026-05-10) — the
agent makes the type decision; the tool scaffolds the DSL.

Schema sources of truth:
  - `code/pipelines/tmg.py:VIZ_TYPE_POOL` (the 6-enum)
  - `code/agent_tools/oneshot_pool.json` (sidecar; populated from Q2
    subagent revision draft once approved)

Mode dispatch:
  - context["tmg_mode"] ∈ {"v4_pool", "v4_consolidated"} — passed
    through `tool_secrets` or the agent's runtime context
  - default: v4_pool (k=1 sample from the pool)

This file is *self-contained* — the agent server process loads it
without requiring the rest of the `code/` package on PYTHONPATH. The
only external imports are stdlib + openai (already present in agent
server's venv per real_vl_tools.py precedent).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


# Sidecar JSON path — populated from Q2 subagent revision (commit
# pending). Schema:
#   {"pool": {<viz_type>: [<exemplar_json_str>, ...]},
#    "consolidated": {<viz_type>: <exemplar_json_str>}}
_POOL_PATH = Path(__file__).parent / "oneshot_pool.json"


VIZ_TYPE_POOL = [
    # chart (5)
    "chartjs_bar",
    "chartjs_line",
    "chartjs_grouped_bar",
    "chartjs_pie",
    "chartjs_scatter",
    # diagram (5)
    "mermaid_flowchart",
    "mermaid_timeline",
    "mermaid_mindmap",
    "mermaid_sequenceDiagram",
    "mermaid_classDiagram",
]


_VIZ_TYPE_USE_CASES = {
    "chartjs_bar": "single-series quantitative comparison across categories",
    "chartjs_line": "trend over ordered axis (time, sequence)",
    "chartjs_grouped_bar": "multi-series quantitative comparison across categories",
    "chartjs_pie": "proportion / share / part-of-whole categorical distribution",
    "chartjs_scatter": "bivariate correlation / 2-D distribution / cluster pattern",
    "mermaid_flowchart": "named-entity relationships, processes, or dependencies",
    "mermaid_timeline": "chronologically ordered events with dates or eras",
    "mermaid_mindmap": "hierarchical taxonomy or category-instance breakdown",
    "mermaid_sequenceDiagram": "interaction protocol / API call flow / message sequence between actors",
    "mermaid_classDiagram": "typed entity-attribute schema / class structure / data model with relationships",
}


def _load_pool() -> Dict[str, Any]:
    """Load oneshot pool sidecar; raise informative error if missing."""
    if not _POOL_PATH.exists():
        raise FileNotFoundError(
            f"oneshot pool sidecar not found at {_POOL_PATH}. "
            "Populate from Q2 subagent revision draft "
            "(docs/analysis/tmg_oneshot/INDEX.md) before running V4."
        )
    with _POOL_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _select_exemplar(viz_type: str, query_id: str, mode: str) -> str:
    """Deterministic exemplar selection.

    For mode='v4_pool': pick 1 from the pool list using sha1(query_id)
    so the choice is reproducible across processes (mentor minor #5 —
    avoid `hash()` because PYTHONHASHSEED salts it).

    For mode='v4_consolidated': single example, no selection needed.
    """
    pool = _load_pool()

    if mode == "v4_consolidated":
        consolidated = pool.get("consolidated", {})
        if viz_type not in consolidated:
            raise KeyError(f"no consolidated exemplar for viz_type={viz_type}")
        return consolidated[viz_type]

    # v4_pool (default)
    pool_for_type = pool.get("pool", {}).get(viz_type, [])
    if not pool_for_type:
        raise KeyError(f"empty pool for viz_type={viz_type}")
    digest = hashlib.sha1(query_id.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(pool_for_type)
    return pool_for_type[idx]


class GenerateVizTool:
    """Tool: viz_type-aware DSL generator for DocViz-Agent V4.

    Agent calls this once per (query, bundle) pair after deciding the
    viz_type. The tool produces a well-formed DSL of that type using a
    type-matched exemplar — either one drawn from the per-type pool
    (V4_pool) or a single integrated exemplar covering all sub-patterns
    (V4_consolidated).
    """

    name = "generate_viz"
    description = (
        "Generate a visualization DSL of the chosen viz_type "
        "(Mermaid markdown or Chart.js JSON) from a natural-language "
        "content brief. Use this tool ONCE per query, after you have "
        "decided which viz_type from the 6-enum pool best fits the "
        "query and source content. Returns a JSON string "
        '{"viz_type": "...", "viz_dsl": "..."} which you should embed '
        "verbatim in your final_answer."
    )
    parameters = {
        "type": "object",
        "properties": {
            "viz_type": {
                "type": "string",
                "enum": VIZ_TYPE_POOL,
                "description": (
                    "The visualization type chosen for this query. "
                    "Must be one of the 6 enum values."
                ),
            },
            "content_brief": {
                "type": "string",
                "description": (
                    "Natural-language description of what the viz "
                    "should contain — entities, relationships, data "
                    "points, structure. Use named entities and "
                    "concrete phrases from the source documents; "
                    "avoid generic placeholder names. The tool will "
                    "expand this into well-formed DSL using a "
                    "type-matched exemplar."
                ),
            },
        },
        "required": ["viz_type", "content_brief"],
    }
    tool_type = "inference"

    def __init__(self, vllm_base_url: Optional[str] = None, model: Optional[str] = None):
        # vLLM endpoint defaults to first known port; can be overridden
        # via env or constructor for multi-host setups.
        self._base_url = (
            vllm_base_url
            or os.environ.get("DOCVIZ_VLLM_BASE_URL")
            or "http://localhost:9101/v1"
        )
        self._model = model or os.environ.get("DOCVIZ_VLLM_MODEL", "Qwen3.6-27B")

    def execute(self, args: Dict[str, Any], context: Dict[str, Any]) -> str:
        viz_type = args.get("viz_type", "")
        content_brief = args.get("content_brief", "")
        # mode + query_id come from agent's per-call context (set by
        # S4_AgenticTMGv4 / v4_consolidated wrapper before run_paper_default)
        mode = context.get("tmg_mode", "v4_pool")
        query_id = context.get("query_id", "_unknown")

        if viz_type not in VIZ_TYPE_POOL:
            return json.dumps(
                {"error": f"invalid viz_type={viz_type!r}; must be one of {VIZ_TYPE_POOL}"},
                ensure_ascii=False,
            )
        if not content_brief:
            return json.dumps({"error": "content_brief is required"}, ensure_ascii=False)

        try:
            exemplar = _select_exemplar(viz_type, query_id, mode)
        except (FileNotFoundError, KeyError) as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

        prompt = self._build_prompt(viz_type, content_brief, exemplar)

        # Lazy import — keeps the module importable in environments
        # where openai is not installed (e.g., test discovery).
        try:
            from openai import OpenAI
        except ImportError:
            return json.dumps(
                {"error": "openai package not installed in agent server venv"},
                ensure_ascii=False,
            )

        client = OpenAI(base_url=self._base_url, api_key="EMPTY")
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                seed=42,
                max_tokens=4096,
                response_format={"type": "json_object"},
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        except Exception as e:
            return json.dumps({"error": f"vLLM call failed: {e}"}, ensure_ascii=False)

        raw = response.choices[0].message.content or ""
        # Pass through — mapper strategy 1a will parse the JSON downstream.
        # If the model deviated, surface the raw text so map_agent_response
        # can still attempt extraction.
        return raw

    def _build_prompt(self, viz_type: str, content_brief: str, exemplar: str) -> str:
        use_case = _VIZ_TYPE_USE_CASES.get(viz_type, "")
        return (
            f"You are a visualization DSL generator.\n\n"
            f"Target viz_type: {viz_type}\n"
            f"Use case: {use_case}\n\n"
            f"═══════════════════════════════════════════════════════════════\n"
            f"REFERENCE EXAMPLE — IMPORTANT GUIDANCE:\n"
            f"\n"
            f"Below is a reference example of a {viz_type} DSL. Use it ONLY\n"
            f"to learn the *syntax / schema / format* of {viz_type} (e.g.,\n"
            f"  - Mermaid header keyword and block layout, OR\n"
            f"  - Chart.js JSON object structure (type / data / options keys)\n"
            f"  - valid edge / node / data / label syntax)\n"
            f"\n"
            f"DO NOT copy the example's content patterns. Specifically, do\n"
            f"NOT carry over:\n"
            f"  - the example's domain (e.g., research provenance, energy LCOE)\n"
            f"  - the example's title format or structural layout\n"
            f"    (e.g., presence/absence of dates, section subgraphs,\n"
            f"     categorical-only edge labels, color palette)\n"
            f"  - the example's level of abstraction (categorical labels vs\n"
            f"    specific numbers / dates / quantities)\n"
            f"\n"
            f"INSTEAD, the content (nodes, edges, labels, titles, data\n"
            f"values, legends, fills, colors, structure depth) MUST come\n"
            f"from the user's query and source documents. Pick whatever\n"
            f"node/edge labels, title text, structural layout, and depth\n"
            f"are most useful for *this specific query and source* —\n"
            f"include source-specific dates, numbers, named entities,\n"
            f"quotes, and direct phrasing whenever the content brief\n"
            f"mentions them. Source-grounded specificity is the priority\n"
            f"over format symmetry with the example.\n"
            f"═══════════════════════════════════════════════════════════════\n"
            f"\n"
            f"Reference example (FORMAT/SYNTAX REFERENCE ONLY, NOT CONTENT):\n"
            f"{exemplar}\n\n"
            f"Content brief from the agent (THIS IS YOUR ACTUAL CONTENT SOURCE):\n"
            f"{content_brief}\n\n"
            f'Return ONLY a JSON object {{"viz_type": "{viz_type}", '
            f'"viz_dsl": "<the raw DSL string>"}}. No prose, no '
            f"markdown fences. Use named entities, specific numbers, dates, "
            f"and concrete phrases from the brief; do not invent unrelated "
            f"entities; do not abstract away source-specific quantities into "
            f"category labels. The example is a syntax guide, not a content "
            f"template."
        )


# Module-level instance — agent server discovers tool classes via
# `custom_tools_path` introspection (same pattern as real_vl_tools.py).
generate_viz = GenerateVizTool
