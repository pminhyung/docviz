"""Map RunResponseV2 (agent) → VizOutput (paper schema §3.6).

The agent returns a multi-step trace; for the prototype we extract:
  - final_answer → expected to embed the DSL block; we parse it out
  - steps_reasoning → sub_queries (Pillar 1) + source_attribution stub
                      (Pillar 3, populated from any tool actions that cite
                      page numbers, mapped back via Bundle.metadata)
  - retrieved_chunks: from agent search/RFD trace if present, otherwise
                      a single entry pointing at the concat-serialized doc

Render success and rendered_image_path are set by the caller after the
sidecar invocation, not here.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from code.adapters.agent_client import AgentRunResponse, StepReasoning
from code.pipelines.base import Bundle, VizOutput


VIZ_TYPE_PATTERN = re.compile(
    r"\b(chartjs_(?:bar|line|grouped_bar)|"
    r"mermaid_(?:flowchart|timeline|mindmap))\b"
)

# Markdown fence with optional language tag — captures the body.
_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_-]*)\s*\n(.*?)```", re.DOTALL)


def _extract_dsl_block(text: str) -> Tuple[str, str]:
    """Best-effort extraction of (viz_type, viz_dsl) from the agent's
    final_answer. Returns ("", text) if no clear block is found.

    Heuristics, in order:
      1a. Whole text is a JSON object with viz_type + viz_dsl (Qwen tends to
          emit chartjs as a NESTED OBJECT under viz_dsl rather than a string;
          re-serialize so downstream sees the same shape it would for Mermaid).
      1b. Inline JSON object regex (legacy fast-path; only matches when
          viz_dsl is a string — kept as a fallback for fenced/wrapped JSON).
      2.  Fenced block ```mermaid …``` → viz_type=mermaid_flowchart (caller may
          downgrade to mermaid_mindmap/timeline by looking at the body).
      3.  Fenced block ```json … ``` → try to parse, look for chartjs spec.
    """
    # Strategy 1a — JSON object at the head of the text (handles
    # viz_dsl-as-nested-object AND "JSON + trailing prose" patterns).
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            obj, _ = json.JSONDecoder().raw_decode(stripped)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            viz_type = obj.get("viz_type", "")
            viz_dsl = obj.get("viz_dsl", "")
            if viz_type:
                if isinstance(viz_dsl, str) and viz_dsl:
                    return viz_type, viz_dsl
                if isinstance(viz_dsl, (dict, list)):
                    # Re-serialize nested object → string. Caller's syntax
                    # check (chartjs JSON parse) succeeds on the round-trip.
                    return viz_type, json.dumps(viz_dsl, ensure_ascii=False)

    # Strategy 1b — inline JSON object regex (string-valued viz_dsl only)
    for match in re.finditer(r"\{[^{}]*\"viz_type\"\s*:\s*\"[^\"]+\"[^{}]*\}", text, re.DOTALL):
        chunk = match.group(0)
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        viz_type = obj.get("viz_type", "")
        viz_dsl = obj.get("viz_dsl", "")
        if viz_type and isinstance(viz_dsl, str) and viz_dsl:
            return viz_type, viz_dsl

    # Strategy 2 — fenced blocks
    for body in _FENCE_RE.findall(text):
        body = body.strip()
        # Mermaid fingerprints
        if re.match(r"^(flowchart|graph|sequenceDiagram|mindmap|timeline|gantt|stateDiagram)", body):
            head = body.splitlines()[0]
            if head.startswith("mindmap"):
                return "mermaid_mindmap", body
            if head.startswith("timeline"):
                return "mermaid_timeline", body
            return "mermaid_flowchart", body
        # Chart.js JSON fingerprint
        if body.startswith("{") and "\"type\"" in body:
            try:
                spec = json.loads(body)
            except json.JSONDecodeError:
                continue
            t = spec.get("type", "")
            if t == "bar":
                return "chartjs_bar", body
            if t == "line":
                return "chartjs_line", body
            # Treat grouped_bar / others under a sensible default.
            return f"chartjs_{t}" if t else "chartjs_bar", body

    return "", text


def _extract_sub_queries(steps: List[StepReasoning]) -> List[str]:
    """Pull search/sub-queries from the agent step trace in order.

    Look at action payloads on tool_call steps; common fields are
    "query", "search_query", "subquery". Falls back to step_name when
    the action is missing structured query text.
    """
    out: List[str] = []
    for s in steps:
        if s.step_type not in {"tool_call", "tool_invoke", "search"}:
            continue
        action = s.action or {}
        for key in ("query", "search_query", "subquery", "q"):
            v = action.get(key)
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
                break
        else:
            if s.step_name:
                out.append(s.step_name)
    return out


def _extract_source_attribution(
    steps: List[StepReasoning],
    bundle: Bundle,
) -> Dict[str, Dict[str, Any]]:
    """Stub Pillar-3 SAO extractor.

    Walks the step trace looking for tool actions that reference a page
    number (e.g. ReadFullDocument / GetPage / Search results). Maps
    page_id → doc_id via Bundle.metadata["page_to_doc_id"] populated by
    bundle_to_docai.write_bundle_as_docai.

    Returns {viz_element_id: {doc_id, chunk_id, evidence_span}} keyed by
    a synthetic step-derived element id (refined in Week 1).
    """
    page_to_doc_id: Dict[str, str] = bundle.metadata.get("page_to_doc_id", {})
    attribution: Dict[str, Dict[str, Any]] = {}

    for s in steps:
        action = s.action or {}
        page = action.get("page") or action.get("page_id")
        if page is None:
            continue
        page_str = str(page)
        doc_id = page_to_doc_id.get(page_str, f"page_{page_str}")
        element_id = f"step_{s.step_number}"
        attribution[element_id] = {
            "doc_id": doc_id,
            "chunk_id": page_str,
            "evidence_span": action.get("snippet", ""),
        }
    return attribution


def _retrieved_chunks_from_steps(
    steps: List[StepReasoning],
    bundle: Bundle,
    fallback_concat_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    page_to_doc_id: Dict[str, str] = bundle.metadata.get("page_to_doc_id", {})
    chunks: List[Dict[str, Any]] = []
    seen_pages: set = set()
    for s in steps:
        action = s.action or {}
        page = action.get("page") or action.get("page_id")
        snippet = action.get("snippet") or action.get("content")
        if page is None or page in seen_pages:
            continue
        seen_pages.add(page)
        page_str = str(page)
        chunks.append(
            {
                "doc_id": page_to_doc_id.get(page_str, f"page_{page_str}"),
                "chunk_id": page_str,
                "content": snippet or "",
            }
        )

    if not chunks and fallback_concat_path:
        chunks.append(
            {
                "doc_id": "concat",
                "chunk_id": "all",
                "content": "",  # too large to embed; kept as path reference
                "source_path": fallback_concat_path,
            }
        )
    return chunks


def map_agent_response(
    response: AgentRunResponse,
    bundle: Bundle,
    *,
    concat_doc_path: Optional[str] = None,
    fallback_viz_type: str = "mermaid_flowchart",
) -> VizOutput:
    """Build a VizOutput from an agent /v2/run response."""
    viz_type, viz_dsl = _extract_dsl_block(response.final_answer)
    if not viz_type:
        viz_type = fallback_viz_type
        viz_dsl = response.final_answer
    sub_queries = _extract_sub_queries(response.steps_reasoning)
    attribution = _extract_source_attribution(response.steps_reasoning, bundle)
    retrieved = _retrieved_chunks_from_steps(
        response.steps_reasoning, bundle, fallback_concat_path=concat_doc_path
    )
    errors: List[str] = list(response.warnings)
    if not viz_dsl:
        # Agent returned empty final_answer (e.g., upstream LLM unreachable).
        # Surface as an error so batch runners don't mistake silence for success.
        errors.append("agent returned empty final_answer")

    return VizOutput(
        viz_dsl=viz_dsl,
        viz_type=viz_type,
        rendered_image_path="",
        render_success=False,
        retrieved_chunks=retrieved,
        sub_queries=sub_queries,
        source_attribution=attribution,
        tokens_in=0,                        # broken out below if available
        tokens_out=response.total_tokens,   # agent reports total_tokens only
        cost_usd=0.0,                       # on-premise vLLM → 0
        errors=errors,
    )
