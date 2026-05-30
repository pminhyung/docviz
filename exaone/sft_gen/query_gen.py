"""LLM-driven query generator for SFT dataset assembly.

For each ``(parsed PDF, style_idx)`` pair this module:
  1. picks a document chunk (a few middle pages joined),
  2. builds a PA-RAG prompt with one style scheduled (S1..S5),
  3. calls the auxiliary LLM (uses the active main_runtime so it shares
     the agent's host pool under multi-host batch generation),
  4. parses out the single generated query.

Failed generations (LLM error, empty response, no [QUERY] tag) return
None so the caller can skip the row instead of writing a bad sample.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from exaone.sft_gen.pa_rag_query_generation import (
    STYLES,
    STYLE_NAMES,
    build_single_query_prompt,
    get_style_tuple_for_index,
    parse_queries,
)

logger = logging.getLogger(__name__)

_CHUNK_TARGET_CHARS = int(os.getenv("EXAONE_QUERY_GEN_CHUNK_CHARS", "8000"))
_MAX_RETRIES = 2


@dataclass(frozen=True)
class GeneratedQuery:
    """One PA-RAG generated query for a (PDF, style) pair."""

    file_stem: str
    filename: str
    style: str         # S1..S5
    style_name: str    # List/Extractive/...
    language: str      # "Korean" / "English"
    query: str


def _load_parsed_pages(parsed_json_path: Path) -> List[str]:
    """Return page texts in page-number order from sft_pipeline parsed JSON."""
    with parsed_json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    outputs = data.get("outputs") or []
    if not outputs or not isinstance(outputs[0], dict):
        return []
    html_parsed = outputs[0].get("html_parsed") or {}
    if not isinstance(html_parsed, dict):
        return []
    ordered = sorted(
        html_parsed.items(),
        key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 0,
    )
    return [
        ("\n".join(str(c) for c in v) if isinstance(v, list) else str(v))
        for _, v in ordered
    ]


def _pick_chunk(pages: List[str], target_chars: int = _CHUNK_TARGET_CHARS) -> str:
    """Concatenate middle pages until reaching ``target_chars`` (rough cap)."""
    if not pages:
        return ""
    n = len(pages)
    mid = n // 2
    # Walk outward from the middle so we cover representative content.
    order = []
    left, right = mid, mid + 1
    while left >= 0 or right < n:
        if left >= 0:
            order.append(left)
            left -= 1
        if right < n:
            order.append(right)
            right += 1
    chunks: List[str] = []
    total = 0
    for i in order:
        p = pages[i].strip()
        if not p:
            continue
        chunks.append(p)
        total += len(p)
        if total >= target_chars:
            break
    chunks_ordered = sorted(
        chunks, key=lambda c: pages.index(c) if c in pages else 0
    )
    out = "\n\n".join(chunks_ordered)
    return out[:target_chars]


async def generate_one_query(
    *,
    parsed_json_path: Path,
    file_stem: str,
    filename: str,
    style_idx: int,
    language: str = "Korean",
) -> Optional[GeneratedQuery]:
    """Generate a single PA-RAG query for the (PDF, style) pair."""
    from agent.auxiliary_client import async_call_llm, extract_content_or_reasoning

    pages = _load_parsed_pages(parsed_json_path)
    if not pages:
        logger.warning("query_gen: no pages in %s", parsed_json_path)
        return None
    chunk = _pick_chunk(pages)
    if not chunk:
        return None

    style_tuple = get_style_tuple_for_index(style_idx)
    style = style_tuple[0]
    prompt = build_single_query_prompt(
        document_chunk=chunk, lang=language, style_idx=style_idx,
    )

    last_error: Optional[str] = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = await async_call_llm(
                task="query_gen",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1024,
                # Disable Qwen's thinking mode here — PA-RAG generation is a
                # simple template-following task and any thinking preamble
                # eats budget before the [QUERY] tag has a chance to emit.
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            text = extract_content_or_reasoning(response) or ""
            queries = parse_queries(text)
            if queries:
                return GeneratedQuery(
                    file_stem=file_stem,
                    filename=filename,
                    style=style,
                    style_name=STYLE_NAMES.get(style, style),
                    language=language,
                    query=queries[0],
                )
            last_error = "empty [QUERY] tags"
        except Exception as exc:
            last_error = f"llm error: {exc}"
        if attempt < _MAX_RETRIES - 1:
            await asyncio.sleep(1.0)
    logger.warning(
        "query_gen failed for %s style=%s: %s",
        filename, style, last_error,
    )
    return None
