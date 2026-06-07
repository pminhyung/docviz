"""Build per-task SEF JSON for Phase-2 (Loong-100) from the parsed docs.

For each runner record (qid + attachments), reconstruct each doc's markdown from
the parsed `html_parsed` pages, build SEF (code.sef), and write the merged SEF
(union of the bundle's docs, doc-namespaced eids) to DOCVIZ_SEF_DIR/{qid}.json.

generate_viz reads this for R5 (source-ref validity). Run once before Phase-2.

  python scripts/build_phase2_sef.py \
      --runner data/queries/loong_phase2_working_runner.jsonl \
      --parsed_root outputs/v0.5_harness/loong_docai_phase2 \
      --out_dir outputs/v0.5_harness/phase2_sef
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from code.sef import build_sef_from_markdown


def _doc_markdown(parsed_json: Path) -> tuple[str, str]:
    """Return (doc_id, joined markdown) from a parsed doc json."""
    d = json.loads(parsed_json.read_text())
    doc_id = d.get("id", parsed_json.stem)
    out = (d.get("outputs") or [{}])[0]
    pages = out.get("html_parsed") or {}
    chunks: list[str] = []
    for page in sorted(pages, key=lambda k: int(k) if str(k).isdigit() else 0):
        for c in pages[page]:
            if isinstance(c, str):
                chunks.append(c)
    title = (d.get("params") or {}).get("title", "")
    return doc_id, title, "\n\n".join(chunks)


def build_for_runner(runner: Path, parsed_root: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    recs = [json.loads(l) for l in runner.read_text().splitlines() if l.strip()]
    stats = {"tasks": 0, "docs": 0, "blocks": 0, "claims": 0, "eids": 0}
    for r in recs:
        qid = r.get("qid")
        if not qid:
            continue
        merged_blocks = []
        eids: set[str] = set()
        for att in r.get("attachments", []):
            stem = Path(att.get("file_path", att.get("filename", ""))).stem
            pj = parsed_root / "loong" / f"{stem}.json"
            if not pj.exists():
                continue
            doc_id, title, md = _doc_markdown(pj)
            if not md.strip():
                continue
            sef = build_sef_from_markdown(
                {"doc_id": doc_id, "title": title, "content": md})
            # doc-namespace eids so multi-doc bundles don't collide
            for blk in sef.blocks:
                nbid = f"{doc_id}#{blk.bid}"
                eids.add(nbid)
                cus = []
                for cu in blk.claim_units:
                    ncuid = f"{doc_id}#{cu.cuid}"
                    eids.add(ncuid)
                    cus.append({"cuid": ncuid})
                if cus or blk.category in ("Picture", "Table"):
                    merged_blocks.append({"bid": nbid, "claim_units": cus})
            stats["docs"] += 1
            stats["claims"] += sum(len(b.claim_units) for b in sef.blocks)
        payload = {"qid": qid, "bundle_id": r.get("bundle_id"),
                   "blocks": merged_blocks}
        (out_dir / f"{qid}.json").write_text(json.dumps(payload, ensure_ascii=False))
        stats["tasks"] += 1
        stats["blocks"] += len(merged_blocks)
        stats["eids"] += len(eids)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=Path, required=True)
    ap.add_argument("--parsed_root", type=Path, required=True)
    ap.add_argument("--out_dir", type=Path, required=True)
    a = ap.parse_args()
    stats = build_for_runner(a.runner, a.parsed_root, a.out_dir)
    print(json.dumps(stats, indent=2))
    print(f"SEF written to {a.out_dir}")


if __name__ == "__main__":
    main()
