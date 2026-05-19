"""Per-item YES / PARTIAL / NO scorer (PAPER_MASTER_SPEC §8.1, action guide §6.2).

Receives the checklist for a (query, bundle) plus the candidate viz
(viz_dsl + parsed struct + sub_queries) and asks a single LLM call to
score every item at once. Output is a JSON list aligned with the input
checklist; per-item answer ∈ {YES, PARTIAL, NO} maps to {1.0, 0.5, 0.0}.

Two-phase judge strategy (cost-efficient):
  ▸ Phase 1 (active, on-prem): Qwen3.5-397B via QwenDirectClient — used to
    pull *trend signal* on all layers (A in-domain, B held-out, D pillar
    ablation). Cheap, fast, deterministic at T=0.
  ▸ Phase 2 (closed-API, deferred): once Phase 1 trend confirms our
    headline claims qualitatively (V4 > B5/B7 with positive multi-doc gap,
    near-specialist on home turfs), the same checklist + candidates are
    re-scored under the paper-spec cross-judge config (Claude Opus 4.6 as
    scorer, cross-judged against GPT-5 generator per spec L342 / §8.2).
    Only the *paper-headline cells* are re-scored — Layer A main result
    table + Layer D ablation overall — to keep API spend bounded.

The Phase-2 cross-judge call site is preserved here as commented-out
reference (`_score_with_closed_api_TODO`) so the swap is mechanical when
budget activates.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from code.adapters.agent_client import (
    PAPER_DEFAULT_SEED,
    QWEN_MODEL,
    QwenDirectClient,
)


# ── Phase-2 closed-API scorer hook (deferred) ───────────────────────────────
# When closed-API budget activates, swap the Qwen scorer with the Claude
# Opus 4.6 scorer below to obtain paper-grade numbers for the *headline*
# Layer A + Layer D result cells. Cross-judge κ vs Qwen Phase-1 scores
# becomes G7 verification gate evidence (target Cohen κ ≥ 0.6).
#
# def _score_with_closed_api_TODO(prompt: str) -> str:
#     """Drop-in for Phase-2 paper-grade scoring.
#     Implementation when ANTHROPIC_API_KEY active:
#         from anthropic import Anthropic
#         cli = Anthropic()
#         msg = cli.messages.create(
#             model="claude-opus-4-6",       # spec L342
#             max_tokens=2200, temperature=0,
#             messages=[{"role": "user", "content": prompt}],
#         )
#         return msg.content[0].text
#     Cost projection: ~$0.25-0.40 per record × ~3,000 headline records ≈ $750-1,200.
#     Confined to Layer A + Layer D headline cells per the §10 budget envelope.
#     """
#     ...


NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}

_ANSWER_TO_SCORE = {"YES": 1.0, "PARTIAL": 0.5, "NO": 0.0}


SCORER_PROMPT = """\
You are scoring a document-grounded visualization against a quality checklist.

User query: {query}
Query type: {query_type}
Strategy: {strategy}

Source documents (bundle):
{sources}

Visualization DSL (raw):
{viz_dsl}

Visualization parsed structure:
{viz_parsed}

Retrieval queries issued by the agent (relevant only for search_query_quality;
covers both `search` tool queries and `ReadFullDocument` retrieval goals;
RFD goals are prefixed with "[RFD]"):
{sub_queries}

Score EACH item in the checklist below. For each item answer:
  - "YES"     — supported by clear evidence in the inputs above
  - "PARTIAL" — partially supported, ambiguous, or only loosely related
  - "NO"      — not supported, contradicted, or absent

Checklist:
{checklist_json}

Return strictly a single JSON object:
  {{"items": [{{"index": <0-based int>, "axis": "<axis>", "answer": "YES|PARTIAL|NO",
               "justification": "one short sentence"}}, ...]}}

Rules:
- Output one entry per checklist item, in the same order.
- Justification ≤ 25 words.
- For "search_query_quality" items when the retrieval queries list is "(none)"
  or empty (i.e., a non-agentic strategy with no search or RFD calls at all),
  answer "NO" with justification "non-agentic strategy: no retrieval queries".
- For agentic strategies that used `ReadFullDocument` instead of `search`,
  evaluate the RFD goal (prefixed "[RFD]") as the retrieval intent and score
  it on the same axis (specificity, on-target framing, exclusion of
  irrelevant material) — do not penalize as if it were absent.
- No prose outside the JSON.
"""


def _strip_to_json(text: str) -> str:
    s = text.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s)
    i = s.find("{")
    j = s.rfind("}")
    if i >= 0 and j > i:
        return s[i:j + 1]
    return s


def _format_sources(docs: List[Dict[str, Any]], char_cap_per_doc: int = 3500) -> str:
    parts: List[str] = []
    for d in docs:
        body = (d.get("content") or "")[:char_cap_per_doc]
        title = d.get("title") or d.get("doc_id") or "untitled"
        parts.append(f"[{title}]\n{body}")
    return "\n\n---\n\n".join(parts)


def score_checklist(
    *,
    query: str,
    query_type: str,
    strategy: str,
    docs: List[Dict[str, Any]],
    viz_dsl: str,
    viz_parsed: Dict[str, Any],
    sub_queries: List[str],
    checklist: List[Dict[str, Any]],
    client: Optional[QwenDirectClient] = None,
    model: str = QWEN_MODEL,
    max_tokens: int = 2200,
    temperature: float = 0.0,
    seed: int = PAPER_DEFAULT_SEED,
) -> Dict[str, Any]:
    """Score every checklist item in one LLM call.

    Returns a dict containing per-item answers + per-axis scores + raw output.
    """
    if not checklist:
        return {
            "scored": [],
            "axis_scores": {},
            "overall": None,
            "tokens_in": 0,
            "tokens_out": 0,
            "raw": "",
        }

    cli = client or QwenDirectClient()
    sub_q_str = "\n".join(f"- {q}" for q in sub_queries) if sub_queries else "(none)"
    parsed_str = json.dumps(viz_parsed, ensure_ascii=False, indent=2)[:3000]
    viz_dsl_str = (viz_dsl or "")[:6000]
    checklist_for_prompt = [
        {"index": i, "axis": it["axis"],
         "question": it["question"],
         "evidence_hint": it.get("evidence_hint", "")}
        for i, it in enumerate(checklist)
    ]
    prompt = SCORER_PROMPT.format(
        query=query,
        query_type=query_type,
        strategy=strategy,
        sources=_format_sources(docs),
        viz_dsl=viz_dsl_str,
        viz_parsed=parsed_str,
        sub_queries=sub_q_str,
        checklist_json=json.dumps(checklist_for_prompt, ensure_ascii=False, indent=2),
    )

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
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        obj = {"items": [], "_parse_error": cleaned[:200]}

    raw_items = obj.get("items") or []
    # Align: index → answer
    by_index: Dict[int, Dict[str, Any]] = {}
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        idx = it.get("index")
        ans = (it.get("answer") or "").upper().strip()
        if isinstance(idx, int) and ans in _ANSWER_TO_SCORE:
            by_index[idx] = {
                "answer": ans,
                "score": _ANSWER_TO_SCORE[ans],
                "justification": (it.get("justification") or "").strip(),
            }

    scored: List[Dict[str, Any]] = []
    by_axis: Dict[str, List[float]] = {}
    for i, item in enumerate(checklist):
        s = by_index.get(i)
        if s is None:
            scored_item = {
                **item,
                "answer": "NO",
                "score": 0.0,
                "justification": "scorer did not return a valid answer for this item",
                "missing_from_response": True,
            }
        else:
            scored_item = {**item, **s}
        scored.append(scored_item)
        by_axis.setdefault(item["axis"], []).append(scored_item["score"])

    axis_scores = {ax: round(sum(vs) / len(vs), 4) for ax, vs in by_axis.items() if vs}
    # `overall` averages ONLY universal axes (faith, cov, TA, CDI) for symmetric
    # cross-strategy comparison. SQQ stays in axis_scores as agentic-only
    # diagnostic but is excluded from the headline composite — otherwise
    # agentic strategies are evaluated on N+1 axes while non-agentic gets N,
    # making the mean asymmetric. CDI was added 2026-05-17 as the 4th universal
    # axis (all 265 prototype bundles are multi-doc).
    _UNIVERSAL = {"faithfulness", "coverage", "type_appropriateness",
                  "cross_document_integration"}
    universal_scores = {ax: v for ax, v in axis_scores.items() if ax in _UNIVERSAL}
    overall = (
        round(sum(universal_scores.values()) / len(universal_scores), 4)
        if universal_scores else None
    )

    usage = resp.get("usage") or {}
    return {
        "scored": scored,
        "axis_scores": axis_scores,
        "overall": overall,
        "tokens_in": usage.get("prompt_tokens", 0),
        "tokens_out": usage.get("completion_tokens", 0),
        "raw": raw,
    }
