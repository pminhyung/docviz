"""Query generator → 60 queries (30 bundles × 2 types).

Per PAPER_MASTER_SPEC §5.2:
  - 2 queries per bundle, types pinned by source (TYPE_ASSIGNMENT)
  - Filter: ≤25 words AND references ≥1 bundle entity
  - Spec L263 prescribes GPT-4o-mini; Week 0 deviates to on-prem Qwen3.6-27B
    (cost = 0, see code/utils/cost_tracker.py docstring + PR1 bootstrap).
    Cross-validation with Claude Opus 4.6 (L266) is deferred to the closed-API
    window — recorded in docs/active/tracks/feat-source-loaders/open-questions.md.

Outputs:
  - data/prototype/queries/all.json   (60 queries, list)
  - data/prototype/queries/raw.jsonl  (per-call audit trail incl. retries)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from code.adapters.agent_client import QWEN_36_27B_MODEL, QwenDirectClient
from code.pipelines.base import Bundle
from code.utils.bundle_io import read_bundles_json
from code.utils.cost_tracker import CostTracker
from code.utils.query_gen_prompt import (
    QUERY_GEN_PROMPT,
    TYPE_ASSIGNMENT,
    TYPE_DEFS,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLES_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "all.json"
OUT_PATH = REPO_ROOT / "data" / "prototype" / "queries" / "all.json"
RAW_PATH = REPO_ROOT / "data" / "prototype" / "queries" / "raw.jsonl"

# Generation knobs
DOC_CHAR_CAP_PER_DOC = 4000        # keep prompt context bounded; full bundles up to 60K chars
MAX_TOKENS = 120                   # ≤25 words ≈ ≤60 BPE tokens, +buffer
MAX_RETRIES = 2                    # filter-fail → retry with seed offset
WORD_LIMIT = 25                    # spec §5.2 L265
MIN_ENTITY_LEN = 4                 # entity tokens must be ≥4 chars to count

# Qwen3.6 ships in thinking mode by default; query generation is an instruction-
# following task, not a reasoning task, so we disable thinking to avoid the
# entire token budget being spent in <think>…</think> with content=None.
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}

_WORD_RE = re.compile(r"\S+")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]+")


def _word_count(s: str) -> int:
    return len(_WORD_RE.findall(s))


def _strip_query(raw: str) -> str:
    """Strip wrapping quotes / leading numbering / role tags Qwen sometimes emits."""
    s = raw.strip()
    # Drop a leading numbered prefix like "1. " or "Q: "
    s = re.sub(r"^(?:[Qq](?:uery)?\s*[:\-]\s*|\d+[.)]\s+)", "", s).strip()
    # Strip wrapping quotes/backticks
    if len(s) >= 2 and s[0] in {'"', "'", "`"} and s[-1] == s[0]:
        s = s[1:-1].strip()
    # Some models emit a blank line + extra commentary; keep first non-empty line
    if "\n" in s:
        s = next((ln.strip() for ln in s.splitlines() if ln.strip()), s)
    return s


def _collect_entity_vocab(bundle: Bundle) -> Set[str]:
    """Build a permissive entity bag for the L265 'references ≥1 bundle entity' filter.

    Sources:
      - every word ≥4 chars from each Doc.title
      - capitalized multi-letter tokens from the first 1500 chars of each Doc.content
      - selected metadata fields (ticker, topic_seed, primary_category)
      - hotpot original_question / original_answer tokens

    Lowercased; the filter is a case-insensitive substring check.
    """
    vocab: Set[str] = set()

    def _add_token(tok: str) -> None:
        t = tok.strip().lower()
        if len(t) >= MIN_ENTITY_LEN and t.isascii():
            vocab.add(t)

    for doc in bundle.docs:
        for tok in _TOKEN_RE.findall(doc.title or ""):
            _add_token(tok)
        head = (doc.content or "")[:1500]
        for tok in _TOKEN_RE.findall(head):
            # Capitalized in source ≈ proper noun heuristic
            if tok[:1].isupper():
                _add_token(tok)

    md = bundle.metadata or {}
    for key in ("ticker", "topic_seed", "primary_category", "original_question",
                "original_answer", "reference_summary"):
        v = md.get(key)
        if not v:
            continue
        for tok in _TOKEN_RE.findall(str(v)):
            _add_token(tok)
    return vocab


def _entity_hits(query: str, vocab: Set[str]) -> List[str]:
    q = query.lower()
    hits: List[str] = []
    for ent in vocab:
        # Word-boundary substring check; avoids bogus matches on "the"/"and"
        if re.search(rf"\b{re.escape(ent)}\b", q):
            hits.append(ent)
    return hits


def _build_docs_concat(bundle: Bundle, char_cap: int = DOC_CHAR_CAP_PER_DOC) -> str:
    parts: List[str] = []
    for d in bundle.docs:
        body = (d.content or "")[:char_cap]
        parts.append(f"[{d.title}]\n{body}")
    return "\n\n---\n\n".join(parts)


def _generate_one(
    client: QwenDirectClient,
    bundle: Bundle,
    qtype: str,
    docs_concat: str,
    vocab: Set[str],
    tracker: CostTracker,
    raw_log,
) -> Tuple[str, List[str], int, Dict]:
    """Return (query_text, entity_hits, retry_count, last_raw_record). Raises on hard failure."""
    prompt = QUERY_GEN_PROMPT.format(
        docs_concat=docs_concat,
        query_type=qtype,
        type_def=TYPE_DEFS[qtype],
    )

    last_record: Dict = {}
    last_query = ""
    last_hits: List[str] = []
    for attempt in range(MAX_RETRIES + 1):
        # Deterministic on attempt 0; nudge seed + temp on retries
        temperature = 0.0 if attempt == 0 else 0.5
        seed = 42 + attempt
        resp = client.chat(
            messages=[{"role": "user", "content": prompt}],
            model=QWEN_36_27B_MODEL,
            temperature=temperature,
            seed=seed,
            max_tokens=MAX_TOKENS,
            extra_body=NO_THINK,
        )
        usage = resp.get("usage", {}) or {}
        msg = resp["choices"][0]["message"]
        choice = msg.get("content") or msg.get("reasoning") or ""
        query = _strip_query(choice)
        wc = _word_count(query)
        hits = _entity_hits(query, vocab)
        record = {
            "bundle_id": bundle.bundle_id,
            "query_type": qtype,
            "attempt": attempt,
            "temperature": temperature,
            "seed": seed,
            "raw": choice,
            "query": query,
            "word_count": wc,
            "entity_hits": hits,
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
        }
        raw_log.write(json.dumps(record, ensure_ascii=False) + "\n")
        raw_log.flush()
        tracker.add(
            provider="vllm-qwen36",
            model=QWEN_36_27B_MODEL,
            tokens_in=record["tokens_in"],
            tokens_out=record["tokens_out"],
            cost_usd=0.0,
            tag=f"qg-{qtype}",
        )
        last_record, last_query, last_hits = record, query, hits
        if 1 <= wc <= WORD_LIMIT and hits:
            return query, hits, attempt, record
    return last_query, last_hits, MAX_RETRIES, last_record


def generate_queries(
    bundles: List[Bundle],
    client: QwenDirectClient,
    raw_log_path: Path,
) -> Tuple[List[Dict], Dict]:
    """Generate 2 queries per bundle. Returns (queries, audit_summary)."""
    raw_log_path.parent.mkdir(parents=True, exist_ok=True)
    tracker = CostTracker()

    queries: List[Dict] = []
    failed: List[Dict] = []
    retried: int = 0

    with open(raw_log_path, "w", encoding="utf-8") as raw_log:
        for bundle in bundles:
            assignment = TYPE_ASSIGNMENT.get(bundle.source)
            if not assignment:
                raise ValueError(
                    f"{bundle.bundle_id}: source '{bundle.source}' has no §5.2 type assignment"
                )
            vocab = _collect_entity_vocab(bundle)
            docs_concat = _build_docs_concat(bundle)
            for qtype in assignment:
                query, hits, attempts, record = _generate_one(
                    client, bundle, qtype, docs_concat, vocab, tracker, raw_log,
                )
                wc = _word_count(query)
                ok = (1 <= wc <= WORD_LIMIT) and bool(hits)
                entry = {
                    "query_id": f"{bundle.bundle_id}_{qtype}",
                    "bundle_id": bundle.bundle_id,
                    "source": bundle.source,
                    "query_type": qtype,
                    "query": query,
                    "word_count": wc,
                    "entity_hits": hits[:8],
                    "model": QWEN_36_27B_MODEL,
                    "retries_used": attempts,
                    "filter_passed": ok,
                }
                queries.append(entry)
                if attempts > 0:
                    retried += 1
                if not ok:
                    failed.append(entry)
                print(
                    f"  {entry['query_id']:<28s} wc={wc:>2d} hits={len(hits):>2d} "
                    f"attempts={attempts} {'OK' if ok else 'FAIL'} :: {query}"
                )

    summary = {
        "n_queries": len(queries),
        "n_filter_failed": len(failed),
        "n_retried": retried,
        "cost": tracker.summary(),
    }
    return queries, summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate 60 prototype queries.")
    ap.add_argument("--bundles", default=str(BUNDLES_PATH))
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--raw", default=str(RAW_PATH))
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero if any query fails the filter.")
    args = ap.parse_args()

    bundles = read_bundles_json(args.bundles)
    print(f"[generate_queries] loaded {len(bundles)} bundles from {args.bundles}")

    client = QwenDirectClient()
    queries, summary = generate_queries(bundles, client, raw_log_path=Path(args.raw))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(queries, f, ensure_ascii=False, indent=2)
    print(f"[generate_queries] wrote {len(queries)} queries → {out_path}")
    print(f"[generate_queries] audit summary: {json.dumps(summary, ensure_ascii=False)}")

    if args.strict and summary["n_filter_failed"] > 0:
        print(f"[generate_queries] STRICT FAIL: {summary['n_filter_failed']} queries did not pass filter")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
