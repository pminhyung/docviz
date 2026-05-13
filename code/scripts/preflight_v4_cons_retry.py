"""Preflight test for the V4_cons Mode A retry fix (Fix 2).

Tests s4_agentic_tmg.py's new "empty final_answer + 0 tokens + <5s duration →
retry once on different reasoner host" logic on 5 known Mode A fail records
from Layer A. Acceptance: ≥3/5 produce non-empty viz_dsl on retry → confirms
the infrastructure-error-masking hypothesis from
docs/analysis/v4_cons_fail_root_cause.md.

Run:
  QWEN_HOSTS=10.1.211.148:8000,10.1.211.163:8000,10.1.211.164:8000,10.1.211.165:8000,10.1.211.166:8000,10.1.211.167:8000,10.1.211.168:8000,10.1.211.169:8000,10.1.211.170:8000 \\
  DOCVIZ_HOST_MODE=multi \\
  DOCVIZ_AGENT_URL=http://localhost:9037 \\
  python -m code.scripts.preflight_v4_cons_retry
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# 5 known Mode A fail query_ids from Layer A. All had:
#   tokens_out=0, duration~2s, errors=["agent returned empty final_answer", ...]
TARGET_QIDS = [
    "hotpot_22_relational",
    "hotpot_31_comparative",
    "hotpot_40_comparative",
    "multinews_17_temporal",
    "govreport_24_temporal",
]


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))

    from code.pipelines.base import Bundle, Doc
    from code.pipelines.s4_agentic_tmg import S4AgenticTMG

    # Load queries and bundles
    queries = json.load(open(repo / "data/prototype/queries/all.json"))
    queries_by_id = {q["query_id"]: q for q in queries}

    bundles = json.load(open(repo / "data/prototype/bundles/all.json"))
    bundles_by_id = {b["bundle_id"]: b for b in bundles}

    print(f"[preflight] loaded {len(queries)} queries, {len(bundles)} bundles")

    pipeline = S4AgenticTMG(mode="v4_consolidated")
    print(f"[preflight] pipeline base_url={pipeline._base_url} sticky_reasoner={pipeline._reasoner_base_url}")

    results = []
    for qid in TARGET_QIDS:
        q = queries_by_id.get(qid)
        if not q:
            print(f"  [{qid}] not found in gold.json — skipping")
            continue
        bundle_id = q.get("bundle_id")
        bdict = bundles_by_id.get(bundle_id)
        if not bdict:
            print(f"  [{qid}] bundle {bundle_id} not found — skipping")
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
            vo = pipeline.run(
                q["query"],
                bundle,
                query_type=q.get("query_type"),
                query_id=qid,
            )
            dur = time.time() - t0
            success = bool(vo.viz_dsl and len(vo.viz_dsl) >= 20)
            results.append({
                "qid": qid,
                "success": success,
                "viz_type": vo.viz_type,
                "viz_dsl_len": len(vo.viz_dsl or ""),
                "tokens_out": vo.tokens_out,
                "duration": dur,
                "errors": vo.errors[:2] if vo.errors else [],
            })
            tag = "OK" if success else "FAIL"
            print(
                f"  [{qid}] {tag:4s} viz_type={vo.viz_type:25s} "
                f"dsl_len={len(vo.viz_dsl or ''):6d} tokens={vo.tokens_out:6d} "
                f"dur={dur:5.1f}s err={vo.errors[:1]}"
            )
        except Exception as e:
            dur = time.time() - t0
            results.append({
                "qid": qid,
                "success": False,
                "exception": f"{type(e).__name__}: {e}",
                "duration": dur,
            })
            print(f"  [{qid}] EXC  {type(e).__name__}: {e} (dur={dur:.1f}s)")

    n_ok = sum(1 for r in results if r.get("success"))
    n = len(results)
    print()
    print(f"[preflight] result: {n_ok}/{n} succeeded on retry-enabled pipeline")
    print(f"[preflight] acceptance threshold: ≥3/5 (60%)")
    print(f"[preflight] verdict: {'PASS — proceed with full Mode A re-batch' if n_ok >= 3 else 'FAIL — investigate before re-batch'}")

    out = repo / "docs/analysis/v4_cons_retry_preflight.json"
    json.dump({"results": results, "n_ok": n_ok, "n": n}, open(out, "w"), indent=2)
    print(f"[preflight] wrote → {out}")

    return 0 if n_ok >= 3 else 1


if __name__ == "__main__":
    sys.exit(main())
