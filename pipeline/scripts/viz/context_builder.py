"""Context builder for VisuBench viz redesign (D7, 2026-04-09).

Single source of truth for the doc context passed to:
  - D5 subtype assigner / chart spec planner
  - D6 query generator (chart/diagram, qwen397b calls)
  - D8 reference generator (qwen397b full-doc)
  - D14 comparison-model inference (4 models)

CRITICAL INVARIANT (Guide 2 §4.3): every phase listed above MUST use the
identical return value of `prepare_full_context(doc)` for a given doc_id.
No per-phase truncation, summarization, or paraphrasing.
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, Any, Union

_WHITESPACE_RE = re.compile(r"\s+")
_MULTI_NEWLINE_RE = re.compile(r"\n\s*\n\s*\n+")


def _load_doc_json(doc: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """Accept either a dict row from corpus.jsonl or a path to a doc JSON."""
    if isinstance(doc, str):
        if os.path.isfile(doc):
            with open(doc, "r", encoding="utf-8") as f:
                return json.load(f)
        raise FileNotFoundError(doc)
    if isinstance(doc, dict):
        if "outputs" in doc and doc["outputs"]:
            # already a loaded doc_json (has outputs[0].html_parsed)
            return doc
        if "doc_json_path" in doc:
            path = doc["doc_json_path"]
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    raise TypeError(f"Cannot resolve doc of type {type(doc).__name__}")


def _join_pages(html_parsed: Dict[str, str]) -> str:
    """Concatenate pages in numerical order."""
    def _key(k: str) -> int:
        try:
            return int(k)
        except (TypeError, ValueError):
            return 10**9
    ordered = sorted(html_parsed.items(), key=lambda kv: _key(kv[0]))
    parts = []
    for _, text in ordered:
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def prepare_full_context(doc: Union[Dict[str, Any], str]) -> str:
    """Return the full-document plain text context for a corpus row.

    Signature matches Guide 2 §3.2. Input is either a dict row from
    corpus.jsonl (must contain `doc_json_path`) or a dict already loaded
    from that path. Output is a single normalised string:
      - all pages concatenated in order
      - whitespace collapsed (tabs/CR → space, runs of spaces → single)
      - runs of 3+ newlines collapsed to 2
      - leading/trailing whitespace stripped

    This function is deterministic: given the same doc input, it always
    returns the same string (required by the context-identity invariant).
    """
    doc_json = _load_doc_json(doc)
    outputs = doc_json.get("outputs") or []
    if not outputs:
        raise ValueError("doc.outputs is empty")
    html_parsed = outputs[0].get("html_parsed")
    if not isinstance(html_parsed, dict):
        raise ValueError("outputs[0].html_parsed must be a dict of pages")

    raw = _join_pages(html_parsed)
    # normalize whitespace conservatively — do NOT destroy paragraph breaks
    # Convert tabs and CR to single space first
    raw = raw.replace("\t", " ").replace("\r", " ")
    # Collapse runs of 3+ newlines to 2 (paragraph break)
    raw = _MULTI_NEWLINE_RE.sub("\n\n", raw)
    # Collapse runs of spaces (not touching newlines) to a single space
    raw = re.sub(r"[ ]{2,}", " ", raw)
    return raw.strip()


# ── Token counting (Qwen-ish approximation via tiktoken) ────────────────────

_ENC_CACHE = {}


def count_tokens(text: str, tokenizer: str = "qwen") -> int:
    """Return token count for `text` using a qwen-approximating encoder.

    Uses tiktoken cl100k_base as a stand-in (Qwen BPE ≈ cl100k within ~10%).
    For the viz pipeline the exact count is not load-bearing (corpus max =
    21,715 tokens, all models support 128K+), so this is used only for
    diagnostic reporting and not for any truncation decisions.
    """
    key = tokenizer
    if key not in _ENC_CACHE:
        try:
            import tiktoken
            _ENC_CACHE[key] = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _ENC_CACHE[key] = None
    enc = _ENC_CACHE[key]
    if enc is None:
        return len(text.split())  # fallback: whitespace count
    return len(enc.encode(text))


def prepare_doc_excerpt(doc: Union[Dict[str, Any], str], max_chars: int) -> str:
    """Return the first `max_chars` characters of `prepare_full_context(doc)`.

    Used by D5 subtype assigner (max_chars=1500) and D6 chart-query prompt
    (max_chars=500). Excerpt is NOT a substitute for full context — it is
    only passed to prompts that explicitly request an excerpt. The full
    context is still what the generator models see at D8/D14.
    """
    full = prepare_full_context(doc)
    return full[:max_chars]


__all__ = ["prepare_full_context", "count_tokens", "prepare_doc_excerpt"]
