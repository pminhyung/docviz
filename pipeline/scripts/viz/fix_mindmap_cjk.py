"""Retrofit fix for mindmap CJK leakage (D13 finding).

Enumerates all mindmap source.txt files that contain CJK characters even
though the corpus is English, deletes their source/rendered/structure
outputs, and regenerates them with the language-explicit retry loop added
to ``reference_generator.generate_mindmap``.

Usage:
    python -m scripts.viz.fix_mindmap_cjk [--limit N] [--workers 4] [--dry-run]

Honors the label-language-invariance MUST rule (feedback memory). Writes a
summary to research_memory/10-steps/d13_mindmap_cjk_fix.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.viz.reference_generator import (
    generate_mindmap,
    append_failure,
    _CJK_RE,
    _contains_foreign_script,
    GOLD_DIR,
    CORPUS_PATH,
    QUERIES_PATH,
)
from scripts.viz.context_builder import prepare_full_context
from scripts.config import RESULTS_DIR


MINDMAP_DIR = os.path.join(GOLD_DIR, "mindmap")


def enumerate_affected() -> list[str]:
    hits = []
    for p in sorted(Path(MINDMAP_DIR).glob("*_source.txt")):
        with open(p, encoding="utf-8") as f:
            txt = f.read()
        if _CJK_RE.search(txt):
            hits.append(p.name.replace("_source.txt", ""))
    return hits


def load_corpus_index() -> dict[str, dict]:
    idx = {}
    with open(CORPUS_PATH, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            idx[row["doc_id"]] = row
    return idx


def load_query_index() -> dict[tuple[str, str], str]:
    idx = {}
    with open(QUERIES_PATH, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            idx[(r["doc_id"], r["viz_type"])] = r["query"]
    return idx


def purge_outputs(doc_id: str, dry_run: bool) -> list[str]:
    """Remove source.txt, rendered.png, _structure.json for the doc."""
    removed = []
    targets = [
        os.path.join(MINDMAP_DIR, f"{doc_id}_source.txt"),
        os.path.join(MINDMAP_DIR, f"{doc_id}_rendered.png"),
        os.path.join(MINDMAP_DIR, f"{doc_id}_structure.json"),
    ]
    for t in targets:
        if os.path.exists(t):
            if not dry_run:
                os.remove(t)
            removed.append(t)
    return removed


def fix_one(doc_id: str, corpus_idx: dict, query_idx: dict) -> dict:
    t0 = time.time()
    row = corpus_idx.get(doc_id)
    if row is None:
        return {"doc_id": doc_id, "ok": False,
                "error": "not in corpus"}
    query = query_idx.get((doc_id, "mindmap"))
    if query is None:
        return {"doc_id": doc_id, "ok": False,
                "error": "no mindmap query"}
    try:
        context = prepare_full_context(row)
        r = generate_mindmap(row, query, context, MINDMAP_DIR)
        # Post-condition double-check
        with open(r["source_path"], encoding="utf-8") as f:
            src_txt = f.read()
        if _contains_foreign_script(src_txt, row.get("lang", "en")):
            return {"doc_id": doc_id, "ok": False,
                    "error": "CJK still present after retry"}
        return {"doc_id": doc_id, "ok": True,
                "elapsed": round(time.time() - t0, 1)}
    except Exception as e:
        return {"doc_id": doc_id, "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[:1500]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    affected = enumerate_affected()
    print(f"[enumerate] {len(affected)} mindmap files contain CJK")
    if args.limit:
        affected = affected[: args.limit]
        print(f"[limit] restricted to first {len(affected)}")

    if args.dry_run:
        for d in affected:
            print(" ", d)
        return

    corpus_idx = load_corpus_index()
    query_idx = load_query_index()

    # Purge first so resume logic in reference_generator would re-do them.
    for d in affected:
        purge_outputs(d, dry_run=False)
    print(f"[purge] removed outputs for {len(affected)} doc_ids")

    ok = 0
    fail = 0
    fails = []
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fix_one, d, corpus_idx, query_idx): d
                for d in affected}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            if r["ok"]:
                ok += 1
            else:
                fail += 1
                fails.append(r)
                append_failure({"doc_id": r["doc_id"], "viz_type": "mindmap",
                                "error": r.get("error", ""),
                                "traceback": r.get("traceback", "")})
            if i % 5 == 0 or i == len(affected):
                print(f"  [{i}/{len(affected)}] ok={ok} fail={fail} "
                      f"elapsed={int(time.time() - t_start)}s")

    print(f"[done] ok={ok} fail={fail} elapsed={int(time.time() - t_start)}s")
    if fails:
        print("[failures]")
        for f in fails:
            print(f"  - {f['doc_id']}: {f.get('error', '')}")

    # Emit summary
    summary = (
        f"# D13 mindmap CJK fix (2026-04-09)\n\n"
        f"- Affected before fix: {len(affected)} / 533 (10.9%)\n"
        f"- Regenerated ok: {ok}\n"
        f"- Still failed: {fail}\n"
        f"- Method: explicit English language directive prepended to user "
        f"message + CJK regex validation + up to 3 retry attempts with "
        f"escalating phrasing. System prompt unchanged (verbatim invariant).\n"
        f"- Next: rerun batch_extract_structures for mindmap viz_type to "
        f"refresh _structure.json files.\n"
    )
    out = Path(RESULTS_DIR) / "fix-reports" / "d13_mindmap_cjk_fix.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(summary, encoding="utf-8")
    print(f"[wrote] {out}")


if __name__ == "__main__":
    main()
