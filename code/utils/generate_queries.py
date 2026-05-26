"""Query generator v0.4 — 1 query per bundle, dependency-type primary.

v0.4 redesign (2026-05-24):
  - Per-bundle: sample dep_type from SOURCE_DEP_TYPES (uniform, seed=42).
  - Content shape (5-type) becomes secondary chart-hint slot.
  - Accept condition: ≤25 words AND _doc_coverage ≥ 2 (entities from
    ≥2 distinct docs).
  - Bundle metadata.bridge_entity surfaced into prompt (T5 CDER, T6 CIC).

Survey: docs/active/tracks/feat-source-loaders/multi_doc_viz_survey.md
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from code.adapters.agent_client import QWEN_MODEL, QwenDirectClient
from code.pipelines.base import Bundle
from code.utils.bundle_io import read_bundles_json
from code.utils.cost_tracker import CostTracker
from code.utils.query_gen_prompt import (
    DEPENDENCY_TYPE_DEFS,
    MULTIDOC_QUERY_GEN_PROMPT,
    SOURCE_DEP_TYPES,
    SOURCE_TYPE_SPLIT,
    TYPE_DEFS,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLES_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "all.json"
OUT_PATH = REPO_ROOT / "data" / "prototype" / "queries" / "all.json"
RAW_PATH = REPO_ROOT / "data" / "prototype" / "queries" / "raw.jsonl"

# Generation knobs
DOC_CHAR_CAP_PER_DOC = 2500        # tighter cap — 5 docs × 2.5K = 12.5K context budget
MAX_TOKENS = 120                   # ≤25 words ≈ ≤60 BPE tokens, +buffer
MAX_RETRIES = 3                    # filter-fail → retry with seed offset
WORD_LIMIT = 25
MIN_ENTITY_LEN = 4
MIN_DOC_COVERAGE = 2               # query must touch ≥2 distinct docs

NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}

_WORD_RE = re.compile(r"\S+")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]+")
_SEED = 42


def _word_count(s: str) -> int:
    return len(_WORD_RE.findall(s))


def _strip_query(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^(?:[Qq](?:uery)?\s*[:\-]\s*|\d+[.)]\s+)", "", s).strip()
    if len(s) >= 2 and s[0] in {'"', "'", "`"} and s[-1] == s[0]:
        s = s[1:-1].strip()
    if "\n" in s:
        s = next((ln.strip() for ln in s.splitlines() if ln.strip()), s)
    return s


def _add_token(vocab: Set[str], tok: str) -> None:
    t = tok.strip().lower()
    if len(t) >= MIN_ENTITY_LEN and t.isascii():
        vocab.add(t)


def _per_doc_vocab(bundle: Bundle) -> Dict[int, Set[str]]:
    """Per-doc entity vocab; index = doc position (0-based)."""
    vocab: Dict[int, Set[str]] = {}
    for i, doc in enumerate(bundle.docs):
        v: Set[str] = set()
        for tok in _TOKEN_RE.findall(doc.title or ""):
            _add_token(v, tok)
        head = (doc.content or "")[:2000]
        for tok in _TOKEN_RE.findall(head):
            if tok[:1].isupper():
                _add_token(v, tok)
        vocab[i] = v
    return vocab


def _bundle_vocab(per_doc_vocab: Dict[int, Set[str]]) -> Set[str]:
    out: Set[str] = set()
    for v in per_doc_vocab.values():
        out |= v
    return out


def _doc_coverage(query: str, per_doc_vocab: Dict[int, Set[str]]) -> Tuple[int, List[int]]:
    """Return (covered_count, covered_doc_indices)."""
    q = query.lower()
    covered: List[int] = []
    for i, vocab in per_doc_vocab.items():
        for ent in vocab:
            if re.search(rf"\b{re.escape(ent)}\b", q):
                covered.append(i)
                break
    return len(covered), covered


def _entity_hits(query: str, vocab: Set[str]) -> List[str]:
    q = query.lower()
    return [ent for ent in vocab if re.search(rf"\b{re.escape(ent)}\b", q)]


def _format_per_doc_entity_lines(per_doc_vocab: Dict[int, Set[str]], max_per_doc: int = 12) -> str:
    """Render per-doc entity inventory for the prompt."""
    lines: List[str] = []
    for i, vocab in per_doc_vocab.items():
        # Stable: sort by length desc then alpha for richer entities first
        sample = sorted(vocab, key=lambda e: (-len(e), e))[:max_per_doc]
        lines.append(f"  [DOC_{i}] {', '.join(sample) if sample else '(none)'}")
    return "\n".join(lines)


def _build_docs_concat_with_tags(bundle: Bundle, char_cap: int = DOC_CHAR_CAP_PER_DOC) -> str:
    parts: List[str] = []
    for i, d in enumerate(bundle.docs):
        body = (d.content or "")[:char_cap]
        parts.append(f"[DOC_{i}] {d.title}\n{body}")
    return "\n\n---\n\n".join(parts)


def _content_shape_for(bundle) -> str:
    """Legacy 5-type secondary slot (deterministic by source + idx)."""
    split = SOURCE_TYPE_SPLIT.get(bundle.source, [("comparative", 50)])
    try:
        idx = int(bundle.bundle_id.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        idx = 0
    cursor = 0
    for qtype, count in split:
        if idx < cursor + count:
            return qtype
        cursor += count
    return split[-1][0]


def _dep_type_for(bundle, rng: random.Random) -> str:
    pool = SOURCE_DEP_TYPES.get(bundle.source)
    if not pool:
        raise ValueError(f"{bundle.bundle_id}: source '{bundle.source}' has no dep-type pool")
    return rng.choice(pool)


def _generate_one(
    client: QwenDirectClient,
    bundle: Bundle,
    dep_type: str,
    content_shape: str,
    per_doc_vocab: Dict[int, Set[str]],
    docs_concat: str,
    tracker: CostTracker,
    raw_log,
) -> Tuple[str, List[int], int, Dict]:
    """Return (query_text, covered_doc_idxs, retry_count, last_record)."""
    n_docs = len(bundle.docs)
    # Default doc_a/doc_b for prompt — first two docs
    doc_a_tag = f"DOC_0"
    doc_b_tag = f"DOC_1" if n_docs >= 2 else doc_a_tag

    bridge = bundle.metadata.get("bridge_entity", "(none)")

    dep = DEPENDENCY_TYPE_DEFS[dep_type]
    content_def = TYPE_DEFS.get(content_shape, "free-form")

    prompt = MULTIDOC_QUERY_GEN_PROMPT.format(
        n_docs=n_docs,
        docs_concat_with_tags=docs_concat,
        per_doc_entity_lines=_format_per_doc_entity_lines(per_doc_vocab),
        bridge_entity=bridge,
        dep_type=dep_type,
        dep_name=dep["name"],
        dep_instruction=dep["instruction"],
        content_shape=content_shape,
        content_def=content_def,
        viz_hint=dep["viz_hint"],
        doc_a_tag=doc_a_tag,
        doc_b_tag=doc_b_tag,
    )

    last_record: Dict = {}
    last_query = ""
    last_covered: List[int] = []
    for attempt in range(MAX_RETRIES + 1):
        temperature = 0.0 if attempt == 0 else 0.5
        seed = _SEED + attempt
        resp = client.chat(
            messages=[{"role": "user", "content": prompt}],
            model=QWEN_MODEL,
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
        cov, cov_idxs = _doc_coverage(query, per_doc_vocab)
        record = {
            "bundle_id": bundle.bundle_id,
            "dep_type": dep_type,
            "content_shape": content_shape,
            "attempt": attempt,
            "temperature": temperature,
            "seed": seed,
            "raw": choice,
            "query": query,
            "word_count": wc,
            "doc_coverage": cov,
            "covered_doc_idxs": cov_idxs,
            "entity_hits": _entity_hits(query, _bundle_vocab(per_doc_vocab))[:8],
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
        }
        raw_log.write(json.dumps(record, ensure_ascii=False) + "\n")
        raw_log.flush()
        tracker.add(
            provider="vllm-qwen35-397b",
            model=QWEN_MODEL,
            tokens_in=record["tokens_in"],
            tokens_out=record["tokens_out"],
            cost_usd=0.0,
            tag=f"qg-{dep_type}",
        )
        last_record, last_query, last_covered = record, query, cov_idxs
        if 1 <= wc <= WORD_LIMIT and cov >= MIN_DOC_COVERAGE:
            return query, cov_idxs, attempt, record
    return last_query, last_covered, MAX_RETRIES, last_record


def generate_queries(
    bundles: List[Bundle],
    client: QwenDirectClient,
    raw_log_path: Path,
) -> Tuple[List[Dict], Dict]:
    raw_log_path.parent.mkdir(parents=True, exist_ok=True)
    tracker = CostTracker()

    rng = random.Random(_SEED)
    queries: List[Dict] = []
    failed: List[Dict] = []
    retried: int = 0

    with open(raw_log_path, "w", encoding="utf-8") as raw_log:
        for bundle in bundles:
            dep_type = _dep_type_for(bundle, rng)
            content_shape = _content_shape_for(bundle)
            per_doc_vocab = _per_doc_vocab(bundle)
            docs_concat = _build_docs_concat_with_tags(bundle)

            query, cov_idxs, attempts, record = _generate_one(
                client, bundle, dep_type, content_shape,
                per_doc_vocab, docs_concat, tracker, raw_log,
            )
            wc = _word_count(query)
            cov = len(cov_idxs)
            ok = (1 <= wc <= WORD_LIMIT) and (cov >= MIN_DOC_COVERAGE)
            entry = {
                "query_id": f"{bundle.bundle_id}_{dep_type}",
                "bundle_id": bundle.bundle_id,
                "source": bundle.source,
                "dep_type": dep_type,
                "content_shape": content_shape,
                "query": query,
                "word_count": wc,
                "doc_coverage": cov,
                "covered_doc_idxs": cov_idxs,
                "model": QWEN_MODEL,
                "retries_used": attempts,
                "filter_passed": ok,
            }
            queries.append(entry)
            if attempts > 0:
                retried += 1
            if not ok:
                failed.append(entry)
            print(
                f"  {entry['query_id']:<32s} wc={wc:>2d} cov={cov} "
                f"att={attempts} {'OK' if ok else 'FAIL'} :: {query}"
            )

    summary = {
        "n_queries": len(queries),
        "n_filter_failed": len(failed),
        "n_retried": retried,
        "cost": tracker.summary(),
    }
    return queries, summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate queries (v0.4 multi-doc).")
    ap.add_argument("--bundles", default=str(BUNDLES_PATH))
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--raw", default=str(RAW_PATH))
    ap.add_argument("--strict", action="store_true")
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
    print(f"[generate_queries] audit: {json.dumps(summary, ensure_ascii=False)}")

    if args.strict and summary["n_filter_failed"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
