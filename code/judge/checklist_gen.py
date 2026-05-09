"""Per-instance checklist generator (PAPER_MASTER_SPEC §8.1, action guide §6.1).

Given (query, query_type, source documents), emit 9 (non-agentic) or 12
(agentic) yes/no items distributed across 4 axes:
  - faithfulness        (4 items)
  - coverage            (3 items)
  - type_appropriateness (2 items)
  - search_query_quality (3 items, agentic only)

Items are grounded in the bundle content and the query type — generic
"is the chart accurate?" questions are forbidden by the prompt; we want
queryable evidence hints that the scorer can later resolve.

Spec L341 prescribes GPT-5 for checklist generation; Week 0 substitutes
on-prem Qwen3.6-27B (cost-zero policy). Cross-judge with Claude Opus 4.6
on the prototype 30-sample subset is deferred to closed-API window.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from code.adapters.agent_client import (
    PAPER_DEFAULT_SEED,
    QWEN_36_27B_MODEL,
    QwenDirectClient,
)


NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}


CHECKLIST_GEN_PROMPT = """\
You are designing a quality checklist for a document-grounded visualization.

Inputs:
- User query: {query}
- Query type: {query_type}
- Strategy class: {strategy_class}    (agentic | non_agentic)
- Source documents (bundle):
{sources}

Generate a JSON LIST of {n_items} yes/no questions distributed exactly as:
- "faithfulness": 4 items — does every visual claim trace to source content?
                  Reference specific entities, numbers, dates, or quotes the
                  scorer can check against the source.
- "coverage": 3 items — does the viz address the key information needs the
              query implies? Reference query intent + source coverage.
- "type_appropriateness": 2 items — does the viz format fit the query type
                           and content? (e.g., temporal → timeline/line)
{search_query_block}
Each item must be JSON of the form:
  {{"axis": "<one of faithfulness | coverage | type_appropriateness{search_query_axis_or_empty}>",
    "question": "Yes/no question grounded in this query+sources (max 25 words)",
    "evidence_hint": "What the scorer should look at to answer (max 20 words)"}}

Output strictly: a single JSON object {{"checklist": [ ... ]}}, nothing else.
No prose, no markdown fences."""


_AGENTIC_TAIL = """\
- "search_query_quality": 3 items — for agentic strategies only, are the
                           sub-queries the agent issued well-targeted at the
                           source content? Reference sub-query intent +
                           retrieval coverage.
"""

_AGENTIC_AXIS_OR_EMPTY = " | search_query_quality"
_NON_AGENTIC_AXIS_OR_EMPTY = ""


def _format_sources(docs: List[Dict[str, Any]], char_cap_per_doc: int = 3500) -> str:
    parts: List[str] = []
    for d in docs:
        body = (d.get("content") or "")[:char_cap_per_doc]
        title = d.get("title") or d.get("doc_id") or "untitled"
        parts.append(f"[{title}]\n{body}")
    return "\n\n---\n\n".join(parts)


def _strip_to_json(text: str) -> str:
    """Trim wrapping markdown fences / leading prose to leave a JSON object."""
    s = text.strip()
    # Drop fenced wrappers
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s)
    # Find first { and last }
    i = s.find("{")
    j = s.rfind("}")
    if i >= 0 and j > i:
        return s[i:j + 1]
    return s


def generate_checklist(
    *,
    query: str,
    query_type: str,
    docs: List[Dict[str, Any]],
    strategy_class: str,                # "agentic" | "non_agentic"
    client: Optional[QwenDirectClient] = None,
    model: str = QWEN_36_27B_MODEL,
    max_tokens: int = 1500,
    temperature: float = 0.0,
    seed: int = PAPER_DEFAULT_SEED,
) -> Dict[str, Any]:
    """Return a dict {"checklist": [...], "raw": <model output>, "usage": {...}}."""
    n_items = 12 if strategy_class == "agentic" else 9
    prompt = CHECKLIST_GEN_PROMPT.format(
        query=query,
        query_type=query_type,
        strategy_class=strategy_class,
        sources=_format_sources(docs),
        n_items=n_items,
        search_query_block=_AGENTIC_TAIL if strategy_class == "agentic" else "",
        search_query_axis_or_empty=(
            _AGENTIC_AXIS_OR_EMPTY if strategy_class == "agentic" else _NON_AGENTIC_AXIS_OR_EMPTY
        ),
    )

    cli = client or QwenDirectClient()
    resp = cli.chat(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        temperature=temperature,
        seed=seed,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        extra_body=NO_THINK,
    )
    msg = resp["choices"][0]["message"]
    raw = msg.get("content") or msg.get("reasoning") or ""
    cleaned = _strip_to_json(raw)
    obj: Dict[str, Any]
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        obj = {"checklist": [], "_parse_error": cleaned[:200]}

    items = obj.get("checklist") or []
    # Light validation: drop malformed items, keep at most n_items
    valid: List[Dict[str, Any]] = []
    allowed_axes = {"faithfulness", "coverage", "type_appropriateness"}
    if strategy_class == "agentic":
        allowed_axes.add("search_query_quality")
    for it in items:
        if not isinstance(it, dict):
            continue
        ax = it.get("axis", "")
        q = it.get("question", "")
        if ax in allowed_axes and isinstance(q, str) and q.strip():
            valid.append({
                "axis": ax,
                "question": q.strip(),
                "evidence_hint": (it.get("evidence_hint") or "").strip(),
            })

    usage = resp.get("usage") or {}
    return {
        "checklist": valid,
        "n_items": len(valid),
        "n_target": n_items,
        "tokens_in": usage.get("prompt_tokens", 0),
        "tokens_out": usage.get("completion_tokens", 0),
        "raw": raw,
    }
