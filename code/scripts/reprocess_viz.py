#!/usr/bin/env python3
"""Re-extract viz_type / viz_dsl from raw model output for syntax-failed records.

When `_extract_dsl_block` could not parse the agent / direct-LLM output, the
mapper falls back to dumping the raw final_answer into `viz_dsl` (and labels
viz_type=mermaid_flowchart). For chartjs cases where Qwen3.5-397B-A17B-FP8 emitted the
spec as a NESTED OBJECT under "viz_dsl", that fallback meant viz_dsl is now
the FULL JSON text (string) of the model's final_answer.

We can re-extract locally — no API calls — by feeding the current viz_dsl
back through the patched `_extract_dsl_block`. Records that successfully
re-parse get their viz_type / viz_dsl / syntax_valid / syntax_check_kind /
errors updated in place.

Usage:
    python -m code.scripts.reprocess_viz \
        --in outputs/prototype/viz/all.json \
        --out outputs/prototype/viz/all.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from code.adapters.viz_output_mapper import _extract_dsl_block

# Mirror run_prototype._check_syntax so the gate uses the same definitions.
_MERMAID_HEADER_RE = re.compile(
    r"^\s*(graph|flowchart|sequenceDiagram|stateDiagram(?:-v2)?|"
    r"classDiagram|erDiagram|gantt|mindmap|timeline|journey|pie|gitGraph)\b",
    re.MULTILINE,
)
_VALID_CHARTJS_TYPES = {
    "bar", "line", "scatter", "bubble", "pie", "doughnut", "polarArea", "radar",
}


def _check_syntax(viz_type: str, viz_dsl: str):
    if not viz_dsl:
        return False, "empty"
    if viz_type.startswith("mermaid"):
        m = _MERMAID_HEADER_RE.search(viz_dsl)
        return bool(m), f"mermaid_header:{m.group(1)}" if m else "mermaid_header:miss"
    if viz_type.startswith("chartjs"):
        try:
            spec = json.loads(viz_dsl)
        except json.JSONDecodeError:
            return False, "chartjs_json:parse_fail"
        if not isinstance(spec, dict) or "data" not in spec:
            return False, "chartjs_json:no_data"
        t = spec.get("type")
        if t not in _VALID_CHARTJS_TYPES:
            return False, f"chartjs_json:unknown_type({t!r})"
        return True, f"chartjs_json:{t}"
    return False, f"unknown_viz_type:{viz_type}"


def _reprocess_one(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Try to re-extract from the (raw) viz_dsl currently stored on rec."""
    raw_text = rec.get("viz_dsl") or ""
    new_type, new_dsl = _extract_dsl_block(raw_text)
    if not new_type:
        return rec   # nothing to fix; keep original
    ok, kind = _check_syntax(new_type, new_dsl)
    if not ok:
        return rec   # re-parse didn't recover a valid DSL either
    rec = dict(rec)
    rec["viz_type"] = new_type
    rec["viz_dsl"] = new_dsl
    rec["syntax_valid"] = True
    rec["syntax_check_kind"] = kind
    rec["reprocessed"] = True
    # Drop the old "fallback" error if still there.
    rec["errors"] = [
        e for e in rec.get("errors", [])
        if "viz_type/viz_dsl JSON not found" not in e
        and "agent returned empty final_answer" not in e
    ]
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    args = ap.parse_args()

    in_path = Path(args.inp)
    records: List[Dict[str, Any]] = json.loads(in_path.read_text(encoding="utf-8"))
    print(f"[reprocess] loaded {len(records)} records from {in_path}")

    fixed: List[Dict[str, Any]] = []
    n_fail_before = 0
    n_fixed = 0
    for r in records:
        if r.get("syntax_valid"):
            fixed.append(r)
            continue
        n_fail_before += 1
        new = _reprocess_one(r)
        fixed.append(new)
        if new.get("reprocessed"):
            n_fixed += 1
            print(f"  fixed {r['query_id']:<28s} {r['strategy']:<11s}"
                  f" → viz_type={new['viz_type']}  kind={new['syntax_check_kind']}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(fixed, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    n_fail_after = sum(1 for r in fixed if not r["syntax_valid"])
    print(f"[reprocess] failures before: {n_fail_before} / {len(records)}")
    print(f"[reprocess] fixed: {n_fixed}")
    print(f"[reprocess] failures after:  {n_fail_after} / {len(records)}")
    print(f"[reprocess] wrote → {out_path}")

    # Final §5.3 syntax-pass + error-rate check
    from collections import Counter
    by_strategy: Dict[str, Counter] = {}
    for r in fixed:
        s = by_strategy.setdefault(r["strategy"], Counter())
        s["n"] += 1
        if r["errors"]:
            s["errors"] += 1
        if r["syntax_valid"]:
            s["syntax_ok"] += 1
    summary = {}
    for label, c in by_strategy.items():
        n = max(c["n"], 1)
        summary[label] = {
            "n": c["n"],
            "errors": c["errors"],
            "syntax_ok": c["syntax_ok"],
            "error_rate": round(c["errors"] / n, 3),
            "syntax_pass_rate": round(c["syntax_ok"] / n, 3),
        }
    print(f"[reprocess] §5.3 summary: {json.dumps(summary, ensure_ascii=False, indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
