"""Run direct-call baselines under Claude Sonnet (via claude -p subprocess).

Limited subset (default 50 records, stratified by source) due to per-call
overhead (~25-40s sequential). Output mirrors run_prototype schema so the
existing judge pipeline can be re-used.

Run:
  python -m code.scripts.run_sonnet_subset \\
      --bundles data/prototype/bundles/all.json \\
      --queries data/prototype/queries/all.json \\
      --out outputs/multi_llm/sonnet/viz/all.json \\
      --raw outputs/multi_llm/sonnet/viz/raw.jsonl \\
      --n 50 --strategies S1,S7,B2,B3,B4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


def stratified_sample(queries: List[Dict[str, Any]], n: int, seed: int = 42) -> List[Dict[str, Any]]:
    """Sample `n` queries stratified by `source`."""
    by_src: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for q in queries:
        by_src[q["source"]].append(q)
    out: List[Dict[str, Any]] = []
    sources = sorted(by_src)
    per_src = max(1, n // max(1, len(sources)))
    import random
    rng = random.Random(seed)
    for s in sources:
        pool = by_src[s][:]
        rng.shuffle(pool)
        out.extend(pool[:per_src])
    # If short, fill from any remaining
    if len(out) < n:
        used = {q["query_id"] for q in out}
        extras = [q for q in queries if q["query_id"] not in used]
        rng.shuffle(extras)
        out.extend(extras[: n - len(out)])
    return out[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--n", type=int, default=50, help="subset size")
    ap.add_argument("--strategies", default="S1,S7,B2,B3,B4",
                    help="comma-separated subset of {S1,S7,B2,B3,B4}")
    ap.add_argument("--sleep", type=float, default=2.0,
                    help="sleep between sonnet calls")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))

    from code.adapters.multi_llm_clients import ClaudeSonnetClient
    from code.pipelines.s1_direct import S1Direct
    from code.pipelines.s7_self_refine import S7SelfRefine
    from code.pipelines.b2_nvagent import B2NVAGENT
    from code.pipelines.b3_coda import B3CoDA
    from code.pipelines.b4_vividoc import B4ViviDoc
    from code.pipelines.base import Bundle, Doc
    from code.run_prototype import _record_from_vizout

    bundles_data = json.loads(Path(args.bundles).read_text())
    bundles_idx = {b["bundle_id"]: b for b in bundles_data}
    queries = json.loads(Path(args.queries).read_text())

    subset = stratified_sample(queries, args.n)
    print(f"[sonnet] subset n={len(subset)} (stratified by source)", flush=True)

    strategy_factories = {
        "S1": ("S1_Direct", lambda c: S1Direct(client=c)),
        "S7": ("S7_SelfRefine", lambda c: S7SelfRefine(client=c)),
        "B2": ("B2_NVAGENT", lambda c: B2NVAGENT(client=c)),
        "B3": ("B3_CoDA", lambda c: B3CoDA(client=c)),
        "B4": ("B4_ViviDoc", lambda c: B4ViviDoc(client=c)),
    }
    selected = [s.strip() for s in args.strategies.split(",") if s.strip()]

    client = ClaudeSonnetClient(sleep_seconds=args.sleep)

    out_path = Path(args.out)
    raw_path = Path(args.raw)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, Any]] = []
    raw_path.write_text("")  # truncate

    for sel in selected:
        if sel not in strategy_factories:
            print(f"[sonnet] unknown strategy: {sel}", flush=True)
            continue
        strat_name, factory = strategy_factories[sel]
        try:
            pipe = factory(client)
        except TypeError:
            print(f"[sonnet] {strat_name} does not accept client= kwarg; skip", flush=True)
            continue

        print(f"\n=== {strat_name} on {len(subset)} records ===", flush=True)
        for i, q in enumerate(subset):
            bid = q["bundle_id"]
            bdict = bundles_idx[bid]
            docs = [
                Doc(doc_id=d["doc_id"], title=d["title"],
                    content=d["content"], page_id=d.get("page_id",""))
                for d in bdict["docs"]
            ]
            bundle = Bundle(bundle_id=bdict["bundle_id"], source=bdict["source"],
                            docs=docs, metadata=bdict.get("metadata",{}))
            t0 = time.time()
            try:
                vo = pipe.run(q["query"], bundle,
                              query_type=q.get("query_type"),
                              query_id=q["query_id"])
                dur = time.time() - t0
                rec = _record_from_vizout(q, strat_name, vo, dur)
                records.append(rec)
                with raw_path.open("a") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"  [{strat_name} {i+1:>3d}/{len(subset)}] {q['query_id']:<28s} "
                      f"syn={'Y' if rec['syntax_valid'] else 'N'} "
                      f"tok={rec['tokens_out']:>5d} dur={dur:>6.1f}s",
                      flush=True)
                # Persist after each (kill-safe)
                out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
            except Exception as e:
                print(f"  [{strat_name} {i+1:>3d}] FAIL: {type(e).__name__}: {str(e)[:160]}", flush=True)

    # Final write
    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(f"\n[sonnet] final: {len(records)} records → {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
