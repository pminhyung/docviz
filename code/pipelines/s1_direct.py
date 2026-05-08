"""S1 Direct pipeline (≡ §7 baseline B5: Direct-LLM).

Concat all bundle docs + query → single Qwen3.6-27B chat call → JSON output
{viz_type, viz_dsl}. No agent loop, no retrieval, no sub-queries.

Used as the non-agentic baseline against which the agentic strategy (S4) is
compared in the Week 0 Go/No-Go gate (QG-MDV §1.2).
"""
from __future__ import annotations

from typing import Any, Dict, List

from code.adapters.agent_client import (
    PAPER_DEFAULT_SEED,
    PAPER_DEFAULT_TEMPERATURE,
    QWEN_36_27B_MODEL,
    QwenDirectClient,
)
from code.adapters.viz_output_mapper import _extract_dsl_block
from code.pipelines.base import Bundle, Pipeline, VizOutput


VIZ_GEN_PROMPT = """\
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
  - chartjs_bar          (for quantitative single-series comparison)
  - chartjs_grouped_bar  (for quantitative multi-series)
  - chartjs_line         (for quantitative trend)

Return ONLY a JSON object with two fields:
  {{"viz_type": "<one of the enums above>",
    "viz_dsl":  "<the raw DSL — Mermaid markdown or Chart.js JSON spec>"}}
No prose, no markdown fences around the JSON.
"""


# Qwen3.6 ships in thinking mode by default; for the Direct baseline we want
# the model to emit DSL immediately, not spend its budget in <think>…</think>.
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}


class S1Direct(Pipeline):
    """Concat-and-prompt baseline. One LLM call per (query, bundle) pair."""

    name = "S1_Direct"

    def __init__(
        self,
        client: QwenDirectClient | None = None,
        model: str = QWEN_36_27B_MODEL,
        max_tokens: int = 4096,
        doc_char_cap: int = 12_000,
    ):
        self._client = client or QwenDirectClient()
        self._model = model
        self._max_tokens = max_tokens
        self._doc_char_cap = doc_char_cap

    def _docs_concat(self, bundle: Bundle) -> str:
        parts: List[str] = []
        for d in bundle.docs:
            body = (d.content or "")[: self._doc_char_cap]
            parts.append(f"[{d.title}]\n{body}")
        return "\n\n---\n\n".join(parts)

    def run(self, query: str, bundle: Bundle) -> VizOutput:
        prompt = VIZ_GEN_PROMPT.format(query=query, docs_concat=self._docs_concat(bundle))

        resp: Dict[str, Any] = self._client.chat(
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            temperature=PAPER_DEFAULT_TEMPERATURE,
            seed=PAPER_DEFAULT_SEED,
            max_tokens=self._max_tokens,
            response_format={"type": "json_object"},
            extra_body=NO_THINK,
        )

        usage = resp.get("usage", {}) or {}
        msg = resp["choices"][0]["message"]
        raw = msg.get("content") or msg.get("reasoning") or ""
        viz_type, viz_dsl = _extract_dsl_block(raw)
        errors: List[str] = []
        if not viz_type:
            # Fall back to mermaid_flowchart if the model didn't emit a usable
            # type — record as an error so the eval pass can flag it.
            viz_type = "mermaid_flowchart"
            viz_dsl = raw
            errors.append("S1: viz_type/viz_dsl JSON not found in model output; using fallback")

        retrieved = [
            {"doc_id": d.doc_id, "chunk_id": d.doc_id, "content": d.content}
            for d in bundle.docs
        ]

        return VizOutput(
            viz_dsl=viz_dsl,
            viz_type=viz_type,
            rendered_image_path="",
            render_success=False,
            retrieved_chunks=retrieved,
            sub_queries=[],
            source_attribution={},
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            cost_usd=0.0,                # vLLM on-prem
            errors=errors,
        )
