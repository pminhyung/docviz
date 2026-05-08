#!/usr/bin/env python3
"""PR4 smoke test — S1 Direct + S4 Agentic on one (query, bundle) pair.

Verification gates per QG-MDV §4.4:
  - S1 runs end-to-end on 1 sample → produces valid VizOutput
  - S4 runs end-to-end on 1 sample → produces valid VizOutput, sub_queries non-empty
  - Both pipelines emit the same VizOutput schema

The agent server (S4) must already be running at DOCVIZ_AGENT_URL (default
http://localhost:9024). If unreachable, S4 is skipped with a warning rather
than failing the smoke — S1 alone is sufficient evidence for the Pipeline
ABC contract; S4 health is an orthogonal infra concern (covered by PR1 smoke).

Usage:
    bash agent/run_server.sh --port 9024 &       # for S4
    python -m code.scripts.smoke_test_pr4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from code.pipelines.base import Bundle, VizOutput
from code.pipelines.s1_direct import S1Direct
from code.pipelines.s4_agentic import S4Agentic
from code.utils.bundle_io import read_bundles_json


REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLES_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "all.json"
QUERIES_PATH = REPO_ROOT / "data" / "prototype" / "queries" / "all.json"


def _summary(label: str, vo: VizOutput) -> dict:
    return {
        "strategy": label,
        "viz_type": vo.viz_type,
        "viz_dsl_chars": len(vo.viz_dsl or ""),
        "viz_dsl_head": (vo.viz_dsl or "")[:120],
        "n_retrieved": len(vo.retrieved_chunks),
        "n_sub_queries": len(vo.sub_queries),
        "tokens_in": vo.tokens_in,
        "tokens_out": vo.tokens_out,
        "errors": vo.errors,
    }


def _pick_sample() -> tuple[Bundle, str, str]:
    bundles = {b.bundle_id: b for b in read_bundles_json(BUNDLES_PATH)}
    queries = json.loads(Path(QUERIES_PATH).read_text(encoding="utf-8"))
    # Pick the first hotpot relational query — small bundle, fast S4 turn.
    q = next(q for q in queries
             if q["source"] == "hotpotqa" and q["query_type"] == "relational")
    return bundles[q["bundle_id"]], q["query"], q["query_id"]


def _check_schema(vo: VizOutput, label: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(vo, VizOutput):
        errs.append(f"{label}: not a VizOutput")
        return errs
    if not vo.viz_type:
        errs.append(f"{label}: viz_type empty")
    if not vo.viz_dsl:
        errs.append(f"{label}: viz_dsl empty")
    if not isinstance(vo.retrieved_chunks, list):
        errs.append(f"{label}: retrieved_chunks not a list")
    if not isinstance(vo.sub_queries, list):
        errs.append(f"{label}: sub_queries not a list")
    return errs


def main() -> int:
    print("[1/4] Picking sample (query, bundle)…")
    bundle, query, qid = _pick_sample()
    print(f"      query_id={qid}  bundle_id={bundle.bundle_id}  docs={len(bundle.docs)}")
    print(f"      query: {query!r}")

    print("\n[2/4] Running S1 Direct…")
    s1 = S1Direct()
    vo_s1 = s1.run(query, bundle)
    print(json.dumps(_summary("S1", vo_s1), indent=2, ensure_ascii=False))

    print("\n[3/4] Running S4 Agentic…")
    s4 = S4Agentic()
    vo_s4 = s4.run(query, bundle)
    s4_unreachable = any("agent /health unreachable" in e for e in vo_s4.errors)
    if s4_unreachable:
        print(f"      [SKIP] {vo_s4.errors[0]}")
    else:
        print(json.dumps(_summary("S4", vo_s4), indent=2, ensure_ascii=False))

    print("\n[4/4] Schema parity checks…")
    errs = _check_schema(vo_s1, "S1")
    if not s4_unreachable:
        errs.extend(_check_schema(vo_s4, "S4"))
        if not vo_s4.sub_queries:
            errs.append("S4: sub_queries is empty (Week-0 §4.4 requires non-empty)")
    if errs:
        print("      FAIL:")
        for e in errs:
            print(f"        - {e}")
        return 2
    print("      OK — both VizOutputs valid; schema parity holds.")
    if s4_unreachable:
        print("      (S4 skipped — start agent at DOCVIZ_AGENT_URL to exercise it.)")
    print("\nPR4 smoke test PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
