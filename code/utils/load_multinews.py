"""MultiNews loader → 10 source-internal multi-doc Bundles.

Per PAPER_MASTER_SPEC §5.1:
  - Each bundle = one validation cluster (2-5 articles)
  - Articles are split on the canonical "|||||" separator
  - random.seed(42)
"""
from __future__ import annotations

import argparse
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Move HF cache to /ex_disk2 because the root partition on this dev box is
# at 100%. Skipped if the user already pinned HF_HOME.
os.environ.setdefault("HF_HOME", "/ex_disk2/mhpark/poc/.cache/huggingface")

from datasets import load_dataset

from code.pipelines.base import Bundle, Doc
from code.utils.bundle_io import validate_bundle, write_bundles_json


SEED = 42
N_BUNDLES = 50
MIN_ARTICLES = 3
MAX_ARTICLES = 5
MIN_CHARS = 15_000
MAX_CHARS = 200_000
SPLIT = "validation"

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "multinews.json"

DOC_SEPARATOR = "|||||"

# Heuristic: trim repetitive whitespace and the leading "NEWLINE_CHAR" that
# the canonical MultiNews release injects between articles.
_NEWLINE_TOKEN_RE = re.compile(r"\s*NEWLINE_CHAR\s*", flags=re.IGNORECASE)
_WS_RE = re.compile(r"[ \t]+")


def _clean(article: str) -> str:
    text = _NEWLINE_TOKEN_RE.sub("\n", article)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _split_cluster(document: str) -> List[str]:
    parts = [p for p in document.split(DOC_SEPARATOR) if p.strip()]
    return [_clean(p) for p in parts if _clean(p)]


def _first_words(text: str, n: int = 8) -> str:
    words = text.split()
    return " ".join(words[:n]) + ("…" if len(words) > n else "")


def _build_bundle(idx: int, ex: Dict[str, Any]) -> Bundle:
    articles = _split_cluster(ex["document"])
    docs: List[Doc] = []
    for j, art in enumerate(articles):
        docs.append(Doc(
            doc_id=f"multinews_{idx:02d}_{j}",
            title=f"Article {j + 1}: {_first_words(art)}",
            content=art,
        ))
    summary = _clean(ex.get("summary", ""))
    event_slug = _first_words(summary, n=8)
    return Bundle(
        bundle_id=f"multinews_{idx:02d}",
        source="multinews",
        docs=docs,
        metadata={
            "language": "en",
            "reference_summary": summary,
            "n_articles": len(articles),
            "bridge_entity": f"event_cluster:{event_slug}",
            "event_cluster": event_slug,
        },
    )


def build_bundles() -> List[Bundle]:
    print("[multinews] loading validation split…")
    ds = load_dataset("alexfabbri/multi_news", split=SPLIT, trust_remote_code=True)
    print(f"  loaded {len(ds)} clusters")

    candidates: List[Dict[str, Any]] = []
    for ex in ds:
        n = len(_split_cluster(ex["document"]))
        if MIN_ARTICLES <= n <= MAX_ARTICLES:
            candidates.append(ex)
    print(f"  {len(candidates)} candidates after cluster-size filter ({MIN_ARTICLES}-{MAX_ARTICLES} articles)")

    random.seed(SEED)
    random.shuffle(candidates)

    bundles: List[Bundle] = []
    rejected_small = rejected_large = 0
    for ex in candidates:
        if len(bundles) >= N_BUNDLES:
            break
        b = _build_bundle(len(bundles), ex)
        if len(b.docs) < MIN_ARTICLES:
            continue
        ch = b.total_chars()
        if ch < MIN_CHARS:
            rejected_small += 1
            continue
        if ch > MAX_CHARS:
            rejected_large += 1
            continue
        bundles.append(b)
    print(f"  built {len(bundles)} bundles (rejected: {rejected_small} <{MIN_CHARS} chars, {rejected_large} >{MAX_CHARS} chars)")
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser(description="Build MultiNews bundles.")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    bundles = build_bundles()
    if len(bundles) < N_BUNDLES:
        print(f"  [WARN] only {len(bundles)} bundles built (target {N_BUNDLES})")
    errors: List[str] = []
    for b in bundles:
        errors.extend(validate_bundle(b, min_docs=MIN_ARTICLES, min_chars=MIN_CHARS, max_chars=MAX_CHARS))
    if errors:
        print("  [VALIDATION ERRORS]")
        for e in errors:
            print(f"    {e}")
        return 2

    write_bundles_json(bundles, args.out)
    print(f"[multinews] wrote {len(bundles)} bundles → {args.out}")
    for b in bundles:
        print(f"    {b.bundle_id}: docs={len(b.docs)}, chars={b.total_chars()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
