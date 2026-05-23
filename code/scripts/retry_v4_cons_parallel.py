"""Parallel version of retry_v4_cons_repair for full-265 V4.5 rerun.

Each worker creates its own S4AgenticTMG instance (sticky-host per
instance) so workers spread across the on-prem cluster.

Run:
  python -m code.scripts.retry_v4_cons_parallel \\
      --bundles data/prototype/bundles/all.json \\
      --queries data/prototype/queries/all.json \\
      --targets /tmp/full_targets.json \\
      --out /tmp/full_results.json \\
      --write-raw /tmp/full_raw.jsonl \\
      --workers 9
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--write-raw", required=True)
    ap.add_argument("--workers", type=int, default=9)
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))

    from code.pipelines.base import Bundle, Doc
    from code.pipelines.s4_agentic_tmg import S4AgenticTMG
    from code.run_prototype import _check_syntax, _record_from_vizout

    target_qids = json.load(open(args.targets))
    queries = json.load(open(args.queries))
    bundles = json.load(open(args.bundles))

    qbi = {q["query_id"]: q for q in queries}
    bbi = {b["bundle_id"]: b for b in bundles}

    print(f"[retry-par] {len(target_qids)} targets, workers={args.workers}")
    raw_lock = threading.Lock()
    results = []
    res_lock = threading.Lock()

    def _one(qid):
        q = qbi.get(qid)
        if not q:
            return {"qid": qid, "ok": False, "error": "query missing"}
        bid = q["bundle_id"]
        bdict = bbi.get(bid)
        if not bdict:
            return {"qid": qid, "ok": False, "error": f"bundle {bid} missing"}
        docs = [Doc(doc_id=d["doc_id"], title=d["title"],
                    content=d["content"], page_id=d.get("page_id", ""))
                for d in bdict["docs"]]
        bundle = Bundle(bundle_id=bdict["bundle_id"], source=bdict["source"],
                        docs=docs, metadata=bdict.get("metadata", {}))
        # Each worker thread creates its own pipeline → its own sticky host.
        pipe = S4AgenticTMG(mode="v4_consolidated")
        t0 = time.time()
        try:
            vo = pipe.run(q["query"], bundle,
                          query_type=q.get("query_type"), query_id=qid)
            dur = time.time() - t0
            syntax_ok, _ = _check_syntax(vo.viz_type, vo.viz_dsl)
            has_dsl = bool(vo.viz_dsl and len(vo.viz_dsl) >= 20)
            ok = has_dsl and syntax_ok
            row = {
                "qid": qid, "ok": ok, "ok_relaxed": has_dsl,
                "viz_type": vo.viz_type,
                "viz_dsl_len": len(vo.viz_dsl or ""),
                "syntax_valid": syntax_ok,
                "tokens_out": vo.tokens_out,
                "duration": dur,
                "errors": vo.errors[:2] if vo.errors else [],
            }
            rec = _record_from_vizout(q, "S4_AgenticTMGv4_consolidated", vo, dur)
            with raw_lock:
                with open(args.write_raw, "a") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            tag = "OK" if ok else ("REL" if has_dsl else "FAIL")
            print(f"  [{qid}] {tag:4s} viz_type={vo.viz_type:25s} "
                  f"dsl={len(vo.viz_dsl or ''):>5d} syn={'Y' if syntax_ok else 'N'} "
                  f"tok={vo.tokens_out:>6d} dur={dur:>5.1f}s",
                  flush=True)
            return row
        except Exception as e:
            return {"qid": qid, "ok": False, "ok_relaxed": False,
                    "exception": f"{type(e).__name__}: {e}",
                    "duration": time.time() - t0}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(_one, q): q for q in target_qids}
        done = 0
        for fut in as_completed(futures):
            r = fut.result()
            with res_lock:
                results.append(r)
                done += 1
            if done % 10 == 0:
                print(f"[retry-par] progress {done}/{len(target_qids)}", flush=True)
            # Persist after each result
            json.dump(
                {"results": results,
                 "n_ok": sum(1 for x in results if x.get("ok")),
                 "n_relaxed": sum(1 for x in results if x.get("ok_relaxed")),
                 "n": len(results)},
                open(args.out, "w"), indent=2,
            )

    n_ok = sum(1 for r in results if r.get("ok"))
    n_rel = sum(1 for r in results if r.get("ok_relaxed"))
    n = len(results)
    print(f"\n[retry-par] strict OK: {n_ok}/{n} ({100*n_ok//max(1,n)}%)")
    print(f"[retry-par] relaxed OK: {n_rel}/{n} ({100*n_rel//max(1,n)}%)")
    print(f"[retry-par] → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
