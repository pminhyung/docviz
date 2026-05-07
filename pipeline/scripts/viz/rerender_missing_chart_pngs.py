"""Re-render all missing _rendered.png files for chart gold artefacts.

Pre-conditions:
- chart sidecar at :3005 supports area/radar/doughnut (templates.js + parser.js)
- _extract_chart_dsl strips leading `%% ...` comment lines (diagram_tools.py)

For every doc in corpus.jsonl with viz_type=chart:
  - if data/gold/chart/<doc>_rendered.png missing:
      1. read _source.txt
      2. call sidecar /render-chart → HTML bytes
      3. chrome headless --screenshot → PNG

Run:
    python -m scripts.viz.rerender_missing_chart_pngs [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from examples.diagram.diagram_tools import _extract_chart_dsl

CORPUS = os.path.join(ROOT, "data", "documents", "corpus.jsonl")
GOLD_CHART = os.path.join(ROOT, "data", "gold", "chart")
SIDECAR = "http://localhost:3005"
CHROMIUM = "/usr/bin/google-chrome"


def render_one(doc_id: str, subtype: str) -> tuple[str, bool, str]:
    src_path = os.path.join(GOLD_CHART, f"{doc_id}_source.txt")
    if not os.path.exists(src_path):
        return doc_id, False, "no source.txt"
    with open(src_path, encoding="utf-8") as f:
        raw = f.read()

    dsl = _extract_chart_dsl(raw, subtype)

    payload = json.dumps({"chart_source": dsl, "theme": "corporate"}).encode()
    req = urllib.request.Request(f"{SIDECAR}/render-chart", method="POST",
                                  headers={"Content-Type": "application/json"},
                                  data=payload)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            ct = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = str(e)
        return doc_id, False, f"sidecar HTTP {e.code}: {err_body[:200]}"
    except Exception as e:
        return doc_id, False, f"sidecar {type(e).__name__}: {e}"

    html_bytes = body
    if "json" in ct:
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
            if "error" in data:
                return doc_id, False, f"sidecar error: {data['error']}"
            html_bytes = data.get("html", "").encode("utf-8")
        except Exception as e:
            return doc_id, False, f"json parse: {e}"

    if not html_bytes:
        return doc_id, False, "empty html"

    html_out = os.path.join(GOLD_CHART, f"{doc_id}_rendered.html")
    with open(html_out, "wb") as f:
        f.write(html_bytes)

    png_out = os.path.join(GOLD_CHART, f"{doc_id}_rendered.png")
    with tempfile.NamedTemporaryFile("wb", suffix=".html", delete=False) as tf:
        tf.write(html_bytes)
        tmp_html = tf.name
    try:
        cmd = [
            CHROMIUM, "--headless", "--no-sandbox", "--disable-gpu",
            "--hide-scrollbars", "--window-size=1600,1000",
            "--default-background-color=FFFFFFFF",
            "--virtual-time-budget=4000",
            f"--screenshot={png_out}",
            f"file://{tmp_html}",
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        if proc.returncode != 0:
            return doc_id, False, f"chrome rc={proc.returncode}: {proc.stderr[:160]!r}"
        if not (os.path.exists(png_out) and os.path.getsize(png_out) > 1024):
            return doc_id, False, "screenshot too small"
        return doc_id, True, ""
    except subprocess.TimeoutExpired:
        return doc_id, False, "chrome timeout"
    finally:
        try:
            os.unlink(tmp_html)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true",
                     help="re-render even if PNG already exists")
    args = ap.parse_args()

    corpus = [json.loads(l) for l in open(CORPUS) if l.strip()]
    todo = []
    for r in corpus:
        d = r["doc_id"]
        st = r.get("chart_subtype", "bar")
        png = os.path.join(GOLD_CHART, f"{d}_rendered.png")
        src = os.path.join(GOLD_CHART, f"{d}_source.txt")
        if not os.path.exists(src):
            continue
        if os.path.exists(png) and not args.force:
            continue
        todo.append((d, st))
    if args.limit:
        todo = todo[: args.limit]
    print(f"[rerender-png] {len(todo)} chart docs need re-rendering "
           f"({args.workers} workers)")

    ok = []
    fail = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(render_one, d, s): d for d, s in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            doc_id, success, err = fut.result()
            if success:
                ok.append(doc_id)
            else:
                fail.append((doc_id, err))
            if i % 25 == 0 or i == len(futs):
                print(f"  {i}/{len(futs)}  OK={len(ok)} FAIL={len(fail)}")

    print(f"\n[rerender-png] DONE: {len(ok)} succeeded, {len(fail)} failed")
    if fail:
        print("\nfirst failures:")
        for d, e in fail[:15]:
            print(f"  {d}: {e}")
        with open(os.path.join(ROOT, "logs", "rerender_chart_pngs_failures.jsonl"),
                  "w", encoding="utf-8") as f:
            for d, e in fail:
                f.write(json.dumps({"doc_id": d, "error": e}) + "\n")
        print(f"\nfull failure log: logs/rerender_chart_pngs_failures.jsonl")


if __name__ == "__main__":
    main()
