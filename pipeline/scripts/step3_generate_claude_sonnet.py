"""Generate VisuBench outputs via `claude -p --model sonnet`.

Mirrors scripts/step3_generate_models.py for a non-vLLM, CLI-based model.
Parallel via ThreadPoolExecutor. Resume-safe: skips (doc_id, viz_type) pairs
whose source.txt already exists AND whose render_log.jsonl entry marks done.

After each generation:
  - writes model_outputs/claude_sonnet_4_6/{viz}/{doc_id}_source.txt
  - invokes the existing render_chart / render_mermaid / render_mindmap
  - appends a JSONL log line (compatible with step6 aggregation)

Usage:
    python -m scripts.step3_generate_claude_sonnet --max-docs 10            # pilot
    python -m scripts.step3_generate_claude_sonnet --max-docs 0 --workers 8 # full
    python -m scripts.step3_generate_claude_sonnet --viz chart              # single viz
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.claude_preflight.claude_client import call_text_generation
from scripts.claude_preflight.parsers import (
    extract_chart,
    extract_diagram,
    extract_mindmap,
)
from scripts.config import DATA_DIR, VIZ_TYPES
from scripts.step3_generate_models import (
    get_default_query,
    get_system_prompt,
    make_specific_chart_query,
)
from scripts.utils.doc_loader import load_doc_excerpts
from scripts.utils.rendering import render_chart, render_mermaid, render_mindmap

MODEL_ID = "claude_sonnet_4_6"
MODEL_OUTPUT_DIR = os.path.join(DATA_DIR, "model_outputs", MODEL_ID)
CORPUS_PATH = os.path.join(DATA_DIR, "documents", "corpus.jsonl")

PARSER_BY_VIZ = {
    "chart": extract_chart,
    "diagram": extract_diagram,
    "mindmap": extract_mindmap,
}


def _load_corpus() -> list[dict]:
    rows = []
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _load_done(log_path: str) -> set[tuple[str, str]]:
    done: set[tuple[str, str]] = set()
    if not os.path.exists(log_path):
        return done
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("success"):
                done.add((row["doc_id"], row["viz_type"]))
    return done


def _write_log(log_path: str, row: dict, lock: Lock):
    with lock:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _process_task(doc: dict, viz_type: str) -> dict:
    doc_id = doc["doc_id"]
    lang = doc.get("lang", "en")
    subtype = (
        doc.get("chart_subtype", "bar") if viz_type == "chart"
        else doc.get("diagram_subtype", "flowchart") if viz_type == "diagram"
        else ""
    )

    result: dict = {
        "doc_id": doc_id,
        "model_id": MODEL_ID,
        "viz_type": viz_type,
        "subtype": subtype,
        "success": False,
        "rendered": False,
        "cost_usd": 0.0,
        "output_tokens": 0,
        "duration_s": 0.0,
    }

    try:
        doc_text = load_doc_excerpts(
            [doc["doc_json_path"]],
            max_pages=8, chars_per_page=1500, max_total=10000,
        )
        if not doc_text or len(doc_text.strip()) < 50:
            result["error"] = "Insufficient document text"
            return result

        system_prompt = get_system_prompt(viz_type, subtype, lang=lang)
        if viz_type == "chart":
            query = make_specific_chart_query(doc_id, lang) or get_default_query("chart")
        else:
            query = get_default_query(viz_type)
        user_content = f"User query: {query}\n\nDocument source:\n{doc_text}"

        t0 = time.time()
        resp = call_text_generation(user_content, system_prompt, timeout=240)
        result["duration_s"] = round(time.time() - t0, 2)
        result["cost_usd"] = round(resp.cost_usd, 6)
        result["output_tokens"] = resp.output_tokens

        if not resp.ok:
            result["error"] = f"claude_error: {resp.error[:200]}"
            return result

        raw = resp.text or ""
        if not raw.strip():
            result["error"] = "empty_response"
            return result

        # Parse (tolerant; we save raw regardless)
        parsed = PARSER_BY_VIZ[viz_type](raw)
        result["parse_ok"] = parsed["ok"]
        result["parse_format"] = parsed["format"]
        if parsed["errors"]:
            result["parse_errors"] = parsed["errors"]

        # Save raw output
        out_dir = os.path.join(MODEL_OUTPUT_DIR, viz_type)
        os.makedirs(out_dir, exist_ok=True)
        src_path = os.path.join(out_dir, f"{doc_id}_source.txt")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(raw)

        # Render using existing renderers (same paths as step3_generate_models)
        try:
            if viz_type == "mindmap":
                rr = render_mindmap(raw, out_dir, doc_id, model_id=MODEL_ID)
            elif viz_type == "diagram":
                rr = render_mermaid(raw, subtype, out_dir, doc_id)
            else:
                rr = render_chart(raw, subtype, out_dir, doc_id)
            result["rendered"] = bool(rr.get("success", False))
            if not result["rendered"] and rr.get("error"):
                result["render_error"] = rr["error"][:200]
        except Exception as e:
            result["render_error"] = f"{type(e).__name__}: {str(e)[:200]}"

        result["success"] = True
        return result
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        result["traceback"] = traceback.format_exc()[-500:]
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-docs", type=int, default=10,
                        help="0 = all docs (default: 10 pilot)")
    parser.add_argument("--viz", default="", help="Restrict to single viz_type")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    os.makedirs(MODEL_OUTPUT_DIR, exist_ok=True)
    log_path = os.path.join(MODEL_OUTPUT_DIR, "render_log.jsonl")
    lock = Lock()
    done = _load_done(log_path)

    corpus = _load_corpus()
    if args.max_docs and args.max_docs > 0:
        # Deterministic pilot slice
        corpus_sorted = sorted(corpus, key=lambda d: d["doc_id"])
        import random as _random
        rnd = _random.Random(args.seed)
        rnd.shuffle(corpus_sorted)
        corpus = corpus_sorted[:args.max_docs]

    viz_types = [args.viz] if args.viz else VIZ_TYPES
    tasks = []
    for doc in corpus:
        if not doc.get("doc_json_path"):
            continue
        for viz_type in viz_types:
            if (doc["doc_id"], viz_type) in done:
                continue
            tasks.append((doc, viz_type))

    total_requested = len(corpus) * len(viz_types)
    print(f"[{MODEL_ID}] {len(tasks)} remaining / {total_requested} requested "
          f"({len(done)} already done), workers={args.workers}", flush=True)
    if not tasks:
        print("Nothing to do.")
        return

    t_start = time.time()
    counters = {"ok": 0, "render_ok": 0, "fail": 0, "cost": 0.0}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(_process_task, doc, viz): (doc["doc_id"], viz)
                   for doc, viz in tasks}
        for i, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            counters["cost"] += row.get("cost_usd", 0.0)
            if row.get("success"):
                counters["ok"] += 1
                if row.get("rendered"):
                    counters["render_ok"] += 1
            else:
                counters["fail"] += 1
            _write_log(log_path, row, lock)
            if i % 10 == 0 or i == len(tasks):
                elapsed = time.time() - t_start
                rate = i / elapsed if elapsed else 0
                eta = (len(tasks) - i) / rate if rate else 0
                print(f"[{i}/{len(tasks)}] ok={counters['ok']} "
                      f"render={counters['render_ok']} fail={counters['fail']} "
                      f"cost=${counters['cost']:.2f} "
                      f"rate={rate:.2f}/s eta={eta/60:.1f}min", flush=True)

    print(f"\nDone. ok={counters['ok']} render={counters['render_ok']} "
          f"fail={counters['fail']} cost=${counters['cost']:.2f}")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()
