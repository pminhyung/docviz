"""3-seed variance aggregation → PHASE2_REPORT — v0.4.3 §13.

Reads PHASE2_GATE_s{42,43,44}.json and reports per-arm per-metric mean±std (no
bootstrap CI / win-rate — those are deprecated for the n=265+ era). Verdict:
the headline is Evidence F1 (SAO) + the SEF ablation (user framing decision);
node/path/intent are reported but flagged gold-floored.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev

ARMS = [("B5", "B5"), ("B7", "B7"), ("B6 full", "B6"),
        ("B6 -SEF", "B6_nosef"), ("B6 -VSC", "B6_novsc")]
METRICS = ["node_f1", "path_f1", "evidence_f1", "intent_cov"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gates", nargs="+", required=True,
                    help="PHASE2_GATE_s*.json paths")
    ap.add_argument("--out", type=Path,
                    default=Path("outputs/v0.5_harness/PHASE2_REPORT.md"))
    a = ap.parse_args()

    runs = [json.loads(Path(g).read_text()) for g in a.gates if Path(g).exists()]
    n = len(runs)
    if n == 0:
        print("no gate files found"); return

    def cell(arm_key, m):
        xs = [r[arm_key][m] for r in runs if arm_key in r and m in r[arm_key]]
        if not xs:
            return "—"
        return f"{mean(xs):.3f}±{(pstdev(xs) if len(xs) > 1 else 0):.3f}"

    lines = [f"# Phase-2 Report — {n}-seed (seeds 42/43/44)", ""]
    lines.append("## Primary metrics (mean±std)")
    lines.append("")
    lines.append("| arm | node_f1 | path_f1 | **evidence_f1** | intent_cov | render |")
    lines.append("|---|---|---|---|---|---|")
    for name, key in ARMS:
        rend = [r[key].get("render_rate", 0) for r in runs if key in r]
        rcell = f"{mean(rend):.2f}" if rend else "—"
        lines.append(f"| {name} | {cell(key,'node_f1')} | {cell(key,'path_f1')} | "
                     f"**{cell(key,'evidence_f1')}** | {cell(key,'intent_cov')} | {rcell} |")
    lines.append("")

    # ablation gates (mean of per-seed booleans/deltas)
    sef = [r.get("ablation", {}).get("sef_effect_proven") for r in runs]
    vsc = [r.get("ablation", {}).get("vsc_effect_proven") for r in runs]
    sef_d = [r.get("ablation", {}).get("delta_nosef_minus_full", {}).get("evidence_f1")
             for r in runs if r.get("ablation")]
    sef_d = [x for x in sef_d if x is not None]
    gate_pass = [r.get("gate", {}).get("metrics_passing", 0) for r in runs]
    lines += [
        "## Ablation + gate",
        "",
        f"- **SEF effect** (Evidence F1 drop when −SEF): "
        f"mean Δ={mean(sef_d):.3f} over {len(sef_d)} seeds; proven in {sum(bool(x) for x in sef)}/{n}.",
        f"- **VSC effect** (violation reduction vs −VSC): proven in {sum(bool(x) for x in vsc)}/{n} "
        f"— marginal on Qwen-397B (direct DSL already clean).",
        f"- **Strict 4-metric gate**: {mean(gate_pass):.1f}/4 metrics pass +0.020 (mean). "
        f"Evidence F1 (SAO) is the discriminating metric; node/path/intent are gold-floored across all arms.",
        "",
        "## Verdict (user framing)",
        "",
        "Lead with **Evidence F1 (SAO) + SEF ablation** as the QG-MDV contribution that "
        "distinguishes it from MD-QA. node/path/intent at floor = single-pass gold limitation "
        "(consistent with Phase-1). VSC reframed as a deterministic validity *guarantee* whose "
        "violation-reduction value is backbone-dependent.",
    ]
    a.out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
