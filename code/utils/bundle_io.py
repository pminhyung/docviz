"""Bundle ↔ JSON IO helpers.

Centralized so every loader emits the same shape and downstream tools can
ingest any source loader's output without per-source branching.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from code.pipelines.base import Bundle, Doc


def bundle_to_dict(b: Bundle) -> Dict[str, Any]:
    return asdict(b)


def bundle_from_dict(d: Dict[str, Any]) -> Bundle:
    docs = [Doc(**doc) for doc in d.get("docs", [])]
    return Bundle(
        bundle_id=d["bundle_id"],
        source=d["source"],
        docs=docs,
        metadata=d.get("metadata", {}),
    )


def write_bundles_json(bundles: List[Bundle], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([bundle_to_dict(b) for b in bundles], f, ensure_ascii=False, indent=2)


def read_bundles_json(path: str | Path) -> List[Bundle]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [bundle_from_dict(d) for d in data]


def validate_bundle(b: Bundle, *, min_docs: int = 2,
                    min_chars: int = 3_000, max_chars: int = 80_000) -> List[str]:
    """Return a list of validation errors. Empty list = OK."""
    errs: List[str] = []
    if len(b.docs) < min_docs:
        errs.append(f"{b.bundle_id}: docs={len(b.docs)} < {min_docs}")
    total = b.total_chars()
    if total < min_chars:
        errs.append(f"{b.bundle_id}: total_chars={total} < {min_chars}")
    if total > max_chars:
        errs.append(f"{b.bundle_id}: total_chars={total} > {max_chars}")
    for d in b.docs:
        if not d.doc_id or not d.content:
            errs.append(f"{b.bundle_id}: empty doc_id or content in a Doc")
    return errs
