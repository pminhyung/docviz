"""GovReport loader (v0.3 amendment D2.1-D2.4) → 50 multi-doc Bundles.

Per AMENDMENT_v0.3_ACTION_SPEC.md §3.3:
  - Source: HuggingFace `ccdv/govreport-summarization` (alt: SCROLLS `gov_report`)
  - Filter to length 10K-40K tokens — multi-doc challenge calibrated
  - Split each report into 2-3 section docs (by section headers; if no
    clear headers, split evenly into 3 docs by paragraph)
  - 50 bundles with `source = "govreport"`, random.seed(42)
  - metadata = {report_id, original_topic}

Verification gate D2.4: each bundle has 2-3 docs of plain text, passes
Bundle schema validation.

The 2-month / 24-month etc. corpus-window concerns in PAPER_MASTER_SPEC
don't apply here — GovReport reports are non-time-bound congressional /
regulatory documents.
"""
from __future__ import annotations

import argparse
import os
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Pin HF cache to /ex_disk2 (root partition full on this dev box)
os.environ.setdefault("HF_HOME", "/ex_disk2/mhpark/poc/.cache/huggingface")

from datasets import load_dataset

from code.pipelines.base import Bundle, Doc
from code.utils.bundle_io import validate_bundle, write_bundles_json


SEED = 42
N_BUNDLES = 50
MIN_DOCS = 2
MAX_DOCS = 3
# Token-length filter on the raw report. Approximate: 1 token ≈ 4 chars
# (English). Use char-based proxy to avoid tokenizer dependency.
MIN_CHARS = 40_000           # ≈ 10K tokens
MAX_CHARS = 160_000          # ≈ 40K tokens
# Body cap per source doc — keep each bundle under the 80K-char doc-step
# truncation budget (run_agent_v2.py:474).
BODY_CAP_CHARS = 30_000

# Section header heuristic — congressional report style.
# Order is intentional: more-specific patterns first.
_SECTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # "Chapter N." / "Section N." / "Title N." headers
    ("chapter", re.compile(r"^\s*(?:Chapter|Section|Title)\s+\d+[\.\:][^\n]*$", re.MULTILINE)),
    # All-caps section headings (≥ 3 chars, on their own line)
    ("allcaps", re.compile(r"^\s*[A-Z][A-Z0-9 ,\-&/]{6,}\s*$", re.MULTILINE)),
    # Numbered headings: "1. Introduction"
    ("numbered", re.compile(r"^\s*\d+\.\s+[A-Z][A-Za-z][^\n]*$", re.MULTILINE)),
]

SPLIT = "train"  # train split is the largest for ccdv/govreport-summarization
DATASET_ID = "ccdv/govreport-summarization"

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "govreport.json"


def _split_by_sections(report_text: str) -> List[Tuple[str, str]]:
    """Try section-header heuristics in priority order. Return list of
    (title, section_text). If no header pattern fires, return [].
    """
    for label, pat in _SECTION_PATTERNS:
        matches = list(pat.finditer(report_text))
        if len(matches) >= 2:  # need at least 2 sections for multi-doc
            sections: List[Tuple[str, str]] = []
            for i, m in enumerate(matches):
                title = m.group(0).strip()
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(report_text)
                body = report_text[start:end].strip()
                if body:
                    sections.append((title, body))
            if len(sections) >= MIN_DOCS:
                return sections
    return []


def _split_evenly_by_paragraph(report_text: str, n_parts: int) -> List[Tuple[str, str]]:
    """Fallback: split into n_parts char-equal chunks at the nearest
    sentence boundary. GovReport HF rows are typically one long paragraph
    with no newlines, so paragraph-based splitting doesn't work; we split
    by sentence boundary (`. `, `? `, `! `) closest to each ideal cut.

    Title is the first 8 words of each chunk.
    """
    text = report_text.strip()
    if not text:
        return []

    total = len(text)
    if n_parts <= 1 or total < 200:
        return [(_first_words_title(text, fallback="Section 1"), text)]

    # Compute ideal cut positions: total/n_parts, 2*total/n_parts, ...
    cuts: List[int] = []
    for i in range(1, n_parts):
        ideal = int(total * i / n_parts)
        # Find nearest sentence-ending punctuation in a window around ideal.
        window = 1500  # search up to ±1.5K chars
        lo = max(0, ideal - window)
        hi = min(total, ideal + window)
        best = ideal
        best_dist = total
        for m in re.finditer(r"[\.\?\!]\s+[A-Z]", text[lo:hi]):
            pos = lo + m.start() + 1  # cut after the punctuation
            d = abs(pos - ideal)
            if d < best_dist:
                best = pos
                best_dist = d
        cuts.append(best)

    # Convert cuts → segment boundaries
    boundaries = [0] + cuts + [total]
    sections: List[Tuple[str, str]] = []
    for i in range(len(boundaries) - 1):
        chunk = text[boundaries[i]:boundaries[i + 1]].strip()
        if not chunk:
            continue
        sections.append((_first_words_title(chunk, fallback=f"Section {i+1}"), chunk))
    return sections


def _first_words_title(text: str, n: int = 8, fallback: str = "Section") -> str:
    words = text.split()[:n]
    title = " ".join(words)
    return (title + ("…" if len(text.split()) > n else "")) or fallback


def _choose_doc_count(text_len: int) -> int:
    """Longer reports → 3 docs, shorter → 2 docs."""
    return MAX_DOCS if text_len >= 80_000 else MIN_DOCS


def _build_bundle(idx: int, report_id: str, report_text: str,
                  summary: str) -> Bundle | None:
    """Split report into docs and assemble Bundle. Returns None if the
    split yields < MIN_DOCS sections after filtering."""
    section_pairs = _split_by_sections(report_text)
    if len(section_pairs) < MIN_DOCS:
        n = _choose_doc_count(len(report_text))
        section_pairs = _split_evenly_by_paragraph(report_text, n)

    if len(section_pairs) < MIN_DOCS:
        return None

    # Cap to MAX_DOCS by merging trailing sections into the last one
    if len(section_pairs) > MAX_DOCS:
        head = section_pairs[: MAX_DOCS - 1]
        tail_bodies = [body for _, body in section_pairs[MAX_DOCS - 1 :]]
        merged_title = section_pairs[MAX_DOCS - 1][0]
        merged_body = "\n\n".join(tail_bodies)
        section_pairs = head + [(merged_title, merged_body)]

    docs: List[Doc] = []
    for j, (title, body) in enumerate(section_pairs):
        capped = body[:BODY_CAP_CHARS]
        docs.append(Doc(
            doc_id=f"govreport_{idx:02d}_{j}",
            title=title[:160],   # safety cap on title length
            content=capped,
            page_id=None,
        ))

    # Original topic = first 10 words of the official summary (HF field).
    topic_words = (summary or "").split()[:10]
    original_topic = " ".join(topic_words) + ("…" if len(topic_words) >= 10 else "")

    return Bundle(
        bundle_id=f"govreport_{idx:02d}",
        source="govreport",
        docs=docs,
        metadata={
            "language": "en",
            "report_id": report_id,
            "original_topic": original_topic,
        },
    )


def load_govreport(
    n_bundles: int = N_BUNDLES,
    min_chars: int = MIN_CHARS,
    max_chars: int = MAX_CHARS,
    split: str = SPLIT,
    seed: int = SEED,
) -> List[Bundle]:
    print(f"[govreport] loading dataset {DATASET_ID} split={split}…")
    ds = load_dataset(DATASET_ID, split=split)
    print(f"[govreport] dataset rows: {len(ds)}")

    # Filter by length
    candidates: List[Tuple[int, str]] = []
    for i, row in enumerate(ds):
        text = row.get("report") or row.get("text") or ""
        if not isinstance(text, str):
            continue
        if min_chars <= len(text) <= max_chars:
            candidates.append((i, text))
    print(f"[govreport] candidates after length filter [{min_chars}-{max_chars}]: {len(candidates)}")

    if len(candidates) < n_bundles:
        print(f"[govreport] WARNING: only {len(candidates)} candidates, need {n_bundles}")

    rng = random.Random(seed)
    rng.shuffle(candidates)

    bundles: List[Bundle] = []
    for idx, (row_idx, text) in enumerate(candidates):
        if len(bundles) >= n_bundles:
            break
        summary = ds[row_idx].get("summary") or ds[row_idx].get("abstract") or ""
        report_id = ds[row_idx].get("id") or f"row_{row_idx}"
        b = _build_bundle(len(bundles), str(report_id), text, summary)
        if b is None:
            continue
        validate_bundle(b)
        bundles.append(b)

    print(f"[govreport] produced {len(bundles)} bundles")
    for b in bundles[:5]:
        print(
            f"  {b.bundle_id}: docs={len(b.docs)}, chars={b.total_chars()}, "
            f"topic={b.metadata.get('original_topic','')!r}"
        )
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-bundles", type=int, default=N_BUNDLES)
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    bundles = load_govreport(n_bundles=args.n_bundles)
    if not bundles:
        print("[govreport] no bundles produced — aborting write")
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_bundles_json(bundles, str(out))
    print(f"[govreport] wrote {len(bundles)} bundles → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
