"""arXiv loader → 5 source-internal multi-doc Bundles.

Per PAPER_MASTER_SPEC §5.1:
  - 5 NLP/ML bundles, 3 papers each
  - Same primary category per bundle
  - Bundle target ~15-50K tokens (§5.1 L220)
  - "Each paper's (abstract + first paragraph of intro) becomes a Doc" was
    the spec's 1st draft, but it conflicts with the 15-50K token target and
    leaves §3.1 Cross-doc Iterative Search nothing to retrieve over. We use
    full_text (capped at 20K chars/paper ≈ 5K tokens) so CIS has substance.

Source: visubench corpus at $DOCVIZ_VISUBENCH/data/corpus/_raw/arxiv/, an
offline cache of 295 papers (2026 Q1-Q2, license: "arXiv non-exclusive —
research/text mining permitted"). No network access at load time.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from code.pipelines.base import Bundle, Doc
from code.utils.bundle_io import validate_bundle, write_bundles_json


N_BUNDLES = 5
PAPERS_PER_BUNDLE = 3
BODY_CAP_CHARS = 20_000

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "arxiv.json"

VISUBENCH_DEFAULT = "/ex_disk2/mhpark/poc/visubench/data/corpus/_raw/arxiv"


# Each bundle = (label, primary_category, optional filter on secondary list).
# cs.LG is split twice because it is the largest group in the visubench
# corpus and naturally separates into general-ML vs life-science-ML.
BUNDLE_SPEC: List[Dict] = [
    {"label": "cs.LG (general ML)", "primary": "cs.LG",
     "secondary_excludes": {"q-bio.QM", "q-bio.GN", "q-bio.BM"}},
    {"label": "cs.LG ∩ q-bio (life-science ML)", "primary": "cs.LG",
     "secondary_includes": {"q-bio.QM", "q-bio.GN", "q-bio.BM"}},
    {"label": "cs.CV", "primary": "cs.CV"},
    {"label": "cs.CL", "primary": "cs.CL"},
    {"label": "cs.AI", "primary": "cs.AI"},
]


def _matches(paper: Dict, spec: Dict) -> bool:
    cats = paper.get("categories") or []
    if not cats or cats[0] != spec["primary"]:
        return False
    secondary = set(cats[1:])
    if "secondary_includes" in spec:
        if not (secondary & spec["secondary_includes"]):
            return False
    if "secondary_excludes" in spec:
        if secondary & spec["secondary_excludes"]:
            return False
    return True


def _load_corpus(corpus_dir: Path) -> List[Dict]:
    papers: List[Dict] = []
    for p in sorted(corpus_dir.glob("*.json")):
        try:
            papers.append(json.loads(p.read_text()))
        except Exception as e:
            print(f"  [skip] {p.name}: {type(e).__name__}: {e}")
    return papers


def _build_bundle(idx: int, spec: Dict, papers: List[Dict]) -> Bundle:
    docs: List[Doc] = []
    primary_cats: List[str] = []
    arxiv_ids: List[str] = []
    licenses: List[str] = []
    for j, p in enumerate(papers):
        body = (p.get("full_text") or "").strip()[:BODY_CAP_CHARS]
        docs.append(Doc(
            doc_id=f"arxiv_{idx:02d}_{j}",
            title=p["title"].strip(),
            content=body,
            page_id=p.get("source_url") or p.get("arxiv_id"),
        ))
        primary_cats.append(p["categories"][0])
        arxiv_ids.append(p["arxiv_id"])
        licenses.append(p.get("license", ""))
    return Bundle(
        bundle_id=f"arxiv_{idx:02d}",
        source="arxiv",
        docs=docs,
        metadata={
            "language": "en",
            "topic_seed": spec["label"],
            "primary_category": spec["primary"],
            "primary_categories": primary_cats,
            "arxiv_ids": arxiv_ids,
            "license": licenses[0] if len(set(licenses)) == 1 else licenses,
            "source_corpus": "visubench/_raw/arxiv",
        },
    )


def build_bundles(corpus_dir: Path) -> List[Bundle]:
    papers = _load_corpus(corpus_dir)
    print(f"[arxiv] loaded {len(papers)} papers from {corpus_dir}")
    bundles: List[Bundle] = []
    for idx, spec in enumerate(BUNDLE_SPEC[:N_BUNDLES]):
        candidates = [p for p in papers if _matches(p, spec)]
        candidates.sort(key=lambda p: p.get("published", ""), reverse=True)
        chosen = candidates[:PAPERS_PER_BUNDLE]
        if len(chosen) < PAPERS_PER_BUNDLE:
            print(f"  [{spec['label']}] only {len(chosen)} candidates "
                  f"(needed {PAPERS_PER_BUNDLE}); skipping")
            continue
        bundles.append(_build_bundle(idx, spec, chosen))
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser(description="Build arXiv bundles from visubench corpus.")
    ap.add_argument("--corpus", default=os.environ.get("DOCVIZ_VISUBENCH_ARXIV", VISUBENCH_DEFAULT),
                    help="Path to visubench _raw/arxiv directory.")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    corpus_dir = Path(args.corpus)
    if not corpus_dir.is_dir():
        print(f"  [error] corpus dir not found: {corpus_dir}")
        return 2

    bundles = build_bundles(corpus_dir)
    errors: List[str] = []
    for b in bundles:
        errors.extend(validate_bundle(b))
    if errors:
        print("  [VALIDATION ERRORS]")
        for e in errors:
            print(f"    {e}")
        return 2

    write_bundles_json(bundles, args.out)
    print(f"[arxiv] wrote {len(bundles)} bundles → {args.out}")
    for b in bundles:
        print(f"    {b.bundle_id} [{b.metadata['topic_seed']}]: docs={len(b.docs)}, "
              f"chars={b.total_chars()}")
    return 0 if bundles else 2


if __name__ == "__main__":
    sys.exit(main())
