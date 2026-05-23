#!/usr/bin/env bash
# After scope re-judge completes, merge new B6+B7 scores into production
# and measure new B6 - B7 gap.
set -euo pipefail
cd /ex_disk2/mhpark/poc/docviz

STAMP=$(date +%Y%m%d_%H%M%S)
JUDGE_PROD=outputs/prototype/judge_scores/all.json

# Backup current
cp "$JUDGE_PROD" "${JUDGE_PROD}.bak_pre_scope_merge_${STAMP}"
echo "[backup] ${JUDGE_PROD}.bak_pre_scope_merge_${STAMP}"

# Merge B6 + B7 scope-rule scores into production
python3 - <<'PY'
import json
from pathlib import Path
JS = Path('outputs/prototype/judge_scores/all.json')
old = json.loads(JS.read_text())
new = json.load(open('/tmp/scope/judge.json'))
lookup = {(r['query_id'], r['strategy']): r for r in new}

out=[]; replaced=0
for r in old:
    k = (r['query_id'], r['strategy'])
    if k in lookup:
        out.append(lookup[k]); replaced += 1
    else:
        out.append(r)
print(f'[merge] replaced {replaced} (B6+B7) score records')
out.sort(key=lambda r: (r['bundle_id'], r['query_type'], r['strategy']))
JS.write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(f'[merge] → {JS}')
PY

# Measure
python3 - <<'PY'
import json
from collections import defaultdict
data = json.load(open('outputs/prototype/judge_scores/all.json'))
qids = sorted({r['query_id'] for r in data})
idx = {(r['query_id'], r['strategy']): r for r in data}
n=len(qids)
B6='S4_AgenticTMGv4_consolidated'; B7='S7_SelfRefine'

print(f'\n========= POST SCOPE RE-JUDGE =========')
print(f'N = {n}\n')
print('Per-baseline mean overall:')
all_strats = ['B1_MatPlotAgent','B2_NVAGENT','B3_CoDA','B4_ViviDoc','S1_Direct',B6,B7]
m_b6 = sum(idx[(q,B6)]['overall'] for q in qids)/n
for s in all_strats:
    m = sum(idx[(q,s)]['overall'] for q in qids)/n
    gap = m_b6 - m
    flag = '★ B6' if s == B6 else ('TIED' if abs(gap)<0.020 else ('PASS' if gap>0 else 'NEG'))
    print(f'  {s:<36} mean={m:.4f}  B6-X={gap:+.4f}  {flag}')

# Paired intersection
both = [q for q in qids if idx[(q,B6)].get('syntax_valid') and idx[(q,B7)].get('syntax_valid')]
mb6_pi = sum(idx[(q,B6)]['overall'] for q in both)/len(both)
mb7_pi = sum(idx[(q,B7)]['overall'] for q in both)/len(both)
print(f'\nPaired intersection (n={len(both)}): B6={mb6_pi:.4f}  B7={mb7_pi:.4f}  Δ={mb6_pi-mb7_pi:+.4f}')

print(f'\nPer-axis (population):')
for ax in ['faithfulness','coverage','type_appropriateness','cross_document_integration']:
    a6 = sum(idx[(q,B6)]['axis_scores'].get(ax,0) or 0 for q in qids)/n
    a7 = sum(idx[(q,B7)]['axis_scores'].get(ax,0) or 0 for q in qids)/n
    print(f'  {ax}: B6={a6:.4f}  B7={a7:.4f}  Δ={a6-a7:+.4f}')

# Compare with pre-scope (from backup)
import glob
bak = sorted(glob.glob('outputs/prototype/judge_scores/all.json.bak_pre_scope_merge_*'))
if bak:
    old_data = json.load(open(bak[-1]))
    old_idx = {(r['query_id'], r['strategy']): r for r in old_data}
    mb6_old = sum(old_idx[(q,B6)]['overall'] for q in qids)/n
    mb7_old = sum(old_idx[(q,B7)]['overall'] for q in qids)/n
    print(f'\nBefore scope rule: B6={mb6_old:.4f}  B7={mb7_old:.4f}  gap={mb6_old-mb7_old:+.4f}')
    print(f'After  scope rule: B6={m_b6:.4f}  B7={sum(idx[(q,B7)]["overall"] for q in qids)/n:.4f}  gap={m_b6 - sum(idx[(q,B7)]["overall"] for q in qids)/n:+.4f}')
    print(f'  Δ_B6 = {m_b6-mb6_old:+.4f}')
    print(f'  Δ_B7 = {sum(idx[(q,B7)]["overall"] for q in qids)/n - mb7_old:+.4f}')
    print(f'  Δ_gap = {(m_b6 - sum(idx[(q,B7)]["overall"] for q in qids)/n) - (mb6_old-mb7_old):+.4f}')

gap = m_b6 - sum(idx[(q,B7)]['overall'] for q in qids)/n
print(f'\nGate +0.020 vs B7: {"PASS — B6 SOTA!" if gap>=0.020 else f"still {round(0.020-gap, 4)} short"}')
PY
