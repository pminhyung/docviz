"""V4 custom tool — viz_type-aware DSL generator with sidecar persistence.

This tool is loaded into the vendored agent via `custom_tools_path`. The
agent reasons over the user query and source content, decides which
viz_type from the 10-enum pool best fits, then calls this tool with that
viz_type plus a content brief. The tool internally:

  1. Looks up the type-matched exemplar from `oneshot_pool.json`
     (per-type pool sample for V4_pool, single integrated example for
     V4_consolidated).
  2. Calls the on-prem Qwen3.5-397B-A17B-FP8 vLLM endpoint with the exemplar +
     content brief as one-shot prompt.
  3. **Writes the produced viz to a sidecar JSON file** keyed by
     `(tmg_mode, query_id)` under `DOCVIZ_VIZ_SIDECAR_DIR`
     (default `/tmp/v4_viz_outputs`). The orchestrator
     (`code/pipelines/s4_agentic_tmg.py:S4AgenticTMG.run`) reads
     the sidecar after the agent returns to populate `VizOutput`.
  4. Returns a short status JSON (e.g., `{"status": "viz_generated",
     "viz_type": ..., "viz_dsl_chars": N}`) so the agent's
     `<final_answer>` can be a one-sentence ack and need not repeat
     the (potentially large) viz_dsl.

This realizes PAPER_MASTER_SPEC §3.2 (Provisional, 2026-05-10) — the
agent makes the type decision; the tool scaffolds the DSL and persists.

Schema sources of truth:
  - `code/pipelines/tmg.py:VIZ_TYPE_POOL` (the 10-enum)
  - `code/agent_tools/oneshot_pool.json` (sidecar; populated from Q2
    revision draft, commit b3bebcf)

Mode dispatch:
  - context["tool_secrets"]["tmg_mode"] ∈ {"v4_pool", "v4_consolidated"}
  - context["tool_secrets"]["query_id"] — record key for sidecar path

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


# oneshot_pool sidecar (read-only) — populated from Q2 revision (b3bebcf).
# Schema: {"pool": {<viz_type>: [<exemplar_json_str>, ...]},
#          "consolidated": {<viz_type>: <exemplar_json_str>}}
#
# NOTE: `Path(__file__).parent` is unsafe here — the agent server
# (ToolRegistry.load_from_file) COPIES this .py file to a tempfile.mkdtemp
# directory and exec_module's it from there. `__file__` therefore points
# at /tmp/doc_agent_tools_XXXX/generate_viz.py, where no sidecar exists.
# Use the absolute path the orchestrator (or env override) supplies.
_POOL_PATH = Path(os.environ.get(
    "DOCVIZ_ONESHOT_POOL_PATH",
    "/ex_disk2/mhpark/poc/docviz/code/agent_tools/oneshot_pool.json",
))

# viz_output sidecar (write) — orchestrator reads this after agent
# returns. Each entry: /{DOCVIZ_VIZ_SIDECAR_DIR}/{tmg_mode}_{query_id}.json
# = {"viz_type": "...", "viz_dsl": "..."}
_DEFAULT_OUTPUT_SIDECAR_DIR = "/tmp/v4_viz_outputs"


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
        "decided which viz_type from the 10-enum pool best fits the "
        "query and source content. The tool persists the produced viz "
        "to a sidecar file for the downstream pipeline; it returns a "
        "short status JSON (e.g., "
        '{"status": "viz_generated", "viz_type": "...", '
        '"viz_dsl_chars": N}). After calling this tool, produce a '
        "brief one-sentence <final_answer> acknowledgment — do not "
        "repeat the DSL."
    )
    parameters = {
        "type": "object",
        "properties": {
            "viz_type": {
                "type": "string",
                "enum": VIZ_TYPE_POOL,
                "description": (
                    "The visualization type chosen for this query. "
                    "Must be one of the 10 enum values."
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
        # Default vLLM endpoint = first host in the on-prem Qwen3.5-397B
        # cluster. Per-call override comes through context["tool_secrets"]
        # ["vllm_base_url"], set by the orchestrator so the tool uses the
        # SAME host as the agent's reasoner (per-sample parallel).
        self._base_url = (
            vllm_base_url
            or os.environ.get("DOCVIZ_VLLM_BASE_URL")
            or "http://10.1.211.163:8000/v1"
        )
        self._model = model or os.environ.get(
            "DOCVIZ_VLLM_MODEL", "Qwen3.5-397B-A17B-FP8"
        )

    def execute(self, args: Dict[str, Any], context: Dict[str, Any]) -> str:
        viz_type = args.get("viz_type", "")
        content_brief = args.get("content_brief", "")
        # mode + query_id come from agent's per-call context (set by
        # S4_AgenticTMG.run() V4 mode via tool_secrets in the request body;
        # the agent server forwards tool_secrets into context here).
        secrets = context.get("tool_secrets") or {}
        mode = secrets.get("tmg_mode", "v4_pool")
        query_id = secrets.get("query_id", "_unknown")

        if viz_type not in VIZ_TYPE_POOL:
            return json.dumps(
                {"status": "error",
                 "error": f"invalid viz_type={viz_type!r}; must be one of {VIZ_TYPE_POOL}"},
                ensure_ascii=False,
            )
        if not content_brief:
            return json.dumps(
                {"status": "error", "error": "content_brief is required"},
                ensure_ascii=False,
            )

        try:
            exemplar = _select_exemplar(viz_type, query_id, mode)
        except (FileNotFoundError, KeyError) as e:
            return json.dumps(
                {"status": "error", "error": str(e)},
                ensure_ascii=False,
            )

        prompt = self._build_prompt(viz_type, content_brief, exemplar)

        # Lazy import — keeps the module importable in environments
        # where openai is not installed (e.g., test discovery).
        try:
            from openai import OpenAI
        except ImportError:
            return json.dumps(
                {"status": "error",
                 "error": "openai package not installed in agent server venv"},
                ensure_ascii=False,
            )

        # Per-call vLLM URL override — orchestrator sticks the agent's
        # reasoner host on tool_secrets so tool ↔ reasoner share the host.
        base_url = secrets.get("vllm_base_url") or self._base_url
        client = OpenAI(base_url=base_url, api_key="EMPTY")

        def _call() -> Any:
            # Qwen3.5-397B recommended non-thinking sampling:
            # T=0.7, top_p=0.8, top_k=20, min_p=0. seed=42 for in-run
            # reproducibility.
            return client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                top_p=0.8,
                seed=42,
                max_tokens=4096,
                response_format={"type": "json_object"},
                extra_body={
                    "top_k": 20,
                    "min_p": 0,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            )

        # 3-second retry on transient failures (matches QwenDirectClient
        # semantics — connection-refused is fatal here since the tool
        # has a sticky base_url tied to the agent's reasoner host).
        import time as _t
        try:
            response = _call()
        except Exception as e:
            err_text = str(e).lower()
            is_refused = "connect" in err_text and (
                "refused" in err_text or "unreachable" in err_text
            )
            if is_refused:
                return json.dumps(
                    {"status": "error", "error": f"vLLM connect refused: {e}"},
                    ensure_ascii=False,
                )
            # transient: 3s sleep + 1 retry
            _t.sleep(3.0)
            try:
                response = _call()
            except Exception as e2:
                return json.dumps(
                    {"status": "error",
                     "error": f"vLLM call failed twice: first={e} retry={e2}"},
                    ensure_ascii=False,
                )

        raw = response.choices[0].message.content or ""

        # Parse the LLM output to extract (viz_type, viz_dsl).
        # Mapper strategy 1a equivalent — whole-text JSON parse.
        viz_dsl = ""
        out_viz_type = viz_type
        try:
            stripped = raw.lstrip()
            if stripped.startswith("{"):
                obj, _ = json.JSONDecoder().raw_decode(stripped)
                if isinstance(obj, dict):
                    parsed_type = obj.get("viz_type", "")
                    parsed_dsl = obj.get("viz_dsl", "")
                    if parsed_type:
                        out_viz_type = parsed_type
                    if isinstance(parsed_dsl, str):
                        viz_dsl = parsed_dsl
                    elif isinstance(parsed_dsl, (dict, list)):
                        # Re-serialize nested object → string (chartjs case)
                        viz_dsl = json.dumps(parsed_dsl, ensure_ascii=False)
        except Exception:
            pass

        if not viz_dsl:
            # LLM didn't produce parseable JSON. Return raw + error status
            # so the agent has visibility; do NOT write a stale sidecar.
            return json.dumps(
                {"status": "error",
                 "error": "LLM did not return parseable {viz_type, viz_dsl} JSON",
                 "raw_preview": raw[:300]},
                ensure_ascii=False,
            )

        # Persist viz output to sidecar so the orchestrator can read it
        # without parsing the agent's <final_answer>.
        sidecar_dir = Path(
            os.environ.get("DOCVIZ_VIZ_SIDECAR_DIR", _DEFAULT_OUTPUT_SIDECAR_DIR)
        )
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        sidecar_path = sidecar_dir / f"{mode}_{query_id}.json"
        sidecar_path.write_text(
            json.dumps(
                {"viz_type": out_viz_type, "viz_dsl": viz_dsl},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # Return short status to the agent — its <final_answer> can be
        # a one-sentence ack, no need to repeat the DSL.
        return json.dumps(
            {
                "status": "viz_generated",
                "viz_type": out_viz_type,
                "viz_dsl_chars": len(viz_dsl),
                "sidecar_path": str(sidecar_path),
            },
            ensure_ascii=False,
        )

    def _build_prompt(self, viz_type: str, content_brief: str, exemplar: str) -> str:
        use_case = _VIZ_TYPE_USE_CASES.get(viz_type, "")
        return (
            f"You are a visualization DSL generator. Convert the content "
            f"brief into a single valid {viz_type} DSL ({use_case}).\n"
            f"\n"
            f"The reference example below shows the SYNTAX of {viz_type} "
            f"only — Mermaid header keyword and block layout, or Chart.js "
            f"JSON object structure (`type`/`data`/`options` keys), or "
            f"valid edge/node/dataset/label/cardinality syntax. Use it as "
            f"a syntax reference, not as a content template. Do not carry "
            f"over the example's domain, title format, structural layout, "
            f"color palette, or level of abstraction; pick whatever is most "
            f"useful for the brief below.\n"
            f"\n"
            f"Reference example (syntax only):\n"
            f"{exemplar}\n"
            f"\n"
            f"Content brief from the agent:\n"
            f"{content_brief}\n"
            f"\n"
            f"When generating the DSL: preserve every specific fact present "
            f"in the brief — named entities, dates, numerical quantities, "
            f"role descriptions, quoted phrases — by placing them in the "
            f"location appropriate for the {viz_type} grammar:\n"
            f"  - For chartjs_* types, numeric quantities go into the "
            f"`data` arrays as numbers, with their context preserved in "
            f"`labels` / `dataset.label` / `options.title` (units, "
            f"timeframes, named entities). Format conversion (e.g., "
            f"\"$150,000\" → 150000 with a label/title noting the unit) "
            f"is acceptable as long as the value and its meaning survive.\n"
            f"  - For mermaid_* types, names / dates / quantities go into "
            f"node labels, edge labels, or annotations as text — preserved "
            f"in their natural source form when meaningful (e.g., "
            f"\"Donated $150,000\" as an edge label rather than reducing "
            f"to a generic \"Donation\" link).\n"
            f"Do not omit a fact because the example's structure would not "
            f"naturally include it; alter the structure to fit the brief's "
            f"facts instead.\n"
            f"\n"
            f"Output simplicity (CRITICAL for valid output):\n"
            f"  - Match the exemplar's structural depth — do NOT introduce "
            f"keys or nesting levels that are not present in the exemplar.\n"
            f"  - For chartjs_* types, do NOT add tooltip callbacks, "
            f"`ticks.callback` formatters, JS function strings (e.g. "
            f"`\"function(context){{...}}\"`), animation configs, or any "
            f"plugin not shown in the exemplar. These features are NOT "
            f"required for valid Chart.js output and significantly "
            f"increase the risk of malformed JSON. Place units / "
            f"formatting context in `dataset.label` / `options.title` / "
            f"`scales.*.title` text instead.\n"
            f"  - For mermaid_* types, avoid styling directives "
            f"(`classDef`, `style ... fill:`, theme blocks) unless the "
            f"exemplar includes them.\n"
            f"  - Keep your output's brace/bracket nesting balance "
            f"verifiable by eye — every `{{` must have a matching `}}`.\n"
            f"\n"
            f"Return ONLY a JSON object "
            f'{{"viz_type": "{viz_type}", "viz_dsl": "<the raw DSL string>"}}. '
            f"No prose, no markdown fences."
        )


# Module-level instance — agent server discovers tool classes via
# `custom_tools_path` introspection (same pattern as real_vl_tools.py).
generate_viz = GenerateVizTool
