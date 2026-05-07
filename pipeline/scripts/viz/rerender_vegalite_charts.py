"""Force re-render all Vega-Lite-source chart docs in data/gold/chart.

Background: docs whose `_source.txt` is a Vega-Lite JSON spec were rendered
in an earlier batch via vl-convert-python. The vl-convert font cache
silently drops text whose spec-level font (e.g. "Arial") cannot be
resolved. `render_vegalite` now registers Noto/DejaVu directories and
coerces unresolvable spec fonts to "sans-serif". This script re-emits
PNGs for the affected docs.

Run:
    python -m scripts.viz.rerender_vegalite_charts [--workers 4]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from scripts.utils.rendering import render_vegalite

GOLD_CHART = os.path.join(ROOT, "data", "gold", "chart")


def _is_vegalite(path: str) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(400)
    except OSError:
        return False
    head = head.lstrip()
    return head.startswith("{") and "vega-lite" in head


def render_one(doc_id: str) -> tuple[str, bool, str]:
    src = os.path.join(GOLD_CHART, f"{doc_id}_source.txt")
    if not os.path.exists(src):
        return doc_id, False, "no source.txt"
    try:
        with open(src, encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as e:
        return doc_id, False, f"json parse: {e}"
    res = render_vegalite(spec, GOLD_CHART, doc_id=doc_id, fmt="png", scale=2.0)
    if not res.get("success"):
        return doc_id, False, str(res.get("error") or "?")
    return doc_id, True, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    todo = []
    for f in sorted(glob.glob(os.path.join(GOLD_CHART, "*_source.txt"))):
        if _is_vegalite(f):
            todo.append(os.path.basename(f).replace("_source.txt", ""))
    if args.limit:
        todo = todo[: args.limit]
    print(f"[rerender-vl] {len(todo)} Vega-Lite chart docs to re-render")

    ok, fail = 0, 0
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(render_one, d): d for d in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            d, success, err = fut.result()
            if success:
                ok += 1
            else:
                fail += 1
                failures.append((d, err))
            if i % 25 == 0 or i == len(futs):
                print(f"  {i}/{len(futs)}  OK={ok} FAIL={fail}")

    print(f"\n[rerender-vl] DONE: OK={ok} FAIL={fail}")
    for d, e in failures[:15]:
        print(f"  {d}: {e}")


if __name__ == "__main__":
    main()
