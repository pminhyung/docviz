"""docviz v0.4.1 §4.4 — query generation pipeline.

For each (bundle, challenge_type) pair from the quota plan, call the LLM with
the base prompt + 1-shot demos and parse a Query JSON. Writes JSONL.

Uses Qwen3.5-397B via the local pool (configs/hosts-eval-qwen.yaml host 147)
for zero-cost generation. Plan §4.4 suggests GPT-4o-mini; we substitute Qwen
since it's free and we already have measurement parity confirmation.

Usage:
    python -m exaone.sft_gen.docviz.generate_queries \\
        --bundles data/bundles/all.json \\
        --out data/queries/pilot_50.jsonl \\
        --target-count 50 \\
        --seed 42
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import threading

import openai

from exaone.sft_gen.docviz.query_schema import Query, Intent
from exaone.sft_gen.docviz.quota import compute_quota, CHALLENGE_TYPES


# Default Qwen multi-host pool — matches configs/hosts-eval-qwen.yaml.
DEFAULT_QWEN_HOSTS = [
    "10.1.211.147", "10.1.211.148", "10.1.211.163", "10.1.211.164",
    "10.1.211.165", "10.1.211.166", "10.1.211.167", "10.1.211.168",
]


class HostPool:
    """Round-robin pool of OpenAI clients over a Qwen multi-host vLLM cluster."""

    def __init__(self, hosts: list[str], port: int, api_key: str):
        self._clients = [
            openai.OpenAI(base_url=f"http://{h}:{port}/v1", api_key=api_key)
            for h in hosts
        ]
        self._cursor = 0
        self._lock = threading.Lock()
        self.hosts = hosts

    def next(self) -> openai.OpenAI:
        with self._lock:
            client = self._clients[self._cursor % len(self._clients)]
            self._cursor += 1
            return client


REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_BASE_PATH = REPO_ROOT / "exaone/sft_gen/docviz/prompts/query_gen/base.txt"


def _doc_summary_lines(bundle: dict, max_chars_per_doc: int = 300) -> str:
    docs = bundle.get("docs") or bundle.get("documents") or []
    lines = []
    for i, d in enumerate(docs, 1):
        title = d.get("title", f"doc {i}")
        content = (d.get("content") or "")[:max_chars_per_doc].replace("\n", " ")
        lines.append(f"  [{i}] {title} — {content}…")
    return "\n".join(lines)


def _build_prompt(bundle: dict, challenge_type: str) -> str:
    base = PROMPT_BASE_PATH.read_text(encoding="utf-8")
    return (
        base
        .replace("{source}", bundle["source"])
        .replace("{bundle_id}", bundle["bundle_id"])
        .replace("{challenge_type}", challenge_type)
        .replace("{document_summaries}", _doc_summary_lines(bundle))
    )


_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*?\}\s*\Z")
_FENCED_JSON_RE = re.compile(r"```(?:json|JSON)?\s*\n([\s\S]*?)\n```")


def _extract_json(text: str) -> dict | None:
    """Robust extraction of a top-level JSON object from the model output.

    Qwen often produces "Thinking Process:\n...\n\n<final JSON>" or wraps
    output in ```json fences. Search strategy (in priority order):
      1. The LAST ```json … ``` fenced block (Qwen places final output last)
      2. The trailing balanced { … } object at end of text
      3. Anywhere in the text as a fallback
    """
    text = (text or "").strip()
    if not text:
        return None

    # 1) Last fenced JSON block.
    fenced = _FENCED_JSON_RE.findall(text)
    for blob in reversed(fenced):  # last-wins
        try:
            return json.loads(blob.strip())
        except json.JSONDecodeError:
            continue

    # 2) Try to parse the entire text as JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3) Walk from end backward to find a balanced { … } object.
    # Find every '{' index and try parsing from there to end.
    for i in range(len(text) - 1, -1, -1):
        if text[i] == "{":
            candidate = text[i:]
            # Find matching brace using a stack-based scan.
            depth = 0
            end = -1
            for j, ch in enumerate(candidate):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break
            if end == -1:
                continue
            try:
                return json.loads(candidate[:end])
            except json.JSONDecodeError:
                continue
    return None


def _call_llm(client: openai.OpenAI, model: str, prompt: str,
              max_retries: int = 2, disable_thinking: bool = True) -> str:
    """Single chat completion. Retries on transient API errors.

    disable_thinking: forwards `chat_template_kwargs={'enable_thinking': False}`
    to vLLM via extra_body. Qwen3.5's default chat template emits a `<think>…
    </think>` block before the actual response which burns the budget on
    structured-output tasks like this one. Disable it for JSON gen.
    """
    extra = {}
    if disable_thinking:
        extra["chat_template_kwargs"] = {"enable_thinking": False}
    for attempt in range(max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=4000,
                extra_body=extra if extra else None,
            )
            return resp.choices[0].message.content or ""
        except Exception:
            if attempt == max_retries:
                raise
            time.sleep(2 ** attempt)
    return ""


def _make_query(bundle: dict, challenge_type: str, parsed: dict,
                qid_seq: int) -> Query | None:
    """Validate the parsed LLM output and construct a Query dataclass."""
    text = (parsed.get("query_text") or "").strip()
    output_type = parsed.get("output_type", "")
    if not text or output_type not in {
        "quantitative", "relational", "temporal", "hierarchical", "comparative"
    }:
        return None
    raw_intents = parsed.get("gold_intents") or []
    intents = []
    for i, it in enumerate(raw_intents):
        if not isinstance(it, dict):
            continue
        intents.append(Intent(
            intent_id=str(it.get("intent_id", str(i + 1))),
            artifact_type_hint=str(it.get("artifact_type_hint", "any")),
            content_summary=str(it.get("content_summary", "")),
        ))
    if not intents:
        intents.append(Intent(
            intent_id="1", artifact_type_hint="any",
            content_summary=text[:120],
        ))
    return Query(
        qid=f"{bundle['source']}_{bundle['bundle_id']}_{challenge_type}_{qid_seq:03d}",
        text=text,
        bundle_id=bundle["bundle_id"],
        source=bundle["source"],
        challenge_type=challenge_type,
        output_type=output_type,
        gold_intent_count=len(intents),
        gold_intents=intents,
    )


def _worker(bundle: dict, challenge_type: str, idx: int,
            pool: HostPool, model: str) -> tuple[int, Query | None, str]:
    prompt = _build_prompt(bundle, challenge_type)
    client = pool.next()
    try:
        raw = _call_llm(client, model, prompt)
    except Exception as exc:
        return idx, None, f"llm_error: {exc}"
    parsed = _extract_json(raw)
    if parsed is None:
        return idx, None, f"parse_error: {raw[:120]!r}"
    q = _make_query(bundle, challenge_type, parsed, idx)
    if q is None:
        return idx, None, f"validation_error: {parsed!r}"
    return idx, q, ""


def generate(
    bundles_path: Path,
    output_jsonl: Path,
    target_count: int,
    seed: int,
    hosts: list[str],
    port: int,
    api_key: str,
    model: str,
    workers: int = 32,
) -> dict[str, Any]:
    bundles_raw = json.loads(bundles_path.read_text(encoding="utf-8"))
    print(f"[gen] {len(bundles_raw)} bundles loaded from {bundles_path}")

    quota = compute_quota(bundles_raw, target_count=target_count, seed=seed)
    bundle_lookup = {b["bundle_id"]: b for b in bundles_raw}

    tasks = []
    seq = 0
    for bid, challenges in quota.items():
        b = bundle_lookup[bid]
        for c in challenges:
            tasks.append((b, c, seq))
            seq += 1
    print(f"[gen] {len(tasks)} (bundle × challenge) tasks to generate")

    pool = HostPool(hosts=hosts, port=port, api_key=api_key)
    print(f"[gen] HostPool: {len(hosts)} hosts × {workers // len(hosts)} concurrent (workers={workers})")

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    queries: list[Query] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as ex, \
         output_jsonl.open("w", encoding="utf-8") as fout:
        futures = {ex.submit(_worker, b, c, i, pool, model): (b, c, i)
                   for (b, c, i) in tasks}
        done = 0
        for fut in as_completed(futures):
            done += 1
            idx, q, err = fut.result()
            if q is not None:
                fout.write(json.dumps(q.to_dict(), ensure_ascii=False) + "\n")
                fout.flush()
                queries.append(q)
                print(f"  [{done:>3}/{len(tasks)}] {q.qid}  challenge={q.challenge_type}  output={q.output_type}")
            else:
                errors.append(err)
                print(f"  [{done:>3}/{len(tasks)}] FAIL — {err}")

    # Summary
    by_challenge = Counter(q.challenge_type for q in queries)
    by_source = Counter(q.source for q in queries)
    by_output = Counter(q.output_type for q in queries)
    print()
    print(f"[gen] WROTE {len(queries)} queries → {output_jsonl}")
    print(f"[gen] FAILED {len(errors)}")
    print(f"[gen] challenge_type distribution: {dict(by_challenge)}")
    print(f"[gen] source distribution:         {dict(by_source)}")
    print(f"[gen] output_type distribution:    {dict(by_output)}")
    return {
        "n_total": len(queries),
        "n_failed": len(errors),
        "by_challenge": dict(by_challenge),
        "by_source": dict(by_source),
        "by_output": dict(by_output),
    }


if __name__ == "__main__":
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", type=Path,
                    default=Path("data/bundles/all.json"))
    ap.add_argument("--out", type=Path,
                    default=Path("data/queries/pilot_50.jsonl"))
    ap.add_argument("--target-count", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--hosts", default=",".join(DEFAULT_QWEN_HOSTS),
                    help="Comma-separated host IPs (Qwen multi-host pool).")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--api-key", default=os.environ.get("EXAONE_API_KEY", "EMPTY"))
    ap.add_argument("--model", default=os.environ.get(
        "EXAONE_MODEL", "Qwen3.5-397B-A17B-FP8"))
    ap.add_argument("--workers", type=int, default=32,
                    help="Total concurrent workers across all hosts (default 8 hosts × 4 = 32).")
    args = ap.parse_args()

    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    summary = generate(
        args.bundles, args.out, args.target_count, args.seed,
        hosts, args.port, args.api_key, args.model, args.workers,
    )
    sys.exit(0 if summary["n_failed"] < max(summary["n_total"], 1) * 0.10 else 1)
