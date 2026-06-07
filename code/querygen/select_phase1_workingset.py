"""Select a viz-type-balanced Phase-1 working set from the typed_v2 query pool,
emit it in the standard Query schema (query_schema.Query) for the downstream
harness (bundles_to_jsonl → gold_builder → B5/B6).

typed_v2 carries natural user queries already (a) multi-doc-enforced, (b) anchored
on the Loong reasoning label, (c) tagged with a gold target_viz_type. We pick a set
balanced across the 5 diagram primitives (all 5 present so the Phase-1 gate's
"all 5 mermaid subtypes" condition is measurable), seed-42 deterministic.
"""
from __future__ import annotations
import argparse, json, random
from collections import defaultdict, Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# gold target_viz_type -> standard OutputType
VIZ2OUTPUT = {
    "mermaid_flowchart": "relational", "mermaid_classDiagram": "relational",
    "mermaid_sequenceDiagram": "relational", "mermaid_timeline": "temporal",
    "mermaid_mindmap": "hierarchical",
    "chartjs_bar": "quantitative", "chartjs_grouped_bar": "comparative",
    "chartjs_line": "temporal", "chartjs_pie": "quantitative", "chartjs_scatter": "quantitative",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--typed", type=Path, default=REPO / "data/queries/loong_phase1_typed_v2.jsonl")
    ap.add_argument("--out", type=Path, default=REPO / "data/queries/loong_phase1_working.jsonl")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    recs = [json.loads(l) for l in args.typed.read_text().splitlines() if l.strip()]
    # flatten to candidate queries grouped by viz_type
    by_viz: dict[str, list] = defaultdict(list)
    for r in recs:
        for i, q in enumerate(r.get("queries", [])):
            vt = q.get("target_viz_type", "")
            if not vt:
                continue
            cand = {
                "bundle_id": r["bundle_id"], "source": r["source"],
                "challenge_type": r["challenge_type"], "loong_task": r.get("loong_task"),
                "viz_type": vt, "query": q.get("query", ""),
                "evidence_docs": q.get("evidence_docs", []),
                "cross_doc_link": q.get("cross_doc_link", ""),
                "reasoning_type": q.get("reasoning_type", ""),
            }
            by_viz[vt].append(cand)

    rng = random.Random(args.seed)
    for v in by_viz.values():
        rng.shuffle(v)

    # balanced round-robin across viz types until n reached (prefer >=2 evidence_docs)
    types = sorted(by_viz, key=lambda t: -len(by_viz[t]))  # but round-robin fairly
    chosen, used = [], set()
    # ensure all types present: take 1 from each first
    order = sorted(by_viz.keys())
    idx = {t: 0 for t in order}
    while len(chosen) < args.n and any(idx[t] < len(by_viz[t]) for t in order):
        for t in order:
            if len(chosen) >= args.n:
                break
            while idx[t] < len(by_viz[t]):
                c = by_viz[t][idx[t]]; idx[t] += 1
                key = (c["bundle_id"], c["query"][:60])
                if key in used:
                    continue
                if len(set(c["evidence_docs"])) < 2:
                    continue
                used.add(key); chosen.append(c); break

    # emit standard Query schema
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for i, c in enumerate(chosen):
            vt = c["viz_type"]
            rec = {
                "qid": f"loong_{c['bundle_id']}_{vt}_{i:03d}",
                "text": c["query"],
                "bundle_id": c["bundle_id"],
                "source": c["source"],
                "challenge_type": c["challenge_type"],
                "output_type": VIZ2OUTPUT.get(vt, "relational"),
                "gold_intent_count": 1,
                "gold_intents": [{
                    "intent_id": "1", "artifact_type_hint": vt,
                    "content_summary": c["cross_doc_link"] or c["query"][:120],
                }],
                # provenance for analysis
                "_evidence_docs": c["evidence_docs"], "_reasoning_type": c["reasoning_type"],
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"selected {len(chosen)}/{args.n} → {args.out}")
    print("viz_type balance:", dict(Counter(c["viz_type"] for c in chosen)))
    print("challenge balance:", dict(Counter(c["challenge_type"] for c in chosen)))
    print("output_type balance:", dict(Counter(VIZ2OUTPUT.get(c["viz_type"], "?") for c in chosen)))
    print("distinct bundles covered:", len({c["bundle_id"] for c in chosen}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
