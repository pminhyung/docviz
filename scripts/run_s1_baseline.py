#!/usr/bin/env python3
"""S1 (Direct-LLM) baseline runner for v0.4.1 pilot.

Single-shot Qwen call per query — no agent loop, no tools. The LLM
receives the full bundle (truncated per-doc) + query + the same viz_type
pool exposure that B6's tool prompt uses. Output is parsed as the same
artifact JSON shape so the aggregator can score it identically.

Output: one .jsonl file with rows matching the harness trajectory
shape that aggregate_pilot.py expects.

Usage:
    python scripts/run_s1_baseline.py \\
        --dataset data/queries/pilot_50_runner.jsonl \\
        --bundles data/bundles/all.json \\
        --out data/s1_qwen_pilot/batch_0.jsonl
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


VIZ_TYPE_POOL = (
    "chartjs_bar | chartjs_line | chartjs_grouped_bar | chartjs_pie | "
    "chartjs_scatter | mermaid_flowchart | mermaid_timeline | "
    "mermaid_mindmap | mermaid_sequenceDiagram | mermaid_classDiagram"
)

PROMPT_TEMPLATE = """You are a direct visualization generator. Given the documents and a query, emit a single visualization artifact specification.

Documents (bundle):
{doc_block}

Query: {query}

Output STRICT JSON only with this schema (NO thinking, NO preamble):
```json
{{
  "artifacts": [
    {{
      "viz_type": "<one of: {viz_types}>",
      "intent": "<one-sentence summary of what this viz shows>",
      "content_brief": "<exhaustive description of entities, dates, numbers, relationships from the docs that the viz must include>",
      "evidence_ids": []
    }}
  ]
}}
```

For multi-artifact queries (e.g., "explain visually" with both chart + diagram), include 2-3 artifacts in the list. Default: 1 artifact.
"""


def _doc_block(bundle: dict, max_chars_per_doc: int = 1200) -> str:
    docs = bundle.get("docs") or bundle.get("documents") or []
    out = []
    for i, d in enumerate(docs, 1):
        title = d.get("title", f"doc {i}")
        content = (d.get("content") or "")[:max_chars_per_doc].replace("\n", " ")
        out.append(f"[{i}] {title}\n{content}\n")
    return "\n".join(out)


def _worker(row: dict, bundle: dict, pool: HostPool, model: str
            ) -> tuple[str, dict | None, str]:
    qid = row["qid"]
    prompt = PROMPT_TEMPLATE.format(
        doc_block=_doc_block(bundle),
        query=row["prompt"],
        viz_types=VIZ_TYPE_POOL,
    )
    client = pool.next()
    try:
        raw = _call_llm(client, model, prompt, disable_thinking=True)
    except Exception as exc:
        return qid, None, f"llm_error: {exc}"
    parsed = _extract_json(raw)
    if not parsed or "artifacts" not in parsed:
        return qid, None, f"parse_error: {raw[:120]!r}"
    return qid, parsed, ""


def _row_to_trajectory(row: dict, parsed: dict | None, err: str) -> dict:
    """Produce a record in the same shape aggregate_pilot.py expects."""
    artifacts_xml = ""
    if parsed:
        tc_json = json.dumps({"name": "generate_viz", "arguments": parsed},
                             ensure_ascii=False)
        artifacts_xml = f"<tool_call>{tc_json}</tool_call>"
    user_msg = row["prompt"]
    # Attached-documents prefix is added in batch_runner; mirror it so the
    # aggregator's qid-matching by-prompt works.
    atts = row.get("attachments", [])
    if atts:
        block = "[Attached documents]\n" + "\n".join(
            f"[{a['idx']}] {a['filename']}" for a in atts)
        user_msg = block + "\n\n" + user_msg
    convs = [
        {"from": "system", "value": "S1_Direct baseline."},
        {"from": "human", "value": user_msg},
        {"from": "gpt", "value": artifacts_xml or f"<error>{err}</error>"},
    ]
    return {
        "prompt_index": 0,
        "conversations": convs,
        "metadata": {"batch_num": 0, "qa_mode": "s1_direct", "host": "qwen",
                     "qid": row["qid"]},
        "completed": parsed is not None,
        "partial": err,
        "api_calls": 1,
        "tool_stats": {},
        "tool_error_counts": {},
        "toolsets_used": [],
    }


def main(dataset_path: Path, bundles_path: Path, out_path: Path,
         hosts: list[str], port: int, api_key: str, model: str,
         workers: int) -> int:
    rows = [json.loads(l) for l in dataset_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    bundles_raw = json.loads(bundles_path.read_text(encoding="utf-8"))
    bundle_lookup = {b["bundle_id"]: b for b in bundles_raw}
    print(f"[s1] {len(rows)} queries × {len(bundle_lookup)} bundles")

    pool = HostPool(hosts, port, api_key)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_ok, n_fail = 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex, \
         out_path.open("w", encoding="utf-8") as fout:
        futures = {ex.submit(_worker, r, bundle_lookup[r["bundle_id"]],
                              pool, model): r for r in rows
                   if r["bundle_id"] in bundle_lookup}
        done = 0
        for fut in as_completed(futures):
            row = futures[fut]
            done += 1
            qid, parsed, err = fut.result()
            traj = _row_to_trajectory(row, parsed, err)
            fout.write(json.dumps(traj, ensure_ascii=False) + "\n")
            fout.flush()
            if parsed:
                n_ok += 1
                n_arts = len(parsed.get("artifacts", []))
                print(f"  [{done:>3}/{len(rows)}] OK   {qid}  artifacts={n_arts}")
            else:
                n_fail += 1
                print(f"  [{done:>3}/{len(rows)}] FAIL {qid} — {err[:80]}")
    print(f"[s1] wrote {n_ok} OK + {n_fail} FAIL → {out_path}")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path,
                    default=Path("data/queries/pilot_50_runner.jsonl"))
    ap.add_argument("--bundles", type=Path,
                    default=Path("data/bundles/all.json"))
    ap.add_argument("--out", type=Path,
                    default=Path("data/s1_qwen_pilot/batch_0.jsonl"))
    ap.add_argument("--hosts", default=",".join(DEFAULT_QWEN_HOSTS))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--api-key", default=os.environ.get("EXAONE_API_KEY", "EMPTY"))
    ap.add_argument("--model", default=os.environ.get(
        "EXAONE_MODEL", "Qwen3.5-397B-A17B-FP8"))
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args()
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    sys.exit(main(args.dataset, args.bundles, args.out,
                  hosts, args.port, args.api_key, args.model, args.workers))
