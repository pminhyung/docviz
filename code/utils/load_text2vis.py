"""Text2Vis adapter (Rahman et al., Text2Vis, EMNLP 2025 Main).

v0.3 amendment §10 Layer B-1: external held-out benchmark, 100 records,
Tier 1. Text2Vis is a table-to-visualization task: given table data
(CSV-like) plus a NL question, generate a viz that answers the question.

Adaptation for docviz (held-out eval):
  - Each Text2Vis record → 1 docviz Bundle with a single Doc whose
    content is the `Table Data` text (CSV-like) plus optional `Summary`
    context. As with Plot2Code (Layer B-3) the multi-doc assumption is
    relaxed for held-out external benchmarks; paper §5 documents this.
  - The user query is the `Question` field directly.
  - Reference outputs (Visualization Code, Chart Type, axis labels) are
    preserved in bundle metadata for downstream eval (the published
    eval compares predicted chart to reference).

Output:
  - data/prototype/bundles/text2vis.json (100 bundles)
  - data/prototype/queries/text2vis.json (100 queries)
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
N_RECORDS = 100
DATASET_ID = "mizanurr/Text2Vis"

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_OUT = REPO_ROOT / "data" / "prototype" / "bundles" / "text2vis.json"
QUERIES_OUT = REPO_ROOT / "data" / "prototype" / "queries" / "text2vis.json"


def _query_from_question(question: str, word_limit: int = 25) -> str:
    """Pass the question as the user query (Text2Vis questions are
    already viz-implying); cap to 25 words to match QG-MDV protocol."""
    words = question.strip().split()
    if len(words) > word_limit:
        return " ".join(words[:word_limit]) + "…"
    return question.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-records", type=int, default=N_RECORDS)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    BUNDLE_OUT.parent.mkdir(parents=True, exist_ok=True)
    QUERIES_OUT.parent.mkdir(parents=True, exist_ok=True)

    print(f"[text2vis] loading {DATASET_ID}…")
    ds = load_dataset(DATASET_ID, split="train")
    print(f"[text2vis] rows: {len(ds)}")

    rng = random.Random(args.seed)
    indices = list(range(len(ds)))
    rng.shuffle(indices)
    chosen = indices[: args.n_records]

    bundles: List[Bundle] = []
    queries: List[Dict] = []

    for idx, src_idx in enumerate(chosen):
        row = ds[src_idx]
        table_data = (row.get("Table Data") or "").strip()
        question = (row.get("Question") or "").strip()
        summary = (row.get("Summary") or "").strip()
        chart_type = (row.get("Chart Type") or "").strip()
        x_label = (row.get("X-Axis Label") or "").strip()
        y_label = (row.get("Y-Axis Label") or "").strip()
        ref_code = (row.get("Visualization Code") or "")[:8000]
        if not table_data or not question:
            continue

        bundle_id = f"text2vis_{idx:03d}"
        # One Doc with the table data; if summary present, include it
        doc_content = f"Data table (CSV-like):\n{table_data}"
        if summary:
            doc_content += f"\n\nReference summary:\n{summary}"

        doc = Doc(
            doc_id=f"{bundle_id}_0",
            title=f"Text2Vis table {idx}",
            content=doc_content,
            page_id=None,
        )
        b = Bundle(
            bundle_id=bundle_id,
            source="text2vis",
            docs=[doc],
            metadata={
                "language": "en",
                "text2vis_src_idx": src_idx,
                "text2vis_dataset_name": row.get("Dataset Name") or "",
                "reference_chart_type": chart_type,
                "reference_x_label": x_label,
                "reference_y_label": y_label,
                "reference_code": ref_code,
                "complexity": row.get("complexity") or "",
                "domain": row.get("domain") or "",
                "high_level_category": row.get("High-Level Category") or "",
                "low_level_category": row.get("Low-Level Category") or "",
            },
        )
        bundles.append(b)

        queries.append({
            "query_id": f"{bundle_id}_text2vis",
            "bundle_id": bundle_id,
            "source": "text2vis",
            "query_type": "external",
            "query": _query_from_question(question),
            "filter_passed": True,
        })

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

    print(f"[text2vis] wrote {len(bundles)} bundles → {BUNDLE_OUT}")
    print(f"[text2vis] wrote {len(queries)} queries → {QUERIES_OUT}")
    print(f"[text2vis] sample queries:")
    for q in queries[:5]:
        print(f"  {q['query_id']}: {q['query']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
