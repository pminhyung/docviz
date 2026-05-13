"""Plot2Code adapter (Wu et al., Plot2Code, 2024).

v0.3 amendment §10 Layer B-3: external held-out benchmark, 50 records,
optional Tier 1. Plot2Code is a single-instruction plot-generation task
where the user gives a natural-language description and a model must
emit Python code that renders to a matching image.

Adaptation for docviz (held-out eval):
  - Each Plot2Code record → 1 docviz Bundle with a single Doc whose
    content is the `instruction` text. The pipeline's "multi-doc"
    assumption is relaxed at Layer B (paper §5 documents the
    held-out adaptation).
  - The user query is the instruction's first sentence (capped to
    25 words) so it fits our generator's query-shape expectations,
    while the full instruction lives in the bundle as the source doc.
  - Target image (`image` field) is cached for downstream image-axis
    evaluation (CLIPScore or A5 image judge when budget permits).

Output:
  - data/prototype/bundles/plot2code.json (50 bundles)
  - data/prototype/queries/plot2code.json (50 queries)
  - data/prototype/sources/raw/plot2code/<id>.png (target images)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("HF_HOME", "/ex_disk2/mhpark/poc/.cache/huggingface")

from datasets import load_dataset

from code.pipelines.base import Bundle, Doc


SEED = 42
N_RECORDS = 50
DATASET_ID = "TencentARC/Plot2Code"

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_OUT = REPO_ROOT / "data" / "prototype" / "bundles" / "plot2code.json"
QUERIES_OUT = REPO_ROOT / "data" / "prototype" / "queries" / "plot2code.json"
TARGET_IMG_DIR = REPO_ROOT / "data" / "prototype" / "sources" / "raw" / "plot2code"


_FIRST_SENTENCE_RE = re.compile(r"(.+?[\.!?])(?:\s|$)")


def _query_from_instruction(instruction: str, word_limit: int = 25) -> str:
    """Use the first sentence of the instruction (capped to N words) as
    the user query."""
    m = _FIRST_SENTENCE_RE.match(instruction.strip())
    first = m.group(1).strip() if m else instruction.split("\n", 1)[0].strip()
    words = first.split()
    if len(words) > word_limit:
        first = " ".join(words[:word_limit]) + "…"
    return first


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-records", type=int, default=N_RECORDS)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    TARGET_IMG_DIR.mkdir(parents=True, exist_ok=True)
    BUNDLE_OUT.parent.mkdir(parents=True, exist_ok=True)
    QUERIES_OUT.parent.mkdir(parents=True, exist_ok=True)

    print(f"[plot2code] loading {DATASET_ID}…")
    ds = load_dataset(DATASET_ID, split="test")
    print(f"[plot2code] rows: {len(ds)}")

    rng = random.Random(args.seed)
    indices = list(range(len(ds)))
    rng.shuffle(indices)
    chosen = indices[: args.n_records]

    bundles: List[Bundle] = []
    queries: List[Dict] = []

    for idx, src_idx in enumerate(chosen):
        row = ds[src_idx]
        instruction = (row.get("instruction") or "").strip()
        image = row.get("image")
        if not instruction:
            print(f"  [skip] row {src_idx} has no instruction")
            continue

        bundle_id = f"plot2code_{idx:02d}"
        # Save target image
        img_path = TARGET_IMG_DIR / f"{bundle_id}.png"
        if image is not None:
            try:
                image.save(str(img_path))
            except Exception as e:
                print(f"  [warn] {bundle_id} image save failed: {e}")

        doc = Doc(
            doc_id=f"{bundle_id}_0",
            title=f"Plot2Code instruction {idx}",
            content=instruction,
            page_id=None,
        )
        b = Bundle(
            bundle_id=bundle_id,
            source="plot2code",
            docs=[doc],
            metadata={
                "language": "en",
                "plot2code_src_idx": src_idx,
                "plot2code_url": row.get("url") or "",
                "reference_code": (row.get("code") or "")[:8000],
                "target_image_path": str(img_path) if image is not None else "",
            },
        )
        bundles.append(b)

        query_text = _query_from_instruction(instruction)
        queries.append({
            "query_id": f"{bundle_id}_plot2code",
            "bundle_id": bundle_id,
            "source": "plot2code",
            "query_type": "external",  # off-enum; not used by 5-type balance
            "query": query_text,
            "filter_passed": True,
        })

    # Write bundles (use raw json dump to keep nested metadata; bundle_io
    # is for the 4-source schema and may not preserve plot2code metadata)
    import json as _j
    out_bundles = [{
        "bundle_id": b.bundle_id,
        "source": b.source,
        "docs": [{"doc_id": d.doc_id, "title": d.title, "content": d.content,
                  "page_id": d.page_id} for d in b.docs],
        "metadata": b.metadata,
    } for b in bundles]
    BUNDLE_OUT.write_text(_j.dumps(out_bundles, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    QUERIES_OUT.write_text(_j.dumps(queries, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    print(f"[plot2code] wrote {len(bundles)} bundles → {BUNDLE_OUT}")
    print(f"[plot2code] wrote {len(queries)} queries → {QUERIES_OUT}")
    print(f"[plot2code] target images → {TARGET_IMG_DIR}")
    print(f"[plot2code] sample queries:")
    for q in queries[:5]:
        print(f"  {q['query_id']}: {q['query']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
