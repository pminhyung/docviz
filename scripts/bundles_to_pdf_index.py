#!/usr/bin/env python3
"""Convert docviz bundles → harness ir-shim pdf_index Mode A format.

Reads:  data/prototype/bundles/all.json (list of bundles, each with `docs`)
Writes: <out_root>/file_mapping.json + <out_root>/<source>/<doc_id>.json

Each docviz "doc" becomes a harness "PdfEntry":
  - stem            = doc_id (e.g., "hotpot_00_0")
  - relative_path   = "<source>/<doc_id>.txt" (fake, no actual PDF exists)
  - absolute_path   = "<abs_out_root>/<source>/<doc_id>.txt"
  - original_filename = "<doc_id>.txt"

The parsed-JSON envelope at <out_root>/<source>/<doc_id>.json:
  {"id": <doc_id>, "outputs": [{"file_name": ..., "html_parsed": {"1": [chunks...]},
                                "list_parsed": {}, "version": "docviz-1.0"}],
   "params": {"source": <source>, "bundle_id": <bundle_id>, "title": <title>}}

Usage:
    python scripts/bundles_to_pdf_index.py \\
        --bundles data/prototype/bundles/all.json \\
        --out outputs/v0.5_harness/docai_out
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CHUNK_TARGET_CHARS = 1500  # rough per-chunk size for search granularity


def _chunk(text: str, target: int = CHUNK_TARGET_CHARS) -> list[str]:
    """Split text into chunks ~target chars, breaking on paragraph boundaries.

    Falls back to single-chunk if text is short.
    """
    text = text.strip()
    if len(text) <= target:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if not buf:
            buf = p
        elif len(buf) + 2 + len(p) <= target * 1.4:
            buf += "\n\n" + p
        else:
            chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks or [text]


def build(bundles_path: Path, out_root: Path) -> None:
    out_root = out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    bundles = json.loads(bundles_path.read_text(encoding="utf-8"))
    print(f"[convert] {len(bundles)} bundles from {bundles_path}")

    file_mapping: dict[str, dict] = {}
    n_docs = 0
    n_chunks_total = 0

    for b in bundles:
        bundle_id = b["bundle_id"]
        source = b["source"]
        docs = b.get("docs") or b.get("documents") or []

        src_dir = out_root / source
        src_dir.mkdir(parents=True, exist_ok=True)

        for doc in docs:
            doc_id = doc["doc_id"]
            title = doc.get("title", doc_id)
            content = doc.get("content") or doc.get("text") or ""
            if not content.strip():
                continue

            chunks = _chunk(content)
            n_chunks_total += len(chunks)

            rel_pdf = f"{source}/{doc_id}.txt"
            abs_pdf = str(out_root / rel_pdf)

            parsed = {
                "id": doc_id,
                "outputs": [
                    {
                        "file_name": f"{doc_id}.txt",
                        "html_parsed": {"1": chunks},
                        "list_parsed": {},
                        "version": "docviz-1.0",
                    }
                ],
                "params": {
                    "source": source,
                    "bundle_id": bundle_id,
                    "title": title,
                },
            }
            parsed_path = src_dir / f"{doc_id}.json"
            parsed_path.write_text(
                json.dumps(parsed, ensure_ascii=False), encoding="utf-8"
            )

            file_mapping[doc_id] = {
                "absolute_path": abs_pdf,
                "relative_path": rel_pdf,
                "original_filename": f"{doc_id}.txt",
            }
            n_docs += 1

    mapping_path = out_root / "file_mapping.json"
    mapping_path.write_text(
        json.dumps(file_mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[convert] wrote {n_docs} docs ({n_chunks_total} chunks total)")
    print(f"[convert] mapping → {mapping_path}")
    print(f"[convert] export EXAONE_PARSED_ROOT={out_root}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    build(args.bundles, args.out)
