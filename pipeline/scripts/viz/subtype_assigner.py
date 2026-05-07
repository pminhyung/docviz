"""D5 — Subtype assigner + chart spec planner.

Two qwen397b calls per document:
  Call A: subtype assignment (CHART + DIAGRAM) via SUBTYPE_ASSIGNMENT_PROMPT
          (Guide 1 §2.2 verbatim). Input = doc excerpt 1500 chars.
  Call B: chart spec planning. Input = doc excerpt 6000 chars + chart_subtype.
          Output = {chart_type_name, x_field, y_field, color_field, title, data_location}
          — NO actual numeric values (leak prevention).

Writes back to data/documents/corpus.jsonl (atomic temp+rename). Cached per
doc_id in data/viz/_subtype_cache.jsonl + _chart_spec_cache.jsonl.

Usage:
    python -m scripts.viz.subtype_assigner [--limit N] [--workers 8]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.viz.prompts import SUBTYPE_ASSIGNMENT_PROMPT
from scripts.viz.context_builder import prepare_doc_excerpt
from scripts.utils.llm_clients import call_model
from scripts.config import CHART_SUBTYPES, DIAGRAM_SUBTYPES

CORPUS_PATH = "/ex_disk2/mhpark/poc/visubench/data/documents/corpus.jsonl"
VIZ_DIR = "/ex_disk2/mhpark/poc/visubench/data/viz"
SUBTYPE_CACHE = os.path.join(VIZ_DIR, "_subtype_cache.jsonl")
CHART_SPEC_CACHE = os.path.join(VIZ_DIR, "_chart_spec_cache.jsonl")

VALID_CHART = set(CHART_SUBTYPES)
VALID_DIAGRAM = set(DIAGRAM_SUBTYPES)


CHART_SPEC_PROMPT = """You are planning a chart for a document-grounded visualization benchmark.

Read the document excerpt. Propose the MOST meaningful chart we could draw from
data ACTUALLY PRESENT in this document. The chart type is already fixed.

Chart type: {chart_subtype}

Output a JSON object with exactly these fields:
- chart_type_name: a natural language name for the chart type (e.g. "bar chart", "line chart")
- x_field: semantic name of the x axis (e.g. "fiscal_year", "region", "product_category")
- y_field: semantic name of the y axis (e.g. "revenue_usd_millions", "accuracy_pct")
- color_field: optional grouping/series field (string or null)
- title: a short chart title in the document's language
- data_location: a short pointer to where in the document the data lives
                 (e.g. "Section 3 quarterly revenues", "Table 2 patient counts")

CRITICAL RULES:
- Do NOT include actual numeric values from the document.
- Do NOT invent data that the document does not describe.
- Choose a meaningful view; if the document truly lacks quantitative data,
  pick the best qualitative approximation (e.g. counts of mentioned entities).

Document excerpt (first 6000 chars):
{doc_excerpt}

Output (JSON only, no explanation):"""


# ── JSON parsing ─────────────────────────────────────────────────────────────

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Optional[dict]:
    """Permissive JSON extractor. Handles ```json fences and leading/trailing junk."""
    if not text:
        return None
    # strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    # first try full parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # fall back to largest brace block
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _normalize_subtype(val: str, valid: set, fallback: str) -> str:
    if not isinstance(val, str):
        return fallback
    v = val.strip()
    if v in valid:
        return v
    # case-insensitive match
    low = v.lower()
    for opt in valid:
        if opt.lower() == low:
            return opt
    return fallback


# ── Cache ────────────────────────────────────────────────────────────────────

def _load_cache(path: str) -> Dict[str, dict]:
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                out[row["doc_id"]] = row
            except Exception:
                continue
    return out


def _append_cache(path: str, row: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── LLM calls ────────────────────────────────────────────────────────────────

def assign_subtype(row: dict) -> dict:
    excerpt = prepare_doc_excerpt(row, max_chars=1500)
    prompt = SUBTYPE_ASSIGNMENT_PROMPT.format(
        doc_excerpt=excerpt,
        doc_language=row.get("lang", "en"),
        doc_domain=row.get("domain", "general"),
    )
    raw = call_model(
        "qwen397b",
        system_prompt="You output only valid JSON as instructed.",
        user_content=prompt,
        temperature=0.2,
    )
    parsed = _extract_json(raw) or {}
    return {
        "doc_id": row["doc_id"],
        "chart_subtype": _normalize_subtype(parsed.get("chart_subtype"), VALID_CHART, "bar"),
        "diagram_subtype": _normalize_subtype(parsed.get("diagram_subtype"), VALID_DIAGRAM, "flowchart"),
        "chart_reason": str(parsed.get("chart_reason", ""))[:500],
        "diagram_reason": str(parsed.get("diagram_reason", ""))[:500],
        "raw": raw[:2000],
    }


def plan_chart_spec(row: dict, chart_subtype: str) -> dict:
    excerpt = prepare_doc_excerpt(row, max_chars=6000)
    prompt = CHART_SPEC_PROMPT.format(chart_subtype=chart_subtype, doc_excerpt=excerpt)
    raw = call_model(
        "qwen397b",
        system_prompt="You output only valid JSON as instructed.",
        user_content=prompt,
        temperature=0.2,
    )
    parsed = _extract_json(raw) or {}
    # Strip any values-like keys to enforce no-data-leak
    for banned in ("data", "values", "data_values"):
        parsed.pop(banned, None)
    return {
        "doc_id": row["doc_id"],
        "chart_subtype": chart_subtype,
        "chart_type_name": str(parsed.get("chart_type_name", f"{chart_subtype} chart"))[:120],
        "x_field": str(parsed.get("x_field", ""))[:120],
        "y_field": str(parsed.get("y_field", ""))[:120],
        "color_field": (None if parsed.get("color_field") in (None, "", "null")
                        else str(parsed.get("color_field"))[:120]),
        "title": str(parsed.get("title", ""))[:200],
        "data_location": str(parsed.get("data_location", ""))[:300],
        "raw": raw[:2000],
    }


def process_doc(row: dict, subtype_cache: dict, spec_cache: dict) -> dict:
    doc_id = row["doc_id"]
    try:
        if doc_id in subtype_cache:
            sub = subtype_cache[doc_id]
        else:
            sub = assign_subtype(row)
            _append_cache(SUBTYPE_CACHE, sub)
        if doc_id in spec_cache:
            spec = spec_cache[doc_id]
        else:
            spec = plan_chart_spec(row, sub["chart_subtype"])
            _append_cache(CHART_SPEC_CACHE, spec)
        return {"doc_id": doc_id, "ok": True, "subtype": sub, "spec": spec}
    except Exception as e:
        return {"doc_id": doc_id, "ok": False, "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[:2000]}


# ── Corpus write-back ────────────────────────────────────────────────────────

def write_back_corpus(subtype_cache: Dict[str, dict], spec_cache: Dict[str, dict]):
    """Atomically rewrite corpus.jsonl with chart_subtype/diagram_subtype/chart_spec fields."""
    rows = []
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    for r in rows:
        doc_id = r["doc_id"]
        if doc_id in subtype_cache:
            s = subtype_cache[doc_id]
            r["chart_subtype"] = s["chart_subtype"]
            r["diagram_subtype"] = s["diagram_subtype"]
            r["chart_reason"] = s.get("chart_reason", "")
            r["diagram_reason"] = s.get("diagram_reason", "")
        if doc_id in spec_cache:
            sp = spec_cache[doc_id]
            r["chart_spec"] = {
                "chart_type_name": sp["chart_type_name"],
                "x_field": sp["x_field"],
                "y_field": sp["y_field"],
                "color_field": sp["color_field"],
                "title": sp["title"],
            }
            r["chart_spec_data_location"] = sp["data_location"]
    tmp = CORPUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, CORPUS_PATH)
    print(f"[write-back] {CORPUS_PATH}: {len(rows)} rows updated")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--skip-writeback", action="store_true")
    args = ap.parse_args()

    os.makedirs(VIZ_DIR, exist_ok=True)
    subtype_cache = _load_cache(SUBTYPE_CACHE)
    spec_cache = _load_cache(CHART_SPEC_CACHE)
    print(f"[cache] subtype={len(subtype_cache)}  chart_spec={len(spec_cache)}")

    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
    print(f"[corpus] {len(rows)} docs to process")

    t0 = time.time()
    done = 0
    failed = []
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_doc, r, subtype_cache, spec_cache): r["doc_id"]
                for r in rows}
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            if r["ok"]:
                results.append(r)
                # update caches in-memory so downstream writeback sees them
                subtype_cache[r["doc_id"]] = r["subtype"]
                spec_cache[r["doc_id"]] = r["spec"]
            else:
                failed.append(r)
            if done % 25 == 0 or done == len(rows):
                elapsed = time.time() - t0
                rate = done / max(elapsed, 1e-6)
                print(f"  [{done}/{len(rows)}]  ok={len(results)}  fail={len(failed)}  "
                      f"elapsed={elapsed:.0f}s  rate={rate:.2f}/s")

    if failed:
        fail_path = os.path.join(VIZ_DIR, "_subtype_failures.jsonl")
        with open(fail_path, "w", encoding="utf-8") as f:
            for r in failed:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[failures] {len(failed)} → {fail_path}")

    # Distribution report
    c_dist = Counter(subtype_cache[d]["chart_subtype"] for d in subtype_cache)
    d_dist = Counter(subtype_cache[d]["diagram_subtype"] for d in subtype_cache)
    print("\n== chart_subtype distribution ==")
    for k, v in c_dist.most_common():
        print(f"  {k:12s} {v}")
    print("\n== diagram_subtype distribution ==")
    for k, v in d_dist.most_common():
        print(f"  {k:16s} {v}")

    if not args.skip_writeback and not failed:
        write_back_corpus(subtype_cache, spec_cache)
    elif failed:
        print("[write-back SKIPPED] rerun to resume failed docs; cache is preserved")

    # Save distribution report
    dist_path = os.path.join(VIZ_DIR, "_subtype_distribution.json")
    with open(dist_path, "w", encoding="utf-8") as f:
        json.dump({"chart": dict(c_dist), "diagram": dict(d_dist),
                   "n": len(subtype_cache)}, f, indent=2, ensure_ascii=False)
    print(f"\n[distribution] → {dist_path}")


if __name__ == "__main__":
    main()
