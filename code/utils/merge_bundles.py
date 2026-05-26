"""Merge per-source bundle JSONs into a single all.json.

Usage:
    python -m code.utils.merge_bundles
    python -m code.utils.merge_bundles --strict       # fail if total != 300

v0.3 amendment D1.1: 6 sources × 50 bundles each = 300 total. Validates
each bundle against the schema (≥2 docs, per-source min_chars).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from code.pipelines.base import Bundle
from code.utils.bundle_io import (
    read_bundles_json,
    validate_bundle,
    write_bundles_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = REPO_ROOT / "data" / "prototype" / "bundles"
OUT_PATH = BUNDLE_DIR / "all.json"

# v0.3 amendment D1.1 — 6 sources × 50 bundles = 300 total
EXPECTED = {
    "hotpotqa":  50,
    "multinews": 50,
    "arxiv":     50,
    "10k":       50,
    "govreport": 50,
    "tech_docs": 50,
}
TARGET_TOTAL = sum(EXPECTED.values())

# v0.4 LOADER_CONTRACT_v04.md — all 6 sources now uniform 15K-200K chars,
# 3-5 docs/bundle. HotpotQA carve-out (500 chars) deprecated 2026-05-24.
PER_SOURCE_MIN_CHARS = {
    "hotpotqa":  15_000,
    "multinews": 15_000,
    "arxiv":     15_000,
    "10k":       15_000,
    "govreport": 15_000,
    "tech_docs": 15_000,
}
PER_SOURCE_MAX_CHARS = 200_000
PER_SOURCE_MIN_DOCS = 3


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge per-source bundle JSONs.")
    ap.add_argument("--strict", action="store_true",
                    help="Fail if total bundles != 30 or per-source counts mismatch.")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    all_bundles: List[Bundle] = []
    counts: Dict[str, int] = {}

    for src in EXPECTED:
        path = BUNDLE_DIR / f"{src}.json"
        if not path.exists():
            print(f"  [missing] {path}")
            counts[src] = 0
            continue
        bundles = read_bundles_json(path)
        all_bundles.extend(bundles)
        counts[src] = len(bundles)

    print(f"[merge] per-source counts: {counts}")
    print(f"[merge] total: {len(all_bundles)}")

    # Validate (per-source min_chars + min_docs, v0.4 contract)
    errors: List[str] = []
    for b in all_bundles:
        floor = PER_SOURCE_MIN_CHARS.get(b.source, 15_000)
        errors.extend(validate_bundle(b, min_docs=PER_SOURCE_MIN_DOCS,
                                      min_chars=floor, max_chars=PER_SOURCE_MAX_CHARS))
    if errors:
        print("  [VALIDATION ERRORS]")
        for e in errors:
            print(f"    {e}")

    write_bundles_json(all_bundles, args.out)
    print(f"[merge] wrote → {args.out}")

    if args.strict:
        if len(all_bundles) != TARGET_TOTAL:
            print(f"  [strict] FAIL — total {len(all_bundles)} != {TARGET_TOTAL}")
            return 2
        for src, expected in EXPECTED.items():
            if counts.get(src, 0) != expected:
                print(f"  [strict] FAIL — {src} count {counts.get(src, 0)} != {expected}")
                return 2
    return 0 if all_bundles else 2


if __name__ == "__main__":
    sys.exit(main())
