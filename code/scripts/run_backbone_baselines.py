"""Run direct-call baselines (S1/S7) with a non-Qwen backbone on full 300.

Used for cross-backbone SOTA verification: agent (B6) runs via the server-
side backbone swap (env QWEN_HOSTS / QWEN3_MODEL_ID), but direct-call
baselines (S1_Direct, S7_SelfRefine) need their `client=` arg set to a
backbone-specific QwenDirectClient.

Usage:
  python -m code.scripts.run_backbone_baselines \\
      --backbone deepseek \\
      --bundles data/prototype/bundles/all.json \\
      --queries data/prototype/queries/all.json \\
      --out outputs/v0.4_backbone_compare/viz/deepseek_baselines.json \\
      --raw outputs/v0.4_backbone_compare/viz/deepseek_baselines.raw.jsonl \\
      --strategies S1,S7 \\
      --workers 8
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from code.adapters.multi_llm_clients import get_vllm_client, _resolve_model
from code.utils.bundle_io import read_bundles_json
from code.pipelines.s1_direct import S1Direct
from code.pipelines.s7_self_refine import S7SelfRefine
from code.pipelines.base import Bundle
from code.run_prototype import _record_from_vizout, _run_one, _append_raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backbone", required=True, choices=["qwen", "deepseek", "gemma3"])
    ap.add_argument("--bundles", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--strategies", default="S1,S7",
                    help="comma-separated subset of {S1,S7}")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    bundles = {b.bundle_id: b for b in read_bundles_json(args.bundles)}
    queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    print(f"[backbone_baselines] backbone={args.backbone}  bundles={len(bundles)}  queries={len(queries)}", flush=True)

    client = get_vllm_client(args.backbone)
    model_id = _resolve_model(args.backbone)
    print(f"[backbone_baselines] using model={model_id}, hosts={client._hosts if hasattr(client, '_hosts') else '?'}", flush=True)

    strategy_factories = {
        "S1": ("S1_Direct", lambda: S1Direct(client=client, model=model_id)),
        "S7": ("S7_SelfRefine", lambda: S7SelfRefine(client=client, model=model_id)),
    }

    selected = [s.strip() for s in args.strategies.split(",") if s.strip()]
    out_path = Path(args.out)
    raw_path = Path(args.raw)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("")

    pairs = [(q, bundles[q["bundle_id"]]) for q in queries]
    all_records: List[Dict[str, Any]] = []

    for sel in selected:
        if sel not in strategy_factories:
            print(f"[backbone_baselines] skip unknown strategy: {sel}", flush=True)
            continue
        name, factory = strategy_factories[sel]
        print(f"\n[backbone_baselines] === {name} ===  (workers={args.workers})", flush=True)
        t0 = time.time()

        def _worker(qb):
            q, b = qb
            return _run_one(factory(), q, b, name)

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(_worker, qb): qb for qb in pairs}
            done = 0
            for fut in as_completed(futures):
                done += 1
                rec = fut.result()
                all_records.append(rec)
                _append_raw(rec, raw_path)
                print(f"  [{name} {done:>3d}/{len(pairs):>3d}] {rec['query_id']:<28s} "
                      f"syntax={'Y' if rec['syntax_valid'] else 'N'} "
                      f"tok_out={rec['tokens_out']:>5d} t={rec['duration_seconds']:>5.1f}s "
                      f"err={len(rec['errors'])}", flush=True)
        print(f"[backbone_baselines] {name} done in {time.time()-t0:.0f}s", flush=True)

    all_records.sort(key=lambda r: (r["bundle_id"], r["query_type"], r["strategy"]))
    out_path.write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[backbone_baselines] wrote {len(all_records)} records → {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
