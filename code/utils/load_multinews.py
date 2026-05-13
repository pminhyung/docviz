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
MIN_ARTICLES = 2
MAX_ARTICLES = 5
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
    return Bundle(
        bundle_id=f"multinews_{idx:02d}",
        source="multinews",
        docs=docs,
        metadata={
            "language": "en",
            "reference_summary": _clean(ex.get("summary", "")),
            "n_articles": len(articles),
        },
    )


def build_bundles() -> List[Bundle]:
    print("[multinews] loading validation split…")
    # `alexfabbri/multi_news` is the canonical author's release and is more
    # reliable than the bare `multi_news` namespace. Both ship a custom loader
    # script — HF requires explicit opt-in via trust_remote_code.
    ds = load_dataset("alexfabbri/multi_news", split=SPLIT, trust_remote_code=True)
    print(f"  loaded {len(ds)} clusters")

    candidates: List[Dict[str, Any]] = []
    for ex in ds:
        n = len(_split_cluster(ex["document"]))
        if MIN_ARTICLES <= n <= MAX_ARTICLES:
            candidates.append(ex)
    print(f"  {len(candidates)} candidates after cluster-size filter")

    random.seed(SEED)
    random.shuffle(candidates)

    bundles: List[Bundle] = []
    for ex in candidates:
        if len(bundles) >= N_BUNDLES:
            break
        b = _build_bundle(len(bundles), ex)
        if len(b.docs) < MIN_ARTICLES:
            continue
        if b.total_chars() < 3000 or b.total_chars() > 80000:
            continue
        bundles.append(b)
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
        errors.extend(validate_bundle(b))
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
