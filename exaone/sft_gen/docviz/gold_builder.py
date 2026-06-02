"""docviz v0.4.1 §8.2 — Gold extraction pipeline (pilot version).

For each query in the input JSONL, build a Gold record by extracting evidence
spans + facts + (optional) tables + graphs + contradictions via a single
LLM extractor (Qwen3.5-397B via the local multi-host pool — free for pilot;
spec calls for GPT-5-mini + Opus 4.8 union in full scale).

Output: data/gold/pilot_50.jsonl — one Gold record per query.

Usage:
    python -m exaone.sft_gen.docviz.gold_builder \\
        --queries data/queries/pilot_50.jsonl \\
        --bundles data/bundles/all.json \\
        --out data/gold/pilot_50.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from exaone.sft_gen.docviz.generate_queries import (
    HostPool, DEFAULT_QWEN_HOSTS, _extract_json, _call_llm,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_PATH = REPO_ROOT / "exaone/sft_gen/docviz/prompts/gold_extraction/base.txt"


def _doc_block(bundle: dict, max_chars_per_doc: int = 1200) -> str:
    docs = bundle.get("docs") or bundle.get("documents") or []
    out = []
    for i, d in enumerate(docs):
        title = d.get("title", f"doc {i}")
        doc_id = d.get("doc_id", f"doc_{i}")
        content = (d.get("content") or "")[:max_chars_per_doc].replace("\n", " ")
        out.append(f"=== {doc_id} | {title} ===\n{content}\n")
    return "\n".join(out)


def _gold_intents_block(query: dict) -> str:
    intents = query.get("gold_intents", [])
    lines = []
    for i in intents:
        lines.append(
            f"  - intent_id={i.get('intent_id', '?')}, "
            f"hint={i.get('artifact_type_hint', 'any')}, "
            f"summary={i.get('content_summary', '')[:120]}"
        )
    return "\n".join(lines) if lines else "  (none provided)"


def _build_prompt(query: dict, bundle: dict) -> str:
    base = PROMPT_PATH.read_text(encoding="utf-8")
    return (
        base
        .replace("{qid}", query["qid"])
        .replace("{challenge_type}", query.get("challenge_type", "?"))
        .replace("{output_type}", query.get("output_type", "?"))
        .replace("{query_text}", query["text"])
        .replace("{source}", query.get("source", "?"))
        .replace("{gold_intents_block}", _gold_intents_block(query))
        .replace("{document_block}", _doc_block(bundle))
    )


def _worker(query: dict, bundle: dict, pool: HostPool, model: str
            ) -> tuple[str, dict | None, str]:
    prompt = _build_prompt(query, bundle)
    client = pool.next()
    try:
        raw = _call_llm(client, model, prompt)
    except Exception as exc:
        return query["qid"], None, f"llm_error: {exc}"
    parsed = _extract_json(raw)
    if parsed is None:
        return query["qid"], None, f"parse_error: {raw[:120]!r}"
    return query["qid"], parsed, ""


def build(
    queries_path: Path, bundles_path: Path, out_path: Path,
    hosts: list[str], port: int, api_key: str, model: str, workers: int,
) -> dict[str, Any]:
    # Load.
    queries = [json.loads(ln) for ln in queries_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    bundles_raw = json.loads(bundles_path.read_text(encoding="utf-8"))
    bundle_lookup = {b["bundle_id"]: b for b in bundles_raw}
    print(f"[gold] {len(queries)} queries × bundle lookup ready ({len(bundle_lookup)} bundles)")

    pool = HostPool(hosts, port, api_key)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    golds: list[dict] = []
    errors: list[str] = []

    tasks = []
    for q in queries:
        bundle = bundle_lookup.get(q["bundle_id"])
        if bundle is None:
            errors.append(f"missing bundle: {q['bundle_id']}")
            continue
        tasks.append((q, bundle))

    with ThreadPoolExecutor(max_workers=workers) as ex, \
         out_path.open("w", encoding="utf-8") as fout:
        futures = {ex.submit(_worker, q, b, pool, model): (q, b) for q, b in tasks}
        done = 0
        for fut in as_completed(futures):
            done += 1
            qid, parsed, err = fut.result()
            if parsed is None:
                errors.append(f"{qid}: {err}")
                print(f"  [{done:>3}/{len(tasks)}] FAIL {qid} — {err[:100]}")
                continue
            # Build Gold record around the parsed payload.
            q = next(q for q, _ in tasks if q["qid"] == qid)
            gold = {
                "qid": qid,
                "evidence": parsed.get("evidence", []),
                "facts": parsed.get("facts", []),
                "tables": parsed.get("tables", []),
                "graphs": parsed.get("graphs", []),
                "contradictions": parsed.get("contradictions", []),
                "intents": q.get("gold_intents", []),
                "extractor_provenance": {"A": model, "human_verified": False},
            }
            fout.write(json.dumps(gold, ensure_ascii=False) + "\n")
            fout.flush()
            golds.append(gold)
            n_ev = len(gold["evidence"])
            n_f = len(gold["facts"])
            n_t = len(gold["tables"])
            n_g = len(gold["graphs"])
            print(f"  [{done:>3}/{len(tasks)}] OK   {qid}  ev={n_ev} facts={n_f} tab={n_t} graph={n_g}")

    print()
    print(f"[gold] wrote {len(golds)} gold records → {out_path}")
    print(f"[gold] errors: {len(errors)}")
    return {"n_total": len(golds), "n_errors": len(errors)}


if __name__ == "__main__":
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=Path, default=Path("data/queries/pilot_50.jsonl"))
    ap.add_argument("--bundles", type=Path, default=Path("data/bundles/all.json"))
    ap.add_argument("--out", type=Path, default=Path("data/gold/pilot_50.jsonl"))
    ap.add_argument("--hosts", default=",".join(DEFAULT_QWEN_HOSTS))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--api-key", default=os.environ.get("EXAONE_API_KEY", "EMPTY"))
    ap.add_argument("--model", default=os.environ.get("EXAONE_MODEL", "Qwen3.5-397B-A17B-FP8"))
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args()
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    s = build(args.queries, args.bundles, args.out,
              hosts, args.port, args.api_key, args.model, args.workers)
    sys.exit(0 if s["n_total"] > 0 else 1)
