"""D6 — Query generator (chart / diagram / mindmap).

Real-world flow:
  - chart    → CHART_QUERY_PROMPT (qwen397b, uses chart_spec from D5)
  - diagram  → DIAGRAM_QUERY_PROMPT (qwen397b, uses diagram_subtype + reason)
  - mindmap  → fixed text from generate_mindmap_query(doc_language)

Output: data/viz/queries.jsonl — one line per (doc_id, viz_type, query, chart_spec).
QC: qc_chart_query() enforces no leaked numeric values, format indicator,
chart-type keyword. Failed chart queries are regenerated up to N_RETRIES times.

Usage:
    python -m scripts.viz.query_generator [--limit N] [--workers 8]
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
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.viz.prompts import (
    CHART_QUERY_PROMPT,
    DIAGRAM_QUERY_PROMPT,
    generate_mindmap_query,
    qc_chart_query,
)
from scripts.viz.context_builder import prepare_doc_excerpt
from scripts.utils.llm_clients import call_model
from scripts.config import DATA_DIR

CORPUS_PATH = os.path.join(DATA_DIR, "documents/corpus.jsonl")
VIZ_DIR = os.path.join(DATA_DIR, "viz")
QUERIES_PATH = os.path.join(VIZ_DIR, "queries.jsonl")
N_RETRIES = 2


def _strip_markdown_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # remove first fence line
        t = t.split("\n", 1)[1] if "\n" in t else ""
    if t.endswith("```"):
        t = t.rsplit("```", 1)[0]
    return t.strip()


def generate_chart_query(row: dict) -> dict:
    spec = row.get("chart_spec") or {}
    chart_type_name = spec.get("chart_type_name") or f"{row.get('chart_subtype','bar')} chart"
    x_field = spec.get("x_field", "") or ""
    y_field = spec.get("y_field", "") or ""
    color_field = spec.get("color_field") or "none"

    excerpt = prepare_doc_excerpt(row, max_chars=500)
    doc_language = row.get("lang", "en")

    prompt = CHART_QUERY_PROMPT.format(
        chart_type_name=chart_type_name,
        x_field=x_field,
        y_field=y_field,
        color_field=color_field,
        document_language=doc_language,
        doc_excerpt=excerpt,
    )

    last_query = ""
    last_issues: List[str] = []
    for attempt in range(N_RETRIES + 1):
        raw = call_model(
            "qwen397b",
            system_prompt="You write concise natural-language user queries exactly as instructed.",
            user_content=prompt + (
                f"\n\nPrevious attempt failed QC: {last_issues}. Fix those issues."
                if attempt > 0 else ""
            ),
            temperature=0.3,
        )
        query = _strip_markdown_fences(raw)
        # one-line query: take first paragraph
        query = query.split("\n\n")[0].strip()
        qc = qc_chart_query(query, {"chart_type_name": chart_type_name,
                                     "x_field": x_field, "y_field": y_field})
        last_query = query
        last_issues = qc["issues"]
        if qc["pass"]:
            break
    return {"query": last_query, "qc_pass": qc["pass"], "qc_issues": last_issues}


def generate_diagram_query(row: dict) -> dict:
    diagram_subtype = row.get("diagram_subtype", "flowchart")
    diagram_reason = row.get("diagram_reason", "")
    excerpt = prepare_doc_excerpt(row, max_chars=1000)
    doc_language = row.get("lang", "en")

    prompt = DIAGRAM_QUERY_PROMPT.format(
        diagram_subtype=diagram_subtype,
        document_language=doc_language,
        doc_excerpt=excerpt,
        diagram_reason=diagram_reason,
    )
    raw = call_model(
        "qwen397b",
        system_prompt="You write concise natural-language user queries exactly as instructed.",
        user_content=prompt,
        temperature=0.3,
    )
    query = _strip_markdown_fences(raw).split("\n\n")[0].strip()
    return {"query": query, "qc_pass": True, "qc_issues": []}


def build_mindmap_query(row: dict) -> dict:
    q = generate_mindmap_query(row.get("lang", "en"))
    return {"query": q, "qc_pass": True, "qc_issues": []}


def process_doc(row: dict) -> dict:
    doc_id = row["doc_id"]
    try:
        chart = generate_chart_query(row)
        diagram = generate_diagram_query(row)
        mindmap = build_mindmap_query(row)
        return {"doc_id": doc_id, "ok": True,
                "chart": chart, "diagram": diagram, "mindmap": mindmap}
    except Exception as e:
        return {"doc_id": doc_id, "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[:1500]}


def load_existing_queries() -> Dict[str, Dict[str, dict]]:
    """Resume support: map doc_id → {viz_type: row}"""
    if not os.path.exists(QUERIES_PATH):
        return {}
    out = {}
    with open(QUERIES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                out.setdefault(r["doc_id"], {})[r["viz_type"]] = r
            except Exception:
                continue
    return out


def append_queries(rows: List[dict]):
    os.makedirs(VIZ_DIR, exist_ok=True)
    with open(QUERIES_PATH, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--force", action="store_true", help="regen even if queries exist")
    args = ap.parse_args()

    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
    print(f"[corpus] {len(rows)} docs")

    existing = load_existing_queries() if not args.force else {}
    pending = [r for r in rows
               if not (existing.get(r["doc_id"], {}).get("chart")
                       and existing.get(r["doc_id"], {}).get("diagram")
                       and existing.get(r["doc_id"], {}).get("mindmap"))]
    print(f"[existing] {sum(len(v) for v in existing.values())} query rows "
          f"({len(existing)} docs)  pending docs: {len(pending)}")
    if not pending:
        print("nothing to do")
        return

    t0 = time.time()
    done = 0
    ok_count = 0
    fail_count = 0
    qc_fail_chart = 0
    to_append = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_doc, r): r for r in pending}
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            row_src = futs[fut]
            if r["ok"]:
                ok_count += 1
                if not r["chart"]["qc_pass"]:
                    qc_fail_chart += 1
                for viz_type, payload in [("chart", r["chart"]),
                                           ("diagram", r["diagram"]),
                                           ("mindmap", r["mindmap"])]:
                    to_append.append({
                        "doc_id": r["doc_id"],
                        "viz_type": viz_type,
                        "query": payload["query"],
                        "qc_pass": payload["qc_pass"],
                        "qc_issues": payload["qc_issues"],
                        "chart_subtype": row_src.get("chart_subtype"),
                        "diagram_subtype": row_src.get("diagram_subtype"),
                        "chart_spec": row_src.get("chart_spec") if viz_type == "chart" else None,
                        "lang": row_src.get("lang", "en"),
                        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    })
            else:
                fail_count += 1
                print(f"[fail] {r['doc_id']}: {r.get('error','')}")
            if done % 25 == 0 or done == len(pending):
                elapsed = time.time() - t0
                print(f"  [{done}/{len(pending)}]  ok={ok_count}  fail={fail_count}  "
                      f"qc_fail_chart={qc_fail_chart}  elapsed={elapsed:.0f}s")
                # flush periodically
                if to_append:
                    append_queries(to_append)
                    to_append = []

    if to_append:
        append_queries(to_append)

    print(f"\n[done] ok={ok_count} fail={fail_count} qc_fail_chart={qc_fail_chart}")
    print(f"       queries → {QUERIES_PATH}")


if __name__ == "__main__":
    main()
