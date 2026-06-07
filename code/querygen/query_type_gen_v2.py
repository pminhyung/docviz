"""query_type_gen v2 — natural user queries, anchored to the source's reasoning/
evidence label, with viz_type as a GOLD label (not in the query text).

Fixes over v1:
  (a) REALISTIC STYLE. Queries read like a real user of a document-chat assistant
      ("Can you show me how ...", "Help me compare ..."). The user NEVER names a
      chart/diagram primitive — choosing the viz type is the agent's (TMG's) job —
      so target_viz_type is recorded as a gold label, not embedded in the query.
  (b) SOURCE-LABEL ANCHORING. Generation is conditioned on the bundle's VALIDATED
      Loong reasoning label (level→task: Chain-of-Reasoning / Clustering) and its
      citation evidence (Reference/Citation). Multi-document challenge is then
      intrinsic (the citation chain spans docs), per exec-plan Stage-2 "anchor the
      query on the sample's reasoning marker".
  (c) NO FORCED TYPES. The model only assigns a viz_type that NATURALLY fits the
      query's information structure; pool types with no natural fit go to "unused"
      — eliminating the "constructed" sequenceDiagram framings of v1.

Pool is dataset-conditioned (SOURCE_POOL in query_type_gen).

Usage:
    python -m code.querygen.query_type_gen_v2 \
        --bundles data/bundles/loong_phase1.json \
        --compressed data/queries/loong_phase1_compressed.json \
        --out data/queries/loong_phase1_typed_v2.jsonl --hosts <8> [--limit N]
"""
from __future__ import annotations
import argparse, json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from exaone.sft_gen.docviz.generate_queries import HostPool, _call_llm, _extract_json, DEFAULT_QWEN_HOSTS
from code.querygen.query_type_gen import _pool_for, SOURCE_POOL
from code.querygen.pipeline_v042 import _citation_anchor

REPO = Path(__file__).resolve().parents[2]

# Loong task → its natural reasoning description (for the anchor).
LOONG_TASK_DESC = {
    "chain_of_reasoning": "follow a logical/citation chain that links the documents step by step",
    "clustering": "group and relate the documents by shared concepts, methods, or lineage",
}

PROMPT = """You write queries that a REAL USER would type into a document-chat assistant that can produce visualizations. The assistant decides the chart/diagram type itself — so the USER never names a visualization type, library, or format, and never refers to documents by id.

## This document set
A Loong "{task}" instance. Its VALIDATED cross-document reasoning is to {task_desc}. The documents are tied together by this real relationship structure:
{anchor}

## Document facts (per document; [1],[2],... are distinct documents)
{facts}

## What to produce
Realistic user requests for a VISUALIZATION, each of which:
- Sounds like a real person ("Can you show me how ...", "I'd like to compare ...", "Help me understand the relationship between ..."). Conversational, specific to this content, NO visualization-type words, NO doc ids.
- INTRINSICALLY needs >= 2 documents linked through the relationship structure above (the source's {task} reasoning). A single-document answer must be impossible.
- Is genuinely groundable: the entities/relations/values the visualization would need actually appear in the facts (assembling them is the assistant's job).

For each query, YOU assign the best-fitting gold `target_viz_type` from the pool below — but ONLY if that type's structure NATURALLY matches what the user is asking for. Never manufacture an interaction/sequence/timeline framing the content doesn't really have. Cover as many pool types as NATURALLY apply across your queries; put pool types with no natural fit in "unused".

## Visualization pool (GOLD labels — must NOT appear in the user query text)
{pool}

## Output STRICT JSON only
```json
{{"queries": [
   {{"query": "<natural user request, no viz-type words, no doc ids>",
     "target_viz_type": "<pool key that naturally fits>",
     "reasoning_type": "{task}",
     "evidence_docs": [1, 2],
     "cross_doc_link": "<the bridge/shared dimension linking the docs>"}}
 ],
 "unused": [{{"viz_type": "<pool key>", "why": "no natural fit in this set"}}]}}
```"""


def _gen(bundle: dict, facts: str, pool: dict, model, host_pool) -> dict:
    task = bundle["metadata"].get("loong_task", "chain_of_reasoning")
    prompt = PROMPT.format(
        task=task, task_desc=LOONG_TASK_DESC.get(task, "integrate the documents"),
        anchor=_citation_anchor(bundle), facts=facts[:13000],
        pool="\n".join(f"  - {k}: {v}" for k, v in pool.items()),
    )
    return _extract_json(_call_llm(host_pool.next(), model, prompt)) or {"queries": [], "unused": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", type=Path, default=REPO / "data/bundles/loong_phase1.json")
    ap.add_argument("--compressed", type=Path, default=REPO / "data/queries/loong_phase1_compressed.json")
    ap.add_argument("--out", type=Path, default=REPO / "data/queries/loong_phase1_typed_v2.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pool", choices=["chart", "diagram", "both"], default=None)
    ap.add_argument("--hosts", default=",".join(DEFAULT_QWEN_HOSTS))
    ap.add_argument("--model", default="Qwen3.5-397B-A17B-FP8")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    bundles = json.loads(args.bundles.read_text())
    if args.limit:
        bundles = bundles[: args.limit]
    comp = json.loads(args.compressed.read_text())
    host_pool = HostPool([h.strip() for h in args.hosts.split(",") if h.strip()], 8000, "EMPTY")

    def run(b):
        pool = _pool_for(b["source"], args.pool)
        return b, _gen(b, comp.get(b["bundle_id"], ""), pool, args.model, host_pool)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    recs, n_q, n_md_bad, by_type, by_reason = [], 0, 0, Counter(), Counter()
    with ThreadPoolExecutor(max_workers=args.workers) as ex, args.out.open("w") as fout:
        for fut in as_completed([ex.submit(run, b) for b in bundles]):
            b, out = fut.result()
            qs = []
            for q in out.get("queries", []):
                docs = q.get("evidence_docs", [])
                if not (isinstance(docs, list) and len(set(docs)) >= 2):
                    n_md_bad += 1
                    continue
                qs.append(q); by_type[q.get("target_viz_type", "?")] += 1
                by_reason[q.get("reasoning_type", "?")] += 1
            rec = {"bundle_id": b["bundle_id"], "source": b["source"],
                   "challenge_type": b["metadata"]["challenge_type"],
                   "loong_task": b["metadata"].get("loong_task"), "queries": qs,
                   "unused": out.get("unused", [])}
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n"); fout.flush()
            recs.append(rec); n_q += len(qs)
            print(f"  {b['bundle_id']} ({b['metadata'].get('loong_task')}): {len(qs)} queries "
                  f"over {len({q.get('target_viz_type') for q in qs})} types")

    print(f"\n[v2] {len(recs)} bundles | {n_q} natural multi-doc queries | dropped {n_md_bad} single-doc")
    print(f"[v2] viz coverage {len(by_type)}: {dict(by_type)}")
    print(f"[v2] reasoning_type: {dict(by_reason)}")
    print(f"[v2] → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
