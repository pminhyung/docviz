"""D24 — Full subtype ranking with feasibility flags.

Replaces the per-doc top-1 pick of subtype_assigner.py. For each doc,
the LLM ranks ALL chart subtypes (bar, line, pie, scatter, combo, area,
radar, doughnut) AND ALL diagram subtypes (flowchart, sequenceDiagram,
classDiagram, stateDiagram, erDiagram, gantt, sankey) by fit, AND flags
each one as `feasible` (the viz would be meaningful) or not.

Output: data/viz/_subtype_rankings_v2.jsonl

This output is the input to a global Hungarian assignment that balances
the corpus-wide subtype distribution under feasibility constraints.

Run:
    python -m scripts.viz.rank_subtypes_v2 [--limit N] [--workers 8]
"""
import argparse
import collections
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from scripts.config import CHART_SUBTYPES, DIAGRAM_SUBTYPES
from scripts.utils.llm_clients import call_model
from scripts.viz.subtype_assigner import (
    _extract_json, prepare_doc_excerpt,
)

# Optional local-endpoint round-robin (set by --endpoints CLI). When non-None,
# rank_one() bypasses the 397B llmpool and round-robins these OpenAI-compatible
# endpoints instead. Used for parallel ranking on locally-served Qwen variants.
_LOCAL_ENDPOINTS: list | None = None
_LOCAL_MODEL: str | None = None
_RR_LOCK = __import__("threading").Lock()
_RR_IDX = 0


def _local_call_model(prompt: str, system_prompt: str = "",
                       temperature: float = 0.7) -> str:
    """Round-robin OpenAI chat call across `_LOCAL_ENDPOINTS`.

    Sampling config follows the Qwen3.6-27B-Instruct (non-thinking) recipe:
        temperature=0.7, top_p=0.80, top_k=20, min_p=0.0,
        presence_penalty=1.5, repetition_penalty=1.0
    `top_k`, `min_p`, `repetition_penalty` are passed through `extra_body`
    because they are vLLM extensions, not standard OpenAI fields.
    `chat_template_kwargs={"enable_thinking": False}` disables Qwen3.6's
    default thinking-mode preamble (verified empirically: without this, the
    model prepends "Here's a thinking process:..." and burns the budget
    before producing JSON).
    """
    global _RR_IDX
    import openai
    with _RR_LOCK:
        idx = _RR_IDX % len(_LOCAL_ENDPOINTS)
        _RR_IDX += 1
    base = _LOCAL_ENDPOINTS[idx]
    client = openai.OpenAI(base_url=base, api_key="EMPTY", timeout=180.0)
    resp = client.chat.completions.create(
        model=_LOCAL_MODEL,
        messages=[
            {"role": "system", "content": system_prompt or "You output only valid JSON as instructed."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        top_p=0.80,
        presence_penalty=1.5,
        extra_body={
            "top_k": 20,
            "min_p": 0.0,
            "repetition_penalty": 1.0,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )
    return resp.choices[0].message.content or ""

VIZ_DIR = os.path.join(ROOT, "data", "viz")
OUT = os.path.join(VIZ_DIR, "_subtype_rankings_v2.jsonl")

VALID_CHART = list(CHART_SUBTYPES)        # 8 entries
VALID_DIAGRAM = list(DIAGRAM_SUBTYPES)    # 7 entries

PROMPT = """You are evaluating which visualization subtypes are SUITABLE for a document.

For CHART, rank ALL of these subtypes by how well they fit this document, AND for each one say whether it is feasible (a meaningful chart could actually be drawn from data the document contains):

CHART subtypes (8 total — must rank ALL):
- bar       : numerical comparisons across categories
- line      : trends over time or sequences
- pie       : proportional composition (parts of a whole)
- scatter   : correlation between two variables
- combo     : two related metrics with different scales
- area      : cumulative trends or stacked compositions
- radar     : multi-dimensional comparison (3+ attributes)
- doughnut  : proportional data with emphasis on specific segments

For DIAGRAM, rank ALL of these subtypes the same way:

DIAGRAM subtypes (7 total — must rank ALL):
- flowchart       : step-by-step processes, decision flows
- sequenceDiagram : temporal interactions between entities
- classDiagram    : hierarchical structures, class relationships
- stateDiagram    : state transitions, lifecycle stages
- erDiagram       : entity relationships, data models
- gantt           : project timelines, scheduling
- sankey          : flow/distribution between categories

Feasibility rule:
- feasible = true  if a meaningful viz of that subtype could be drawn from data/content actually present in the document
- feasible = false if the document genuinely lacks the content needed (e.g. doughnut needs proportional composition; radar needs ≥3 comparable dimensions; gantt needs scheduled tasks)

Be honest: if only 2-3 chart subtypes are truly feasible, flag the rest as feasible=false. The benchmark needs honest feasibility, not forced ranking.

Document excerpt (first 2500 chars):
{doc_excerpt}

Document language: {doc_language}
Document domain: {doc_domain}

Output JSON only, exactly this shape:
{{
  "chart_rankings": [
    {{"subtype": "bar", "rank": 1, "feasible": true,  "reason": "one short clause"}},
    {{"subtype": "line", "rank": 2, "feasible": true, "reason": "..."}},
    ... (all 8 chart subtypes; rank 1..8 unique)
  ],
  "diagram_rankings": [
    {{"subtype": "flowchart", "rank": 1, "feasible": true, "reason": "..."}},
    ... (all 7 diagram subtypes; rank 1..7 unique)
  ]
}}"""


def _normalize_rank_list(items: list, valid: list) -> list:
    """Coerce LLM rank list → canonical [{subtype, rank, feasible, reason}].

    - Drops unknown subtypes.
    - Backfills missing subtypes at the end (rank > given), feasible=False.
    - Renumbers ranks 1..N to be sequential after backfill.
    """
    seen = {}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        st = str(it.get("subtype", "")).strip()
        if st not in valid:
            continue
        try:
            r = int(it.get("rank", 99))
        except (TypeError, ValueError):
            r = 99
        seen[st] = {
            "subtype": st,
            "rank": r,
            "feasible": bool(it.get("feasible", False)),
            "reason": str(it.get("reason", ""))[:200],
        }
    out = sorted(seen.values(), key=lambda x: x["rank"])
    # Backfill missing as rank=len+1, infeasible
    for st in valid:
        if st not in seen:
            out.append({"subtype": st, "rank": len(out) + 1,
                         "feasible": False, "reason": "(not returned by LLM)"})
    # Re-rank 1..N
    for i, item in enumerate(out, 1):
        item["rank"] = i
    return out


def rank_one(row: dict) -> dict:
    excerpt = prepare_doc_excerpt(row, max_chars=2500)
    prompt = PROMPT.format(
        doc_excerpt=excerpt,
        doc_language=row.get("lang", "en"),
        doc_domain=row.get("domain", "general"),
    )
    if _LOCAL_ENDPOINTS:
        raw = _local_call_model(prompt)
    else:
        raw = call_model(
            "qwen397b",
            system_prompt="You output only valid JSON as instructed.",
            user_content=prompt,
            temperature=0.2,
        )
    parsed = _extract_json(raw) or {}
    return {
        "doc_id": row["doc_id"],
        "chart_rankings": _normalize_rank_list(parsed.get("chart_rankings"), VALID_CHART),
        "diagram_rankings": _normalize_rank_list(parsed.get("diagram_rankings"), VALID_DIAGRAM),
        "raw": raw[:3000],
    }


def _load_done(path: str) -> set:
    if not os.path.exists(path):
        return set()
    out = set()
    with open(path) as f:
        for line in f:
            try:
                out.add(json.loads(line)["doc_id"])
            except Exception:
                continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--corpus", default=os.path.join(ROOT, "data", "documents",
                                                       "corpus.jsonl"))
    ap.add_argument("--endpoints", default="",
                     help="Comma-separated OpenAI base URLs. If set, bypass "
                          "the 397B llmpool and round-robin across these "
                          "endpoints instead.")
    ap.add_argument("--model", default="Qwen3.6-27B",
                     help="served-model-name for the local endpoints "
                          "(only used when --endpoints is set).")
    args = ap.parse_args()

    if args.endpoints:
        global _LOCAL_ENDPOINTS, _LOCAL_MODEL
        _LOCAL_ENDPOINTS = [u.strip().rstrip("/") for u in args.endpoints.split(",") if u.strip()]
        _LOCAL_MODEL = args.model
        print(f"[rank] using local endpoints: {_LOCAL_ENDPOINTS} (model={_LOCAL_MODEL})")

    rows = [json.loads(l) for l in open(args.corpus) if l.strip()]
    if args.limit > 0:
        rows = rows[:args.limit]
    done = _load_done(OUT)
    todo = [r for r in rows if r["doc_id"] not in done]
    print(f"[rank] total={len(rows)} done={len(done)} todo={len(todo)} "
          f"workers={args.workers}")

    os.makedirs(VIZ_DIR, exist_ok=True)
    n_ok = 0
    n_fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex, \
         open(OUT, "a", encoding="utf-8") as f:
        futures = {ex.submit(rank_one, r): r for r in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            r = futures[fut]
            try:
                res = fut.result()
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
                f.flush()
                n_ok += 1
            except Exception as e:
                n_fail += 1
                print(f"  FAIL {r['doc_id']}: {type(e).__name__}: {e}", flush=True)
            if i % 25 == 0:
                print(f"  {i}/{len(todo)} ok={n_ok} fail={n_fail}", flush=True)
    print(f"[rank] done. ok={n_ok} fail={n_fail}  out={OUT}")

    # Quick supply summary
    chart_supply = collections.Counter()
    diag_supply = collections.Counter()
    chart_top1 = collections.Counter()
    with open(OUT) as f:
        for line in f:
            d = json.loads(line)
            for r in d.get("chart_rankings", []):
                if r["feasible"]:
                    chart_supply[r["subtype"]] += 1
            for r in d.get("diagram_rankings", []):
                if r["feasible"]:
                    diag_supply[r["subtype"]] += 1
            top = next((r for r in d.get("chart_rankings", []) if r["rank"] == 1), {})
            if top:
                chart_top1[top.get("subtype", "?")] += 1
    print()
    print("== chart subtype FEASIBILITY supply (count of docs where feasible=true) ==")
    for st in VALID_CHART:
        print(f"  {st:9s}: {chart_supply[st]}")
    print()
    print("== chart subtype TOP-1 (rank=1, regardless of feasibility) ==")
    for st in VALID_CHART:
        print(f"  {st:9s}: {chart_top1[st]}")
    print()
    print("== diagram subtype FEASIBILITY supply ==")
    for st in VALID_DIAGRAM:
        print(f"  {st:14s}: {diag_supply[st]}")


if __name__ == "__main__":
    main()
