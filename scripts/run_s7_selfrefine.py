#!/usr/bin/env python3
"""B7 = SelfRefine baseline (Madaan et al., NeurIPS 2023), faithful neutral port.

Protocol fidelity
-----------------
This is NOT our DocViz-Agent code path. To keep the B6-vs-B7 comparison fair,
B7 reproduces the *official* Self-Refine visual loop
(github.com/madaan/self-refine, colabs/Visual-Self-Refine-GPT4V.ipynb) — the
combined "understand the current picture → think how it can be improved →
rewrite the code" refinement step — with **task-neutral prompts**. It does NOT
import any of our CIS / TMG / SAO logic, our generate_viz tool prompt, or our
viz-type-pool exposure framing beyond the shared 10-type task enum that every
arm (B5/B6/B7) sees identically.

Faithful deviation (disclosed): the official notebook feeds the *rendered
image* to GPT-4V for visual self-feedback. Our served Qwen3.5-397B is
given the docs as text, so — like Self-Refine's text tasks (gsm, code
optimization, readability) — the self-feedback reasons over the emitted DSL
text + the source documents, not over a rendered image. This is the only
adaptation; the loop structure and prompt intent are the official ones.

Stages per (query, bundle):
    1. initial generation  : docs + query -> {viz_type, viz_dsl, intent}   (1 call)
    2. refine loop (K iters): understand -> improve -> rewrite DSL          (K calls)
Total LLM calls = 1 + K (default K=2).

Output: one .jsonl of trajectory records in the SAME shape run_s1_baseline.py
emits (qa_mode="s7_selfrefine"), so score_phase1.py's is_s1 loader scores it
identically. Artifacts carry the refined dsl_code directly; evidence_ids=[]
(SelfRefine has no source-attribution mechanism — evidence_f1 = 0, like B5).

Usage:
    python scripts/run_s7_selfrefine.py \\
        --dataset data/queries/loong_phase2_working_runner.jsonl \\
        --bundles data/bundles/loong_phase2.json \\
        --out data/s7_qwen_phase2/batch_0.jsonl [--iters 2]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from exaone.sft_gen.docviz.generate_queries import (
    HostPool, DEFAULT_QWEN_HOSTS, _extract_json, _call_llm,
)

# Shared task framing — identical to B5's pool (NOT a B6-specific advantage).
VIZ_TYPE_POOL = (
    "chartjs_bar | chartjs_line | chartjs_grouped_bar | chartjs_pie | "
    "chartjs_scatter | mermaid_flowchart | mermaid_timeline | "
    "mermaid_mindmap | mermaid_sequenceDiagram | mermaid_classDiagram"
)

# ── Stage 1: initial generation (direct, single-shot — Self-Refine's y0) ──────
INITIAL_PROMPT = """You are a visualization assistant. Using ONLY the source documents below, produce ONE visualization that best answers the user's query. Do not invent facts.

Documents (bundle):
{doc_block}

Query: {query}

Pick the most appropriate format from: {viz_types}

Output STRICT JSON only (no preamble, no fences):
{{"viz_type": "<one of the types above>",
  "intent": "<one-sentence summary of what this visualization shows>",
  "viz_dsl": "<the raw DSL: mermaid_* -> mermaid markdown starting with the kind keyword; chartjs_* -> JSON spec>"}}"""

# ── Stage 2: refine (official visual-self-refine wording) ────────────────────
# Verbatim structure of madaan/self-refine Visual-Self-Refine-GPT4V:
#   "First, understand the current picture. Then, think about how can it be
#    improved. Then, rewrite the Tikz code to improve the image."
# We swap image->DSL text (docs given as text) and the source docs are provided
# so the model can ground — NO dimension checklist / coaching is added (that
# would be an unfair advantage not present in the original fixed pipeline).
REFINE_PROMPT = """This is the {viz_type} visualization DSL for the query, shown below.

Query: {query}

Source documents:
{doc_block}

Current DSL:
{current_dsl}

Can you improve it? First, understand what the current visualization depicts. Then, think about how it can be improved. Then, rewrite the DSL to improve it.

Output STRICT JSON only (no preamble, no fences):
{{"viz_type": "<one of: {viz_types}>",
  "intent": "<one-sentence summary>",
  "viz_dsl": "<the improved raw DSL>"}}"""


def _doc_block(bundle: dict, max_chars_per_doc: int = 1200) -> str:
    docs = bundle.get("docs") or bundle.get("documents") or []
    out = []
    for i, d in enumerate(docs, 1):
        title = d.get("title", f"doc {i}")
        content = (d.get("content") or "")[:max_chars_per_doc].replace("\n", " ")
        out.append(f"[{i}] {title}\n{content}\n")
    return "\n".join(out)


def _strip_fence(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        m = re.match(r"```[a-zA-Z]*\s*\n([\s\S]*?)\n```", s)
        if m:
            return m.group(1).strip()
    return s


def _parse(raw: str) -> tuple[str, str, str] | None:
    """-> (viz_type, viz_dsl, intent) or None."""
    p = _extract_json(raw)
    if not p or "viz_dsl" not in p:
        return None
    return (p.get("viz_type", ""), _strip_fence(str(p.get("viz_dsl", ""))),
            str(p.get("intent", "")))


def _worker(row: dict, bundle: dict, pool: HostPool, model: str, iters: int
            ) -> tuple[str, dict | None, str, int]:
    qid = row["qid"]
    doc_block = _doc_block(bundle)
    calls = 0

    # Stage 1: initial direct generation (Self-Refine y0).
    try:
        raw = _call_llm(pool.next(), model,
                        INITIAL_PROMPT.format(doc_block=doc_block, query=row["prompt"],
                                              viz_types=VIZ_TYPE_POOL),
                        disable_thinking=True)
        calls += 1
    except Exception as exc:
        return qid, None, f"stage1_llm_error: {exc}", calls
    parsed = _parse(raw)
    if parsed is None:
        return qid, None, f"stage1_parse_error: {raw[:120]!r}", calls
    viz_type, viz_dsl, intent = parsed

    # Stage 2: refine loop (K iterations).
    for _ in range(max(0, iters)):
        if not viz_dsl.strip():
            break
        try:
            raw = _call_llm(pool.next(), model,
                            REFINE_PROMPT.format(viz_type=viz_type, query=row["prompt"],
                                                 doc_block=doc_block, current_dsl=viz_dsl[:4000],
                                                 viz_types=VIZ_TYPE_POOL),
                            disable_thinking=True)
            calls += 1
        except Exception:
            break  # keep last good output (Self-Refine falls back to prior y)
        rp = _parse(raw)
        if rp is None or not rp[1].strip():
            break  # un-parseable refinement -> keep prior output
        viz_type, viz_dsl, intent = rp

    artifact = {"viz_type": viz_type, "intent": intent,
                "content_brief": "", "evidence_ids": [], "dsl_code": viz_dsl}
    return qid, {"artifacts": [artifact]}, "", calls


def _row_to_trajectory(row: dict, parsed: dict | None, err: str, api_calls: int) -> dict:
    artifacts_xml = ""
    if parsed:
        tc_json = json.dumps({"name": "generate_viz", "arguments": parsed}, ensure_ascii=False)
        artifacts_xml = f"<tool_call>{tc_json}</tool_call>"
    user_msg = row["prompt"]
    atts = row.get("attachments", [])
    if atts:
        block = "[Attached documents]\n" + "\n".join(
            f"[{a['idx']}] {a['filename']}" for a in atts)
        user_msg = block + "\n\n" + user_msg
    convs = [
        {"from": "system", "value": "S7_SelfRefine baseline (Madaan et al. 2023)."},
        {"from": "human", "value": user_msg},
        {"from": "gpt", "value": artifacts_xml or f"<error>{err}</error>"},
    ]
    return {
        "prompt_index": 0,
        "conversations": convs,
        "metadata": {"batch_num": 0, "qa_mode": "s7_selfrefine", "host": "qwen",
                     "qid": row["qid"]},
        "completed": parsed is not None,
        "partial": err,
        "api_calls": api_calls,
        "tool_stats": {}, "tool_error_counts": {}, "toolsets_used": [],
    }


def main(dataset_path: Path, bundles_path: Path, out_path: Path,
         hosts: list[str], port: int, api_key: str, model: str,
         workers: int, iters: int) -> int:
    rows = [json.loads(l) for l in dataset_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    bundles_raw = json.loads(bundles_path.read_text(encoding="utf-8"))
    bundle_lookup = {b["bundle_id"]: b for b in bundles_raw}
    print(f"[s7] {len(rows)} queries × {len(bundle_lookup)} bundles | refine iters={iters}")

    pool = HostPool(hosts, port, api_key)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_ok, n_fail = 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex, \
         out_path.open("w", encoding="utf-8") as fout:
        futures = {ex.submit(_worker, r, bundle_lookup[r["bundle_id"]], pool, model, iters): r
                   for r in rows if r["bundle_id"] in bundle_lookup}
        done = 0
        for fut in as_completed(futures):
            row = futures[fut]
            done += 1
            qid, parsed, err, calls = fut.result()
            traj = _row_to_trajectory(row, parsed, err, calls)
            fout.write(json.dumps(traj, ensure_ascii=False) + "\n")
            fout.flush()
            if parsed:
                n_ok += 1
                print(f"  [{done:>3}/{len(rows)}] OK   {qid}  "
                      f"vt={parsed['artifacts'][0]['viz_type']} calls={calls}")
            else:
                n_fail += 1
                print(f"  [{done:>3}/{len(rows)}] FAIL {qid} — {err[:80]}")
    print(f"[s7] wrote {n_ok} OK + {n_fail} FAIL → {out_path}")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--bundles", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--hosts", default=",".join(DEFAULT_QWEN_HOSTS))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--model", default="Qwen3.5-397B-A17B-FP8")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--iters", type=int, default=2, help="Self-Refine refinement iterations (K)")
    a = ap.parse_args()
    hosts = [h.strip() for h in a.hosts.split(",") if h.strip()]
    sys.exit(main(a.dataset, a.bundles, a.out, hosts, a.port, a.api_key,
                  a.model, a.workers, a.iters))
