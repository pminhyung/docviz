"""Optimized query_type_gen agent (user's Method A, refined).

Refinements over the naive enumeration:
  1. DATASET-CONDITIONED POOL. Each source benchmark gets only the viz pool it
     can genuinely support for MULTI-DOC visualization, so the model never wastes
     effort proposing types the dataset can't ground cross-document. The Loong
     paper split is set to DIAGRAM-only — empirically (viztype_explore) its only
     genuine cross-document visualizable structure is relational (citation /
     adoption / shared-concept graphs); its chart material is single-document.
  2. AGGRESSIVE DISCOVERY. The model is told to exhaustively surface every
     groundable type and 1-3 queries each — maximize coverage.
  3. HARD MULTI-DOC CHALLENGE CONSTRAINT. Every query MUST require synthesizing /
     comparing / linking evidence across >= 2 DISTINCT documents. A query
     answerable from a single document or page is INVALID and must be excluded;
     each kept query states its cross-document linkage (docs + bridge). A type
     groundable only within one document is marked infeasible-for-multidoc.

Strict JSON output → parsed. Consumes cached Stage-1 compressed facts.

Usage:
    python -m code.querygen.query_type_gen \
        --bundles data/bundles/loong_phase1.json \
        --compressed data/queries/loong_phase1_compressed.json \
        --out data/queries/loong_phase1_typed.jsonl --hosts <8> [--limit N]
"""
from __future__ import annotations
import argparse, json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from exaone.sft_gen.docviz.generate_queries import HostPool, _call_llm, _extract_json, DEFAULT_QWEN_HOSTS

REPO = Path(__file__).resolve().parents[2]

CHART_POOL = {
    "chartjs_bar": "single-series numeric bars",
    "chartjs_grouped_bar": "multi-series numeric comparison bars",
    "chartjs_line": "numeric trend over an ordered axis",
    "chartjs_pie": "part-of-whole proportions",
    "chartjs_scatter": "two-variable numeric correlation",
}
DIAGRAM_POOL = {
    "mermaid_flowchart": "nodes + directed edges (process / relations / causality)",
    "mermaid_timeline": "dated events in order",
    "mermaid_mindmap": "hierarchical tree from a root",
    "mermaid_sequenceDiagram": "ordered messages between actors",
    "mermaid_classDiagram": "entities with attributes + relations",
}

# Per-source pool selection (research judgement; loong=diagram is evidence-based).
SOURCE_POOL = {
    "loong": "diagram",          # cross-doc signal is relational; charts are single-doc only
    "finmmdocr": "both",         # financial reports: numeric tables + processes
    "finauditing": "chart",      # XBRL structured numbers
    "tempo": "chart",            # multi-domain time series
    "visdombench": "both",       # SciGraphQA + PaperTab/FeTaTab tables
    "dochopqa": "both",
    "multihoprag": "diagram",    # news entities / events
}


def _pool_for(source: str, override: str | None) -> dict:
    kind = override or SOURCE_POOL.get(source, "both")
    if kind == "chart":
        return dict(CHART_POOL)
    if kind == "diagram":
        return dict(DIAGRAM_POOL)
    return {**CHART_POOL, **DIAGRAM_POOL}


PROMPT = """You are query_type_gen, authoring a MULTI-DOCUMENT visualization benchmark. You will exhaustively discover every visualization this document set can genuinely support — under a strict multi-document constraint.

## Visualization pool (use ONLY these types)
{pool}

## Document set (compressed key facts, per document — [1],[2],... are distinct documents)
{facts}

## Rules
- AGGRESSIVE DISCOVERY: surface EVERY pool type whose material genuinely exists, and 1-3 distinct queries per feasible type. Maximize coverage and creativity.
- HARD MULTI-DOCUMENT CONSTRAINT (non-negotiable): every query MUST require integrating evidence from >= 2 DISTINCT documents — comparing, linking, synthesizing, or reconciling across them. A query answerable from ONE document (or a single page/section) is INVALID; DO NOT output it. Assembling scattered evidence into the final chart/diagram is a downstream pipeline's job — you only ensure the raw material for a genuinely cross-document visualization is present.
- GROUNDED: the entities / relations / values the visualization needs must actually appear in the facts. For a chart, the numeric VALUES must exist across the documents being compared.
- For each kept query, state `docs_used` (>=2 indices) and `cross_doc_link` (the bridge entity / shared dimension / relation that ties the documents).
- If a pool type can only be grounded within a single document here, put it in `infeasible` with reason "single-doc only" (or the missing material).

## Output STRICT JSON only
```json
{{"feasible": [
   {{"viz_type": "<pool key>",
     "queries": [
       {{"query": "<NL query, no document ids>",
         "docs_used": [1,2],
         "cross_doc_link": "<bridge/shared dimension across the docs>"}}
     ]}}
 ],
 "infeasible": [{{"viz_type": "<pool key>", "why_not": "<missing material or 'single-doc only'>"}}]}}
```"""


def _gen(bundle: dict, facts: str, pool: dict, model, host_pool) -> dict:
    raw = _call_llm(host_pool.next(), model,
                    PROMPT.format(pool="\n".join(f"  - {k}: {v}" for k, v in pool.items()),
                                  facts=facts[:14000]))
    return _extract_json(raw) or {"feasible": [], "infeasible": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", type=Path, default=REPO / "data/bundles/loong_phase1.json")
    ap.add_argument("--compressed", type=Path, default=REPO / "data/queries/loong_phase1_compressed.json")
    ap.add_argument("--out", type=Path, default=REPO / "data/queries/loong_phase1_typed.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pool", choices=["chart", "diagram", "both"], default=None,
                    help="override per-source pool selection")
    ap.add_argument("--hosts", default=",".join(DEFAULT_QWEN_HOSTS))
    ap.add_argument("--model", default="Qwen3.5-397B-A17B-FP8")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    bundles = json.loads(args.bundles.read_text())
    if args.limit:
        bundles = bundles[: args.limit]
    comp = json.loads(args.compressed.read_text())
    host_pool = HostPool([h.strip() for h in args.hosts.split(",") if h.strip()], 8000, "EMPTY")

    def run(b):
        src = b["source"]
        pool = _pool_for(src, args.pool)
        out = _gen(b, comp.get(b["bundle_id"], ""), pool, args.model, host_pool)
        return b, ("chart" if args.pool == "chart" else "diagram" if args.pool == "diagram"
                   else SOURCE_POOL.get(src, "both")), out

    args.out.parent.mkdir(parents=True, exist_ok=True)
    recs, n_q, n_md_bad = [], 0, 0
    type_cov, by_type = Counter(), Counter()
    with ThreadPoolExecutor(max_workers=args.workers) as ex, args.out.open("w") as fout:
        for fut in as_completed([ex.submit(run, b) for b in bundles]):
            b, poolkind, out = fut.result()
            feas = out.get("feasible", [])
            qs = []
            for f in feas:
                vt = f.get("viz_type", "?")
                for q in f.get("queries", []):
                    docs = q.get("docs_used", [])
                    ok_md = isinstance(docs, list) and len(set(docs)) >= 2
                    if not ok_md:
                        n_md_bad += 1
                        continue
                    qs.append({"viz_type": vt, "query": q.get("query", ""),
                               "docs_used": docs, "cross_doc_link": q.get("cross_doc_link", "")})
                    by_type[vt] += 1
                type_cov[vt] += 1
            rec = {"bundle_id": b["bundle_id"], "source": b["source"],
                   "challenge_type": b["metadata"]["challenge_type"], "pool": poolkind,
                   "queries": qs, "infeasible": out.get("infeasible", [])}
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n"); fout.flush()
            recs.append(rec); n_q += len(qs)
            print(f"  {b['bundle_id']} [{poolkind}]: {len(qs)} multi-doc queries over {len({q['viz_type'] for q in qs})} types")

    print(f"\n[query_type_gen] {len(recs)} bundles | {n_q} multi-doc queries | "
          f"dropped {n_md_bad} single-doc | viz coverage {len(by_type)} types")
    print(f"[query_type_gen] per-type: {dict(by_type)}")
    print(f"[query_type_gen] avg queries/bundle: {n_q/max(len(recs),1):.1f}")
    print(f"[query_type_gen] → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
