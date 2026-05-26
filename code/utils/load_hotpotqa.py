"""HotpotQA loader v0.4 → 50 cross-document Bundles with full Wikipedia bodies.

v0.4 redesign (2026-05-24):
  - Bumped from 2 supporting paragraphs (~900 chars) to 3-5 full Wikipedia
    article bodies (~15-50K chars/bundle) to match the other 5 source
    loaders' multi-doc shape (LOADER_CONTRACT_v04.md).
  - Each bundle = 2 supporting Wikipedia articles + 2-3 distractor articles
    drawn from the same HotpotQA example's context (already entity-linked).
  - Full article body fetched via Wikipedia REST API (cached locally) and
    trimmed to per-Doc cap.
  - Supports survey-defined T5 CDER (entity merge) + T4 CCEM
    (claim-evidence) dependency types via bridge_entity metadata.

Source: HF `hotpot_qa/distractor` validation split.
Output: data/prototype/bundles/hotpotqa.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("HF_HOME", "/ex_disk2/mhpark/poc/.cache/huggingface")

from code.pipelines.base import Bundle, Doc
from code.utils.bundle_io import validate_bundle, write_bundles_json


SEED = 42
N_BUNDLES = 50
ALLOWED_TYPES = {"comparison", "bridge"}
MIN_DOCS = 3
MAX_DOCS = 5
MIN_CHARS = 15_000
MAX_CHARS = 200_000
PER_DOC_CAP = 12_000  # chars, trim Wikipedia body

REPO_ROOT = Path(__file__).resolve().parents[2]
WIKI_CACHE_DIR = REPO_ROOT / "data" / "prototype" / "sources" / "raw" / "wikipedia_intros"
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "hotpotqa.json"

USER_AGENT = "docviz-research/0.4 (pminhyung12@g.skku.edu)"


def _load_examples() -> List[Dict[str, Any]]:
    from datasets import load_dataset
    ds = load_dataset("hotpot_qa", "distractor", split="validation",
                      trust_remote_code=True)
    out: List[Dict[str, Any]] = []
    for ex in ds:
        ctx_titles = ex["context"]["title"]
        ctx_sents = ex["context"]["sentences"]
        sf_titles = ex["supporting_facts"]["title"]
        out.append({
            "_id": ex["id"],
            "question": ex["question"],
            "answer": ex["answer"],
            "type": ex["type"],
            "context_titles": list(ctx_titles),
            "context_sentences": list(ctx_sents),
            "supporting_titles": list(set(sf_titles)),
        })
    return out


def _safe_slug(title: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in title)[:120]


def _wiki_fetch(title: str, wiki) -> str | None:
    """Fetch Wikipedia article body; cache to disk. Return text or None."""
    WIKI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = WIKI_CACHE_DIR / f"{_safe_slug(title)}.txt"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    try:
        page = wiki.page(title)
        if not page.exists():
            return None
        body = page.text
        if not body:
            return None
        cache_path.write_text(body, encoding="utf-8")
        return body
    except Exception as e:
        print(f"  [wiki-skip] {title!r}: {type(e).__name__}: {e}")
        return None


def _build_bundle(idx: int, ex: Dict[str, Any], wiki) -> Bundle | None:
    """Build a bundle of 3-5 Wikipedia articles from one HotpotQA example."""
    sup_titles = ex["supporting_titles"]
    if len(sup_titles) < 2:
        return None
    # Remaining context titles = distractors (entity-linked but non-supporting)
    distractors = [t for t in ex["context_titles"] if t not in set(sup_titles)]
    random.shuffle(distractors)

    # Target: take all 2 sup + 1-3 distractors → 3-5 doc bundle
    titles = list(sup_titles)
    titles.extend(distractors[:3])  # cap at 5 total
    titles = titles[:MAX_DOCS]

    docs: List[Doc] = []
    fetched_titles: List[str] = []
    for j, title in enumerate(titles):
        body = _wiki_fetch(title, wiki)
        if not body or len(body) < 1000:
            continue
        if len(body) > PER_DOC_CAP:
            body = body[:PER_DOC_CAP]
        docs.append(Doc(
            doc_id=f"hotpot_{idx:02d}_{j}",
            title=title,
            content=body,
        ))
        fetched_titles.append(title)
        if len(docs) >= MAX_DOCS:
            break

    if len(docs) < MIN_DOCS:
        return None

    bridge = (f"comparison({sup_titles[0]}, {sup_titles[1]})"
              if ex["type"] == "comparison"
              else f"bridge(answer={ex['answer']!r}; {sup_titles[0]} → {sup_titles[1]})")

    return Bundle(
        bundle_id=f"hotpot_{idx:02d}",
        source="hotpotqa",
        docs=docs,
        metadata={
            "language": "en",
            "original_question": ex.get("question", ""),
            "original_answer": ex.get("answer", ""),
            "type_hint": ex.get("type", ""),
            "supporting_titles": sup_titles,
            "doc_titles": fetched_titles,
            "bridge_entity": bridge,
            "topic_hint": bridge,
        },
    )


def build_bundles() -> List[Bundle]:
    import wikipediaapi
    wiki = wikipediaapi.Wikipedia(language="en", user_agent=USER_AGENT)

    print("[hotpotqa] loading dev distractor split…")
    examples = _load_examples()
    print(f"  loaded {len(examples)} examples")

    candidates = [
        ex for ex in examples
        if ex.get("type") in ALLOWED_TYPES and len(ex["supporting_titles"]) >= 2
    ]
    print(f"  {len(candidates)} candidates after type/SF filter")

    random.seed(SEED)
    random.shuffle(candidates)

    bundles: List[Bundle] = []
    rejected_size = rejected_chars = 0
    t0 = time.time()
    for ex in candidates:
        if len(bundles) >= N_BUNDLES:
            break
        b = _build_bundle(len(bundles), ex, wiki)
        if b is None:
            rejected_size += 1
            continue
        ch = b.total_chars()
        if ch < MIN_CHARS or ch > MAX_CHARS:
            rejected_chars += 1
            continue
        bundles.append(b)
        if len(bundles) % 10 == 0:
            print(f"  built {len(bundles)}/{N_BUNDLES} in {time.time()-t0:.0f}s "
                  f"(rejected size={rejected_size}, chars={rejected_chars})")
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser(description="Build HotpotQA v0.4 bundles.")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    bundles = build_bundles()
    if len(bundles) < N_BUNDLES:
        print(f"  [WARN] only {len(bundles)} bundles built (target {N_BUNDLES})")

    errors: List[str] = []
    for b in bundles:
        errors.extend(validate_bundle(b, min_docs=MIN_DOCS,
                                      min_chars=MIN_CHARS, max_chars=MAX_CHARS))
    if errors:
        print("  [VALIDATION ERRORS]")
        for e in errors:
            print(f"    {e}")
        return 2

    write_bundles_json(bundles, args.out)
    print(f"[hotpotqa] wrote {len(bundles)} bundles → {args.out}")
    for b in bundles:
        print(f"    {b.bundle_id}: docs={len(b.docs)}, chars={b.total_chars()}, "
              f"type={b.metadata.get('type_hint')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
