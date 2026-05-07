#!/usr/bin/env python3
"""D11 — Batch extract _structure.json for every generated source file.

Walks data/gold/{chart,diagram,mindmap}/ and data/model_outputs/{model}/{viz}/
and for each `{doc_id}_source.txt` that lacks a matching `_structure.json`,
runs `extract_structure_v2` and writes the JSON (with node_labels serialized
as a sorted list so json.load can round-trip it).

Usage:
    python -m scripts.viz.batch_extract_structures [--base PATH] [--viz chart]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.config import DATA_DIR, VIZ_TYPES
from scripts.viz.structure_extract_v2 import extract_structure_v2


def _load_subtypes() -> dict:
    """Return {doc_id: diagram_subtype} from corpus.jsonl."""
    path = os.path.join(DATA_DIR, "documents", "corpus.jsonl")
    subs = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            subs[r["doc_id"]] = r.get("diagram_subtype", "flowchart")
    return subs


def _serialize_structure(s: dict) -> dict:
    out = {}
    for k, v in s.items():
        if isinstance(v, set):
            out[k] = sorted(v)
        else:
            out[k] = v
    return out


def _load_gold_chart_hint(doc_id: str) -> Optional[dict]:
    p = os.path.join(DATA_DIR, "gold", "chart", f"{doc_id}_structure.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            g = json.load(f)
        return {
            "x_field": g.get("x_field", ""),
            "y_field": g.get("y_field", ""),
            "color_field": g.get("color_field") or "",
        }
    except (json.JSONDecodeError, OSError):
        return None


def process_dir(dirpath: str, viz_type: str, subtypes: dict,
                overwrite: bool = False,
                is_model_output: bool = False) -> tuple[int, int, int]:
    """Return (processed, skipped, errors)."""
    if not os.path.isdir(dirpath):
        return (0, 0, 0)
    proc = skip = err = 0
    for name in sorted(os.listdir(dirpath)):
        if not name.endswith("_source.txt"):
            continue
        doc_id = name[: -len("_source.txt")]
        src_path = os.path.join(dirpath, name)
        out_path = os.path.join(dirpath, f"{doc_id}_structure.json")
        if os.path.exists(out_path) and not overwrite:
            skip += 1
            continue
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                src = f.read()
            gold_hint = None
            if viz_type == "chart" and is_model_output:
                gold_hint = _load_gold_chart_hint(doc_id)
            struct = extract_structure_v2(
                src, viz_type, subtypes.get(doc_id, "flowchart"),
                gold_hint=gold_hint,
            )
            data = _serialize_structure(struct)
            tmp = out_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, out_path)
            proc += 1
        except Exception as e:
            err += 1
            print(f"[err] {dirpath}/{name}: {e}", file=sys.stderr)
    return (proc, skip, err)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=str, default=None,
                    help="e.g. data/gold or data/model_outputs/qwen9b")
    ap.add_argument("--viz", type=str, default=",".join(VIZ_TYPES))
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    subtypes = _load_subtypes()
    viz_list = [v.strip() for v in args.viz.split(",") if v.strip()]

    if args.base:
        bases = [args.base]
    else:
        # default: gold + every model_outputs/* subdirectory
        bases = [os.path.join(DATA_DIR, "gold")]
        mo_root = os.path.join(DATA_DIR, "model_outputs")
        if os.path.isdir(mo_root):
            for m in sorted(os.listdir(mo_root)):
                bases.append(os.path.join(mo_root, m))

    t0 = time.time()
    grand_proc = grand_skip = grand_err = 0
    for base in bases:
        is_model = os.sep + "model_outputs" + os.sep in (base + os.sep)
        for v in viz_list:
            dirp = os.path.join(base, v)
            p, s, e = process_dir(dirp, v, subtypes, args.overwrite,
                                  is_model_output=is_model)
            if p + s + e > 0:
                print(f"  {base}/{v}: processed={p} skipped={s} errors={e}")
            grand_proc += p
            grand_skip += s
            grand_err += e
    dt = time.time() - t0
    print(f"\ntotal processed={grand_proc} skipped={grand_skip} errors={grand_err} "
          f"in {dt:.1f}s")


if __name__ == "__main__":
    main()
