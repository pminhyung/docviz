#!/usr/bin/env python3
"""PR5 — 120-viz prototype batch (60 queries × {S1 Direct, S4 Agentic}).

Per QG-MDV Week 0 Action Guide §5 (Day 7-8) and PAPER_MASTER_SPEC §3.6 / §5.3:
  - For every (query, bundle) pair, run S1 + S4 to produce a VizOutput.
  - Capture viz_dsl, viz_type, sub_queries, retrieved_chunks, tokens, errors.
  - Add a lightweight DSL syntax check (M1 approximation) — Mermaid header
    sniff or Chart.js JSON parse. Full puppeteer-based render-check is left
    to a separate sidecar pass.
  - Idempotent resume: existing (query_id, strategy) records in the output
    file are skipped unless --force is given.

Concurrency:
  - S1 uses QwenDirectClient (round-robin over 3 vLLM ports) and is
    stateless — run with a small ThreadPool (default workers=3, matches
    port count).
  - S4 calls /v2/run on the agent server; the agent loop is heavier and
    not safe to parallelize aggressively from one process. Keep sequential
    by default (workers=1).

Outputs:
  - outputs/prototype/viz/all.json    (all 120 records)
  - outputs/prototype/viz/raw.jsonl   (append-only audit log)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from code.pipelines.base import Bundle, Pipeline, VizOutput
from code.pipelines.s1_direct import S1Direct
from code.pipelines.s4_agentic import S4Agentic
from code.pipelines.s4_agentic_tmg import S4AgenticTMG
from code.utils.bundle_io import read_bundles_json
from code.utils.cost_tracker import CostTracker


REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLES_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "all.json"
QUERIES_PATH = REPO_ROOT / "data" / "prototype" / "queries" / "all.json"
OUT_DIR = REPO_ROOT / "outputs" / "prototype" / "viz"
OUT_PATH = OUT_DIR / "all.json"
RAW_PATH = OUT_DIR / "raw.jsonl"


# ── DSL syntax sniffers ───────────────────────────────────────────────────


_MERMAID_HEADER_RE = re.compile(
    r"^\s*(graph|flowchart|sequenceDiagram|stateDiagram(?:-v2)?|"
    r"classDiagram|erDiagram|gantt|mindmap|timeline|journey|pie|gitGraph)\b",
    re.MULTILINE,
)
_VALID_CHARTJS_TYPES = {
    "bar", "line", "scatter", "bubble", "pie", "doughnut", "polarArea", "radar",
}


def _check_syntax(viz_type: str, viz_dsl: str) -> Tuple[bool, str]:
    """Return (ok, kind). 'kind' is a short label for the validator that ran."""
    if not viz_dsl:
        return False, "empty"
    if viz_type.startswith("mermaid"):
        m = _MERMAID_HEADER_RE.search(viz_dsl)
        return bool(m), f"mermaid_header:{m.group(1)}" if m else "mermaid_header:miss"
    if viz_type.startswith("chartjs"):
        # viz_dsl may be the JSON string or already-trimmed text.
        try:
            spec = json.loads(viz_dsl)
        except json.JSONDecodeError:
            return False, "chartjs_json:parse_fail"
        t = spec.get("type")
        if not isinstance(spec, dict) or "data" not in spec:
            return False, "chartjs_json:no_data"
        if t not in _VALID_CHARTJS_TYPES:
            return False, f"chartjs_json:unknown_type({t!r})"
        return True, f"chartjs_json:{t}"
    return False, f"unknown_viz_type:{viz_type}"


# ── Record IO ─────────────────────────────────────────────────────────────


def _record_from_vizout(
    q: Dict[str, Any],
    strategy: str,
    vo: VizOutput,
    duration_s: float,
) -> Dict[str, Any]:
    syntax_ok, syntax_kind = _check_syntax(vo.viz_type, vo.viz_dsl)
    return {
        "query_id": q["query_id"],
        "bundle_id": q["bundle_id"],
        "source": q["source"],
        "query_type": q["query_type"],
        "query": q["query"],
        "strategy": strategy,
        "viz_dsl": vo.viz_dsl,
        "viz_type": vo.viz_type,
        "rendered_image_path": vo.rendered_image_path,
        "render_success": vo.render_success,
        "syntax_valid": syntax_ok,
        "syntax_check_kind": syntax_kind,
        "n_retrieved": len(vo.retrieved_chunks),
        "sub_queries": list(vo.sub_queries),
        "n_sub_queries": len(vo.sub_queries),
        "source_attribution_keys": list(vo.source_attribution.keys()),
        "tokens_in": vo.tokens_in,
        "tokens_out": vo.tokens_out,
        "cost_usd": vo.cost_usd,
        "errors": list(vo.errors),
        "duration_seconds": round(duration_s, 3),
    }


def _load_existing(out_path: Path) -> Dict[Tuple[str, str], Dict[str, Any]]:
    if not out_path.exists():
        return {}
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    return {(r["query_id"], r["strategy"]): r for r in data}


def _write_all(records: List[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def _append_raw(rec: Dict[str, Any], raw_path: Path) -> None:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with open(raw_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── Strategy runners ──────────────────────────────────────────────────────


def _run_one(
    pipeline: Pipeline,
    q: Dict[str, Any],
    bundle: Bundle,
    strategy: str,
) -> Dict[str, Any]:
    t0 = time.time()
    try:
        vo = pipeline.run(q["query"], bundle, query_type=q.get("query_type"))
    except Exception as e:
        # Build a degraded VizOutput so downstream code doesn't have to branch
        vo = VizOutput(
            viz_dsl="",
            viz_type="",
            rendered_image_path="",
            render_success=False,
            retrieved_chunks=[],
            sub_queries=[],
            source_attribution={},
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            errors=[f"{type(e).__name__}: {e}"],
        )
    return _record_from_vizout(q, strategy, vo, time.time() - t0)


def _run_strategy_pool(
    label: str,
    pipeline_factory,
    pairs: List[Tuple[Dict[str, Any], Bundle]],
    workers: int,
    raw_path: Path,
) -> List[Dict[str, Any]]:
    print(f"[{label}] running {len(pairs)} pairs (workers={workers})…")
    out: List[Dict[str, Any]] = []
    if workers <= 1:
        pipe = pipeline_factory()
        for i, (q, b) in enumerate(pairs, 1):
            rec = _run_one(pipe, q, b, label)
            out.append(rec)
            _append_raw(rec, raw_path)
            print(f"  [{label} {i:>3d}/{len(pairs):>3d}] {rec['query_id']:<28s}"
                  f" syntax={'Y' if rec['syntax_valid'] else 'N'}"
                  f" tok_out={rec['tokens_out']:>5d}"
                  f" t={rec['duration_seconds']:>5.1f}s"
                  f" err={len(rec['errors'])}")
        return out

    # Pool workers — each gets its own pipeline instance to avoid sharing
    # state (e.g., httpx clients, round-robin counters).
    def _worker(q_b):
        q, b = q_b
        return _run_one(pipeline_factory(), q, b, label)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_worker, qb): qb for qb in pairs}
        done = 0
        for fut in as_completed(futures):
            done += 1
            rec = fut.result()
            out.append(rec)
            _append_raw(rec, raw_path)
            print(f"  [{label} {done:>3d}/{len(pairs):>3d}] {rec['query_id']:<28s}"
                  f" syntax={'Y' if rec['syntax_valid'] else 'N'}"
                  f" tok_out={rec['tokens_out']:>5d}"
                  f" t={rec['duration_seconds']:>5.1f}s"
                  f" err={len(rec['errors'])}")
    return out


# ── Summary ───────────────────────────────────────────────────────────────


def _summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_strategy: Dict[str, Dict[str, Any]] = {}
    for r in records:
        s = by_strategy.setdefault(r["strategy"], {
            "n": 0, "errors": 0, "syntax_ok": 0,
            "tokens_in": 0, "tokens_out": 0,
            "n_sub_queries_total": 0, "duration_total_s": 0.0,
        })
        s["n"] += 1
        if r["errors"]:
            s["errors"] += 1
        if r["syntax_valid"]:
            s["syntax_ok"] += 1
        s["tokens_in"] += r["tokens_in"]
        s["tokens_out"] += r["tokens_out"]
        s["n_sub_queries_total"] += r["n_sub_queries"]
        s["duration_total_s"] += r["duration_seconds"]
    for s in by_strategy.values():
        n = max(s["n"], 1)
        s["error_rate"] = round(s["errors"] / n, 3)
        s["syntax_pass_rate"] = round(s["syntax_ok"] / n, 3)
        s["mean_sub_queries"] = round(s["n_sub_queries_total"] / n, 2)
        s["mean_duration_s"] = round(s["duration_total_s"] / n, 2)
    return {"total": len(records), "by_strategy": by_strategy}


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate 120 prototype viz outputs.")
    ap.add_argument("--bundles", default=str(BUNDLES_PATH))
    ap.add_argument("--queries", default=str(QUERIES_PATH))
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--raw", default=str(RAW_PATH))
    ap.add_argument("--limit", type=int, default=0,
                    help="If >0, only run the first N queries (smoke / debug).")
    ap.add_argument("--strategies", default="S1,S4",
                    help="Comma-separated subset of {S1, S4}.")
    ap.add_argument("--s1-workers", type=int, default=3)
    ap.add_argument("--s4-workers", type=int, default=1)
    ap.add_argument("--force", action="store_true",
                    help="Re-run even if (query_id, strategy) already exists in --out.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero if §5.3 gates fail "
                         "(error_rate > 5%% or syntax_pass_rate < 90%%).")
    args = ap.parse_args()

    bundles = {b.bundle_id: b for b in read_bundles_json(args.bundles)}
    queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    if args.limit > 0:
        queries = queries[: args.limit]
    print(f"[run_prototype] {len(bundles)} bundles, {len(queries)} queries")

    out_path = Path(args.out)
    raw_path = Path(args.raw)
    existing = {} if args.force else _load_existing(out_path)
    if existing:
        print(f"[run_prototype] resume: {len(existing)} records already in {out_path}")

    selected = {s.strip() for s in args.strategies.split(",") if s.strip()}
    pairs = [(q, bundles[q["bundle_id"]]) for q in queries]

    def _checkpoint() -> None:
        merged = list(existing.values())
        merged.sort(key=lambda r: (r["bundle_id"], r["query_type"], r["strategy"]))
        _write_all(merged, out_path)
        print(f"[run_prototype] checkpoint: {len(merged)} records → {out_path}")

    # Dispatch per strategy, skipping already-done pairs unless --force.
    # Checkpoint all.json after each strategy pool so a kill mid-run keeps
    # the completed strategy intact and a restart with --strategies can
    # pick up exactly where we stopped.
    if "S1" in selected:
        s1_pairs = [(q, b) for (q, b) in pairs
                    if (q["query_id"], "S1_Direct") not in existing]
        if s1_pairs:
            new = _run_strategy_pool(
                "S1_Direct", lambda: S1Direct(), s1_pairs,
                workers=args.s1_workers, raw_path=raw_path,
            )
            for r in new:
                existing[(r["query_id"], r["strategy"])] = r
            _checkpoint()
    if "S4" in selected:
        s4_pairs = [(q, b) for (q, b) in pairs
                    if (q["query_id"], "S4_Agentic") not in existing]
        if s4_pairs:
            new = _run_strategy_pool(
                "S4_Agentic", lambda: S4Agentic(), s4_pairs,
                workers=args.s4_workers, raw_path=raw_path,
            )
            for r in new:
                existing[(r["query_id"], r["strategy"])] = r
            _checkpoint()
    if "S4_TMG" in selected:
        s4t_pairs = [(q, b) for (q, b) in pairs
                     if (q["query_id"], "S4_AgenticTMG") not in existing]
        if s4t_pairs:
            new = _run_strategy_pool(
                "S4_AgenticTMG", lambda: S4AgenticTMG(), s4t_pairs,
                workers=args.s4_workers, raw_path=raw_path,
            )
            for r in new:
                existing[(r["query_id"], r["strategy"])] = r
            _checkpoint()

    merged = list(existing.values())
    merged.sort(key=lambda r: (r["bundle_id"], r["query_type"], r["strategy"]))
    print(f"[run_prototype] final: {len(merged)} records in {out_path}")

    summary = _summarize(merged)
    print(f"[run_prototype] summary: {json.dumps(summary, ensure_ascii=False, indent=2)}")

    if args.strict:
        for label, s in summary["by_strategy"].items():
            if s["error_rate"] > 0.05:
                print(f"[run_prototype] STRICT FAIL: {label} error_rate "
                      f"{s['error_rate']:.3f} > 0.05")
                return 2
            if s["syntax_pass_rate"] < 0.90:
                print(f"[run_prototype] STRICT FAIL: {label} syntax_pass_rate "
                      f"{s['syntax_pass_rate']:.3f} < 0.90")
                return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
