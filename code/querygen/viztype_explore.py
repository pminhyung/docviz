"""Experiment: viz-type coverage / feasibility for a document set, two ways.

Method A (user's idea — feasibility enumeration over the pool):
  Give the model the 10-type pool; ask it to enumerate EVERY viz_type that can be
  genuinely grounded in THIS document set, write a multi-doc query per feasible
  type, and explicitly mark infeasible types. Strict JSON → parse.

Method B (evidence-first typed derivation):
  Step 1 — LLM inventories the concrete VISUALIZABLE DATA OBJECTS actually present
           (object_type + actual content + scope single/cross-doc + source docs).
  Step 2 — DETERMINISTIC map object_type → viz primitive(s); generate a query per
           object grounded in its extracted content. Feasibility is evidenced by an
           extracted object (with values/entities), not the model's self-claim.

Both consume the cached Stage-1 compressed facts (consistent input). Outputs a
side-by-side comparison: per-method viz_type coverage, chart/diagram split,
cross-doc grounding rate.

Usage:
    python -m code.querygen.viztype_explore \
        --bundles data/bundles/loong_phase1.json \
        --compressed data/queries/loong_phase1_compressed.json \
        --out outputs/viztype_explore.json --n 6 --hosts <8 hosts>
"""
from __future__ import annotations
import argparse, json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from exaone.sft_gen.docviz.generate_queries import HostPool, _call_llm, _extract_json, DEFAULT_QWEN_HOSTS

REPO = Path(__file__).resolve().parents[2]

VIZ_POOL = {
    "chartjs_bar": "single-series numeric bars", "chartjs_grouped_bar": "multi-series numeric comparison bars",
    "chartjs_line": "numeric trend over an ordered axis", "chartjs_pie": "part-of-whole proportions",
    "chartjs_scatter": "two-variable numeric correlation",
    "mermaid_flowchart": "nodes + directed edges (process/relations/causality)",
    "mermaid_timeline": "dated events in order", "mermaid_mindmap": "hierarchical tree from a root",
    "mermaid_sequenceDiagram": "ordered messages between actors", "mermaid_classDiagram": "entities with attributes + relations",
}
POOL_STR = "\n".join(f"  - {k}: {v}" for k, v in VIZ_POOL.items())

# ── Method A ──────────────────────────────────────────────────────────────
METHOD_A = """You author multi-document VISUALIZATION benchmark queries. Visualization primitive pool:
{pool}

Document set (compressed key facts per document):
{facts}

Task: Considering ONLY the facts above, decide which primitives can be GENUINELY grounded — i.e., the specific data/entities/relations needed to build that visualization actually EXIST in these documents (assembling them into the diagram/chart is a downstream pipeline's job; you only judge whether the raw material is present). A chart requires the actual numeric VALUES to plot; do not claim a chart feasible if the values are absent. Prefer queries that require integrating >= 2 documents.

Output STRICT JSON only:
```json
{{"feasible": [{{"viz_type":"<pool key>","query":"<NL query, no doc ids>","multi_doc":true,"grounding":"<which facts supply the material>"}}],
  "infeasible": [{{"viz_type":"<pool key>","why_not":"<what's missing>"}}]}}
```"""

# ── Method B step 1 ─────────────────────────────────────────────────────────
METHOD_B1 = """You inventory the VISUALIZABLE DATA OBJECTS that actually exist in a document set, for downstream visualization.

Document set (compressed key facts per document):
{facts}

List every concrete data object present whose material is sufficient to visualize. For each, give:
- object_type: one of [numeric_series, comparison_values, entity_relation_graph, process_flow, event_timeline, hierarchy_taxonomy, attribute_matrix]
- content: the ACTUAL entities/values/relations (verbatim specifics; for numeric give the numbers)
- scope: "single_doc" (within one doc) or "cross_doc" (spans >= 2 docs)
- docs: which document indices supply it

Only include an object if its material is really present (a numeric_series/comparison_values REQUIRES actual numbers). Do not invent.

Output STRICT JSON only:
```json
{{"objects":[{{"object_type":"...","content":"...","scope":"single_doc|cross_doc","docs":[1,2]}}]}}
```"""

# deterministic object_type -> candidate viz primitives
OBJ2VIZ = {
    "numeric_series": ["chartjs_line", "chartjs_bar"],
    "comparison_values": ["chartjs_grouped_bar", "chartjs_bar"],
    "attribute_matrix": ["chartjs_grouped_bar", "mermaid_classDiagram"],
    "entity_relation_graph": ["mermaid_flowchart", "mermaid_classDiagram"],
    "process_flow": ["mermaid_flowchart", "mermaid_sequenceDiagram"],
    "event_timeline": ["mermaid_timeline", "chartjs_line"],
    "hierarchy_taxonomy": ["mermaid_mindmap"],
}

METHOD_B2 = """Write ONE multi-document visualization query for the data object below. The query must ask for a {viz_type} ({viz_desc}) and ground in this object's content. No document ids in the query.

Data object (scope={scope}): {content}

Output STRICT JSON only:
```json
{{"viz_type":"{viz_type}","query":"<NL query>","multi_doc":{multi_doc}}}
```"""


def method_a(facts: str, pool, model) -> dict:
    raw = _call_llm(pool.next(), model, METHOD_A.format(pool=POOL_STR, facts=facts[:14000]))
    return _extract_json(raw) or {"feasible": [], "infeasible": []}


def method_b(facts: str, pool, model) -> dict:
    inv = _extract_json(_call_llm(pool.next(), model, METHOD_B1.format(facts=facts[:14000]))) or {"objects": []}
    queries = []
    for obj in inv.get("objects", [])[:8]:
        ot = obj.get("object_type", "")
        vts = OBJ2VIZ.get(ot, [])
        if not vts:
            continue
        vt = vts[0]  # primary derived primitive
        cross = obj.get("scope") == "cross_doc"
        prompt = METHOD_B2.format(viz_type=vt, viz_desc=VIZ_POOL.get(vt, ""),
                                  scope=obj.get("scope", ""), content=str(obj.get("content", ""))[:800],
                                  multi_doc=str(cross).lower())
        q = _extract_json(_call_llm(pool.next(), model, prompt)) or {}
        if q.get("query"):
            queries.append({"viz_type": vt, "query": q["query"], "multi_doc": cross,
                            "object_type": ot, "scope": obj.get("scope", "")})
    return {"objects": inv.get("objects", []), "queries": queries}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", type=Path, default=REPO / "data/bundles/loong_phase1.json")
    ap.add_argument("--compressed", type=Path, default=REPO / "data/queries/loong_phase1_compressed.json")
    ap.add_argument("--out", type=Path, default=REPO / "outputs/viztype_explore.json")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--hosts", default=",".join(DEFAULT_QWEN_HOSTS))
    ap.add_argument("--model", default="Qwen3.5-397B-A17B-FP8")
    args = ap.parse_args()

    bundles = json.loads(args.bundles.read_text())[: args.n]
    comp = json.loads(args.compressed.read_text())
    pool = HostPool([h.strip() for h in args.hosts.split(",") if h.strip()], 8000, "EMPTY")

    def run(b):
        facts = comp.get(b["bundle_id"], "")
        return {"bundle_id": b["bundle_id"], "challenge": b["metadata"]["challenge_type"],
                "A": method_a(facts, pool, args.model), "B": method_b(facts, pool, args.model)}

    results = []
    with ThreadPoolExecutor(max_workers=min(args.n, 8)) as ex:
        for fut in as_completed([ex.submit(run, b) for b in bundles]):
            r = fut.result(); results.append(r)
            na = len(r["A"].get("feasible", [])); nb = len(r["B"].get("queries", []))
            print(f"  {r['bundle_id']} ({r['challenge']}): A feasible={na}  B queries={nb}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    # ── comparison summary ──
    def is_chart(v): return v.startswith("chartjs")
    A_types, B_types, A_md, A_tot, B_md, B_tot = Counter(), Counter(), 0, 0, 0, 0
    for r in results:
        for f in r["A"].get("feasible", []):
            A_types[f.get("viz_type", "?")] += 1; A_tot += 1; A_md += int(bool(f.get("multi_doc")))
        for q in r["B"].get("queries", []):
            B_types[q["viz_type"]] += 1; B_tot += 1; B_md += int(bool(q.get("multi_doc")))
    print("\n===== COMPARISON =====")
    print(f"Method A: {A_tot} queries | viz coverage {len(A_types)}/10 | chart {sum(v for k,v in A_types.items() if is_chart(k))} diagram {sum(v for k,v in A_types.items() if not is_chart(k))} | cross-doc {A_md}/{A_tot}")
    print(f"  A types: {dict(A_types)}")
    print(f"Method B: {B_tot} queries | viz coverage {len(B_types)}/10 | chart {sum(v for k,v in B_types.items() if is_chart(k))} diagram {sum(v for k,v in B_types.items() if not is_chart(k))} | cross-doc {B_md}/{B_tot}")
    print(f"  B types: {dict(B_types)}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
