#!/usr/bin/env python3
"""P0 parser preflight (v0.4.1 §7.3).

Runs the v0.4.1 chartjs + mermaid parsers on a stratified 30-record sample of
existing Qwen3.5-397B B6 prototype outputs and reports per-parser success
rate. Gate (per IMPLEMENTATION_GUIDE_v0.4.1.md §14):

    chartjs_success >= 0.85  AND  mermaid_success >= 0.85

A "success" = the parser returns a structurally-populated normalized object
(not None, and basic shape sanity holds).

Usage:
    python scripts/parser_pilot.py \\
        --input _legacy_v0.4_pre_harness/outputs/v0.4_final/judge/b6_nocis_seed42.json \\
        --n 30 \\
        --out outputs/v0.5_harness/p0_parser_pilot.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from code.metrics.chart_metrics import parse_chartjs_to_table
from code.metrics.mermaid_metrics import parse_mermaid_to_graph


def stratified_sample(
    records: list[dict], n: int, seed: int = 42
) -> list[dict]:
    """Sample n records stratified by viz_type family (chartjs vs mermaid)."""
    rng = random.Random(seed)
    by_family: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        vt = r.get("viz_type", "")
        if not vt or not r.get("viz_dsl"):
            continue
        fam = "chartjs" if vt.startswith("chartjs") else (
            "mermaid" if vt.startswith("mermaid") else "other"
        )
        by_family[fam].append(r)

    # Target ratio: 50/50 chartjs vs mermaid for parser comparison fairness;
    # fall back to whatever's available.
    half = n // 2
    out: list[dict] = []
    for fam in ("chartjs", "mermaid"):
        pool = by_family.get(fam, [])
        rng.shuffle(pool)
        out.extend(pool[:half])
    rng.shuffle(out)
    return out[:n]


def _chartjs_success(dsl: str) -> tuple[bool, str]:
    """A chartjs parse succeeds when we recover at least the chart_type and
    one cell (a real row × col × value). Empty cells = uninformative parse."""
    tbl = parse_chartjs_to_table(dsl)
    if tbl is None:
        return False, "parse_returned_none"
    if not tbl.chart_type:
        return False, "missing_chart_type"
    if not tbl.cells:
        return False, "zero_cells"
    return True, ""


def _mermaid_success(dsl: str) -> tuple[bool, str]:
    """A mermaid parse succeeds when we recover a known header AND at least
    one structural piece — either a node OR an extra_line (for timeline/
    mindmap where node-level extraction is intentionally absent)."""
    g = parse_mermaid_to_graph(dsl)
    if g is None:
        return False, "parse_returned_none"
    if g.kind == "mermaid_unknown":
        return False, "unknown_header"
    if not g.nodes and not g.extra_lines:
        return False, "no_structural_content"
    return True, ""


def run(input_path: Path, n: int, out_path: Path | None) -> dict:
    records = json.loads(input_path.read_text(encoding="utf-8"))
    sample = stratified_sample(records, n)

    results: list[dict] = []
    type_counts = Counter(r.get("viz_type", "?") for r in sample)
    per_family_total = {"chartjs": 0, "mermaid": 0}
    per_family_pass = {"chartjs": 0, "mermaid": 0}
    failure_buckets: dict[str, Counter] = {
        "chartjs": Counter(), "mermaid": Counter()
    }

    for r in sample:
        vt = r.get("viz_type", "")
        dsl = r.get("viz_dsl", "")
        fam = "chartjs" if vt.startswith("chartjs") else "mermaid"
        per_family_total[fam] += 1
        if fam == "chartjs":
            ok, why = _chartjs_success(dsl)
        else:
            ok, why = _mermaid_success(dsl)
        if ok:
            per_family_pass[fam] += 1
        else:
            failure_buckets[fam][why] += 1
        results.append({
            "query_id": r.get("query_id"),
            "viz_type": vt,
            "family": fam,
            "success": ok,
            "fail_reason": why,
        })

    def _rate(p: int, t: int) -> float:
        return p / t if t else 0.0

    chartjs_rate = _rate(per_family_pass["chartjs"], per_family_total["chartjs"])
    mermaid_rate = _rate(per_family_pass["mermaid"], per_family_total["mermaid"])
    gate_pass = chartjs_rate >= 0.85 and mermaid_rate >= 0.85

    summary = {
        "n_total": len(sample),
        "type_distribution": dict(type_counts),
        "per_family": {
            "chartjs": {
                "n": per_family_total["chartjs"],
                "pass": per_family_pass["chartjs"],
                "rate": round(chartjs_rate, 4),
                "failures": dict(failure_buckets["chartjs"]),
            },
            "mermaid": {
                "n": per_family_total["mermaid"],
                "pass": per_family_pass["mermaid"],
                "rate": round(mermaid_rate, 4),
                "failures": dict(failure_buckets["mermaid"]),
            },
        },
        "gate": {
            "threshold": 0.85,
            "chartjs_pass": chartjs_rate >= 0.85,
            "mermaid_pass": mermaid_rate >= 0.85,
            "overall_pass": gate_pass,
        },
    }

    print("=" * 60)
    print(f"P0 parser pilot: {len(sample)} records")
    print("=" * 60)
    print(f"chartjs  {per_family_pass['chartjs']:>3d} / {per_family_total['chartjs']:<3d}  "
          f"({chartjs_rate*100:5.1f}%)  "
          f"{'PASS' if chartjs_rate >= 0.85 else 'FAIL'}")
    print(f"mermaid  {per_family_pass['mermaid']:>3d} / {per_family_total['mermaid']:<3d}  "
          f"({mermaid_rate*100:5.1f}%)  "
          f"{'PASS' if mermaid_rate >= 0.85 else 'FAIL'}")
    print(f"GATE     {'PASS' if gate_pass else 'FAIL'}  (both >= 0.85)")
    print()
    if failure_buckets["chartjs"]:
        print(f"chartjs failure buckets: {dict(failure_buckets['chartjs'])}")
    if failure_buckets["mermaid"]:
        print(f"mermaid failure buckets: {dict(failure_buckets['mermaid'])}")

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps({"summary": summary, "records": results},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nWrote: {out_path}")

    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input",
        default="_legacy_v0.4_pre_harness/outputs/v0.4_final/judge/b6_nocis_seed42.json",
        type=Path,
    )
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument(
        "--out",
        default="outputs/v0.5_harness/p0_parser_pilot.json",
        type=Path,
    )
    args = ap.parse_args()
    summary = run(args.input, args.n, args.out)
    sys.exit(0 if summary["gate"]["overall_pass"] else 1)
