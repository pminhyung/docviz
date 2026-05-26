"""arXiv loader → 50 cross-document multi-paper bundles.

LOADER_CONTRACT_v04 redesign (2026-05-24):
  - Each bundle = 3-5 distinct arXiv papers from the same primary category
    (true cross-doc, no intra-paper section splits)
  - 50 bundles total, 15K-200K chars/bundle
  - Doc = title + first ~10K chars of full_text per paper (header + abstract
    + introduction + early body)
  - random.seed(42)

Source corpus: visubench `_raw/arxiv/` cache, 295 papers with category
metadata + full_text (no network calls). Categories include cs.LG, cs.SE,
cs.CV, cs.CL, cs.AI, cs.DC, cs.CR, econ.GN, math.OC, stat.ML, q-bio.QM,
cond-mat.mtrl-sci, etc.

Why this corpus over HF `ccdv/arxiv-summarization`: ccdv has no category
metadata; the visubench cache has both category + body, so each bundle's
`arxiv_category` field is grounded in real arXiv taxonomy (not a clustering
proxy). Spec calls out cs.* as illustrative — we honour the *spirit* (same
arxiv_category per bundle) for both cs.* and adjacent fields to reach the
50-bundle target.

Bundle metadata (per LOADER_CONTRACT_v04 §"Bundle.metadata"):
  - language: "en"
  - bridge_entity: f"arxiv_category:{primary_cat}"   # what ties docs
  - arxiv_category: e.g. "cs.LG"                     # the category itself
  - paper_ids: ["2603.xxxxxv1", ...]
  - paper_titles: [...]   (for human inspection)
  - n_docs: int
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("HF_HOME", "/ex_disk2/mhpark/poc/.cache/huggingface")

from code.pipelines.base import Bundle, Doc
from code.utils.bundle_io import validate_bundle, write_bundles_json


SEED = 42
N_BUNDLES = 50

MIN_DOCS = 3
MAX_DOCS = 5
MIN_CHARS = 15_000
MAX_CHARS = 200_000

# Per-paper Doc.content cap. With 3-5 docs/bundle and 10K cap, bundle char
# range is ~18K-50K (well inside 15K-200K). Most paper full_texts (median
# 60K) get truncated to the header + abstract + intro + early body — which
# matches the contract's "title + abstract + intro/section1 per paper".
PER_DOC_CHAR_CAP = 12_000
# Per-paper minimum after cap; skip stubs.
PER_DOC_MIN_CHARS = 4_000

# Primary-category bundle plan: how many bundles to draw from each category,
# in priority order. Sums to >=50. Categories with <3 papers are skipped.
# Tuned to the visubench cache distribution (n_papers per primary cat).
CATEGORY_BUNDLE_PLAN: List[tuple] = [
    # (primary_category, target_n_bundles, target_docs_per_bundle)
    ("cs.LG",             10, 3),   # 31 papers / 3 = 10
    ("cs.SE",              9, 3),   # 29 / 3 = 9
    ("econ.GN",            8, 3),   # 25 / 3 = 8
    ("math.OC",            7, 3),   # 22 / 3 = 7
    ("cs.CV",              5, 3),   # 15 / 3 = 5
    ("cond-mat.mtrl-sci",  5, 3),   # 15 / 3 = 5
    ("cs.CL",              4, 3),   # 13 / 3 = 4
    ("cs.AI",              3, 3),   # 10 / 3 = 3
    # Backup categories if any of the above underfill:
    ("astro-ph.GA",        3, 3),   # 9 / 3 = 3
    ("q-bio.QM",           2, 3),   # 8 / 3 = 2
    ("physics.optics",     2, 3),   # 8 / 3 = 2
    ("cs.DC",              2, 3),   # 8 / 3 = 2
    ("cs.CR",              2, 3),   # 7 / 3 = 2
    ("q-bio.GN",           2, 3),   # 6 / 3 = 2
    ("eess.SY",            2, 3),   # 6 / 3 = 2
    ("stat.ML",            2, 3),   # 6 / 3 = 2
    ("quant-ph",           2, 3),   # 6 / 3 = 2
]

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "arxiv.json"

VISUBENCH_DEFAULT = Path(
    os.environ.get(
        "DOCVIZ_VISUBENCH_ARXIV",
        "/ex_disk2/mhpark/poc/visubench/data/corpus/_raw/arxiv",
    )
)


_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def _clean_text(s: str) -> str:
    s = _WS_RE.sub(" ", s)
    s = _NL_RE.sub("\n\n", s)
    return s.strip()


def _load_corpus(corpus_dir: Path) -> List[Dict]:
    """Load every JSON paper, returning only those with a non-empty
    full_text and at least one category."""
    papers: List[Dict] = []
    for p in sorted(corpus_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [skip] {p.name}: {type(e).__name__}: {e}")
            continue
        full_text = (d.get("full_text") or "").strip()
        cats = d.get("categories") or []
        if not full_text or not cats:
            continue
        # quick prune: per-doc body must clear the per-paper char floor
        # *after* truncation, which is at most len(full_text).
        if len(full_text) < PER_DOC_MIN_CHARS:
            continue
        papers.append({
            "arxiv_id": d.get("arxiv_id") or p.stem,
            "title": (d.get("title") or "").strip() or "Untitled arXiv paper",
            "categories": cats,
            "primary_category": cats[0],
            "full_text": full_text,
            "license": d.get("license", ""),
            "source_url": d.get("source_url", ""),
            "published": d.get("published", ""),
            "source_file": p.name,
        })
    return papers


def _group_by_primary(papers: List[Dict]) -> Dict[str, List[Dict]]:
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for p in papers:
        groups[p["primary_category"]].append(p)
    return groups


def _make_doc(idx: int, j: int, paper: Dict) -> Doc:
    """Build a Doc from a paper: title + truncated body."""
    body = _clean_text(paper["full_text"])[:PER_DOC_CHAR_CAP]
    return Doc(
        doc_id=f"arxiv_{idx:02d}_{j}",
        title=paper["title"][:200],
        content=body,
        page_id=paper.get("arxiv_id"),
    )


def _build_bundle(idx: int, primary_cat: str, papers: List[Dict]) -> Bundle:
    docs = [_make_doc(idx, j, p) for j, p in enumerate(papers)]
    licenses = sorted({p.get("license", "") for p in papers if p.get("license")})
    return Bundle(
        bundle_id=f"arxiv_{idx:02d}",
        source="arxiv",
        docs=docs,
        metadata={
            "language": "en",
            "bridge_entity": f"arxiv_category:{primary_cat}",
            "arxiv_category": primary_cat,
            "paper_ids": [p["arxiv_id"] for p in papers],
            "paper_titles": [p["title"][:160] for p in papers],
            "n_docs": len(docs),
            "license": licenses if len(licenses) > 1 else (licenses[0] if licenses else ""),
            "source_corpus": "visubench/_raw/arxiv",
        },
    )


def build_bundles(corpus_dir: Path, n_bundles: int = N_BUNDLES,
                  seed: int = SEED) -> List[Bundle]:
    papers = _load_corpus(corpus_dir)
    print(f"[arxiv] loaded {len(papers)} usable papers from {corpus_dir}")
    groups = _group_by_primary(papers)
    print(f"[arxiv] primary-category groups: "
          f"{ {c: len(v) for c, v in sorted(groups.items(), key=lambda x: -len(x[1]))[:10]} }")

    rng = random.Random(seed)
    # Deterministic shuffle within each primary-category pool
    for cat in groups:
        rng.shuffle(groups[cat])

    bundles: List[Bundle] = []
    for primary_cat, target_n, docs_per_bundle in CATEGORY_BUNDLE_PLAN:
        if len(bundles) >= n_bundles:
            break
        pool = groups.get(primary_cat, [])
        if len(pool) < docs_per_bundle:
            continue
        cursor = 0
        made_for_cat = 0
        while cursor + docs_per_bundle <= len(pool) and made_for_cat < target_n:
            if len(bundles) >= n_bundles:
                break
            chunk = pool[cursor:cursor + docs_per_bundle]
            cursor += docs_per_bundle
            b = _build_bundle(len(bundles), primary_cat, chunk)
            # Validate before accepting; on failure, try to extend to 4 docs
            errs = validate_bundle(b, min_docs=MIN_DOCS,
                                   min_chars=MIN_CHARS, max_chars=MAX_CHARS)
            if errs and cursor < len(pool):
                # Try adding one more doc (up to MAX_DOCS) to clear char floor
                extra = pool[cursor]
                cursor += 1
                chunk = chunk + [extra]
                b = _build_bundle(len(bundles), primary_cat, chunk)
                errs = validate_bundle(b, min_docs=MIN_DOCS,
                                       min_chars=MIN_CHARS, max_chars=MAX_CHARS)
            if errs:
                print(f"  [skip] {primary_cat} chunk @cursor={cursor}: {errs}")
                continue
            bundles.append(b)
            made_for_cat += 1

    if len(bundles) < n_bundles:
        print(f"[arxiv] only built {len(bundles)} bundles from planned categories; "
              f"trying fallback fill from remaining categories…")
        # Fallback: any remaining category with >=3 unused papers
        # (We track per-category cursors in the loop above; here just walk
        # categories not yet visited or with leftover papers.)
        used_arxiv_ids = {p for b in bundles for p in b.metadata["paper_ids"]}
        for cat, pool in sorted(groups.items(), key=lambda x: -len(x[1])):
            if len(bundles) >= n_bundles:
                break
            remaining = [p for p in pool if p["arxiv_id"] not in used_arxiv_ids]
            cursor = 0
            while cursor + MIN_DOCS <= len(remaining):
                if len(bundles) >= n_bundles:
                    break
                chunk = remaining[cursor:cursor + MIN_DOCS]
                cursor += MIN_DOCS
                b = _build_bundle(len(bundles), cat, chunk)
                errs = validate_bundle(b, min_docs=MIN_DOCS,
                                       min_chars=MIN_CHARS, max_chars=MAX_CHARS)
                if errs:
                    continue
                bundles.append(b)
                used_arxiv_ids.update(p["arxiv_id"] for p in chunk)

    return bundles


def main() -> int:
    ap = argparse.ArgumentParser(description="Build cross-doc arXiv bundles.")
    ap.add_argument("--corpus", default=str(VISUBENCH_DEFAULT))
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--n-bundles", type=int, default=N_BUNDLES)
    args = ap.parse_args()

    corpus_dir = Path(args.corpus)
    if not corpus_dir.is_dir():
        print(f"[error] corpus dir not found: {corpus_dir}")
        return 2

    bundles = build_bundles(corpus_dir, n_bundles=args.n_bundles)
    print(f"[arxiv] built {len(bundles)} bundles")

    # Final per-bundle validation pass (defensive)
    errors: List[str] = []
    for b in bundles:
        errors.extend(validate_bundle(b, min_docs=MIN_DOCS,
                                      min_chars=MIN_CHARS, max_chars=MAX_CHARS))
    if errors:
        print("[arxiv] VALIDATION ERRORS:")
        for e in errors:
            print(f"  {e}")
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_bundles_json(bundles, str(out))
    print(f"[arxiv] wrote {len(bundles)} bundles → {out}")
    for b in bundles:
        print(f"  {b.bundle_id} [{b.metadata['arxiv_category']}]: "
              f"docs={len(b.docs)}, chars={b.total_chars()}")
    return 0 if len(bundles) >= args.n_bundles else 2


if __name__ == "__main__":
    sys.exit(main())
