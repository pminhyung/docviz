#!/usr/bin/env python3
"""
exaone/sft_gen/build_dataset.py — assemble the SFT JSONL the batch
runner consumes.

Flow per row:
  1. Pick a PDF (or a small set, for multi-doc rows) from
     ``EXAONE_PARSED_ROOT/file_mapping.json``.
  2. Generate a single PA-RAG query for the *primary* PDF in a chosen
     style (S1..S5) via the auxiliary LLM (uses the active main_runtime
     so the host pool is shared with batch execution).
  3. Emit a JSONL row carrying:
        attachments  — list of {idx, file_path, filename}
        prompt       — the generated query (the [Attached documents]
                       block is added by the batch runner itself)
        qa_mode      — 'docqa'
        prewarm      — true/false (decides existing-pool vs new-upload)
        style/style_name/language — metadata for inspection / filtering

Failed query generations are skipped and counted; the run still
produces the file with however many succeeded.

Usage:
    HERMES_EXAONE_AGENT=1 HERMES_DOC_SOURCE=local \\
      EXAONE_BASE_URL=http://10.1.211.148:8000/v1 EXAONE_MODEL=Qwen3.5-397B-A17B-FP8 \\
      python -m exaone.sft_gen.build_dataset \\
        --output=data/sft_v1_input.jsonl \\
        --n-pdfs=561 --n-styles=5 \\
        --multi-doc-rows=200 --multi-doc-min=2 --multi-doc-max=5 \\
        --prewarm-fraction=0.5 \\
        --concurrency=20 --language=Korean

Output rows are ready to feed batch_runner_pool.py directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make repo root importable when invoked as a script.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import fire

from exaone.config import bootstrap_gateway_env
from exaone.sft_gen.pa_rag_query_generation import STYLES, STYLE_NAMES
from exaone.sft_gen.query_gen import GeneratedQuery, generate_one_query
from exaone.sft_gen.shim.pdf_index import get_index

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PdfRef:
    stem: str
    file_path: str
    filename: str
    parsed_json_path: Path


def _load_pdf_refs(limit: Optional[int] = None) -> List[_PdfRef]:
    """Build PDF refs from the on-disk file_mapping index.

    The display ``filename`` comes from the actual file on disk
    (``Path(file_path).name``) — not from the file_mapping JSON's
    ``original_filename`` field which carries HTML escapes and stray
    spaces from old PDF metadata. Locally we have the ground truth in
    the path; in production the user-supplied filename plays the same
    role (clean, exact).
    """
    idx = get_index()
    refs: List[_PdfRef] = []
    for stem, entry in idx._by_abs_path.items():  # internal access — same module
        refs.append(_PdfRef(
            stem=entry.stem,
            file_path=str(entry.raw_pdf_path),
            filename=entry.raw_pdf_path.name,
            parsed_json_path=entry.parsed_json_path,
        ))
    refs.sort(key=lambda r: r.filename)
    if limit is not None:
        refs = refs[:limit]
    return refs


def _row_from_query(
    *,
    primary: _PdfRef,
    extra_attachments: List[_PdfRef],
    gen: GeneratedQuery,
    prewarm: bool,
) -> Dict[str, Any]:
    attachments_refs = [primary] + list(extra_attachments)
    random.shuffle(attachments_refs)  # primary's idx is randomized 1..N
    primary_idx = next(
        i + 1 for i, ref in enumerate(attachments_refs) if ref.stem == primary.stem
    )
    attachments = [
        {"idx": i + 1, "file_path": ref.file_path, "filename": ref.filename}
        for i, ref in enumerate(attachments_refs)
    ]
    # Tag the prompt with the primary doc idx so the model knows which doc
    # the query is about (the query itself was generated on this doc's chunk).
    prompt = f"[Primary document]: [{primary_idx}]\n\n{gen.query}"
    return {
        "prompt": prompt,
        "qa_mode": "docqa",
        # Top-level `language` so batch_runner forwards it to ExaoneAgent
        # as a kwarg → pins the {language} placeholder in the system
        # prompt deterministically. Kept in `meta` too for downstream
        # loaders that key off the meta block.
        "language": gen.language,
        "attachments": attachments,
        "prewarm": prewarm,
        "meta": {
            "primary_stem": primary.stem,
            "primary_idx": primary_idx,
            "style": gen.style,
            "style_name": gen.style_name,
            "language": gen.language,
            "n_attachments": len(attachments),
        },
    }


async def _gen_one(
    *,
    primary: _PdfRef,
    style_idx: int,
    language: str,
    sem: asyncio.Semaphore,
) -> Optional[GeneratedQuery]:
    async with sem:
        try:
            return await generate_one_query(
                parsed_json_path=primary.parsed_json_path,
                file_stem=primary.stem,
                filename=primary.filename,
                style_idx=style_idx,
                language=language,
            )
        except Exception as exc:
            logger.warning("generate_one_query crashed for %s: %s", primary.filename, exc)
            return None


async def _build(
    *,
    output_path: Path,
    target_rows: int,
    n_styles: int,
    cluster_min: int,
    cluster_max: int,
    cluster_weights: List[int],
    prewarm_fraction: float,
    concurrency: int,
    language: str,
    seed: int,
) -> Dict[str, int]:
    refs = _load_pdf_refs()
    print(f"[build_dataset] {len(refs)} PDFs loaded")
    if not refs:
        return {"target": target_rows, "planned": 0, "written": 0, "failed": 0}

    rng = random.Random(seed)
    # Reset module-level random so attachment shuffles inside _row_from_query
    # are also reproducible.
    random.seed(seed)

    cluster_sizes = list(range(cluster_min, cluster_max + 1))
    if len(cluster_weights) != len(cluster_sizes):
        raise ValueError(
            f"cluster_weights length {len(cluster_weights)} != "
            f"cluster size range {cluster_sizes}"
        )

    # === Plan ``target_rows`` rows ===
    # - style: round-robin S1..S{n_styles} (perfectly balanced when
    #   target_rows is divisible by n_styles; off-by-one otherwise).
    # - cluster size: weighted random draw from cluster_min..cluster_max.
    # - primary doc + extras: random sample from the PDF pool.
    tasks = []
    for i in range(target_rows):
        style_idx = i % n_styles  # round-robin → S1..S{n_styles} balanced
        size = rng.choices(cluster_sizes, weights=cluster_weights, k=1)[0]
        size = min(size, len(refs))
        group = rng.sample(refs, size)
        primary = group[0]
        extras = group[1:]
        tasks.append((primary, style_idx, extras))

    print(
        f"[build_dataset] planned {len(tasks)} rows "
        f"(cluster sizes={cluster_sizes}, weights={cluster_weights}, "
        f"styles round-robin over {n_styles})"
    )
    print(f"[build_dataset] concurrency={concurrency}, language={language}")

    # === Generate queries concurrently ===
    sem = asyncio.Semaphore(concurrency)
    start = time.time()
    coros = [
        _gen_one(primary=p, style_idx=s, language=language, sem=sem)
        for (p, s, _extras) in tasks
    ]
    gens = await asyncio.gather(*coros)

    # === Assemble + write JSONL ===
    n_written = 0
    n_failed = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for (primary, _, extras), gen in zip(tasks, gens):
            if gen is None:
                n_failed += 1
                continue
            prewarm = rng.random() < prewarm_fraction
            row = _row_from_query(
                primary=primary, extra_attachments=extras,
                gen=gen, prewarm=prewarm,
            )
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_written += 1

    elapsed = time.time() - start
    print(
        f"[build_dataset] generated {n_written} rows "
        f"({n_failed} query gen failures) in {elapsed:.1f}s -> {output_path}"
    )
    return {
        "target": target_rows,
        "planned": len(tasks),
        "written": n_written,
        "failed": n_failed,
    }


def main(
    output: str,
    target_rows: int = 3000,
    n_styles: int = 5,
    cluster_min: int = 1,
    cluster_max: int = 3,
    cluster_weights: str = "1,1,1",
    prewarm_fraction: float = 0.5,
    concurrency: int = 20,
    language: str = "Korean",
    seed: int = 42,
):
    """
    Build SFT JSONL via PA-RAG query generation.

    Args:
        output (str): Output JSONL path.
        target_rows (int): Total rows to plan (default 3000). Style round-robin
            over n_styles makes each style appear ``target_rows // n_styles``
            times (±1).
        n_styles (int): PA-RAG style cycle length (default 5: S1..S5).
        cluster_min (int): Minimum documents per row (default 1).
        cluster_max (int): Maximum documents per row (default 3).
        cluster_weights (str): Comma-separated integer weights for each
            cluster size from cluster_min to cluster_max. Length must equal
            ``cluster_max - cluster_min + 1``. Default "1,1,1" → equal odds
            of 1/2/3-doc clusters.
        prewarm_fraction (float): Fraction of rows to mark prewarm=true.
        concurrency (int): Concurrent LLM calls (per-process semaphore).
        language (str): Query language ('Korean'|'English'|...).
        seed (int): RNG seed for reproducible cluster picks and prewarm flips.
    """
    bootstrap_gateway_env()
    logging.basicConfig(level=logging.WARNING)

    try:
        if isinstance(cluster_weights, (list, tuple)):
            weights = [int(x) for x in cluster_weights]
        else:
            weights = [
                int(x.strip())
                for x in str(cluster_weights).split(",")
                if x.strip()
            ]
    except (TypeError, ValueError):
        raise ValueError(
            f"cluster_weights must be a list of ints or comma-separated string, "
            f"got: {cluster_weights!r}"
        )

    out = Path(output)
    stats = asyncio.run(_build(
        output_path=out,
        target_rows=int(target_rows),
        n_styles=int(n_styles),
        cluster_min=int(cluster_min),
        cluster_max=int(cluster_max),
        cluster_weights=weights,
        prewarm_fraction=float(prewarm_fraction),
        concurrency=int(concurrency),
        language=str(language),
        seed=int(seed),
    ))
    print()
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    fire.Fire(main)
