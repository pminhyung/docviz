"""Build a SEF-rendered parsed root for the B6-full arm — v0.4.3 −SEF lever.

Produces a parallel EXAONE_PARSED_ROOT whose parsed JSON content is the SEF
*structured* representation (claim_units + eids + viz-affordance) instead of raw
markdown. The B6-full arm points EXAONE_PARSED_ROOT here; the −SEF arm and all
baselines keep the original markdown root. Same file_mapping.json (PDF paths
unchanged) so the docqa pdf_index resolves attachments identically.

  python scripts/build_phase2_sef_root.py \
      --markdown_root outputs/v0.5_harness/loong_docai_phase2 \
      --out_root outputs/v0.5_harness/loong_docai_phase2_sef
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from code.sef import build_sef_from_markdown
from code.sef.render import sef_to_parsed_doc


def _markdown_from_parsed(parsed: dict) -> tuple[str, str, str]:
    doc_id = parsed.get("id", "doc")
    out = (parsed.get("outputs") or [{}])[0]
    pages = out.get("html_parsed") or {}
    chunks: list[str] = []
    for page in sorted(pages, key=lambda k: int(k) if str(k).isdigit() else 0):
        for c in pages[page]:
            if isinstance(c, str):
                chunks.append(c)
    title = (parsed.get("params") or {}).get("title", "")
    return doc_id, title, "\n\n".join(chunks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown_root", type=Path, required=True)
    ap.add_argument("--out_root", type=Path, required=True)
    a = ap.parse_args()

    mapping = json.loads((a.markdown_root / "file_mapping.json").read_text())
    (a.out_root).mkdir(parents=True, exist_ok=True)
    # file_mapping unchanged — PDF paths and stems stay valid.
    shutil.copy(a.markdown_root / "file_mapping.json",
                a.out_root / "file_mapping.json")

    stats = {"docs": 0, "blocks": 0, "claims": 0, "empty": 0}
    for stem, meta in mapping.items():
        rel = Path(meta.get("relative_path", f"loong/{stem}.pdf"))
        src = a.markdown_root / rel.parent / f"{stem}.json"
        if not src.exists():
            continue
        parsed = json.loads(src.read_text())
        doc_id, title, md = _markdown_from_parsed(parsed)
        domain = (parsed.get("params") or {}).get("source", "")
        sef = build_sef_from_markdown(
            {"doc_id": doc_id, "title": title, "content": md}, domain=domain)
        out_doc = sef_to_parsed_doc(sef, filename=f"{stem}.pdf")
        dst = a.out_root / rel.parent / f"{stem}.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(out_doc, ensure_ascii=False))
        nclaims = sum(len(b.claim_units) for b in sef.blocks)
        stats["docs"] += 1
        stats["blocks"] += len(sef.blocks)
        stats["claims"] += nclaims
        if nclaims == 0:
            stats["empty"] += 1

    print(json.dumps(stats, indent=2))
    print(f"SEF parsed root → {a.out_root}")


if __name__ == "__main__":
    main()
