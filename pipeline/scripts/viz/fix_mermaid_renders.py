"""Retrofit fixer for mermaid render failures (D14 follow-up).

Finding: many failed diagram/mindmap renders are from our conservative
`sanitize_mermaid` v1 missing certain label patterns (lines starting with
`(`, labels containing `:` or `;`, etc.). v2 is now in
``reference_generator.sanitize_mermaid``; this script re-applies it to
every already-saved `_source.txt` that has no `_rendered.png`, and
retries the mermaid sidecar render.

No new LLM calls — the source text is treated as-is except for the
label-wrapping sanitization.

Usage:
    python -m scripts.viz.fix_mermaid_renders [--root data/gold|data/model_outputs]
                                              [--dry-run]

Outputs a summary to research_memory/10-steps/d14_mermaid_render_fix.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.viz.reference_generator import sanitize_mermaid
from scripts.utils.rendering import render_mermaid
from scripts.config import DATA_DIR as _DATA_DIR, RESULTS_DIR

DATA_DIR = Path(_DATA_DIR)


def find_unrendered(root: Path, viz_type: str) -> list[Path]:
    base = root / viz_type
    if not base.exists():
        return []
    out = []
    for sp in sorted(base.glob("*_source.txt")):
        doc_id = sp.name.replace("_source.txt", "")
        png = base / f"{doc_id}_rendered.png"
        if not png.exists():
            out.append(sp)
    return out


def process_one(src_path: Path, viz_type: str, dry: bool) -> dict:
    doc_id = src_path.name.replace("_source.txt", "")
    out_dir = src_path.parent
    try:
        raw = src_path.read_text(encoding="utf-8")
    except Exception as e:
        return {"doc_id": doc_id, "status": "read_error",
                "error": f"{type(e).__name__}: {e}"}

    is_mindmap = (viz_type == "mindmap")
    fixed = sanitize_mermaid(raw, is_mindmap=is_mindmap)
    changed = (fixed != raw)
    if dry:
        return {"doc_id": doc_id,
                "status": "would_update" if changed else "would_retry",
                "changed": changed}

    if changed:
        src_path.write_text(fixed, encoding="utf-8")

    diagram_type = "mindmap" if is_mindmap else "flowchart"
    r = render_mermaid(fixed, diagram_type, str(out_dir),
                       doc_id=doc_id, fmt="png")
    return {"doc_id": doc_id,
            "status": "ok" if r["success"] else "fail",
            "changed": changed,
            "error": str(r.get("error") or "")[:300]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=str, default="both",
                    help="'gold', 'model_outputs', or 'both'")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    roots = []
    if args.root in ("gold", "both"):
        roots.append(("reference", DATA_DIR / "gold"))
    if args.root in ("model_outputs", "both"):
        for m in sorted((DATA_DIR / "model_outputs").iterdir()):
            if m.is_dir():
                roots.append((m.name, m))

    grand = {"total": 0, "ok": 0, "fail": 0, "changed_ok": 0,
             "changed_fail": 0, "read_error": 0,
             "would_update": 0, "would_retry": 0}
    per_model = {}

    for name, root in roots:
        per_vt = {}
        model_total = 0
        for vt in ("diagram", "mindmap"):
            unrendered = find_unrendered(root, vt)
            if not unrendered:
                continue
            vt_stats = {"total": 0, "ok": 0, "fail": 0, "changed": 0}
            if args.dry_run:
                for sp in unrendered:
                    rec = process_one(sp, vt, True)
                    grand["total"] += 1
                    vt_stats["total"] += 1
                    model_total += 1
                    grand[rec["status"]] = grand.get(rec["status"], 0) + 1
            else:
                with ThreadPoolExecutor(max_workers=args.workers) as ex:
                    futs = [ex.submit(process_one, sp, vt, False)
                            for sp in unrendered]
                    for i, fut in enumerate(as_completed(futs), 1):
                        rec = fut.result()
                        grand["total"] += 1
                        vt_stats["total"] += 1
                        model_total += 1
                        st = rec["status"]
                        grand[st] = grand.get(st, 0) + 1
                        if rec.get("changed"):
                            vt_stats["changed"] += 1
                        if st == "ok":
                            vt_stats["ok"] += 1
                            if rec.get("changed"):
                                grand["changed_ok"] = grand.get("changed_ok", 0) + 1
                        elif st == "fail":
                            vt_stats["fail"] += 1
                            if rec.get("changed"):
                                grand["changed_fail"] = grand.get("changed_fail", 0) + 1
                        if i % 20 == 0 or i == len(unrendered):
                            print(f"  [{name}/{vt}] {i}/{len(unrendered)} "
                                  f"ok={vt_stats['ok']} fail={vt_stats['fail']}",
                                  flush=True)
            per_vt[vt] = vt_stats
        if model_total:
            per_model[name] = per_vt
            print(f"[{name}] {per_vt}")

    print("\n== grand ==")
    for k, v in sorted(grand.items()):
        if v:
            print(f"  {k}: {v}")

    out = Path(RESULTS_DIR) / "fix-reports" / "d14_mermaid_render_fix.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    content = ["# D14 mermaid render fix (2026-04-09)\n",
               "## Problem",
               "Many diagram/mindmap render failures were from our "
               "`sanitize_mermaid` v1 not wrapping labels that begin with "
               "`(` (e.g. `(a)(1) Financial Statements`) or contain `:` / "
               "`;`. Mermaid 11.x parser rejects these as invalid node "
               "syntax with `Expecting NL/EOF, got NODE_DSTART` errors.",
               "",
               "## Fix",
               "- Extended `_MERMAID_SPECIAL` to include `: ; ' .`",
               "- Mindmap already-quoted check now only exempts `[`, `\"`, "
               "backtick — not `(`, because round-brackets in a mindmap "
               "leaf are a circle-node shorthand reserved for root, not a "
               "label wrapper.",
               "- Retrofit script resanitizes already-saved `_source.txt` "
               "files (no new LLM calls) and retries `render_mermaid`.",
               "",
               "## Results per (model, viz_type)",
               ""]
    for name, vts in per_model.items():
        content.append(f"### {name}")
        for vt, s in vts.items():
            content.append(f"- {vt}: {s}")
        content.append("")
    content.append("## Grand total")
    for k, v in sorted(grand.items()):
        if v:
            content.append(f"- {k}: {v}")
    out.write_text("\n".join(content) + "\n", encoding="utf-8")
    print(f"\n[wrote] {out}")


if __name__ == "__main__":
    main()
