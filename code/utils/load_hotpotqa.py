"""HotpotQA loader → 10 source-internal multi-doc Bundles.

Per PAPER_MASTER_SPEC §5.1:
  - Each bundle = supporting Wikipedia paragraphs only (drop distractors)
  - Filter on type ∈ {comparison, bridge}
  - random.seed(42)

The source-of-truth dev-distractor JSON is fetched lazily. We try the
HuggingFace `hotpot_qa` dataset first (no auth required for open data) and
fall back to the canonical Curtis URL if that fails. The downloaded raw is
cached at `data/prototype/sources/raw/hotpotqa_dev_distractor.json` and the
output bundle list is written to `data/prototype/bundles/hotpotqa.json`.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

# Make `code.*` importable when invoked from repo root or CLI.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Root partition on this dev box is at 100%; redirect HF cache to /ex_disk2.
os.environ.setdefault("HF_HOME", "/ex_disk2/mhpark/poc/.cache/huggingface")

from code.pipelines.base import Bundle, Doc
from code.utils.bundle_io import validate_bundle, write_bundles_json


SEED = 42
N_BUNDLES = 10
ALLOWED_TYPES = {"comparison", "bridge"}
# HotpotQA supporting paragraphs are short by construction (1-3 sents per
# Wikipedia title). The PAPER_MASTER_SPEC §5.1 char floor (3K) is calibrated
# for the larger sources (MultiNews / arXiv / 10-K); we relax to 500 for
# HotpotQA only, documented in WEEK0_LOG.md.
MIN_CHARS = 500
MAX_CHARS = 80_000
HOTPOT_URL = "http://curtis.ml.cmu.edu/datasets/hotpot/hotpot_dev_distractor_v1.json"

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "prototype" / "sources" / "raw"
RAW_PATH = RAW_DIR / "hotpotqa_dev_distractor.json"
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "hotpotqa.json"


def _load_via_hf() -> List[Dict[str, Any]] | None:
    """Try HuggingFace `hotpot_qa` dataset (distractor / validation)."""
    try:
        from datasets import load_dataset
    except ImportError:
        return None
    try:
        ds = load_dataset("hotpot_qa", "distractor", split="validation",
                          trust_remote_code=True)
    except Exception as e:
        print(f"  HF load failed: {type(e).__name__}: {e}")
        return None
    out: List[Dict[str, Any]] = []
    for ex in ds:
        # HF schema differs slightly from canonical: context is a dict-of-arrays.
        ctx_titles = ex["context"]["title"]
        ctx_sents = ex["context"]["sentences"]
        sf_titles = ex["supporting_facts"]["title"]
        sf_sids = ex["supporting_facts"]["sent_id"]
        out.append({
            "_id": ex["id"],
            "question": ex["question"],
            "answer": ex["answer"],
            "type": ex["type"],
            "context": list(zip(ctx_titles, ctx_sents)),
            "supporting_facts": list(zip(sf_titles, sf_sids)),
        })
    return out


def _load_via_url() -> List[Dict[str, Any]]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if not RAW_PATH.exists():
        print(f"  downloading {HOTPOT_URL} → {RAW_PATH}")
        urllib.request.urlretrieve(HOTPOT_URL, RAW_PATH)
    with open(RAW_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_examples() -> List[Dict[str, Any]]:
    print("[hotpotqa] loading dev distractor split…")
    data = _load_via_hf()
    if data is None:
        data = _load_via_url()
    print(f"  loaded {len(data)} examples")
    return data


def _build_bundle(idx: int, ex: Dict[str, Any]) -> Bundle:
    sf_titles = {t for t, _ in ex["supporting_facts"]}
    docs: List[Doc] = []
    for j, (title, sentences) in enumerate(ex["context"]):
        if title not in sf_titles:
            continue
        content = " ".join(sentences).strip()
        if not content:
            continue
        docs.append(Doc(
            doc_id=f"hotpot_{idx:02d}_{j}",
            title=title,
            content=content,
        ))
    return Bundle(
        bundle_id=f"hotpot_{idx:02d}",
        source="hotpotqa",
        docs=docs,
        metadata={
            "language": "en",
            "original_question": ex.get("question", ""),
            "original_answer": ex.get("answer", ""),
            "type_hint": ex.get("type", ""),
        },
    )


def build_bundles() -> List[Bundle]:
    examples = load_examples()
    candidates = [
        ex for ex in examples
        if ex.get("type") in ALLOWED_TYPES and len(ex.get("supporting_facts", [])) >= 2
    ]
    print(f"  {len(candidates)} candidates after type/SF filter")
    random.seed(SEED)
    random.shuffle(candidates)

    bundles: List[Bundle] = []
    for ex in candidates:
        if len(bundles) >= N_BUNDLES:
            break
        b = _build_bundle(len(bundles), ex)
        if len(b.docs) < 2:
            continue
        if b.total_chars() < MIN_CHARS or b.total_chars() > MAX_CHARS:
            continue
        bundles.append(b)
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser(description="Build HotpotQA bundles.")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    bundles = build_bundles()
    if len(bundles) < N_BUNDLES:
        print(f"  [WARN] only {len(bundles)} bundles built (target {N_BUNDLES})")
    errors: List[str] = []
    for b in bundles:
        errors.extend(validate_bundle(b, min_chars=MIN_CHARS, max_chars=MAX_CHARS))
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
