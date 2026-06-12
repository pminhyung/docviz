"""Aggregate B1-B7+B6 across seeds (42/43/44) per source → per-seed rows + mean±std.
Reads outputs/v0.5_harness/dgeval_{arm}_{src}_s{seed}.json (node/path ok-only).
Records EACH seed individually AND the mean±std (paper 3-seed protocol)."""
import json, statistics as st, sys
from pathlib import Path
R=Path("outputs/v0.5_harness")
ARMS=[("B1","b1"),("B2","b2"),("B3","b3"),("B4","b4"),("B5","b5"),("B7","b7"),("B6","full")]
SEEDS=[42,43,44]

def cell(arm_key, src, seed):
    # try several naming conventions used during the build-out
    for f in (R/f"dgeval_{arm_key}_{src}_s{seed}.json", R/f"dgeval_{arm_key}_{src}.json" if seed==42 else None,
              R/f"dgeval_{arm_key}_s{seed}.json"):
        if f and f.exists():
            d=json.loads(f.read_text()); ok=[r for r in d.values() if r["ok"]]
            if ok: return (st.mean([r["node_f1"] for r in ok]), st.mean([r["path_f1"] for r in ok]), len(ok), len(d))
    return None

def report(src):
    lines=[f"# {src} — B1-B7 vs B6 (3-seed, node/path ok-only)",""]
    lines.append("| arm | node mean±std | path mean±std | per-seed node | n |")
    lines.append("|---|---|---|---|---|")
    for name,key in ARMS:
        per=[cell(key,src,s) for s in SEEDS]; per=[p for p in per if p]
        if not per: lines.append(f"| {name} | — | — | — | — |"); continue
        nm=[p[0] for p in per]; pm=[p[1] for p in per]
        ns=f"{st.mean(nm):.3f}±{st.pstdev(nm) if len(nm)>1 else 0:.3f}"
        ps=f"{st.mean(pm):.3f}±{st.pstdev(pm) if len(pm)>1 else 0:.3f}"
        perstr=" / ".join(f"{x:.3f}" for x in nm)
        lines.append(f"| {name} | {ns} | {ps} | {perstr} | {sum(p[2] for p in per)} |")
    return "\n".join(lines)

if __name__=="__main__":
    srcs=sys.argv[1:] or ["loong"]
    out=[]
    for s in srcs: out.append(report(s))
    txt="\n\n".join(out)
    (R/"BASELINE_3SEED_REPORT.md").write_text(txt)
    print(txt)
