"""Batch render + CLIPScore for all Layer A viz records.

Pipeline:
  1. For each viz record with non-empty viz_dsl, render to PNG.
  2. Compute CLIPScore (ViT-L-14 + Hessel rescaling) between PNG and a
     text summary derived from query + DSL elements.
  3. Persist results to outputs/prototype/clip_scores/all.json.

Skips records that already have a CLIPScore entry. Skips fail records
(empty viz_dsl).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--viz", default="outputs/prototype/viz/all.json")
    ap.add_argument("--queries", default="data/prototype/queries/all.json")
    ap.add_argument("--out-dir", default="outputs/prototype/clip_scores")
    ap.add_argument("--render-dir", default="outputs/prototype/renders")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[2]
    os.chdir(repo)
    sys.path.insert(0, str(repo))

    # Force CPU for CLIP (cudnn mismatch documented earlier)
    os.environ.setdefault("DOCVIZ_CLIP_DEVICE", "cpu")

    from code.metrics.clipscore import compute_clipscore
    from code.render import render

    render_dir = Path(args.render_dir)
    out_dir = Path(args.out_dir)
    render_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "all.json"

    viz = json.load(open(args.viz))
    queries = {q["query_id"]: q for q in json.load(open(args.queries))}
    current_qids = set(queries.keys())

    # Filter: current-qid + non-empty viz_dsl
    todo = [
        r for r in viz
        if r.get("query_id") in current_qids
        and len(r.get("viz_dsl") or "") >= 20
        and r.get("viz_type")
    ]
    if args.limit > 0:
        todo = todo[: args.limit]
    print(f"[clip] {len(todo)} records to process")

    # Load existing
    existing = {}
    if out_path.exists():
        try:
            for rec in json.load(open(out_path)):
                existing[(rec["query_id"], rec["strategy"])] = rec
        except Exception:
            pass
    print(f"[clip] existing scores: {len(existing)}")

    todo = [r for r in todo if (r["query_id"], r["strategy"]) not in existing]
    print(f"[clip] new to process: {len(todo)}")

    # Single worker for CLIP (model is process-global); render in workers though
    def process_one(rec):
        qid = rec["query_id"]; strat = rec["strategy"]
        png_path = render_dir / f"{strat}__{qid}.png"
        t0 = time.time()
        if not png_path.exists():
            try:
                rr = render(rec["viz_type"], rec["viz_dsl"], str(png_path))
                if not rr.success:
                    return {"query_id": qid, "strategy": strat,
                            "stage": "render", "success": False,
                            "error": rr.error[:200], "duration": time.time() - t0}
            except Exception as e:
                return {"query_id": qid, "strategy": strat,
                        "stage": "render", "success": False,
                        "error": f"{type(e).__name__}: {e}"[:200],
                        "duration": time.time() - t0}

        # compute_clipscore takes (image_path, record_dict)
        record_for_clip = {
            "viz_dsl": rec.get("viz_dsl"),
            "viz_type": rec.get("viz_type"),
            "query": queries.get(qid, {}).get("query", ""),
        }
        try:
            cs = compute_clipscore(str(png_path), record_for_clip)
            return {"query_id": qid, "strategy": strat,
                    "viz_type": rec.get("viz_type"),
                    "render_success": True,
                    "clip_score_raw": cs.score,
                    "clip_score_hessel": max(2.5 * max(cs.score, 0), 0),
                    "success": cs.success,
                    "duration": time.time() - t0}
        except Exception as e:
            return {"query_id": qid, "strategy": strat,
                    "stage": "clip", "success": False,
                    "error": f"{type(e).__name__}: {e}"[:200],
                    "duration": time.time() - t0}

    # Render in parallel; CLIP is serial (model is global)
    new_recs = []
    n_done = 0
    for rec in todo:
        result = process_one(rec)
        new_recs.append(result)
        existing[(result["query_id"], result["strategy"])] = result
        n_done += 1
        if n_done % 50 == 0 or n_done == len(todo):
            # Persist
            all_recs = list(existing.values())
            json.dump(all_recs, open(out_path, "w"), ensure_ascii=False, indent=2)
            ok = sum(1 for r in new_recs if r.get("clip_score_raw") is not None)
            fail = len(new_recs) - ok
            print(f"  [{n_done}/{len(todo)}] ok={ok} fail={fail} latest={result.get('query_id')[:40]} score={result.get('clip_score_raw')}")

    # Final write
    all_recs = list(existing.values())
    json.dump(all_recs, open(out_path, "w"), ensure_ascii=False, indent=2)
    print(f"[clip] wrote {len(all_recs)} records → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
