"""B2 NVAGENT-adapted (Wu et al., NVAGENT, ACL 2025).

v0.3 amendment §9 baseline: "NVAGENT-adapted — Concat docs → extract
pseudo-table → pass to NVAGENT VQL pipeline. Pseudo-table extraction."

We reimplement the NVAGENT pipeline on-prem so the same QwenDirectClient
(multi-host queue + retry) is used end-to-end. The NVAGENT protocol's
core idea — extract structured tabular data from the raw input before
asking the LLM to produce a visualization — distinguishes B2 from
B5 Direct-LLM (no extraction step) and from B1 MatPlotAgent (no explicit
table; goes straight to code).

Stages (2 LLM calls):
  1. Pseudo-table extraction: convert the multi-doc bundle into a JSON
     table {columns: [...], rows: [[...], ...]} that captures the
     numeric / categorical / temporal facts the query will visualize.
  2. Viz generation: given (query, pseudo_table), generate a single
     Chart.js spec (one of our 10 viz_type enum values) that plots the
     answer. Chart.js chosen for renderer compatibility — NVAGENT's
     original output (Vega-Lite VQL) would require a separate renderer.

Output mapping to docviz VizOutput:
  - viz_type ∈ chartjs_{bar, line, grouped_bar, pie, scatter}
  - viz_dsl = the Chart.js JSON spec (renderable via code.render)
  - sub_queries = ["pseudo_table: <rows>"] (the agentic action B2 takes)
  - retrieved_chunks = full bundle docs (same as B5)
  - render_success / rendered_image_path set by upstream render() call
    in run_prototype.py
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from code.adapters.agent_client import (
    PAPER_DEFAULT_SEED,
    QWEN_MODEL,
    QWEN_NON_THINKING_SAMPLING,
    QwenDirectClient,
)
from code.adapters.viz_output_mapper import _extract_dsl_block
from code.pipelines.base import Bundle, Pipeline, VizOutput


# ── Stage 1: Pseudo-table extraction ────────────────────────────────────────
PSEUDO_TABLE_PROMPT = """\
You are the Pseudo-Table Extraction stage of NVAGENT (Wu et al., ACL 2025).

A user has asked the following query about a multi-document text bundle:

User query:
{query}

Source documents (multi-doc bundle):
{docs_concat}

Your task: extract from the source documents the structured tabular data
needed to answer the user's query as a chart. The output is a JSON
"pseudo-table" with two top-level keys:
  - "columns": ordered list of column names (≤8 columns).
  - "rows": list of rows, each row is a list of cells aligned with
    "columns". Cells are strings or numbers. ≤25 rows.

The pseudo-table should:
  - Contain ONLY facts present in the source documents above (no
    inference, no fabrication; if a value is missing, omit the row).
  - Be visualization-ready: numeric cells as numbers, dates as
    "YYYY" or "YYYY-MM" strings, categorical labels as short strings.
  - Capture the entities, values, and timeframes the user query implies
    are relevant.

Return ONLY a JSON object: {{"columns": [...], "rows": [[...], ...]}}.
No prose, no markdown fences.
"""

# ── Stage 2: Viz generation from pseudo-table ───────────────────────────────
VIZ_GEN_PROMPT = """\
You are the Visualization Generation stage of NVAGENT (Wu et al., ACL 2025).

Pseudo-table extracted from the source documents:
{pseudo_table}

Original user query:
{query}

Your task: choose the most appropriate Chart.js visualization type and
write a single Chart.js spec that plots the pseudo-table as an answer to
the user's query.

Allowed viz_type values (10-type enum):
  - chartjs_bar           (single-series quantitative comparison)
  - chartjs_line          (trend over an ordered axis)
  - chartjs_grouped_bar   (multi-series quantitative comparison)
  - chartjs_pie           (proportion / part-of-whole)
  - chartjs_scatter       (bivariate correlation)
  - mermaid_flowchart     (relational / process)
  - mermaid_timeline      (chronological events)
  - mermaid_mindmap       (hierarchical taxonomy)
  - mermaid_sequenceDiagram (interaction protocol)
  - mermaid_classDiagram  (typed structural schema)

For chartjs_* types: viz_dsl is the Chart.js JSON spec string with
`type`, `data.labels`, `data.datasets[{{label, data}}]`, and `options.title`.
For mermaid_* types: viz_dsl is the Mermaid markdown string.

Keep the spec minimal — do NOT add tooltip callbacks, ticks formatters,
JS function strings, or styling beyond `backgroundColor` / `borderColor`.
Every "{{" must have a matching "}}".

Return ONLY a JSON object:
  {{"viz_type": "<one of the 10 enums>",
    "viz_dsl":  "<the raw DSL string>"}}
No prose, no markdown fences.
"""


class B2NVAGENT(Pipeline):
    """B2 NVAGENT-adapted baseline.

    Two-LLM-call agentic pipeline (pseudo_table → viz_gen). Output is
    Chart.js / Mermaid DSL renderable via the project's code.render
    pipeline.
    """

    name = "B2_NVAGENT"

    def __init__(
        self,
        client: QwenDirectClient | None = None,
        model: str = QWEN_MODEL,
        max_tokens_table: int = 1500,
        max_tokens_viz: int = 4096,
        doc_char_cap: int = 12_000,
    ):
        self._client = client or QwenDirectClient()
        self._model = model
        self._max_tokens_table = max_tokens_table
        self._max_tokens_viz = max_tokens_viz
        self._doc_char_cap = doc_char_cap

    def _docs_concat(self, bundle: Bundle) -> str:
        parts: List[str] = []
        for d in bundle.docs:
            body = (d.content or "")[: self._doc_char_cap]
            parts.append(f"[{d.title}]\n{body}")
        return "\n\n---\n\n".join(parts)

    def _chat(self, prompt: str, max_tokens: int) -> Dict[str, Any]:
        return self._client.chat(
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            temperature=QWEN_NON_THINKING_SAMPLING["temperature"],
            top_p=QWEN_NON_THINKING_SAMPLING["top_p"],
            seed=PAPER_DEFAULT_SEED,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            extra_body=QWEN_NON_THINKING_SAMPLING["extra_body"],
        )

    @staticmethod
    def _msg_content(resp: Dict[str, Any]) -> str:
        msg = resp["choices"][0]["message"]
        return msg.get("content") or msg.get("reasoning") or ""

    @staticmethod
    def _usage_pair(resp: Dict[str, Any]) -> tuple[int, int]:
        u = resp.get("usage") or {}
        return int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))

    def run(
        self,
        query: str,
        bundle: Bundle,
        *,
        query_type: str | None = None,
        query_id: str | None = None,
    ) -> VizOutput:
        docs_concat = self._docs_concat(bundle)
        errors: List[str] = []
        total_tokens_in = 0
        total_tokens_out = 0

        # ── Stage 1: pseudo-table extraction ───────────────────────────
        pseudo_table_str = "{}"
        try:
            stage1 = self._chat(
                PSEUDO_TABLE_PROMPT.format(query=query, docs_concat=docs_concat),
                self._max_tokens_table,
            )
            raw1 = self._msg_content(stage1)
            ti, to = self._usage_pair(stage1)
            total_tokens_in += ti
            total_tokens_out += to
            try:
                parsed_table = json.loads(raw1)
                # Re-serialize compactly so the stage-2 prompt is bounded
                pseudo_table_str = json.dumps(parsed_table, ensure_ascii=False)
            except json.JSONDecodeError as e:
                errors.append(f"B2: pseudo-table not parseable JSON: {e}; "
                              "passing raw text to stage-2")
                pseudo_table_str = raw1[:2000]
        except Exception as e:
            errors.append(f"B2: stage-1 (pseudo-table) failed: {e}")
            return self._empty_output(bundle, errors,
                                      total_tokens_in, total_tokens_out)

        # ── Stage 2: viz generation ────────────────────────────────────
        try:
            stage2 = self._chat(
                VIZ_GEN_PROMPT.format(query=query, pseudo_table=pseudo_table_str),
                self._max_tokens_viz,
            )
            raw2 = self._msg_content(stage2)
            ti, to = self._usage_pair(stage2)
            total_tokens_in += ti
            total_tokens_out += to
        except Exception as e:
            errors.append(f"B2: stage-2 (viz_gen) failed: {e}")
            return self._empty_output(bundle, errors,
                                      total_tokens_in, total_tokens_out)

        viz_type, viz_dsl = _extract_dsl_block(raw2)
        if not viz_type:
            viz_type = "mermaid_flowchart"
            viz_dsl = raw2
            errors.append("B2: stage-2 viz_type/viz_dsl JSON not found; using fallback")

        return VizOutput(
            viz_dsl=viz_dsl,
            viz_type=viz_type,
            rendered_image_path="",
            render_success=False,
            retrieved_chunks=[
                {"doc_id": d.doc_id, "chunk_id": d.doc_id, "content": d.content}
                for d in bundle.docs
            ],
            sub_queries=[f"pseudo_table: {pseudo_table_str[:400]}"],
            source_attribution={},
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            cost_usd=0.0,
            errors=errors,
        )

    @staticmethod
    def _empty_output(
        bundle: Bundle, errors: List[str], ti: int, to: int
    ) -> VizOutput:
        return VizOutput(
            viz_dsl="", viz_type="",
            rendered_image_path="", render_success=False,
            retrieved_chunks=[
                {"doc_id": d.doc_id, "chunk_id": d.doc_id, "content": d.content}
                for d in bundle.docs
            ],
            sub_queries=[], source_attribution={},
            tokens_in=ti, tokens_out=to, cost_usd=0.0, errors=errors,
        )
