"""D24 §3b — Regenerate chart_spec ONLY for docs whose chart_subtype changed.

Why a separate script (not subtype_assigner)?
- subtype_assigner is doc_id-keyed and would (a) reuse the stale cached
  chart_spec for the OLD subtype and (b) write_back_corpus the OLD subtype,
  undoing the Hungarian balance assignment.

What it does
- Reads `data/viz/_subtype_assignment_v2.jsonl` (Hungarian output).
- For each `swap=true` doc:
    1. Removes the doc's entry from `_chart_spec_cache.jsonl`
       (cache rewritten without that doc_id; new entry appended).
    2. Updates the doc's entry in `_subtype_cache.jsonl` to the v2 subtype
       so a later subtype_assigner full-run leaves it alone.
    3. Calls `plan_chart_spec(row, chart_subtype_v2)` and patches
       `corpus.jsonl` with the new chart_spec / chart_spec_data_location.

Run:
    python -m scripts.viz.regen_chart_specs_for_swapped [--workers 8]
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from scripts.viz.subtype_assigner import (
    plan_chart_spec, _append_cache,
    SUBTYPE_CACHE, CHART_SPEC_CACHE, CORPUS_PATH,
)

ASSIGN = os.path.join(ROOT, "data", "viz", "_subtype_assignment_v2.jsonl")


def _load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def _drop_doc_ids_from_cache(path: str, drop: set):
    """Rewrite cache file without entries whose doc_id is in `drop`."""
    if not os.path.exists(path):
        return
    rows = _load_jsonl(path)
    kept = [r for r in rows if r.get("doc_id") not in drop]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    print(f"[cache] {os.path.basename(path)}: dropped {len(rows)-len(kept)} stale entries")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--assignment", default=ASSIGN,
                     help="path to *_subtype_assignment*.jsonl (default: v2)")
    args = ap.parse_args()

    assign_path = args.assignment
    if not os.path.exists(assign_path):
        print(f"[regen-spec] missing {assign_path}; run balance_chart_subtypes*.py first")
        sys.exit(1)

    def _to_st(a):
        return a.get("chart_subtype_v3") or a.get("chart_subtype_v2")

    swaps = [a for a in _load_jsonl(assign_path)
             if a.get("swap") and not a.get("unassigned")]
    if not swaps:
        print("[regen-spec] nothing to do (no swaps)")
        return

    swap_ids = {s["doc_id"] for s in swaps}
    print(f"[regen-spec] {len(swap_ids)} swapped docs")

    # 1) Drop stale chart_spec entries for swapped docs
    _drop_doc_ids_from_cache(CHART_SPEC_CACHE, swap_ids)

    # 2) Drop stale subtype entries (will rewrite below with v2)
    _drop_doc_ids_from_cache(SUBTYPE_CACHE, swap_ids)

    # Re-append v2 subtype entries so subtype_assigner trusts them.
    # subtype cache schema: {doc_id, chart_subtype, diagram_subtype, ...}
    # We only flip chart_subtype; preserve diagram_subtype + reasons via the
    # original cache row if available (otherwise fill in stubs).
    orig_subtype = {r["doc_id"]: r for r in _load_jsonl(SUBTYPE_CACHE)}
    for s in swaps:
        prior = orig_subtype.get(s["doc_id"], {})
        new_entry = {
            "doc_id": s["doc_id"],
            "chart_subtype": _to_st(s),
            "diagram_subtype": prior.get("diagram_subtype", "flowchart"),
            "chart_reason": "D24 Hungarian balance reassignment",
            "diagram_reason": prior.get("diagram_reason", ""),
        }
        _append_cache(SUBTYPE_CACHE, new_entry)
    print(f"[regen-spec] subtype cache updated for {len(swaps)} docs")

    # 3) Generate fresh chart_spec for each swapped doc, patch corpus.jsonl
    corpus = _load_jsonl(CORPUS_PATH)
    by_id = {r["doc_id"]: r for r in corpus}
    todo = [(s["doc_id"], _to_st(s)) for s in swaps
            if s["doc_id"] in by_id]

    new_specs = {}
    failures = []

    def _work(doc_id, subtype):
        row = by_id[doc_id]
        try:
            sp = plan_chart_spec(row, subtype)
            return doc_id, sp, None
        except Exception as e:
            return doc_id, None, f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_work, d, s) for d, s in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            doc_id, sp, err = fut.result()
            if err:
                failures.append((doc_id, err))
                continue
            new_specs[doc_id] = sp
            _append_cache(CHART_SPEC_CACHE, sp)
            if i % 25 == 0 or i == len(futs):
                print(f"[regen-spec] {i}/{len(futs)} specs generated")

    print(f"[regen-spec] {len(new_specs)} succeeded, {len(failures)} failed")
    for d, e in failures[:10]:
        print(f"  FAIL {d}: {e}")

    # Patch corpus.jsonl
    for doc_id, sp in new_specs.items():
        r = by_id[doc_id]
        r["chart_spec"] = {
            "chart_type_name": sp["chart_type_name"],
            "x_field": sp["x_field"],
            "y_field": sp["y_field"],
            "color_field": sp["color_field"],
            "title": sp["title"],
        }
        r["chart_spec_data_location"] = sp["data_location"]

    tmp = CORPUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in corpus:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, CORPUS_PATH)
    print(f"[regen-spec] corpus.jsonl patched for {len(new_specs)} swapped docs")


if __name__ == "__main__":
    main()
