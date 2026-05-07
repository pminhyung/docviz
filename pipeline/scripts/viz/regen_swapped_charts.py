"""D24 §3 — Re-generate gold + model_outputs/chart for docs that swapped subtype.

After balance_chart_subtypes.py decides a new chart_subtype per doc, any doc
whose subtype changed needs:

1. corpus.jsonl row updated with chart_subtype_v2
2. queries.jsonl row regenerated (new chart_spec for the new subtype)
3. data/gold/chart/<doc>_*.{json,source.txt,rendered.png} regenerated
4. data/model_outputs/<model>/chart/<doc>_*.{json,source.txt,rendered.png}
   regenerated for all 6 evaluation models

This script handles 1+2 (corpus + queries) and orchestrates 3 (gold) by
re-invoking the existing reference_generator + render pipeline. Step 4
(model outputs) is delegated to a separate orchestrator that knows about
each model's vLLM endpoint.

Run:
    python -m scripts.viz.regen_swapped_charts [--dry-run]

Pre-condition:
- data/viz/_subtype_assignment_v2.jsonl exists.
- data/viz/_subtype_rankings_v2.jsonl exists (used to extract chart_spec).
"""
import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

ASSIGN = os.path.join(ROOT, "data", "viz", "_subtype_assignment_v2.jsonl")
CORPUS = os.path.join(ROOT, "data", "documents", "corpus.jsonl")
QUERIES = os.path.join(ROOT, "data", "viz", "queries.jsonl")
GOLD_CHART = os.path.join(ROOT, "data", "gold", "chart")
MODEL_OUT = os.path.join(ROOT, "data", "model_outputs")
BACKUP_SUFFIX = "_pre_v2_balance"


def load_jsonl(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                     help="report swap list, do not modify files")
    ap.add_argument("--assignment", default=ASSIGN,
                     help="path to *_subtype_assignment*.jsonl (default: v2)")
    args = ap.parse_args()

    assign_path = args.assignment
    if not os.path.exists(assign_path):
        print(f"[regen] missing {assign_path}; run balance_chart_subtypes*.py first")
        sys.exit(1)

    assignments = load_jsonl(assign_path)
    # Detect schema: v2 uses chart_subtype_v1/_v2; v3 uses chart_subtype_v2/_v3.
    # Normalise to (from_st, to_st) per record.
    def _from_to(a):
        if "chart_subtype_v3" in a:
            return a.get("chart_subtype_v2"), a.get("chart_subtype_v3")
        return a.get("chart_subtype_v1"), a.get("chart_subtype_v2")
    swaps = [a for a in assignments if a.get("swap") and not a.get("unassigned")]
    print(f"[regen] {len(swaps)} / {len(assignments)} docs need chart re-gen")

    if not swaps:
        print("[regen] nothing to do")
        return

    if args.dry_run:
        for s in swaps[:20]:
            f_st, t_st = _from_to(s)
            print(f"  {s['doc_id']}: {f_st} → {t_st}")
        if len(swaps) > 20:
            print(f"  ... +{len(swaps)-20} more")
        return

    # Backup originals (only on first ever run; v3 reuses v2 backup)
    for d in (GOLD_CHART, ):
        bak = d + BACKUP_SUFFIX
        if not os.path.exists(bak):
            print(f"[regen] backing up {d} → {bak}")
            shutil.copytree(d, bak)
    for f in (CORPUS, QUERIES):
        if not os.path.exists(f + BACKUP_SUFFIX):
            shutil.copy(f, f + BACKUP_SUFFIX)
            print(f"[regen] backed up {f} → {f}{BACKUP_SUFFIX}")

    # 1) Update corpus.jsonl with the "to" subtype
    swap_map = {s["doc_id"]: _from_to(s)[1] for s in swaps}
    corpus = load_jsonl(CORPUS)
    for r in corpus:
        if r["doc_id"] in swap_map:
            r["chart_subtype"] = swap_map[r["doc_id"]]
    with open(CORPUS, "w", encoding="utf-8") as f:
        for r in corpus:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[regen] corpus.jsonl updated for {len(swap_map)} docs")

    # 2) Drop chart-row entries from queries.jsonl for swapped docs
    #    (they will be re-created by the query regenerator next step).
    qs = load_jsonl(QUERIES)
    kept = [q for q in qs if not (q.get("viz_type") == "chart" and
                                    q.get("doc_id") in swap_map)]
    print(f"[regen] queries.jsonl: dropped {len(qs)-len(kept)} chart entries")
    with open(QUERIES, "w", encoding="utf-8") as f:
        for q in kept:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    # 3) Remove swapped docs' gold/chart artefacts so step2_generate_gold
    #    re-creates them. Same for model_outputs/<model>/chart.
    removed = 0
    for doc_id in swap_map:
        # gold
        for ext in ("json", "txt", "png", "html", "svg"):
            for suffix in ("_structure.json", "_source.txt",
                            "_rendered.png", "_rendered.html",
                            "_rendered.svg"):
                p = os.path.join(GOLD_CHART, f"{doc_id}{suffix}")
                if os.path.exists(p):
                    os.remove(p); removed += 1
        # model_outputs/<model>/chart/<doc>_*
        if os.path.isdir(MODEL_OUT):
            for model in os.listdir(MODEL_OUT):
                d = os.path.join(MODEL_OUT, model, "chart")
                if not os.path.isdir(d):
                    continue
                for suffix in ("_structure.json", "_source.txt",
                                "_rendered.png", "_rendered.html",
                                "_rendered.svg"):
                    p = os.path.join(d, f"{doc_id}{suffix}")
                    if os.path.exists(p):
                        os.remove(p); removed += 1
    print(f"[regen] removed {removed} chart artefacts (gold + model_outputs).")
    print()
    print("Next steps (run in order):")
    print("  1. python -m scripts.viz.subtype_assigner --only-chart-spec")
    print("       → fills queries.jsonl with new chart_spec for swapped docs")
    print("  2. python -m scripts.step2_generate_gold --viz chart")
    print("       → re-creates gold/chart for swapped docs")
    print("  3. python -m scripts.step3_generate_models --viz chart")
    print("     python -m scripts.step3_generate_claude_sonnet --viz chart")
    print("       → re-creates model_outputs/<model>/chart for swapped docs")
    print("  4. python -m scripts.step4_structural_metrics  # idempotent: re-fills holes")
    print("  5. python -m scripts.step5_vlm_judge --all --parallel 8")
    print("  6. python -m scripts.step6_aggregate")


if __name__ == "__main__":
    main()
