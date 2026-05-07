"""D14 — Comparison model inference.

Runs the same query + full-document context through a specified comparison
model and writes `data/model_outputs/{model_id}/{viz_type}/{doc_id}_source.txt
+ _rendered.png`.  Reuses the identical context-builder, prompts, and parsing
helpers as reference_generator.py so the context-identity invariant
(Guide 2 §4.3) holds across D5/D6/D8/D14.

Precondition: the model's vLLM server(s) must already be running on the
ports declared in scripts.config.MODEL_CONFIGS[model_id]['ports'].  Use the
`inference-pipeline` skill to start/stop them; this script is the per-model
inference payload only.

Usage:
    python -m scripts.viz.model_inference --model qwen9b [--limit N]
                                           [--workers 8] [--viz chart,diagram,mindmap]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.config import DATA_DIR, MODEL_CONFIGS
from scripts.viz.prompts import (
    SYSTEM_PROMPT_CHART, SYSTEM_PROMPT_DIAGRAM, SYSTEM_PROMPT_MINDMAP,
)
from scripts.viz.context_builder import prepare_full_context
from scripts.viz.reference_generator import (
    extract_vegalite, extract_mermaid, sanitize_mermaid,
)
from scripts.utils.llm_clients import call_model
from scripts.utils.rendering import render_vegalite, render_mermaid

CORPUS_PATH = os.path.join(DATA_DIR, "documents", "corpus.jsonl")
QUERIES_PATH = os.path.join(DATA_DIR, "viz", "queries.jsonl")
MODEL_OUT_BASE = os.path.join(DATA_DIR, "model_outputs")

SYSTEM_PROMPTS = {
    "chart": SYSTEM_PROMPT_CHART,
    "diagram": SYSTEM_PROMPT_DIAGRAM,
    "mindmap": SYSTEM_PROMPT_MINDMAP,
}


def _already_done(out_dir: str, doc_id: str) -> bool:
    src = os.path.join(out_dir, f"{doc_id}_source.txt")
    png = os.path.join(out_dir, f"{doc_id}_rendered.png")
    return os.path.exists(src) and os.path.exists(png)


def generate_chart(model_id: str, row: dict, query: str, context: str,
                   out_dir: str) -> dict:
    user = f"{query}\n\nDocument:\n{context}"
    raw = call_model(model_id, SYSTEM_PROMPT_CHART, user,
                     temperature=0.2)
    spec = extract_vegalite(raw)
    src = os.path.join(out_dir, f"{row['doc_id']}_source.txt")
    with open(src, "w", encoding="utf-8") as f:
        f.write(json.dumps(spec, ensure_ascii=False, indent=2))
    r = render_vegalite(spec, out_dir, doc_id=row["doc_id"], fmt="png")
    if not r["success"]:
        raise RuntimeError(f"render_vegalite failed: {r['error']}")
    return {"ok": True}


def generate_diagram(model_id: str, row: dict, query: str, context: str,
                     out_dir: str, diagram_subtype: str) -> dict:
    user = f"{query}\n\nDocument:\n{context}"
    raw = call_model(model_id, SYSTEM_PROMPT_DIAGRAM, user,
                     temperature=0.2)
    mmd = extract_mermaid(raw, expect_mindmap=False)
    mmd = sanitize_mermaid(mmd, is_mindmap=False)
    src = os.path.join(out_dir, f"{row['doc_id']}_source.txt")
    with open(src, "w", encoding="utf-8") as f:
        f.write(mmd)
    r = render_mermaid(mmd, diagram_subtype, out_dir, doc_id=row["doc_id"], fmt="png")
    if not r["success"]:
        raise RuntimeError(f"render_mermaid failed: {r['error']}")
    return {"ok": True}


def generate_mindmap(model_id: str, row: dict, query: str, context: str,
                     out_dir: str) -> dict:
    user = f"{query}\n\nDocument:\n{context}"
    raw = call_model(model_id, SYSTEM_PROMPT_MINDMAP, user,
                     temperature=0.2)
    mmd = extract_mermaid(raw, expect_mindmap=True)
    mmd = sanitize_mermaid(mmd, is_mindmap=True)
    src = os.path.join(out_dir, f"{row['doc_id']}_source.txt")
    with open(src, "w", encoding="utf-8") as f:
        f.write(mmd)
    r = render_mermaid(mmd, "mindmap", out_dir, doc_id=row["doc_id"], fmt="png")
    if not r["success"]:
        raise RuntimeError(f"render_mermaid failed: {r['error']}")
    return {"ok": True}


def process_one(model_id: str, row: dict, viz_type: str, query: str,
                diagram_subtype: str) -> dict:
    doc_id = row["doc_id"]
    out_dir = os.path.join(MODEL_OUT_BASE, model_id, viz_type)
    os.makedirs(out_dir, exist_ok=True)
    if _already_done(out_dir, doc_id):
        return {"doc_id": doc_id, "viz_type": viz_type, "ok": True, "skipped": True}
    try:
        context = prepare_full_context(row)
        if viz_type == "chart":
            generate_chart(model_id, row, query, context, out_dir)
        elif viz_type == "diagram":
            generate_diagram(model_id, row, query, context, out_dir, diagram_subtype)
        else:
            generate_mindmap(model_id, row, query, context, out_dir)
        return {"doc_id": doc_id, "viz_type": viz_type, "ok": True}
    except Exception as e:
        tb = traceback.format_exc()[:2000]
        return {"doc_id": doc_id, "viz_type": viz_type, "ok": False,
                "error": f"{type(e).__name__}: {e}", "traceback": tb}


def append_failure(model_id: str, rec: dict):
    path = os.path.join(MODEL_OUT_BASE, model_id, "failures.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({k: rec.get(k) for k in
                            ("doc_id", "viz_type", "error", "traceback")},
                           ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(MODEL_CONFIGS.keys()))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--viz", type=str, default="chart,diagram,mindmap")
    args = ap.parse_args()

    viz_types = [v.strip() for v in args.viz.split(",") if v.strip()]
    for v in viz_types:
        if v not in SYSTEM_PROMPTS:
            raise SystemExit(f"unknown viz_type: {v}")

    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
    rows_by_id = {r["doc_id"]: r for r in rows}

    queries = {}
    with open(QUERIES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            q = json.loads(line)
            if q["doc_id"] in rows_by_id and q["viz_type"] in viz_types:
                queries[(q["doc_id"], q["viz_type"])] = q

    tasks = []
    for r in rows:
        for v in viz_types:
            if (r["doc_id"], v) not in queries:
                continue
            tasks.append((r, v, queries[(r["doc_id"], v)]["query"]))

    print(f"[{args.model}] tasks={len(tasks)} ({len(rows)} docs × {len(viz_types)} viz)")
    t0 = time.time()
    done = ok = fail = skip = 0
    fail_by_viz: dict = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {}
        for row, viz_type, query in tasks:
            diagram_subtype = row.get("diagram_subtype", "flowchart")
            futs[ex.submit(process_one, args.model, row, viz_type,
                           query, diagram_subtype)] = (row["doc_id"], viz_type)
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            if r.get("skipped"):
                skip += 1
                ok += 1
            elif r["ok"]:
                ok += 1
            else:
                fail += 1
                fail_by_viz[r["viz_type"]] = fail_by_viz.get(r["viz_type"], 0) + 1
                append_failure(args.model, r)
            if done % 50 == 0 or done == len(tasks):
                elapsed = time.time() - t0
                print(f"  [{done}/{len(tasks)}]  ok={ok} (skip={skip})  "
                      f"fail={fail}  by_viz={fail_by_viz}  "
                      f"elapsed={elapsed:.0f}s  rate={done/max(elapsed,1e-6):.2f}/s")

    elapsed = time.time() - t0
    print(f"[{args.model}] DONE ok={ok} fail={fail} skip={skip} in {elapsed:.0f}s")


if __name__ == "__main__":
    main()
