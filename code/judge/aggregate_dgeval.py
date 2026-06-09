"""Aggregate real-DiagramEval node/path across 5 arms × 3 seeds → report."""
from __future__ import annotations
import json
import statistics as st
from pathlib import Path

R = Path("outputs/v0.5_harness")
ARMS = [("B6 full", "full"), ("B6 -SEF", "nosef"), ("B6 -VSC", "novsc"),
        ("B5", "b5"), ("B7", "b7")]
SEEDS = [42, 43, 44]


def _arm_seed(arm, seed):
    f = R / f"dgeval_{arm}_s{seed}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text())
    ok = [r for r in d.values() if r["ok"]]
    return {
        "n": len(d), "n_ok": len(ok),
        "node_ok": st.mean([r["node_f1"] for r in ok]) if ok else 0,
        "path_ok": st.mean([r["path_f1"] for r in ok]) if ok else 0,
        "node_all": st.mean([r["node_f1"] for r in d.values()]) if d else 0,
        "path_all": st.mean([r["path_f1"] for r in d.values()]) if d else 0,
    }


def main():
    lines = ["# Phase-2 real DiagramEval (Qwen-VL) — node/path, 3-seed mean±std", ""]
    lines.append("| arm | node_f1 (ok) | path_f1 (ok) | node_f1 (all) | path_f1 (all) | n_ok/n |")
    lines.append("|---|---|---|---|---|---|")
    table = {}
    for name, arm in ARMS:
        rows = [_arm_seed(arm, s) for s in SEEDS]
        rows = [r for r in rows if r]
        if not rows:
            lines.append(f"| {name} | — | — | — | — | — |"); continue
        def cell(k):
            xs = [r[k] for r in rows]
            return f"{st.mean(xs):.3f}±{(st.pstdev(xs) if len(xs)>1 else 0):.3f}"
        nok = sum(r["n_ok"] for r in rows); ntot = sum(r["n"] for r in rows)
        table[name] = {k: st.mean([r[k] for r in rows]) for k in ("node_ok","path_ok","node_all","path_all")}
        lines.append(f"| {name} | {cell('node_ok')} | {cell('path_ok')} | "
                     f"{cell('node_all')} | {cell('path_all')} | {nok}/{ntot} |")
    lines.append("")
    if "B6 full" in table:
        b6 = table["B6 full"]
        strong = max((table[n] for n in ("B5","B7") if n in table),
                     key=lambda t: t["node_ok"], default=None)
        if strong:
            lines.append(f"- B6 full vs strongest baseline: node Δ={b6['node_ok']-strong['node_ok']:+.3f}, "
                         f"path Δ={b6['path_ok']-strong['path_ok']:+.3f} (ok-only)")
    out = R / "PHASE2_DGEVAL_REPORT.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
