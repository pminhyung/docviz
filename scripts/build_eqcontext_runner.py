#!/usr/bin/env python3
"""Build a B6-equalized-context runner JSONL (cycle 4 experiment).

Injects the full bundle text into the user prompt (same as S1's context budget)
in addition to the attachments[]. This tests whether B6's loss to S1 across
cycles 1-3 is a context-budget asymmetry (eval artifact) vs a true B6 module
weakness.

If B6_eqctx ≥ S1: eval artifact confirmed → scale to 300 with this protocol.
If B6_eqctx < S1: agent architecture has a genuine cost — needs deeper rethink.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _doc_block(bundle: dict, max_chars: int = 1200) -> str:
    docs = bundle.get("docs") or bundle.get("documents") or []
    out = []
    for i, d in enumerate(docs, 1):
        title = d.get("title", f"doc {i}")
        content = (d.get("content") or "")[:max_chars].replace("\n", " ")
        out.append(f"[{i}] {title}\n{content}")
    return "\n\n".join(out)


def main(queries: Path, bundles: Path, out: Path) -> int:
    qs = [json.loads(l) for l in queries.read_text(encoding="utf-8").splitlines() if l.strip()]
    bs = {b["bundle_id"]: b for b in json.loads(bundles.read_text(encoding="utf-8"))}
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as fout:
        for q in qs:
            bundle = bs.get(q["bundle_id"])
            if not bundle: continue
            ctx_block = (
                "## BUNDLE CONTENTS (full text; use as primary context, "
                "supplement with doc_search if needed)\n"
                + _doc_block(bundle) + "\n\n"
                "## QUERY\n"
            )
            new = dict(q)
            new["prompt"] = ctx_block + q["prompt"]
            fout.write(json.dumps(new, ensure_ascii=False) + "\n")
            n += 1
    print(f"[eqctx] wrote {n} rows → {out}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=Path, default=Path("data/queries/pilot_50_runner.jsonl"))
    ap.add_argument("--bundles", type=Path, default=Path("data/bundles/all.json"))
    ap.add_argument("--out", type=Path, default=Path("data/queries/pilot_50_eqctx_runner.jsonl"))
    args = ap.parse_args()
    main(args.queries, args.bundles, args.out)
