#!/usr/bin/env python3
"""Convert docviz bundles → harness ir-shim pdf_index format (Mode A).

For each doc in each bundle, emit a per-doc parsed JSON envelope:
  {"id": doc_id, "outputs": [{"file_name": ..., "html_parsed": {"1": [chunks]}}]}

Plus a file_mapping.json indexing all docs.

Usage:
    python scripts/bundles_to_pdf_index.py \\
        --bundles data/bundles/all.json \\
        --queries data/queries/pilot_50.jsonl \\
        --out outputs/v0.5_harness/docai_out
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CHUNK_TARGET = 1500


def _chunk(text: str, target: int = CHUNK_TARGET) -> list[str]:
    text = text.strip()
    if len(text) <= target:
        return [text]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, buf = [], ""
    for p in paragraphs:
        if not buf:
            buf = p
        elif len(buf) + 2 + len(p) <= target * 1.4:
            buf += "\n\n" + p
        else:
            out.append(buf); buf = p
    if buf: out.append(buf)
    return out or [text]


def build(bundles_path: Path, queries_path: Path | None, out_root: Path) -> dict:
    out_root = out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    bundles = json.loads(bundles_path.read_text(encoding="utf-8"))

    # Filter to pilot bundles if queries provided
    needed_bundle_ids = None
    if queries_path and queries_path.exists():
        qs = [json.loads(l) for l in queries_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        needed_bundle_ids = {q["bundle_id"] for q in qs}
        bundles = [b for b in bundles if b["bundle_id"] in needed_bundle_ids]
        print(f"[convert] filtered to {len(bundles)} pilot bundles from queries")

    mapping = {}
    n_docs = 0
    for b in bundles:
        bid = b["bundle_id"]; source = b["source"]
        src_dir = out_root / source
        src_dir.mkdir(parents=True, exist_ok=True)
        for doc in (b.get("docs") or b.get("documents") or []):
            doc_id = doc["doc_id"]
            content = (doc.get("content") or doc.get("text") or "").strip()
            if not content:
                continue
            chunks = _chunk(content)
            rel = f"{source}/{doc_id}.pdf"
            abs_pdf = str(out_root / rel)
            parsed = {
                "id": doc_id,
                "outputs": [{"file_name": f"{doc_id}.pdf",
                             "html_parsed": {"1": chunks},
                             "list_parsed": {}, "version": "docviz-1.0"}],
                "params": {"source": source, "bundle_id": bid,
                           "title": doc.get("title", doc_id)},
            }
            (src_dir / f"{doc_id}.json").write_text(
                json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
            mapping[doc_id] = {"absolute_path": abs_pdf, "relative_path": rel,
                               "original_filename": f"{doc_id}.pdf"}
            n_docs += 1

    (out_root / "file_mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[convert] wrote {n_docs} parsed JSON envelopes + file_mapping.json")
    print(f"[convert] export EXAONE_PARSED_ROOT={out_root}")
    return {"n_docs": n_docs, "n_bundles": len(bundles)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", type=Path, default=Path("data/bundles/all.json"))
    ap.add_argument("--queries", type=Path,
                    default=Path("data/queries/pilot_50.jsonl"),
                    help="Filter bundles to only those referenced by these queries.")
    ap.add_argument("--out", type=Path,
                    default=Path("outputs/v0.5_harness/docai_out"))
    args = ap.parse_args()
    build(args.bundles, args.queries, args.out)
