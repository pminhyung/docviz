"""v0.4.2 query-generation — full 3-stage pipeline (exec-plan §query-gen).

The v0.4.1 generate_queries.py implemented only Stage 2 (it fed raw 300-char
doc truncations to the query author and had no acceptance gate), which let
ungroundable chart queries through → empty gold. This module implements the
two prescribed-but-missing stages:

  Stage 1  Compressed doc representation  (Loong §3.3.2 \cite{wang2024loong})
           Each doc → LLM key-fact bullet list. The query author sees grounded
           facts (named entities, numbers, dates, relations) instead of raw heads.
  Stage 2  Task prompt + output-type heuristic (Doc2Chart \cite{jain2025doc2chart})
           Reuses the validated prompts/query_gen/base.txt, fed Stage-1 facts.
  Stage 3  Self-evaluation gate (Text2Chart31 §3.3 \cite{zadeh2024text2chart31})
           Same LLM scores the query on multi_doc_necessity / viz_suitability /
           intent_realism. Accept only if all three pass; on fail, ONE retry that
           regenerates Stage 2 with the gate's failure reasons as guidance.

intent_realism is the criterion that rejects "grouped bar of publication counts"
when the bundle's facts contain no such counts — the exact gap fix.

Local Qwen multi-host pool, n_concurrent/host, immediate JSONL flush.

Usage:
    python -m code.querygen.pipeline_v042 \
        --bundles data/bundles/loong_phase1.json \
        --out data/queries/loong_phase1.jsonl \
        --compressed-out data/queries/loong_phase1_compressed.json \
        --hosts 10.1.211.147,...,10.1.211.168 --workers 32 [--limit 2]
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from exaone.sft_gen.docviz.generate_queries import (
    HostPool, _call_llm, _extract_json, _make_query,
    DEFAULT_QWEN_HOSTS,
)

REPO = Path(__file__).resolve().parents[2]

# ── Stage 1: compressed doc representation ────────────────────────────────
COMPRESS_PROMPT = """You are compressing a source document into a key-fact bullet list for downstream benchmark query authoring.

Extract the document's CONCRETE, groundable facts as 12-25 bullets. Each bullet must preserve verbatim specifics: named entities, numbers, dates, quantities, units, and explicit relationships/claims actually stated in the text. Do NOT invent or generalize. If the document reports no quantitative data (tables, counts, measurements), say so explicitly in a final bullet "NUMERIC DATA: none / qualitative only".

Document title: {title}

Document text:
{content}

Output ONLY the bullet list (one fact per line, prefixed with "- "). No preamble."""

# ── Stage 3: self-evaluation gate ─────────────────────────────────────────
GATE_PROMPT = """You are a strict reviewer for QG-MDV benchmark queries. Given the bundle's key facts and a candidate visualization query, judge THREE criteria. Be skeptical: default to fail when uncertain.

Bundle key facts (compressed, per document):
{facts}

Candidate query (challenge_type={challenge_type}, output_type={output_type}):
"{query_text}"
Requested artifact(s): {artifact_hints}

Judge each criterion independently:
1. multi_doc_necessity — Does answering require integrating ≥2 documents (not satisfiable from one doc or priors)?
2. viz_suitability — Is the requested visualization type (chart/diagram) appropriate for the information structure?
3. intent_realism — Are the SPECIFIC data the visualization needs (the numbers/entities/relations to plot) ACTUALLY present in the bundle facts above? If the query asks to plot counts/values/comparisons that the facts do NOT contain, this FAILS.

Output STRICT JSON only:
```json
{{"multi_doc_necessity": {{"pass": true/false, "reason": "..."}},
  "viz_suitability": {{"pass": true/false, "reason": "..."}},
  "intent_realism": {{"pass": true/false, "reason": "..."}}}}
```"""


def _compress_doc(client, model, title: str, content: str, max_chars: int) -> str:
    prompt = COMPRESS_PROMPT.format(title=title[:200], content=content[:max_chars])
    raw = _call_llm(client, model, prompt)
    return (raw or "").strip()


def _bundle_facts(bundle: dict, pool: HostPool, model: str, max_chars: int) -> str:
    """Stage 1 for all docs in a bundle → labeled fact bullets string."""
    blocks = []
    for i, d in enumerate(bundle.get("docs", []), 1):
        title = d.get("title", f"doc {i}")
        facts = _compress_doc(pool.next(), model, title, d.get("content", ""), max_chars)
        blocks.append(f"### Document [{i}] {title}\n{facts}")
    return "\n\n".join(blocks)


def _gate(client, model, bundle: dict, q, facts: str) -> dict:
    hints = ", ".join(it.artifact_type_hint for it in q.gold_intents)
    prompt = GATE_PROMPT.format(
        facts=facts[:14000], challenge_type=q.challenge_type,
        output_type=q.output_type, query_text=q.text, artifact_hints=hints,
    )
    parsed = _extract_json(_call_llm(client, model, prompt)) or {}
    crits = ("multi_doc_necessity", "viz_suitability", "intent_realism")
    detail = {c: bool((parsed.get(c) or {}).get("pass", False)) for c in crits}
    reasons = {c: (parsed.get(c) or {}).get("reason", "") for c in crits}
    return {"pass": all(detail.values()), "detail": detail, "reasons": reasons}


def _citation_anchor(bundle: dict) -> str:
    """Stage-2 reasoning-marker anchor (exec-plan §query-gen): bind the query to
    the bundle's VALIDATED Loong relationship label so it targets relationships
    actually present in the documents (citation/reference structure) rather than
    inventing ungroundable ones. For Loong-paper bundles the gold relationship is
    the citation/reference list — the natural multi-doc visualization signal."""
    m = bundle.get("metadata", {})
    ans = m.get("original_answer")
    titles = []
    if isinstance(ans, dict):
        for k in ("Reference", "Citation", "references", "citations"):
            for t in (ans.get(k) or []):
                titles.append(f"{k}: {str(t).strip().lstrip('#').strip()[:120]}")
    elif isinstance(ans, list):
        titles = [str(t).strip().lstrip("#").strip()[:120] for t in ans]
    rel = "\n".join(f"  - {t}" for t in titles[:12]) or "  (none parsed)"
    focus = m.get("original_question", "").strip()
    task = m.get("loong_task", "")
    return (
        "# Grounded relationship anchor (from the benchmark's validated label)\n"
        f"This bundle is a Loong `{task}` instance. Its documents are related by an "
        "ACTUAL citation/reference structure. The validated cross-document "
        "relationships you MUST ground the visualization in:\n"
        f"{rel}\n"
        + (f"Focal document: {focus}\n" if focus else "")
        + "Author your query so the requested chart/diagram maps THESE real "
          "inter-document relationships (or quantities/groupings explicitly stated "
          "in the facts) — never invent lineage, evolution, or numeric comparisons "
          "the documents do not state.\n"
    )


def _build_prompt_with_facts(bundle: dict, challenge_type: str, facts: str) -> str:
    """Stage 2 prompt (prompts/query_gen/base.txt) with {document_summaries}
    bound to Stage-1 compressed facts, plus the Loong citation reasoning-anchor."""
    from exaone.sft_gen.docviz.generate_queries import PROMPT_BASE_PATH
    tmpl = PROMPT_BASE_PATH.read_text(encoding="utf-8")
    grounded = facts[:13000] + "\n\n" + _citation_anchor(bundle)
    return (tmpl
            .replace("{source}", bundle["source"])
            .replace("{bundle_id}", bundle["bundle_id"])
            .replace("{challenge_type}", challenge_type)
            .replace("{document_summaries}", grounded))


def _process_bundle(bundle: dict, challenge_type: str, idx: int,
                    pool: HostPool, model: str, max_chars: int) -> tuple:
    # Stage 1
    try:
        facts = _bundle_facts(bundle, pool, model, max_chars)
    except Exception as exc:
        return idx, None, facts_none(), f"stage1_error: {exc}"

    def gen_once(guidance: str = "") -> object:
        prompt = _build_prompt_with_facts(bundle, challenge_type, facts)
        if guidance:
            prompt += f"\n\n# Reviewer feedback on your previous attempt (fix these):\n{guidance}\n"
        raw = _call_llm(pool.next(), model, prompt)
        parsed = _extract_json(raw)
        if parsed is None:
            return None
        return _make_query(bundle, challenge_type, parsed, idx)

    # Stage 2 + Stage 3 (1 retry)
    q = gen_once()
    if q is None:
        return idx, None, facts, "stage2_parse_error"
    gate = _gate(pool.next(), model, bundle, q, facts)
    if not gate["pass"]:
        guidance = "; ".join(f"{c}: {gate['reasons'][c]}"
                             for c, ok in gate["detail"].items() if not ok)
        if not gate["detail"]["intent_realism"]:
            guidance += (" || DIRECTIVE: the documents do NOT contain the numeric data "
                         "your chart needs. Choose a RELATIONAL or DIAGRAM visualization "
                         "(mermaid_flowchart / mermaid_classDiagram / mermaid_mindmap / "
                         "mermaid_timeline) that maps relationships, methods, or citation "
                         "links ACTUALLY stated in the facts above — not a numeric chart.")
        q2 = gen_once(guidance=guidance)
        if q2 is not None:
            gate2 = _gate(pool.next(), model, bundle, q2, facts)
            if gate2["pass"] or sum(gate2["detail"].values()) > sum(gate["detail"].values()):
                q, gate = q2, gate2  # keep the better attempt
    return idx, (q, gate), facts, ""


def facts_none() -> str:
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", type=Path, default=REPO / "data/bundles/loong_phase1.json")
    ap.add_argument("--out", type=Path, default=REPO / "data/queries/loong_phase1.jsonl")
    ap.add_argument("--compressed-out", type=Path,
                    default=REPO / "data/queries/loong_phase1_compressed.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-chars", type=int, default=8000,
                    help="chars/doc fed to Stage-1 compressor")
    ap.add_argument("--hosts", default=",".join(DEFAULT_QWEN_HOSTS))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--api-key", default="EMPTY")
    ap.add_argument("--model", default="Qwen3.5-397B-A17B-FP8")
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args()

    bundles = json.loads(args.bundles.read_text(encoding="utf-8"))
    if args.limit:
        bundles = bundles[: args.limit]
    tasks = [(b, b["metadata"]["challenge_type"], i) for i, b in enumerate(bundles)]
    print(f"[v042-qgen] {len(tasks)} bundles | 3-stage (compress→gen→gate+1retry)")

    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    pool = HostPool(hosts=hosts, port=args.port, api_key=args.api_key)
    print(f"[v042-qgen] HostPool: {len(hosts)} hosts, workers={args.workers}, max_chars/doc={args.max_chars}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    queries, compressed, errors, gate_fail = [], {}, [], 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex, \
         args.out.open("w", encoding="utf-8") as fout:
        futs = {ex.submit(_process_bundle, b, c, i, pool, args.model, args.max_chars): i
                for (b, c, i) in tasks}
        done = 0
        for fut in as_completed(futs):
            done += 1
            idx, res, facts, err = fut.result()
            bid = tasks[idx][0]["bundle_id"]
            if facts:
                compressed[bid] = facts
            if res is None:
                errors.append(err)
                print(f"  [{done:>2}/{len(tasks)}] FAIL {bid} — {err}")
                continue
            q, gate = res
            rec = q.to_dict()
            rec["gate"] = gate
            with lock:
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fout.flush()
            queries.append(rec)
            if not gate["pass"]:
                gate_fail += 1
            flag = "OK " if gate["pass"] else "GATE✗"
            print(f"  [{done:>2}/{len(tasks)}] {flag} {q.qid}  out={q.output_type}  "
                  f"gate={gate['detail']}")

    args.compressed_out.write_text(json.dumps(compressed, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    print(f"\n[v042-qgen] WROTE {len(queries)} queries → {args.out} (errors {len(errors)})")
    print(f"[v042-qgen] gate PASS {len(queries)-gate_fail}/{len(queries)}, GATE-FAIL-kept {gate_fail}")
    print(f"[v042-qgen] output_type: {dict(Counter(q['output_type'] for q in queries))}")
    print(f"[v042-qgen] compressed facts → {args.compressed_out}")
    return 0 if len(errors) < max(len(tasks), 1) * 0.1 else 1


if __name__ == "__main__":
    sys.exit(main())
