#!/usr/bin/env python3
"""D13 — Reference verification sanity queries.

Walks data/gold/ and reports:
  1. corpus.jsonl subtype field coverage
  2. per-viz source/rendered counts
  3. Vega-Lite JSON parse rate for chart
  4. failure counts from failures.jsonl
  5. CJK leakage in mindmap sources (corpus is EN-only)
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.config import DATA_DIR


CORPUS = os.path.join(DATA_DIR, "documents", "corpus.jsonl")
GOLD = os.path.join(DATA_DIR, "gold")


def main():
    print("== D13 verification ==\n")

    # 1. corpus subtype coverage
    with open(CORPUS, "r", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    cs = Counter(r.get("chart_subtype", "<missing>") for r in rows)
    ds = Counter(r.get("diagram_subtype", "<missing>") for r in rows)
    print(f"corpus rows: {len(rows)}")
    print(f"  chart_subtype: {dict(cs)}")
    print(f"  diagram_subtype: {dict(ds)}\n")

    # 2. gold counts
    for v in ("chart", "diagram", "mindmap"):
        d = os.path.join(GOLD, v)
        srcs = len([f for f in os.listdir(d) if f.endswith("_source.txt")])
        rnds = len([f for f in os.listdir(d) if f.endswith("_rendered.png")])
        structs = len([f for f in os.listdir(d) if f.endswith("_structure.json")])
        print(f"  {v:8s}: source={srcs} rendered={rnds} structure={structs}")
    print()

    # 3. Vega-Lite JSON validity
    ok = bad = 0
    for p in glob.glob(os.path.join(GOLD, "chart", "*_source.txt")):
        try:
            d = json.loads(open(p).read())
            assert "mark" in d or "layer" in d
            ok += 1
        except Exception:
            bad += 1
    print(f"  vegalite valid: {ok}/{ok+bad}\n")

    # 4. failures.jsonl
    fpath = os.path.join(GOLD, "failures.jsonl")
    if os.path.isfile(fpath):
        fails = [json.loads(l) for l in open(fpath) if l.strip()]
        fc = Counter(f.get("viz_type") for f in fails)
        print(f"  failures.jsonl total={len(fails)} by_viz={dict(fc)}")
    else:
        print("  failures.jsonl: <missing>")
    print()

    # 5. CJK leakage
    cjk_re = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
    bad_lang = 0
    for p in glob.glob(os.path.join(GOLD, "mindmap", "*_source.txt")):
        if cjk_re.search(open(p).read()):
            bad_lang += 1
    total_mm = len(glob.glob(os.path.join(GOLD, "mindmap", "*_source.txt")))
    print(f"  mindmap CJK leakage: {bad_lang}/{total_mm}")


if __name__ == "__main__":
    main()
