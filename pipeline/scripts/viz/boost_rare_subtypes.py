"""D24 v3 — Re-evaluate rare chart-subtype feasibility per doc.

Why: the v2 ranker (rank_subtypes_v2) used a strict prompt; rare types
(combo/area/radar/doughnut) ended up with insufficient feasibility supply
to fill Hungarian quotas. This script asks an LLM a more permissive,
focused question:

    "For EACH of these 4 rare chart types, could ANY plausible subset of
     this document's data form a meaningful version of the chart, even if
     a different chart would be more natural?"

Per-subtype hints frame what each chart represents to reduce
default-to-no answers.

Output: data/viz/_rare_feasibility_v3.jsonl
    {"doc_id": ..., "rare": {
        "combo":    {"feasible": bool, "reason": str},
        "area":     {"feasible": bool, "reason": str},
        "radar":    {"feasible": bool, "reason": str},
        "doughnut": {"feasible": bool, "reason": str}}}

Run:
    python -m scripts.viz.boost_rare_subtypes [--workers 8] [--limit N]
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from scripts.utils.llm_clients import call_model
from scripts.viz.subtype_assigner import _extract_json, prepare_doc_excerpt

CORPUS = os.path.join(ROOT, "data", "documents", "corpus.jsonl")
OUT = os.path.join(ROOT, "data", "viz", "_rare_feasibility_v3.jsonl")

RARE = ["combo", "area", "radar", "doughnut"]

PROMPT = """You are evaluating whether a document COULD be visualized as
ANY of these 4 rare chart subtypes. Be GENEROUS — feasibility means
"plausible enough that a meaningful chart of this kind could be drawn
from SOME subset of the document's data," NOT "this is the ideal chart."

For each subtype, output feasible=true if the document contains ANY data
where the chart kind below would convey real information. Output
feasible=false ONLY when the document has zero structure that fits.

CHART subtypes (evaluate ALL 4):
- combo:    any TWO related metrics with different scales that share a
            common axis (absolute + percentage, count + ratio, value +
            growth). Bar y-left + line y-right is the canonical layout.
- area:     any time-series or sequence with cumulative or stacked
            components (composition over time, multi-series totals).
- radar:    any single entity with 3 OR MORE measurable attributes /
            dimensions (KPI scorecards, multi-attribute comparisons,
            capability profiles, performance across categories).
- doughnut: any breakdown of a whole into 2-5 categories (proportional
            composition, market share, portfolio allocation, segment
            split).

Document context:
- Document id: {doc_id}
- Language: {doc_language}
- Domain: {doc_domain}

Document excerpt:
{doc_excerpt}

Respond with ONLY a JSON object in this EXACT shape:
{{
  "combo":    {{"feasible": true|false, "reason": "<one short sentence>"}},
  "area":     {{"feasible": true|false, "reason": "<one short sentence>"}},
  "radar":    {{"feasible": true|false, "reason": "<one short sentence>"}},
  "doughnut": {{"feasible": true|false, "reason": "<one short sentence>"}}
}}"""


def _eval_one(row: dict) -> dict:
    excerpt = prepare_doc_excerpt(row, max_chars=2500)
    prompt = PROMPT.format(
        doc_id=row["doc_id"],
        doc_language=row.get("lang", "en"),
        doc_domain=row.get("domain", "general"),
        doc_excerpt=excerpt,
    )
    raw = call_model(
        "qwen397b",
        system_prompt="You output only valid JSON as instructed.",
        user_content=prompt,
        temperature=0.2,
    )
    parsed = _extract_json(raw) or {}
    out = {}
    for st in RARE:
        entry = parsed.get(st, {}) if isinstance(parsed, dict) else {}
        out[st] = {
            "feasible": bool(entry.get("feasible", False)),
            "reason": str(entry.get("reason", ""))[:200],
        }
    return {"doc_id": row["doc_id"], "rare": out}


def _load_done(path: str) -> set:
    if not os.path.exists(path):
        return set()
    return {json.loads(l)["doc_id"] for l in open(path) if l.strip()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    corpus = [json.loads(l) for l in open(CORPUS) if l.strip()]
    done = _load_done(OUT)
    todo = [r for r in corpus if r["doc_id"] not in done]
    if args.limit:
        todo = todo[: args.limit]

    print(f"[boost-rare] {len(todo)} docs to evaluate "
           f"(workers={args.workers}, already-done={len(done)})")
    if not todo:
        return

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out_lock = __import__("threading").Lock()
    fout = open(OUT, "a", encoding="utf-8")
    ok, fail = 0, 0
    fail_examples = []
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(_eval_one, r) for r in todo]
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    res = fut.result()
                    with out_lock:
                        fout.write(json.dumps(res, ensure_ascii=False) + "\n")
                        fout.flush()
                    ok += 1
                except Exception as e:
                    fail += 1
                    if len(fail_examples) < 5:
                        fail_examples.append(f"{type(e).__name__}: {e}")
                if i % 50 == 0 or i == len(futs):
                    print(f"  {i}/{len(futs)}  OK={ok} FAIL={fail}")
    finally:
        fout.close()

    print(f"\n[boost-rare] DONE: OK={ok} FAIL={fail}")
    if fail_examples:
        print("first failures:")
        for e in fail_examples:
            print(f"  {e}")

    # Quick supply summary
    print()
    rows = [json.loads(l) for l in open(OUT)]
    counts = {st: 0 for st in RARE}
    for r in rows:
        for st in RARE:
            if r["rare"].get(st, {}).get("feasible"):
                counts[st] += 1
    print(f"[boost-rare] feasibility supply (v3 supplement):")
    for st in RARE:
        print(f"  {st:9s}: {counts[st]}")


if __name__ == "__main__":
    main()
