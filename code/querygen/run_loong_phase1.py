"""Phase-1 query generation for the Loong-30 bundles.

Reuses the validated v0.4.1 query-gen machinery
(exaone/sft_gen/docviz/generate_queries.py) but bypasses compute_quota: each
Loong bundle already carries its Loong-derived `metadata.challenge_type`
(multi_hop / artifact_planning), which we preserve rather than re-randomize.

Multi-host Qwen pool (round-robin, n_concurrent/host) + immediate JSONL flush.

Usage:
    python -m code.querygen.run_loong_phase1 \
        --bundles data/bundles/loong_phase1.json \
        --out data/queries/loong_phase1.jsonl [--limit 2]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from exaone.sft_gen.docviz.generate_queries import (
    HostPool, _worker, DEFAULT_QWEN_HOSTS,
)

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", type=Path, default=REPO / "data/bundles/loong_phase1.json")
    ap.add_argument("--out", type=Path, default=REPO / "data/queries/loong_phase1.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="preflight: only first N bundles")
    ap.add_argument("--hosts", default=",".join(DEFAULT_QWEN_HOSTS))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--model", default="Qwen3.5-397B-A17B-FP8")
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args()

    bundles = json.loads(args.bundles.read_text(encoding="utf-8"))
    if args.limit:
        bundles = bundles[: args.limit]
    # One query per bundle, using the bundle's preserved Loong challenge_type.
    tasks = [(b, b["metadata"]["challenge_type"], i) for i, b in enumerate(bundles)]
    print(f"[loong-qgen] {len(tasks)} bundle×challenge tasks "
          f"({dict(Counter(c for _, c, _ in tasks))})")

    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    pool = HostPool(hosts=hosts, port=args.port, api_key=args.api_key)
    print(f"[loong-qgen] HostPool: {len(hosts)} hosts, workers={args.workers}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    queries, errors = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as ex, \
         args.out.open("w", encoding="utf-8") as fout:
        futs = {ex.submit(_worker, b, c, i, pool, args.model): i for (b, c, i) in tasks}
        done = 0
        for fut in as_completed(futs):
            done += 1
            idx, q, err = fut.result()
            if q is not None:
                fout.write(json.dumps(q.to_dict(), ensure_ascii=False) + "\n")
                fout.flush()
                queries.append(q)
                print(f"  [{done:>2}/{len(tasks)}] {q.qid}  challenge={q.challenge_type}  "
                      f"output={q.output_type}  intents={q.gold_intent_count}")
            else:
                errors.append(err)
                print(f"  [{done:>2}/{len(tasks)}] FAIL — {err}")

    print(f"\n[loong-qgen] WROTE {len(queries)} -> {args.out}  (failed {len(errors)})")
    print(f"[loong-qgen] challenge: {dict(Counter(q.challenge_type for q in queries))}")
    print(f"[loong-qgen] output_type: {dict(Counter(q.output_type for q in queries))}")
    return 0 if len(errors) < max(len(tasks), 1) * 0.10 else 1


if __name__ == "__main__":
    sys.exit(main())
