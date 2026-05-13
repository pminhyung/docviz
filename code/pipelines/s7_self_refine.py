"""S7 Self-Refine pipeline (≡ v0.3 §9 baseline B7: SelfRefine).

Implements the Madaan et al. 2023 NeurIPS "Self-Refine" protocol adapted
for document-grounded viz DSL generation:

    1. Initial generation: same as B5 Direct-LLM (concat docs + query →
       one LLM call → {viz_type, viz_dsl}).
    2. Self-critique: feed the initial viz_dsl + the original query and
       documents back to the same model and ask it to critique on three
       dimensions: (a) faithfulness to the source, (b) coverage of the
       query intent, (c) structural validity of the DSL.
    3. Refine: pass the original prompt + the initial output + the
       critique back to the model and ask it to produce a final
       {viz_type, viz_dsl}.

No retrieval, no agent loop, no sub-queries — it differs from B5 only in
the two-extra-LLM-call refinement loop. v0.3 §5.2 promotes this from a
within-method ablation variant to a top-level baseline (B7) so the paper
can claim DocViz-Agent improvements come from CIS/TMG/SAO, not just from
inference-time self-correction.

References:
    Madaan et al., "Self-Refine: Iterative Refinement with Self-Feedback",
    NeurIPS 2023 (https://arxiv.org/abs/2303.17651).
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


# ── Stage 1 prompt — initial generation (same shape as S1Direct's) ──────────
INITIAL_GEN_PROMPT = """\
You are a document-grounded visualization assistant.

User query:
{query}

Source documents (multi-doc bundle):
{docs_concat}

Produce ONE visualization that best answers the query, using the source
documents only — do not invent facts. Pick the most appropriate format from:

  - mermaid_flowchart    (for relational, process, dependency)
  - mermaid_timeline     (for temporal / time-ordered events)
  - mermaid_mindmap      (for hierarchical / taxonomy)
  - mermaid_sequenceDiagram (for interaction protocol / message sequence)
  - mermaid_classDiagram (for typed entity / structural schema)
  - chartjs_bar          (for quantitative single-series comparison)
  - chartjs_grouped_bar  (for quantitative multi-series)
  - chartjs_line         (for quantitative trend over ordered axis)
  - chartjs_pie          (for proportional / part-of-whole)
  - chartjs_scatter      (for bivariate correlation)

Return ONLY a JSON object with two fields:
  {{"viz_type": "<one of the 10 enums above>",
    "viz_dsl":  "<the raw DSL — Mermaid markdown or Chart.js JSON spec>"}}
No prose, no markdown fences around the JSON.
"""

# ── Stage 2 prompt — self-critique ──────────────────────────────────────────
CRITIQUE_PROMPT = """\
You produced the visualization below for the given query and source documents.
Critique it on three dimensions, citing specific evidence from the documents
where applicable. Be concise (≤ 2 sentences per dimension).

User query:
{query}

Source documents:
{docs_concat}

Your initial output:
{initial_output}

Critique:
1. Faithfulness — are all entities, dates, numbers, and relationships in the
   visualization actually present in the source documents? List any
   fabrications, mis-attributions, or contradictions.
2. Coverage — does the visualization address the user's query intent? List
   any salient facts from the documents that should be present but are
   missing.
3. Structural validity — is the DSL well-formed for its declared `viz_type`?
   For Mermaid: header keyword + valid node/edge syntax. For Chart.js:
   valid JSON with `type`, `data.labels`, `data.datasets[].data` arrays.
   List any syntax issues (unbalanced braces, missing required fields).

Return ONLY a JSON object with three keys:
  {{"faithfulness": "<critique>",
    "coverage":     "<critique>",
    "structural_validity": "<critique>"}}
No prose outside the JSON.
"""

# ── Stage 3 prompt — refine using critique ──────────────────────────────────
REFINE_PROMPT = """\
You are refining a document-grounded visualization based on a critique of
your previous attempt.

User query:
{query}

Source documents:
{docs_concat}

Your previous output:
{initial_output}

Critique of your previous output:
{critique}

Produce an IMPROVED visualization that addresses the critique. Pick the
most appropriate format from the same 10-type enum:
  mermaid_flowchart | mermaid_timeline | mermaid_mindmap |
  mermaid_sequenceDiagram | mermaid_classDiagram |
  chartjs_bar | chartjs_grouped_bar | chartjs_line | chartjs_pie | chartjs_scatter

You MAY change `viz_type` if a different type better fits the corrected
content. Address the critique's specific points: add missing salient facts
(coverage), remove fabrications and use only document-grounded entities/
numbers (faithfulness), and produce a structurally valid DSL.

Return ONLY a JSON object with two fields:
  {{"viz_type": "<one of the 10 enums>",
    "viz_dsl":  "<the raw DSL>"}}
No prose, no markdown fences.
"""


class S7SelfRefine(Pipeline):
    """Self-Refine baseline: initial → critique → refine in 3 LLM calls.

    No retrieval, no agent loop — same I/O contract as S1Direct but with
    two extra inference-time refinement calls. Total LLM calls per
    (query, bundle): 3.
    """

    name = "S7_SelfRefine"

    def __init__(
        self,
        client: QwenDirectClient | None = None,
        model: str = QWEN_MODEL,
        max_tokens: int = 4096,
        doc_char_cap: int = 12_000,
        critique_max_tokens: int = 1024,
    ):
        self._client = client or QwenDirectClient()
        self._model = model
        self._max_tokens = max_tokens
        self._doc_char_cap = doc_char_cap
        self._critique_max_tokens = critique_max_tokens

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

        # ── Stage 1: initial generation ─────────────────────────────────────
        try:
            stage1 = self._chat(
                INITIAL_GEN_PROMPT.format(query=query, docs_concat=docs_concat),
                max_tokens=self._max_tokens,
            )
            raw1 = self._msg_content(stage1)
            ti, to = self._usage_pair(stage1)
            total_tokens_in += ti
            total_tokens_out += to
        except Exception as e:
            errors.append(f"S7: stage-1 (initial) call failed: {e}")
            return self._empty_output(bundle, errors, total_tokens_in, total_tokens_out)

        initial_viz_type, initial_viz_dsl = _extract_dsl_block(raw1)
        if not initial_viz_type:
            initial_viz_type = "mermaid_flowchart"
            initial_viz_dsl = raw1
            errors.append("S7: stage-1 viz_type/viz_dsl JSON not found; using raw output")

        initial_output_str = json.dumps(
            {"viz_type": initial_viz_type, "viz_dsl": initial_viz_dsl},
            ensure_ascii=False,
        )

        # ── Stage 2: self-critique ──────────────────────────────────────────
        critique_str = ""
        try:
            stage2 = self._chat(
                CRITIQUE_PROMPT.format(
                    query=query,
                    docs_concat=docs_concat,
                    initial_output=initial_output_str,
                ),
                max_tokens=self._critique_max_tokens,
            )
            critique_str = self._msg_content(stage2)
            ti, to = self._usage_pair(stage2)
            total_tokens_in += ti
            total_tokens_out += to
        except Exception as e:
            errors.append(f"S7: stage-2 (critique) call failed: {e} — refining on initial only")

        if not critique_str.strip():
            critique_str = (
                "(critique unavailable — refine should still attempt to "
                "improve faithfulness, coverage, and structural validity)"
            )

        # ── Stage 3: refine using critique ──────────────────────────────────
        try:
            stage3 = self._chat(
                REFINE_PROMPT.format(
                    query=query,
                    docs_concat=docs_concat,
                    initial_output=initial_output_str,
                    critique=critique_str,
                ),
                max_tokens=self._max_tokens,
            )
            raw3 = self._msg_content(stage3)
            ti, to = self._usage_pair(stage3)
            total_tokens_in += ti
            total_tokens_out += to
        except Exception as e:
            errors.append(f"S7: stage-3 (refine) call failed: {e} — falling back to initial output")
            # Keep initial output as final.
            return VizOutput(
                viz_dsl=initial_viz_dsl,
                viz_type=initial_viz_type,
                rendered_image_path="",
                render_success=False,
                retrieved_chunks=[
                    {"doc_id": d.doc_id, "chunk_id": d.doc_id, "content": d.content}
                    for d in bundle.docs
                ],
                sub_queries=[],
                source_attribution={},
                tokens_in=total_tokens_in,
                tokens_out=total_tokens_out,
                cost_usd=0.0,
                errors=errors,
            )

        refined_viz_type, refined_viz_dsl = _extract_dsl_block(raw3)
        if not refined_viz_type:
            # Refine call didn't yield a usable JSON — keep initial.
            errors.append(
                "S7: stage-3 (refine) output had no parseable viz_type; "
                "keeping initial output"
            )
            refined_viz_type, refined_viz_dsl = initial_viz_type, initial_viz_dsl

        return VizOutput(
            viz_dsl=refined_viz_dsl,
            viz_type=refined_viz_type,
            rendered_image_path="",
            render_success=False,
            retrieved_chunks=[
                {"doc_id": d.doc_id, "chunk_id": d.doc_id, "content": d.content}
                for d in bundle.docs
            ],
            sub_queries=[],
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
            viz_dsl="",
            viz_type="",
            rendered_image_path="",
            render_success=False,
            retrieved_chunks=[
                {"doc_id": d.doc_id, "chunk_id": d.doc_id, "content": d.content}
                for d in bundle.docs
            ],
            sub_queries=[],
            source_attribution={},
            tokens_in=ti,
            tokens_out=to,
            cost_usd=0.0,
            errors=errors,
        )
