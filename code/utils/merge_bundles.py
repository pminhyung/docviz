"""Merge per-source bundle JSONs into a single all.json.

Usage:
    python -m code.utils.merge_bundles
    python -m code.utils.merge_bundles --strict       # fail if total != 30

Validates each bundle against the schema (≥2 docs, 3K-80K chars).
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

EXPECTED = {
    "hotpotqa": 10,
    "multinews": 10,
    "arxiv": 5,
    "10k": 5,
}
TARGET_TOTAL = sum(EXPECTED.values())

# Per-source char floor. HotpotQA supporting paragraphs are inherently short
# (see WEEK0_LOG.md decision note). Master spec's 3K-80K range applies to the
# larger sources.
PER_SOURCE_MIN_CHARS = {
    "hotpotqa": 500,
    "multinews": 3_000,
    "arxiv": 3_000,
    "10k": 3_000,
}


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

    # Validate (per-source min_chars)
    errors: List[str] = []
    for b in all_bundles:
        floor = PER_SOURCE_MIN_CHARS.get(b.source, 3_000)
        errors.extend(validate_bundle(b, min_chars=floor, max_chars=80_000))
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
