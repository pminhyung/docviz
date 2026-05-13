"""B3 CoDA-adapted (Code Data Analyst, 2025).

v0.3 amendment §9 baseline: "CoDA-adapted — Treat docs as text dataset →
run CoDA's analyzer agent. Treat docs as CSV-like."

CoDA's distinctive idea: an "Analyzer Agent" first explores the data
corpus to identify what's interesting before generating any
visualization. This contrasts with MatPlotAgent (B1) which jumps to
code generation, and with NVAGENT (B2) which extracts a fixed table
upfront. CoDA's analyzer can pivot the framing if the data reveals an
unexpected angle.

Reimplemented on-prem so the same QwenDirectClient (multi-host queue +
retry) is used end-to-end. Two-LLM-call pipeline:
  1. Analyzer Agent: examine the multi-doc bundle as a "data corpus",
     identify ≥3 candidate analytical angles + pick the one that best
     answers the user query. Output: JSON {chosen_angle, candidates}.
  2. Viz Spec Generator: given (query, chosen_angle, source docs),
     produce the Chart.js / Mermaid DSL.

Output mapping to docviz VizOutput:
  - viz_type ∈ 10-type enum
  - viz_dsl = the generated DSL (renderable via code.render)
  - sub_queries = [chosen_angle, alternative1, alternative2, ...]
  - retrieved_chunks = full bundle docs
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from code.adapters.agent_client import (
    PAPER_DEFAULT_SEED,
    QWEN_MODEL,
    QWEN_NON_THINKING_SAMPLING,
    QwenDirectClient,
)
from code.adapters.viz_output_mapper import _extract_dsl_block
from code.pipelines.base import Bundle, Pipeline, VizOutput


# ── Stage 1: Analyzer Agent ─────────────────────────────────────────────────
ANALYZER_PROMPT = """\
You are the Analyzer Agent of CoDA (Code Data Analyst, 2025).

The user has asked the following query about a multi-document text bundle:

User query:
{query}

Source documents (treat as a data corpus to analyze):
{docs_concat}

Your task: examine the corpus, identify 3-4 candidate analytical angles
that could answer the user's query, then select the best one. Each angle
is one sentence describing what could be measured / compared / shown.
The chosen angle drives the downstream viz generation.

Considerations:
  - Prefer angles that are well-grounded in the corpus (specific
    entities, dates, numbers, relationships present in the documents).
  - Prefer the angle that best matches the user query's intent.
  - Avoid angles that would require inference or fabrication.

Return ONLY a JSON object:
  {{"candidates":     ["angle 1", "angle 2", "angle 3"],
    "chosen_angle":   "<the picked angle, 1 sentence>",
    "rationale":      "<1 short sentence on why chosen>"}}

No prose outside the JSON. No markdown fences.
"""

# ── Stage 2: Viz Spec Generator ─────────────────────────────────────────────
VIZ_SPEC_PROMPT = """\
You are the Visualization Spec Generator of CoDA (2025).

The user's original query:
{query}

The Analyzer Agent's chosen analytical angle:
{chosen_angle}

Source documents (for grounding the data values):
{docs_concat}

Your task: produce ONE visualization that implements the chosen angle.

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

DSL format requirements:
  - For chartjs_* types: viz_dsl is a VALID JSON STRING of a Chart.js
    spec with keys `type`, `data.labels`, `data.datasets[].label`,
    `data.datasets[].data`, and `options.title.text`. Use double-quoted
    JSON, not JS object literal or YAML. Example shape:
      "{{\\"type\\":\\"bar\\",\\"data\\":{{\\"labels\\":[\\"A\\",\\"B\\"],\\"datasets\\":[{{\\"label\\":\\"x\\",\\"data\\":[1,2]}}]}},\\"options\\":{{\\"title\\":{{\\"display\\":true,\\"text\\":\\"...\\"}}}}}}"
  - For mermaid_* types: viz_dsl is a Mermaid markdown string starting
    with a header keyword (graph, timeline, mindmap, sequenceDiagram,
    classDiagram).

Keep the spec minimal — do NOT add tooltip callbacks, ticks formatters,
JS function strings, or styling beyond the exemplar level. Every "{{"
must have a matching "}}".

Return ONLY a JSON object:
  {{"viz_type": "<one of the 10 enums>",
    "viz_dsl":  "<the raw DSL string per format above>"}}
No prose, no markdown fences.
"""


class B3CoDA(Pipeline):
    """B3 CoDA-adapted baseline.

    Two-LLM-call agentic pipeline (analyzer → viz_spec).
    """

    name = "B3_CoDA"

    def __init__(
        self,
        client: QwenDirectClient | None = None,
        model: str = QWEN_MODEL,
        max_tokens_analyzer: int = 800,
        max_tokens_viz: int = 4096,
        doc_char_cap: int = 12_000,
    ):
        self._client = client or QwenDirectClient()
        self._model = model
        self._max_tokens_analyzer = max_tokens_analyzer
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

        # ── Stage 1: Analyzer ──────────────────────────────────────────
        chosen_angle = ""
        candidates: List[str] = []
        try:
            stage1 = self._chat(
                ANALYZER_PROMPT.format(query=query, docs_concat=docs_concat),
                self._max_tokens_analyzer,
            )
            raw1 = self._msg_content(stage1)
            ti, to = self._usage_pair(stage1)
            total_tokens_in += ti
            total_tokens_out += to
            try:
                a = json.loads(raw1)
                chosen_angle = (a.get("chosen_angle") or "").strip()
                candidates = [str(c) for c in (a.get("candidates") or [])]
            except json.JSONDecodeError as e:
                errors.append(f"B3: analyzer JSON parse failed: {e}; using raw")
                chosen_angle = raw1[:300]
        except Exception as e:
            errors.append(f"B3: stage-1 (analyzer) failed: {e}")
            return self._empty_output(bundle, errors,
                                      total_tokens_in, total_tokens_out)

        if not chosen_angle:
            chosen_angle = f"answer the user's query directly: {query}"

        # ── Stage 2: Viz Spec ──────────────────────────────────────────
        try:
            stage2 = self._chat(
                VIZ_SPEC_PROMPT.format(
                    query=query,
                    chosen_angle=chosen_angle,
                    docs_concat=docs_concat,
                ),
                self._max_tokens_viz,
            )
            raw2 = self._msg_content(stage2)
            ti, to = self._usage_pair(stage2)
            total_tokens_in += ti
            total_tokens_out += to
        except Exception as e:
            errors.append(f"B3: stage-2 (viz_spec) failed: {e}")
            return self._empty_output(bundle, errors,
                                      total_tokens_in, total_tokens_out)

        viz_type, viz_dsl = _extract_dsl_block(raw2)
        if not viz_type:
            viz_type = "mermaid_flowchart"
            viz_dsl = raw2
            errors.append("B3: stage-2 viz_type/viz_dsl JSON not found; using fallback")

        return VizOutput(
            viz_dsl=viz_dsl,
            viz_type=viz_type,
            rendered_image_path="",
            render_success=False,
            retrieved_chunks=[
                {"doc_id": d.doc_id, "chunk_id": d.doc_id, "content": d.content}
                for d in bundle.docs
            ],
            sub_queries=[chosen_angle] + candidates[:3],
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
