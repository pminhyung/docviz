"""arXiv loader → 50 multi-doc Bundles from visubench docai corpus.

v0.3 amendment D1.1: scale from 5 → 50 bundles. The earlier loader
(`load_arxiv.py.old`) required a plain-text corpus with category metadata
that we no longer have access to. Instead this loader consumes the
visubench docai corpus at
`/ex_disk2/mhpark/poc/visubench/data/corpus/arxiv/*.json`, which holds
295 papers with page-keyed parsed text (`outputs[0].html_parsed`).

Bundle composition (intra-paper multi-doc, matching govreport / tech_docs):
  - 1 paper → 1 bundle
  - Pages partitioned into 3-4 sections (equal-char chunks of contiguous
    pages); each section becomes one Doc
  - Doc.title = f"{paper_title} — Section N (pages X-Y)"
  - 50 bundles sampled with random.seed(42)

Spec deviation note (paper §5.1): amendment §3.2 line 87 calls for
"3-5 paper abstracts in same conference track". The visubench corpus
does not retain arXiv category metadata, so we substitute "3-4 sections
from one long paper" — same multi-doc topology, same retrieval challenge
shape, simpler controlled grouping. Within-paper sections preserve
topic coherence the same way same-track abstracts would.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("HF_HOME", "/ex_disk2/mhpark/poc/.cache/huggingface")

from code.pipelines.base import Bundle, Doc
from code.utils.bundle_io import validate_bundle, write_bundles_json


SEED = 42
N_BUNDLES = 5  # preflight; bulk target 50

# Doc-shape constraints
MIN_DOCS = 3
MAX_DOCS = 4
MIN_PAGES_PER_PAPER = 5     # skip stub papers
BODY_CAP_CHARS = 18_000     # per-Doc cap (per amendment scaling guidance)

CORPUS_DIR = Path("/ex_disk2/mhpark/poc/visubench/data/corpus/arxiv")

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "arxiv.json"

_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def _normalize_page(pg) -> str:
    """Coerce a page value (str or list) into a flat plain-text block."""
    if isinstance(pg, list):
        text = "\n".join(str(x) for x in pg if x)
    else:
        text = str(pg)
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


def _load_paper(path: Path) -> Dict | None:
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print(f"  [skip] {path.name}: {type(e).__name__}: {e}")
        return None
    outputs = d.get("outputs") or []
    if not outputs:
        return None
    o = outputs[0]
    title = (o.get("file_name") or "").strip()
    pages_raw = o.get("html_parsed") or {}
    if not isinstance(pages_raw, dict):
        return None
    # Sort by integer page number
    try:
        sorted_pairs = sorted(
            ((int(k), v) for k, v in pages_raw.items() if str(k).isdigit()),
            key=lambda kv: kv[0],
        )
    except Exception:
        return None
    if len(sorted_pairs) < MIN_PAGES_PER_PAPER:
        return None
    pages = [(str(pn), _normalize_page(v)) for pn, v in sorted_pairs]
    pages = [(pn, t) for pn, t in pages if t]
    if len(pages) < MIN_PAGES_PER_PAPER:
        return None
    return {
        "title": title or "Untitled arXiv paper",
        "pages": pages,
        "source_file": path.name,
    }


def _split_pages_into_docs(
    pages: List[Tuple[str, str]],
    target_docs: int,
) -> List[Tuple[str, str]]:
    """Partition `pages` into `target_docs` roughly char-equal chunks of
    contiguous pages. Each chunk yields one (section_title, body) tuple."""
    n = len(pages)
    target_docs = max(MIN_DOCS, min(MAX_DOCS, target_docs))
    if n < target_docs:
        target_docs = max(2, n)

    total_chars = sum(len(t) for _, t in pages)
    target_chunk = total_chars / target_docs

    docs: List[Tuple[str, str]] = []
    cur_pages: List[Tuple[str, str]] = []
    cur_chars = 0
    for pn, text in pages:
        cur_pages.append((pn, text))
        cur_chars += len(text)
        if cur_chars >= target_chunk and len(docs) + 1 < target_docs:
            docs.append(_assemble_doc(cur_pages))
            cur_pages = []
            cur_chars = 0
    if cur_pages:
        docs.append(_assemble_doc(cur_pages))
    return docs


def _assemble_doc(page_pairs: List[Tuple[str, str]]) -> Tuple[str, str]:
    """Build (title, body) from a sequence of (page_no, page_text)."""
    if not page_pairs:
        return ("Empty section", "")
    first_pn = page_pairs[0][0]
    last_pn = page_pairs[-1][0]
    if first_pn == last_pn:
        sec_title = f"Section (page {first_pn})"
    else:
        sec_title = f"Section (pages {first_pn}-{last_pn})"
    body = "\n\n".join(text for _, text in page_pairs)
    return (sec_title, body[:BODY_CAP_CHARS])


def _choose_doc_count(n_pages: int) -> int:
    """Longer papers → 4 docs, shorter → 3 docs."""
    return MAX_DOCS if n_pages >= 12 else MIN_DOCS


def _build_bundle(idx: int, paper: Dict) -> Bundle | None:
    target = _choose_doc_count(len(paper["pages"]))
    sections = _split_pages_into_docs(paper["pages"], target_docs=target)
    sections = [(t, b) for t, b in sections if b]
    if len(sections) < MIN_DOCS:
        return None

    title_short = paper["title"][:160]
    docs: List[Doc] = []
    for j, (sec_title, body) in enumerate(sections):
        docs.append(Doc(
            doc_id=f"arxiv_{idx:02d}_{j}",
            title=f"{title_short} — {sec_title}"[:200],
            content=body,
            page_id=None,
        ))

    return Bundle(
        bundle_id=f"arxiv_{idx:02d}",
        source="arxiv",
        docs=docs,
        metadata={
            "language": "en",
            "paper_title": title_short,
            "visubench_file": paper["source_file"],
            "n_pages": len(paper["pages"]),
            "section_count": len(docs),
        },
    )


def load_arxiv(
    n_bundles: int = N_BUNDLES,
    seed: int = SEED,
    corpus_dir: Path = CORPUS_DIR,
) -> List[Bundle]:
    if not corpus_dir.is_dir():
        raise FileNotFoundError(f"arxiv corpus dir not found: {corpus_dir}")

    paths = sorted(corpus_dir.glob("*.json"))
    print(f"[arxiv] discovered {len(paths)} candidate papers in {corpus_dir}")

    # Shuffle for deterministic sampling
    rng = random.Random(seed)
    rng.shuffle(paths)

    bundles: List[Bundle] = []
    skipped = 0
    for path in paths:
        if len(bundles) >= n_bundles:
            break
        paper = _load_paper(path)
        if paper is None:
            skipped += 1
            continue
        b = _build_bundle(len(bundles), paper)
        if b is None:
            skipped += 1
            continue
        try:
            validate_bundle(b)
        except Exception as e:
            print(f"  [skip] {path.name}: bundle validation failed: {e}")
            skipped += 1
            continue
        bundles.append(b)

    print(f"[arxiv] produced {len(bundles)} bundles (skipped {skipped})")
    for b in bundles[:5]:
        print(
            f"  {b.bundle_id}: docs={len(b.docs)}, chars={b.total_chars()}, "
            f"pages={b.metadata.get('n_pages')}, title={b.metadata.get('paper_title','')[:60]!r}"
        )
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser(description="Build arXiv bundles from visubench docai corpus.")
    ap.add_argument("--n-bundles", type=int, default=N_BUNDLES)
    ap.add_argument("--corpus", default=str(CORPUS_DIR))
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    bundles = load_arxiv(
        n_bundles=args.n_bundles,
        corpus_dir=Path(args.corpus),
    )
    if not bundles:
        print("[arxiv] no bundles produced — aborting write")
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_bundles_json(bundles, str(out))
    print(f"[arxiv] wrote {len(bundles)} bundles → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
