#!/usr/bin/env python3
"""PR6 — Run checklist judge across the 120-record viz batch.

Pipeline (per PAPER_MASTER_SPEC §8.1, action guide §6):
  1. Load the 120 viz records (outputs/prototype/viz/all.json).
  2. For each unique (query_id, strategy_class) pair, generate ONE checklist
     (cached by key). 60 queries × 2 strategy classes = 120 checklists,
     but in practice agentic and non_agentic share most items + add the
     search_query_quality axis only for agentic.
  3. For each viz record, score the matching checklist in one LLM call.
  4. Aggregate axis scores per record, write to
     outputs/prototype/judge_scores/all.json.

Output schema per record:
  {query_id, bundle_id, source, query_type, strategy, viz_type,
   axis_scores: {faithfulness, coverage, type_appropriateness,
                 search_query_quality?},
   overall, n_items, scored: [...]}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from code.adapters.agent_client import QwenDirectClient
from code.judge.checklist_gen import generate_checklist
from code.judge.dsl_parser import parse_viz
from code.judge.scorer import score_checklist
from code.utils.bundle_io import read_bundles_json


REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLES_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "all.json"
VIZ_PATH = REPO_ROOT / "outputs" / "prototype" / "viz" / "all.json"
OUT_DIR = REPO_ROOT / "outputs" / "prototype" / "judge_scores"
OUT_PATH = OUT_DIR / "all.json"
CHECKLIST_PATH = OUT_DIR / "checklists.json"
RAW_PATH = OUT_DIR / "raw.jsonl"


def _strategy_class(strategy: str) -> str:
    return "agentic" if "S4" in strategy else "non_agentic"


def _checklist_key(query_id: str, strategy_class: str) -> str:
    return f"{query_id}::{strategy_class}"


def _bundle_docs(bundle) -> List[Dict[str, Any]]:
    return [
        {"doc_id": d.doc_id, "title": d.title, "content": d.content}
        for d in bundle.docs
    ]


def _load_checklist_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_checklist_cache(path: Path, cache: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_existing_scored(path: Path) -> Dict[Tuple[str, str], Dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(r["query_id"], r["strategy"]): r for r in data}


def _append_raw(rec: Dict[str, Any], raw_path: Path) -> None:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with open(raw_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _build_checklists(
    viz_records: List[Dict[str, Any]],
    bundles_by_id: Dict[str, Any],
    cache: Dict[str, Any],
    workers: int,
    raw_path: Path,
) -> Dict[str, Any]:
    """Generate (or reuse cached) checklists keyed by (query_id, strategy_class)."""
    needed: List[Tuple[str, str, Dict[str, Any]]] = []   # (key, strategy_class, viz_rec)
    seen_keys = set()
    for r in viz_records:
        sc = _strategy_class(r["strategy"])
        key = _checklist_key(r["query_id"], sc)
        if key in cache or key in seen_keys:
            continue
        seen_keys.add(key)
        needed.append((key, sc, r))

    print(f"[judge] checklists: {len(cache)} cached, {len(needed)} to generate")

    def _gen(arg):
        key, sc, viz_rec = arg
        b = bundles_by_id[viz_rec["bundle_id"]]
        out = generate_checklist(
            query=viz_rec["query"],
            query_type=viz_rec["query_type"],
            docs=_bundle_docs(b),
            strategy_class=sc,
            client=QwenDirectClient(),
        )
        return key, out

    if not needed:
        return cache

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_gen, n): n for n in needed}
        done = 0
        for fut in as_completed(futures):
            done += 1
            key, out = fut.result()
            cache[key] = out
            _append_raw({"phase": "checklist", "key": key, **out}, raw_path)
            print(f"  [checklist {done:>3d}/{len(needed):>3d}] {key:<40s} "
                  f"items={out['n_items']}/{out['n_target']}  "
                  f"tok_in={out['tokens_in']:>5d} tok_out={out['tokens_out']:>4d}")
    return cache


def _score_record(
    viz_rec: Dict[str, Any],
    bundle,
    checklist: List[Dict[str, Any]],
) -> Dict[str, Any]:
    parsed = parse_viz(viz_rec["viz_type"], viz_rec["viz_dsl"])
    t0 = time.time()
    out = score_checklist(
        query=viz_rec["query"],
        query_type=viz_rec["query_type"],
        strategy=viz_rec["strategy"],
        docs=_bundle_docs(bundle),
        viz_dsl=viz_rec["viz_dsl"],
        viz_parsed=parsed,
        sub_queries=viz_rec.get("sub_queries") or [],
        checklist=checklist,
        client=QwenDirectClient(),
    )
    return {
        "query_id": viz_rec["query_id"],
        "bundle_id": viz_rec["bundle_id"],
        "source": viz_rec["source"],
        "query_type": viz_rec["query_type"],
        "strategy": viz_rec["strategy"],
        "viz_type": viz_rec["viz_type"],
        "syntax_valid": viz_rec.get("syntax_valid", False),
        "viz_parsed_summary": parsed.get("summary", ""),
        "axis_scores": out["axis_scores"],
        "overall": out["overall"],
        "n_items": len(out["scored"]),
        "scored": out["scored"],
        "tokens_in": out["tokens_in"],
        "tokens_out": out["tokens_out"],
        "duration_seconds": round(time.time() - t0, 3),
    }


def _summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_strategy: Dict[str, Dict[str, Any]] = {}
    axis_keys = ("faithfulness", "coverage", "type_appropriateness",
                 "search_query_quality")
    for r in records:
        s = by_strategy.setdefault(r["strategy"], {
            "n": 0,
            "overall_sum": 0.0,
            "axes": {ax: {"sum": 0.0, "n": 0} for ax in axis_keys},
        })
        s["n"] += 1
        if r["overall"] is not None:
            s["overall_sum"] += r["overall"]
        for ax, v in r["axis_scores"].items():
            s["axes"][ax]["sum"] += v
            s["axes"][ax]["n"] += 1
    out: Dict[str, Any] = {}
    for label, s in by_strategy.items():
        n = max(s["n"], 1)
        axes = {ax: round(d["sum"] / d["n"], 4) for ax, d in s["axes"].items() if d["n"] > 0}
        out[label] = {
            "n": s["n"],
            "mean_overall": round(s["overall_sum"] / n, 4),
            "mean_axis_scores": axes,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Run checklist judge over viz batch.")
    ap.add_argument("--viz", default=str(VIZ_PATH))
    ap.add_argument("--bundles", default=str(BUNDLES_PATH))
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--checklist-cache", default=str(CHECKLIST_PATH))
    ap.add_argument("--raw", default=str(RAW_PATH))
    ap.add_argument("--limit", type=int, default=0,
                    help="If >0, only score the first N viz records (smoke).")
    ap.add_argument("--checklist-workers", type=int, default=3)
    ap.add_argument("--score-workers", type=int, default=3)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    bundles = {b.bundle_id: b for b in read_bundles_json(args.bundles)}
    viz_records: List[Dict[str, Any]] = json.loads(Path(args.viz).read_text(encoding="utf-8"))
    if args.limit > 0:
        viz_records = viz_records[: args.limit]
    print(f"[judge] {len(bundles)} bundles, {len(viz_records)} viz records")

    cache = {} if args.force else _load_checklist_cache(Path(args.checklist_cache))
    cache = _build_checklists(
        viz_records, bundles, cache,
        workers=args.checklist_workers,
        raw_path=Path(args.raw),
    )
    _save_checklist_cache(Path(args.checklist_cache), cache)
    print(f"[judge] checklist cache size: {len(cache)} → {args.checklist_cache}")

    existing = {} if args.force else _load_existing_scored(Path(args.out))
    if existing:
        print(f"[judge] resume: {len(existing)} scored records already in {args.out}")

    todo: List[Dict[str, Any]] = [
        r for r in viz_records
        if (r["query_id"], r["strategy"]) not in existing
    ]
    print(f"[judge] scoring: {len(todo)} new records")

    def _score_worker(viz_rec):
        sc = _strategy_class(viz_rec["strategy"])
        key = _checklist_key(viz_rec["query_id"], sc)
        cl = cache.get(key, {}).get("checklist") or []
        b = bundles[viz_rec["bundle_id"]]
        return _score_record(viz_rec, b, cl)

    new_scored: List[Dict[str, Any]] = []
    raw_path = Path(args.raw)
    with ThreadPoolExecutor(max_workers=args.score_workers) as ex:
        futures = {ex.submit(_score_worker, r): r for r in todo}
        done = 0
        for fut in as_completed(futures):
            done += 1
            scored = fut.result()
            new_scored.append(scored)
            existing[(scored["query_id"], scored["strategy"])] = scored
            _append_raw({"phase": "score", **scored}, raw_path)
            ax_str = " ".join(
                f"{ax[:4]}={v:.2f}" for ax, v in scored["axis_scores"].items()
            )
            print(f"  [score {done:>3d}/{len(todo):>3d}] {scored['query_id']:<28s} "
                  f"{scored['strategy']:<11s} overall={scored['overall']:.2f}  {ax_str}  "
                  f"t={scored['duration_seconds']:>5.1f}s")
            # Persist after each record so a kill mid-run doesn't lose work.
            merged = list(existing.values())
            merged.sort(key=lambda r: (r["bundle_id"], r["query_type"], r["strategy"]))
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(
                json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8",
            )

    merged = list(existing.values())
    merged.sort(key=lambda r: (r["bundle_id"], r["query_type"], r["strategy"]))
    print(f"[judge] final: {len(merged)} scored records → {args.out}")
    print(f"[judge] §6.4 summary:\n{json.dumps(_summary(merged), ensure_ascii=False, indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
