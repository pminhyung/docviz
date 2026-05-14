"""Retry V4_consolidated on specific fail records with Fix 1+2+3 applied.

Targets the records identified in
docs/analysis/{text2vis,plot2code}_v4_cons_fail_analysis.md as Mode D/G/H/B
(schema/format issues recoverable by tool auto-repair + orchestrator
sidecar rescue + retry-on-empty broadening).

Run:
  python -m code.scripts.retry_v4_cons_repair \\
      --bundles data/prototype/bundles/text2vis.json \\
      --queries data/prototype/queries/text2vis.json \\
      --targets /tmp/text2vis_repair_targets.json \\
      --out /tmp/text2vis_repair_results.json

Targets file = JSON list of query_ids.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--targets", required=True, help="JSON list of query_ids to retry")
    ap.add_argument("--out", required=True, help="JSON path to write results")
    ap.add_argument("--write-raw", help="Optional path to viz/raw.jsonl — if set, "
                                        "append run_prototype-format records there. "
                                        "Existing records for target qids+strategy are NOT removed; "
                                        "the merge step (separate script) handles that.")
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

    pipe = S4AgenticTMG(mode="v4_consolidated")
    print(f"[retry] {len(target_qids)} targets, pipe={pipe._base_url}")
    print(f"[retry] sticky_reasoner={pipe._reasoner_base_url}")

    results = []
    for qid in target_qids:
        q = qbi.get(qid)
        if not q:
            print(f"  [{qid}] not found in queries — skip")
            continue
        bid = q["bundle_id"]
        bdict = bbi.get(bid)
        if not bdict:
            print(f"  [{qid}] bundle {bid} missing — skip")
            continue

        docs = [
            Doc(
                doc_id=d["doc_id"],
                title=d["title"],
                content=d["content"],
                page_id=d.get("page_id", ""),
            )
            for d in bdict["docs"]
        ]
        bundle = Bundle(
            bundle_id=bdict["bundle_id"],
            source=bdict["source"],
            docs=docs,
            metadata=bdict.get("metadata", {}),
        )

        t0 = time.time()
        try:
            vo = pipe.run(q["query"], bundle, query_type=q.get("query_type"), query_id=qid)
            dur = time.time() - t0
            syntax_ok, _ = _check_syntax(vo.viz_type, vo.viz_dsl)
            has_dsl = bool(vo.viz_dsl and len(vo.viz_dsl) >= 20)
            ok = has_dsl and syntax_ok
            results.append({
                "qid": qid,
                "ok": ok,
                "ok_relaxed": has_dsl,
                "viz_type": vo.viz_type,
                "viz_dsl_len": len(vo.viz_dsl or ""),
                "syntax_valid": syntax_ok,
                "tokens_out": vo.tokens_out,
                "duration": dur,
                "errors": vo.errors[:2] if vo.errors else [],
            })
            if args.write_raw:
                rec = _record_from_vizout(q, "S4_AgenticTMGv4_consolidated", vo, dur)
                with open(args.write_raw, "a") as raw_f:
                    raw_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            tag = "OK" if ok else ("REL" if has_dsl else "FAIL")
            print(
                f"  [{qid}] {tag:4s} viz_type={vo.viz_type:25s} "
                f"dsl_len={len(vo.viz_dsl or ''):5d} syntax={'Y' if syntax_ok else 'N'} "
                f"tokens={vo.tokens_out:6d} dur={dur:5.1f}s"
            )
        except Exception as e:
            dur = time.time() - t0
            results.append({"qid": qid, "ok": False, "ok_relaxed": False,
                          "exception": f"{type(e).__name__}: {e}", "duration": dur})
            print(f"  [{qid}] EXC  {type(e).__name__}: {str(e)[:100]} dur={dur:.1f}s")

    n_ok = sum(1 for r in results if r.get("ok"))
    n_rel = sum(1 for r in results if r.get("ok_relaxed"))
    n = len(results)
    print()
    print(f"[retry] strict OK (viz_dsl + syntax_valid): {n_ok}/{n} ({100*n_ok//max(1,n)}%)")
    print(f"[retry] relaxed OK (viz_dsl >= 20 chars):    {n_rel}/{n} ({100*n_rel//max(1,n)}%)")

    json.dump({"results": results, "n_ok": n_ok, "n_relaxed": n_rel, "n": n},
              open(args.out, "w"), indent=2)
    print(f"[retry] → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
