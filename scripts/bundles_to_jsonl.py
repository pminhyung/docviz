#!/usr/bin/env python3
"""Convert (queries + bundles) → harness batch_runner_pool JSONL input.

Each row:
  {
    "prompt": "<query text>",
    "attachments": [{"idx": 1, "file_path": "<abs path>", "filename": "..."}, ...],
    "qa_mode": "docviz",
    "qid": "<query_id>",
    "bundle_id": "<bundle_id>",
    "challenge_type": "...",
    "output_type": "...",
    "prewarm": true,
  }

Usage:
    python scripts/bundles_to_jsonl.py \\
        --queries data/queries/pilot_50.jsonl \\
        --bundles data/bundles/all.json \\
        --parsed-root outputs/v0.5_harness/docai_out \\
        --out data/queries/pilot_50_runner.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build(queries: Path, bundles: Path, parsed_root: Path, out: Path,
          qa_mode: str = "docviz") -> int:
    qs = [json.loads(l) for l in queries.read_text(encoding="utf-8").splitlines() if l.strip()]
    bs_raw = json.loads(bundles.read_text(encoding="utf-8"))
    bundle_lookup = {b["bundle_id"]: b for b in bs_raw}

    parsed_root = parsed_root.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    with out.open("w", encoding="utf-8") as fout:
        for q in qs:
            b = bundle_lookup.get(q["bundle_id"])
            if not b:
                continue
            atts = []
            for i, d in enumerate(b.get("docs") or b.get("documents") or [], 1):
                doc_id = d["doc_id"]
                rel = f"{b['source']}/{doc_id}.pdf"
                fp = str(parsed_root / rel)
                atts.append({"idx": i, "file_path": fp,
                             "filename": f"{doc_id}.pdf"})
            if not atts:
                continue
            row = {
                "prompt": q["text"],
                "attachments": atts,
                "qa_mode": qa_mode,
                "qid": q["qid"],
                "bundle_id": q["bundle_id"],
                "challenge_type": q["challenge_type"],
                "output_type": q["output_type"],
                "prewarm": True,
            }
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_written += 1
    print(f"[convert] wrote {n_written} rows → {out}")
    return n_written


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=Path, default=Path("data/queries/pilot_50.jsonl"))
    ap.add_argument("--bundles", type=Path, default=Path("data/bundles/all.json"))
    ap.add_argument("--parsed-root", type=Path,
                    default=Path("outputs/v0.5_harness/docai_out"))
    ap.add_argument("--out", type=Path,
                    default=Path("data/queries/pilot_50_runner.jsonl"))
    ap.add_argument("--qa-mode", default="docviz")
    args = ap.parse_args()
    build(args.queries, args.bundles, args.parsed_root, args.out, args.qa_mode)
