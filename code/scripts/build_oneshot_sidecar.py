#!/usr/bin/env python3
"""Build code/agent_tools/oneshot_pool.json from per-type markdown drafts.

Reads each `docs/analysis/tmg_oneshot/<viz_type>.md` file (excluding
INDEX.md), extracts the ``` python ``` code blocks containing
`ONE_SHOT_POOL_BY_VIZ_TYPE["<vt>"] = [...]` and
`ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE["<vt>"] = "..."`, exec()s them into
a namespace, and writes the combined dicts to
`code/agent_tools/oneshot_pool.json` in the schema:

  {"pool":         {<viz_type>: [<exemplar_str>, ...]},
   "consolidated": {<viz_type>: <exemplar_str>}}

This sidecar is loaded at runtime by `code/agent_tools/generate_viz.py`.

Usage:
  python -m code.scripts.build_oneshot_sidecar [--strict] [--out PATH]

`--strict` checks that the sidecar covers every viz_type in
`code.agent_tools.generate_viz.VIZ_TYPE_POOL` (10 types). Without
--strict, partial coverage (e.g., 6 types only, before the 4 new types
land) is allowed and emits a warning.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DRAFT_DIR = REPO_ROOT / "docs" / "analysis" / "tmg_oneshot"
DEFAULT_OUT = REPO_ROOT / "code" / "agent_tools" / "oneshot_pool.json"
INDEX_NAME = "INDEX.md"


_CODE_BLOCK_RE = re.compile(
    r"```python\s*\n(.*?)\n```",
    re.DOTALL,
)
_INTERESTING_RE = re.compile(
    r"\bONE_SHOT_(POOL|CONSOLIDATED)_BY_VIZ_TYPE\b"
)


def _extract_pool_literals(md_path: Path) -> List[str]:
    """Return python code chunks from md_path that mention the dicts."""
    text = md_path.read_text(encoding="utf-8")
    out: List[str] = []
    for block in _CODE_BLOCK_RE.findall(text):
        if _INTERESTING_RE.search(block):
            out.append(block)
    return out


def build(draft_dir: Path) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    namespace: Dict[str, Any] = {
        "ONE_SHOT_POOL_BY_VIZ_TYPE": {},
        "ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE": {},
    }

    files = sorted(p for p in draft_dir.glob("*.md") if p.name != INDEX_NAME)
    if not files:
        print(f"[build_sidecar] no per-type files in {draft_dir}", file=sys.stderr)
        return {}, {}

    for md_path in files:
        chunks = _extract_pool_literals(md_path)
        if not chunks:
            print(f"[build_sidecar] {md_path.name}: no pool literal found, skipping",
                  file=sys.stderr)
            continue
        for chunk in chunks:
            try:
                exec(chunk, namespace)
            except Exception as e:
                print(f"[build_sidecar] {md_path.name}: exec failed: {e}",
                      file=sys.stderr)
                raise
        print(f"[build_sidecar] {md_path.name}: ok ({len(chunks)} block(s))")

    return (
        namespace["ONE_SHOT_POOL_BY_VIZ_TYPE"],
        namespace["ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE"],
    )


def validate(pool: Dict[str, List[str]], consolidated: Dict[str, str]) -> int:
    """Best-effort schema validation. Returns count of issues found."""
    issues = 0
    for vt, items in pool.items():
        if not items:
            print(f"[validate] pool[{vt}] is empty", file=sys.stderr)
            issues += 1
            continue
        for i, s in enumerate(items):
            try:
                obj = json.loads(s)
            except json.JSONDecodeError as e:
                print(f"[validate] pool[{vt}][{i}] not valid JSON: {e}",
                      file=sys.stderr)
                issues += 1
                continue
            if obj.get("viz_type") != vt:
                print(f"[validate] pool[{vt}][{i}] viz_type mismatch: "
                      f"expected={vt}, got={obj.get('viz_type')!r}",
                      file=sys.stderr)
                issues += 1
    for vt, s in consolidated.items():
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            print(f"[validate] consolidated[{vt}] not valid JSON: {e}",
                  file=sys.stderr)
            issues += 1
            continue
        if obj.get("viz_type") != vt:
            print(f"[validate] consolidated[{vt}] viz_type mismatch: "
                  f"expected={vt}, got={obj.get('viz_type')!r}",
                  file=sys.stderr)
            issues += 1
    return issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft-dir", type=Path, default=DEFAULT_DRAFT_DIR)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--strict", action="store_true",
                    help="Require coverage of every viz_type in VIZ_TYPE_POOL.")
    args = ap.parse_args()

    pool, consolidated = build(args.draft_dir)

    issues = validate(pool, consolidated)

    # Coverage check
    sys.path.insert(0, str(REPO_ROOT))
    from code.agent_tools.generate_viz import VIZ_TYPE_POOL  # noqa: E402

    pool_missing = [vt for vt in VIZ_TYPE_POOL if vt not in pool]
    cons_missing = [vt for vt in VIZ_TYPE_POOL if vt not in consolidated]

    print(f"[build_sidecar] pool coverage:         "
          f"{len(pool)}/{len(VIZ_TYPE_POOL)} types "
          f"(missing: {pool_missing or 'none'})")
    print(f"[build_sidecar] consolidated coverage: "
          f"{len(consolidated)}/{len(VIZ_TYPE_POOL)} types "
          f"(missing: {cons_missing or 'none'})")

    if args.strict and (pool_missing or cons_missing or issues):
        print("[build_sidecar] --strict failure", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sidecar = {"pool": pool, "consolidated": consolidated}
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(sidecar, f, ensure_ascii=False, indent=2)
    print(f"[build_sidecar] wrote {args.out} "
          f"({sum(len(v) for v in pool.values())} pool entries, "
          f"{len(consolidated)} consolidated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
