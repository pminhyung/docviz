#!/usr/bin/env python3
"""IAP — Intent-Anticipated Planning preprocessor (v0.4.1 remediation).

For each query in pilot_50_runner.jsonl, makes a lightweight Qwen LLM call to
produce a plan {expected_artifact_count, viz_type_candidates, query_class,
evidence_required, preretrieval_keys}. Then injects the plan as a `## PLAN`
preamble into the user prompt, producing pilot_50_iap_runner.jsonl.

This conditions the subsequent B6 agent on:
  - Explicit artifact count (eliminates empty-artifact + under-emission)
  - Narrowed viz_type space (faster, more accurate selection)
  - Routing for contradiction queries (per challenge_type)

Usage:
    python scripts/iap_planner.py \\
        --in data/queries/pilot_50_runner.jsonl \\
        --out data/queries/pilot_50_iap_runner.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from exaone.sft_gen.docviz.generate_queries import (
    HostPool, DEFAULT_QWEN_HOSTS, _extract_json, _call_llm,
)


PLAN_PROMPT = """You are an Intent-Anticipated Planner for a query-grounded visualization agent.

Given a user query about a document bundle, produce a structured plan that
the downstream visualization agent will execute. Your plan decides:

  1. How many distinct visualization artifacts the agent should emit (1-3).
     - 1 if the query asks for ONE chart/diagram.
     - 2 if the query implies both quantitative (chart) AND structural (diagram).
     - 3 only when the query explicitly lists three distinct deliverables.

  2. Which 2-3 viz_type candidates are most likely a good fit, chosen from:
        chartjs_bar, chartjs_line, chartjs_grouped_bar, chartjs_pie,
        chartjs_scatter, mermaid_flowchart, mermaid_timeline, mermaid_mindmap,
        mermaid_sequenceDiagram, mermaid_classDiagram

  3. The query_class — one of:
        - "single_chart"          (one quantitative chart)
        - "single_diagram"        (one structural diagram)
        - "chart_plus_diagram"    (one of each)
        - "multi_compare"         (multiple parallel charts/diagrams)
        - "contradiction"         (visualize conflicting claims; needs
                                   both a timeline-style view AND a
                                   comparative summary)

  4. The most useful 2-4 search keywords to anchor retrieval.

# Output STRICT JSON only — NO thinking, NO preamble:

```json
{
  "expected_artifact_count": 1,
  "viz_type_candidates": ["mermaid_flowchart", "chartjs_bar"],
  "query_class": "single_diagram",
  "preretrieval_keys": ["keyword1", "keyword2"]
}
```

# Query

{query_text}
"""


def _build_plan_prompt(query_text: str) -> str:
    return PLAN_PROMPT.replace("{query_text}", query_text)


def _worker(row: dict, pool: HostPool, model: str) -> tuple[dict, dict | None, str]:
    prompt = _build_plan_prompt(row["prompt"])
    client = pool.next()
    try:
        raw = _call_llm(client, model, prompt, disable_thinking=True)
    except Exception as exc:
        return row, None, f"llm_error: {exc}"
    parsed = _extract_json(raw)
    if not parsed:
        return row, None, f"parse_error: {raw[:100]!r}"
    # Validate fields
    if not isinstance(parsed.get("expected_artifact_count"), int):
        parsed["expected_artifact_count"] = 1
    parsed["expected_artifact_count"] = max(1, min(3, parsed["expected_artifact_count"]))
    if not isinstance(parsed.get("viz_type_candidates"), list):
        parsed["viz_type_candidates"] = ["mermaid_flowchart"]
    return row, parsed, ""


def _inject_plan(row: dict, plan: dict) -> dict:
    """Prepend a PLAN block to the user prompt, instructing the agent."""
    plan_block = (
        "## PLAN (Intent-Anticipated Planning — follow strictly):\n"
        f"- expected_artifact_count: **{plan['expected_artifact_count']}** "
        f"(you MUST emit exactly this many artifacts in your generate_viz call)\n"
        f"- viz_type_candidates: {plan['viz_type_candidates']} "
        "(prefer these viz_types unless content strongly disagrees)\n"
        f"- query_class: {plan.get('query_class', 'unknown')}\n"
    )
    if plan.get("query_class") == "contradiction":
        plan_block += (
            "- **Contradiction routing**: emit ONE mermaid_timeline showing "
            "both conflicting dated claims with side markers, AND ONE "
            "chartjs_bar or comparative summary if expected_artifact_count >= 2.\n"
        )
    if plan.get("preretrieval_keys"):
        plan_block += (
            f"- Suggested doc_search keys: {plan['preretrieval_keys']}\n"
        )
    plan_block += "\n"

    new_row = dict(row)
    new_row["prompt"] = plan_block + row["prompt"]
    new_row["iap_plan"] = plan
    return new_row


def main(in_path: Path, out_path: Path, hosts: list[str], port: int,
         api_key: str, model: str, workers: int) -> int:
    rows = [json.loads(l) for l in in_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"[iap] {len(rows)} queries → planning")

    pool = HostPool(hosts, port, api_key)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_ok, n_fail = 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex, \
         out_path.open("w", encoding="utf-8") as fout:
        futures = {ex.submit(_worker, r, pool, model): r for r in rows}
        done = 0
        for fut in as_completed(futures):
            done += 1
            row, plan, err = fut.result()
            if plan is None:
                # Fall back to default plan
                plan = {"expected_artifact_count": 1,
                        "viz_type_candidates": ["mermaid_flowchart"],
                        "query_class": "unknown",
                        "preretrieval_keys": []}
                n_fail += 1
                print(f"  [{done:>3}/{len(rows)}] FAIL {row['qid']} — using default plan ({err[:60]})")
            else:
                n_ok += 1
                print(f"  [{done:>3}/{len(rows)}] OK   {row['qid']}  count={plan.get('expected_artifact_count')} class={plan.get('query_class')}")
            new_row = _inject_plan(row, plan)
            fout.write(json.dumps(new_row, ensure_ascii=False) + "\n")
            fout.flush()
    print(f"[iap] wrote {n_ok} planned + {n_fail} default → {out_path}")
    return 0


if __name__ == "__main__":
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", type=Path,
                    default=Path("data/queries/pilot_50_runner.jsonl"))
    ap.add_argument("--out", type=Path,
                    default=Path("data/queries/pilot_50_iap_runner.jsonl"))
    ap.add_argument("--hosts", default=",".join(DEFAULT_QWEN_HOSTS))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--api-key", default=os.environ.get("EXAONE_API_KEY", "EMPTY"))
    ap.add_argument("--model", default=os.environ.get(
        "EXAONE_MODEL", "Qwen3.5-397B-A17B-FP8"))
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args()
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    sys.exit(main(args.in_path, args.out, hosts, args.port,
                  args.api_key, args.model, args.workers))
