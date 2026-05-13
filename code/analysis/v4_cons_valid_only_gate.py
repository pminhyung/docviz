"""Supplementary gate analysis — V4_cons valid-only vs full headline.

Phase 9's standard gate decision in /tmp/phase9_analysis.sh computes
mean(B6) over ALL records including Mode A infrastructure-failure rows
(see docs/analysis/v4_cons_fail_root_cause.md). The full-set gate is
HALT (Δ -0.145 vs S1_Direct). This script computes the parallel
valid-only gate (excluding records with empty viz_dsl) so paper §16
reviewer-defense framing can report both cells.

Output: docs/analysis/v4_cons_dual_gate.md

Run: python -m code.analysis.v4_cons_valid_only_gate
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    scores_path = REPO / "outputs/prototype/judge_scores/all.json"
    viz_path = REPO / "outputs/prototype/viz/raw.jsonl"
    out_path = REPO / "docs/analysis/v4_cons_dual_gate.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Index viz records to identify fail (empty viz_dsl) records per strategy
    fail_qids_by_strategy: dict[str, set[str]] = defaultdict(set)
    with open(viz_path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            qid = r.get("query_id")
            strat = r.get("strategy")
            if not qid or not strat:
                continue
            if len(r.get("viz_dsl") or "") < 20:
                fail_qids_by_strategy[strat].add(qid)

    # Aggregate judge scores per strategy: full vs valid-only
    scores = json.load(open(scores_path))
    by_s_full: dict[str, list[float]] = defaultdict(list)
    by_s_valid: dict[str, list[float]] = defaultdict(list)
    for r in scores:
        strat = r.get("strategy")
        qid = r.get("query_id")
        overall = r.get("overall")
        if not strat or overall is None:
            continue
        by_s_full[strat].append(overall)
        if qid not in fail_qids_by_strategy.get(strat, set()):
            by_s_valid[strat].append(overall)

    baselines = [
        "S1_Direct",
        "S7_SelfRefine",
        "B1_MatPlotAgent",
        "B2_NVAGENT",
        "B3_CoDA",
        "B4_ViviDoc",
    ]
    b6 = "S4_AgenticTMGv4_consolidated"

    lines: list[str] = []
    lines.append("# V4_cons Dual-Cell Gate Analysis (full vs valid-only)\n")
    lines.append("Per `docs/analysis/v4_cons_fail_root_cause.md` Mode A (26 records of")
    lines.append("agent-server silent error masking) inflates V4_cons fail rate to 15.1%.")
    lines.append("This report computes both the unfiltered headline (full) and the")
    lines.append("infrastructure-corrected reference (valid-only).\n")

    lines.append("## Per-strategy mean overall\n")
    lines.append("| Strategy | Full mean (n) | Valid-only mean (n) | Drag from fails |")
    lines.append("|---|---|---|---|")
    all_strategies = sorted(set(by_s_full) | set(by_s_valid))
    for s in all_strategies:
        vf = by_s_full.get(s, [])
        vv = by_s_valid.get(s, [])
        mf = mean(vf) if vf else float("nan")
        mv = mean(vv) if vv else float("nan")
        drag = mv - mf if vf and vv else 0.0
        lines.append(
            f"| {s} | {mf:.4f} ({len(vf)}) | {mv:.4f} ({len(vv)}) | "
            f"{drag:+.4f} |"
        )

    # Gate decision: per amendment §16
    best_b_full = -1.0
    best_b_valid = -1.0
    best_b_full_name = ""
    best_b_valid_name = ""
    for b in baselines:
        if b in by_s_full:
            m = mean(by_s_full[b])
            if m > best_b_full:
                best_b_full = m
                best_b_full_name = b
        if b in by_s_valid:
            m = mean(by_s_valid[b])
            if m > best_b_valid:
                best_b_valid = m
                best_b_valid_name = b

    b6_full = mean(by_s_full[b6]) if b6 in by_s_full else float("nan")
    b6_valid = mean(by_s_valid[b6]) if b6 in by_s_valid else float("nan")

    def _gate(delta: float) -> str:
        if delta >= 0.05:
            return "GO Phase-2 closed-API re-judge"
        if delta >= 0.02:
            return "BORDERLINE — 20-record Phase-2 disambiguation"
        return "HALT — method iteration needed"

    lines.append("\n## Gate decisions per amendment §16\n")
    lines.append("| View | Best baseline | B6 mean | Δ(B6 − best) | Decision |")
    lines.append("|---|---|---|---|---|")
    delta_full = b6_full - best_b_full
    delta_valid = b6_valid - best_b_valid
    lines.append(
        f"| Full (unfiltered) | {best_b_full_name} = {best_b_full:.4f} | "
        f"{b6_full:.4f} | {delta_full:+.4f} | {_gate(delta_full)} |"
    )
    lines.append(
        f"| Valid-only (Mode A corrected) | {best_b_valid_name} = {best_b_valid:.4f} | "
        f"{b6_valid:.4f} | {delta_valid:+.4f} | {_gate(delta_valid)} |"
    )

    lines.append("\n## Mode A breakdown for B6\n")
    fail_qids = fail_qids_by_strategy.get(b6, set())
    lines.append(f"- B6 fail records (empty `viz_dsl`): **{len(fail_qids)}** of {len(by_s_full.get(b6, []))}")
    lines.append(f"- Fail rate: **{100 * len(fail_qids) / max(1, len(by_s_full.get(b6, []))):.1f}%**")
    fail_means = [s for r in scores
                  if r.get("strategy") == b6
                  and r.get("query_id") in fail_qids
                  and (s := r.get("overall")) is not None]
    if fail_means:
        lines.append(f"- Mean judge score on fail records: {mean(fail_means):.4f}")
        lines.append(f"  (judge scored them low but non-zero → drag effect on full mean)")

    out_path.write_text("\n".join(lines) + "\n")
    print(f"[v4-cons-valid-only-gate] wrote → {out_path}")
    print()
    print(f"FULL  : B6={b6_full:.4f} vs best({best_b_full_name})={best_b_full:.4f} Δ={delta_full:+.4f} → {_gate(delta_full)}")
    print(f"VALID : B6={b6_valid:.4f} vs best({best_b_valid_name})={best_b_valid:.4f} Δ={delta_valid:+.4f} → {_gate(delta_valid)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
