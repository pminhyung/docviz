"""Loong source loader → v0.4.2 QG-MDV bundle schema.

Loong (MozerWang/Loong, EMNLP 2024 Oral; data on ModelScope iic/Loong) provides
extended multi-doc QA. We use the English *paper* split (arXiv markdown, every
bundle's docs resolve locally) for the v0.4.2 Phase-1 foundation pilot.

Loong `level` == task (README §data):
    level1 Spotlight Locating, level2 Comparison, level3 Clustering,
    level4 Chain of Reasoning.
v0.4.2 challenge-type map (paper draft §corpus table):
    level4 Chain of Reasoning -> multi_hop          (다단계 추론)
    level3 Clustering         -> artifact_planning  (산출물 계획)

Output matches the existing bundle schema used by data/bundles/*.json:
    {bundle_id, source, docs:[{doc_id,title,content,page_id}], metadata:{...}}

This loader only BUILDS bundles (documents + Loong task metadata). The
viz-oriented query + gold are generated downstream by the local-Qwen query-gen
pipeline (no closed API keys in this env).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOONG_JSONL = REPO / "data/_raw/loong_repo/data/loong.jsonl"
DOC_ROOT = REPO / "data/_raw/loong_ms/doc_extracted/doc"

# Loong level -> v0.4.2 challenge type (paper draft corpus table).
LEVEL_TO_CHALLENGE = {4: "multi_hop", 3: "artifact_planning"}
_HEADER_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _index_docs(doc_root: Path) -> dict[str, Path]:
    """basename -> path for every doc under doc/{financial,legal,paper}."""
    idx: dict[str, Path] = {}
    for p in glob.glob(str(doc_root / "**" / "*.md"), recursive=True):
        idx.setdefault(os.path.basename(p), Path(p))
    return idx


def _title_of(text: str, fallback: str) -> str:
    m = _HEADER_RE.search(text)
    return m.group(1).strip() if m else fallback


def build_bundles(
    n: int = 30,
    seed: int = 42,
    doc_min: int = 3,
    doc_max: int = 5,
    per_challenge: dict[int, int] | None = None,
) -> list[dict]:
    rows = _load_jsonl(LOONG_JSONL)
    doc_idx = _index_docs(DOC_ROOT)

    # English academic-paper bundles whose docs all resolve locally, within the
    # doc-count band (keeps Phase-1 context manageable; gate is discrimination).
    pool: dict[int, list[dict]] = {3: [], 4: []}
    for r in rows:
        if r["language"] != "en" or r["type"] != "paper":
            continue
        if r["level"] not in LEVEL_TO_CHALLENGE:
            continue
        if not (doc_min <= len(r["doc"]) <= doc_max):
            continue
        if not all(d in doc_idx for d in r["doc"]):
            continue
        pool[r["level"]].append(r)

    # Stratified: split n evenly across the two available challenge types.
    if per_challenge is None:
        half = n // 2
        per_challenge = {4: half, 3: n - half}  # level4 multi_hop, level3 artifact_planning

    rng = random.Random(seed)
    chosen: list[dict] = []
    for level, k in per_challenge.items():
        cand = pool[level]
        if len(cand) < k:
            raise ValueError(f"level {level}: need {k}, only {len(cand)} resolvable bundles")
        chosen.extend(rng.sample(cand, k))

    bundles = []
    for i, r in enumerate(chosen):
        challenge = LEVEL_TO_CHALLENGE[r["level"]]
        docs = []
        for fname in r["doc"]:
            text = doc_idx[fname].read_text(encoding="utf-8", errors="replace")
            docs.append({
                "doc_id": Path(fname).stem,
                "title": _title_of(text, Path(fname).stem),
                "content": text,
                "page_id": None,
            })
        bundles.append({
            "bundle_id": f"loong_{i:03d}",
            "source": "loong",
            "docs": docs,
            "metadata": {
                "language": "en",
                "challenge_type": challenge,
                "loong_level": r["level"],
                "loong_task": {3: "clustering", 4: "chain_of_reasoning"}[r["level"]],
                "loong_id": r["id"],
                "loong_length": r["length"],
                "original_question": r["question"],
                "original_instruction": r["instruction"],
                "original_answer": r["answer"],
                "doc_titles": [d["title"] for d in docs],
                "n_docs": len(docs),
            },
        })
    return bundles


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--doc-min", type=int, default=3)
    ap.add_argument("--doc-max", type=int, default=5)
    ap.add_argument("--out", default=str(REPO / "data/bundles/loong_phase1.json"))
    args = ap.parse_args()

    bundles = build_bundles(n=args.n, seed=args.seed, doc_min=args.doc_min, doc_max=args.doc_max)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundles, ensure_ascii=False, indent=2), encoding="utf-8")

    from collections import Counter
    ch = Counter(b["metadata"]["challenge_type"] for b in bundles)
    nd = Counter(b["metadata"]["n_docs"] for b in bundles)
    total_chars = sum(len(d["content"]) for b in bundles for d in b["docs"])
    print(f"wrote {len(bundles)} bundles -> {out}")
    print(f"  challenge_type: {dict(ch)}")
    print(f"  n_docs dist:    {dict(sorted(nd.items()))}")
    avg_docs = sum(b["metadata"]["n_docs"] for b in bundles) / len(bundles)
    print(f"  avg docs/bundle: {avg_docs:.1f}")
    print(f"  total content chars: {total_chars:,} (~{total_chars//4:,} tokens est)")


if __name__ == "__main__":
    main()
