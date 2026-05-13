"""B4 ViviDoc-style (ViviBench/ViviDoc, 2026).

v0.3 amendment §9 baseline: "ViviDoc-style — Use query as topic → run
ViviDoc planner-executor. Topic = query reframing."

ViviDoc's distinctive idea: a planner-executor architecture where a
Planner LLM first reframes the user query as a TOPIC + an outline of
viz components, then an Executor LLM generates each component. This
captures the structured "viz as multi-section answer" style ViviDoc
uses for interactive document visualization.

Reimplemented on-prem so the same QwenDirectClient is used end-to-end.
For the docviz comparison we collapse the planner-executor to its core
two-LLM-call shape with output as a single viz DSL (rather than
ViviDoc's multi-section interactive output, which would require its
own renderer):
  1. Planner: reframe the query as a topic + outline what to visualize.
     Output: JSON {topic, sections: [...], primary_viz: "<type>"}.
  2. Executor: generate the viz DSL given (topic, primary_viz, source).

This is the closest single-output approximation of ViviDoc's
planner-executor decomposition.

Output mapping to docviz VizOutput:
  - viz_type ∈ 10-type enum
  - viz_dsl = the executed DSL
  - sub_queries = [topic, section_1, section_2, ...]
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


PLANNER_PROMPT = """\
You are the Planner of ViviDoc (ViviBench/ViviDoc, 2026).

The user has asked the following query about a multi-document text bundle:

User query:
{query}

Source documents:
{docs_concat}

Your task: reframe the user query as a TOPIC and outline the
visualization plan. The plan has:
  - "topic": a 1-sentence reframing of what the visualization is about
  - "sections": 2-4 short bullet labels describing the sub-aspects the
    viz should cover (these become the elements / nodes / data series)
  - "primary_viz": the best Chart.js / Mermaid type from this 10-type
    enum:
        chartjs_bar, chartjs_line, chartjs_grouped_bar, chartjs_pie,
        chartjs_scatter, mermaid_flowchart, mermaid_timeline,
        mermaid_mindmap, mermaid_sequenceDiagram, mermaid_classDiagram

Return ONLY a JSON object:
  {{"topic":       "<1 sentence>",
    "sections":    ["...", "...", ...],
    "primary_viz": "<one viz_type enum>"}}

No prose outside the JSON.
"""

EXECUTOR_PROMPT = """\
You are the Executor of ViviDoc (2026).

Planner's reframing:
  topic:       {topic}
  sections:    {sections}
  primary_viz: {primary_viz}

User's original query:
{query}

Source documents (for grounding the data values):
{docs_concat}

Your task: implement the planner's primary_viz with the listed sections
as the visualization's elements. Use only facts present in the source
documents.

DSL format requirements:
  - For chartjs_* types: viz_dsl is a VALID JSON STRING of a Chart.js
    spec with keys `type`, `data.labels`, `data.datasets[].label`,
    `data.datasets[].data`, and `options.title.text`. Use double-quoted
    JSON, not JS object literal or YAML. Example shape:
      "{{\\"type\\":\\"bar\\",\\"data\\":{{\\"labels\\":[\\"A\\",\\"B\\"],\\"datasets\\":[{{\\"label\\":\\"x\\",\\"data\\":[1,2]}}]}},\\"options\\":{{\\"title\\":{{\\"display\\":true,\\"text\\":\\"...\\"}}}}}}"
  - For mermaid_* types: viz_dsl is a Mermaid markdown string starting
    with a header keyword (graph, timeline, mindmap, sequenceDiagram,
    classDiagram).

Keep the DSL minimal — do NOT add tooltip callbacks, ticks formatters,
JS function strings, or unnecessary styling. Every "{{" must have a
matching "}}". Match the planner's chosen primary_viz exactly.

Return ONLY a JSON object:
  {{"viz_type": "{primary_viz}",
    "viz_dsl":  "<the raw DSL string per format above>"}}
No prose, no markdown fences.
"""


class B4ViviDoc(Pipeline):
    """B4 ViviDoc-style baseline.

    Two-LLM-call planner-executor pipeline.
    """

    name = "B4_ViviDoc"

    def __init__(
        self,
        client: QwenDirectClient | None = None,
        model: str = QWEN_MODEL,
        max_tokens_planner: int = 600,
        max_tokens_executor: int = 4096,
        doc_char_cap: int = 12_000,
    ):
        self._client = client or QwenDirectClient()
        self._model = model
        self._max_tokens_planner = max_tokens_planner
        self._max_tokens_executor = max_tokens_executor
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

        # ── Stage 1: Planner ───────────────────────────────────────────
        topic = ""
        sections: List[str] = []
        primary_viz = "mermaid_flowchart"
        try:
            stage1 = self._chat(
                PLANNER_PROMPT.format(query=query, docs_concat=docs_concat),
                self._max_tokens_planner,
            )
            raw1 = self._msg_content(stage1)
            ti, to = self._usage_pair(stage1)
            total_tokens_in += ti
            total_tokens_out += to
            try:
                p = json.loads(raw1)
                topic = (p.get("topic") or "").strip()
                sections = [str(s) for s in (p.get("sections") or [])]
                pv = (p.get("primary_viz") or "").strip()
                if pv:
                    primary_viz = pv
            except json.JSONDecodeError as e:
                errors.append(f"B4: planner JSON parse failed: {e}; using fallback")
                topic = query
                sections = []
        except Exception as e:
            errors.append(f"B4: stage-1 (planner) failed: {e}")
            return self._empty_output(bundle, errors,
                                      total_tokens_in, total_tokens_out)

        # ── Stage 2: Executor ──────────────────────────────────────────
        try:
            stage2 = self._chat(
                EXECUTOR_PROMPT.format(
                    topic=topic or query,
                    sections=json.dumps(sections, ensure_ascii=False),
                    primary_viz=primary_viz,
                    query=query,
                    docs_concat=docs_concat,
                ),
                self._max_tokens_executor,
            )
            raw2 = self._msg_content(stage2)
            ti, to = self._usage_pair(stage2)
            total_tokens_in += ti
            total_tokens_out += to
        except Exception as e:
            errors.append(f"B4: stage-2 (executor) failed: {e}")
            return self._empty_output(bundle, errors,
                                      total_tokens_in, total_tokens_out)

        viz_type, viz_dsl = _extract_dsl_block(raw2)
        if not viz_type:
            viz_type = primary_viz
            viz_dsl = raw2
            errors.append("B4: stage-2 viz_type/viz_dsl JSON not found; using fallback")

        return VizOutput(
            viz_dsl=viz_dsl,
            viz_type=viz_type,
            rendered_image_path="",
            render_success=False,
            retrieved_chunks=[
                {"doc_id": d.doc_id, "chunk_id": d.doc_id, "content": d.content}
                for d in bundle.docs
            ],
            sub_queries=[topic or query] + sections[:4],
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
