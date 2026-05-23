#!/usr/bin/env bash
# Final merge: combine scope-v3 B6+B7 scores + scope-v3-full B1-B4/S1 scores
# into production judge_scores/all.json. Ablations retain old scores
# (re-judge later if needed).
set -euo pipefail
cd /ex_disk2/mhpark/poc/docviz

STAMP=$(date +%Y%m%d_%H%M%S)
JUDGE_PROD=outputs/prototype/judge_scores/all.json
CHECKLIST_PROD=outputs/prototype/judge_scores/checklists.json

# Backup current production (SOTA)
cp "$JUDGE_PROD" "${JUDGE_PROD}.bak_pre_scope_v3_merge_${STAMP}"
cp "$CHECKLIST_PROD" "${CHECKLIST_PROD}.bak_pre_scope_v3_merge_${STAMP}"

python3 - <<'PY'
import json
from pathlib import Path

old = json.loads(Path('outputs/prototype/judge_scores/all.json').read_text())
b6b7 = json.load(open('/tmp/scope_v3/judge.json'))
others = json.load(open('/tmp/scope_v3_full/judge.json'))
new_strats = {'S4_AgenticTMGv4_consolidated','S7_SelfRefine','B1_MatPlotAgent','B2_NVAGENT','B3_CoDA','B4_ViviDoc','S1_Direct'}
new_lookup = {(r['query_id'], r['strategy']): r for r in (b6b7 + others)}
print(f'new scope-v3 scores: {len(new_lookup)} (B6+B7={len(b6b7)}, others={len(others)})')

out = []
replaced = 0
ablation_kept = 0
for r in old:
    k = (r['query_id'], r['strategy'])
    if k in new_lookup:
        out.append(new_lookup[k]); replaced += 1
    else:
        out.append(r)
        if r['strategy'] not in new_strats:
            ablation_kept += 1
print(f'replaced: {replaced}  kept (ablations): {ablation_kept}')
out.sort(key=lambda r: (r['bundle_id'], r['query_type'], r['strategy']))
Path('outputs/prototype/judge_scores/all.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))

Path('outputs/prototype/judge_scores/checklists.json').write_text(
    Path('/tmp/scope_v3/checklists.json').read_text()
)
print('checklists updated')
PY

python3 - <<'PY'
import json
data = json.load(open('outputs/prototype/judge_scores/all.json'))
qids = sorted({r['query_id'] for r in data})
idx = {(r['query_id'], r['strategy']): r for r in data}
n = len(qids)
B6='S4_AgenticTMGv4_consolidated'; B7='S7_SelfRefine'

print('\n========= POST SCOPE-V3 FULL RE-JUDGE =========')
print(f'N = {n}\n')

strats = ['B1_MatPlotAgent','B2_NVAGENT','B3_CoDA','B4_ViviDoc','S1_Direct',B7,B6]
ranks = []
for s in strats:
    pairs = [(q, s) for q in qids if (q,s) in idx]
    m = sum(idx[k]['overall'] for k in pairs)/len(pairs)
    ranks.append((s, m))
ranks.sort(key=lambda x:-x[1])
m_b6 = next(m for s,m in ranks if s==B6)
m_b7 = next(m for s,m in ranks if s==B7)

print('Final ranking (mean overall, descending):')
for i,(s,m) in enumerate(ranks):
    gap = m_b6 - m
    flag = '★ B6 SOTA' if s==B6 else ('PASS gate +0.020' if gap >= 0.020 else ('TIED' if 0 < gap < 0.020 else 'NEG'))
    print(f'  {i+1}. {s:<36}  {m:.4f}  B6-X={gap:+.4f}  {flag}')

gate_pass = (m_b6 - m_b7) >= 0.020
print(f'\nSTRICT GATE (B6 - B7 >= +0.020):')
print(f'  B6 - B7 = {m_b6 - m_b7:+.4f}')
print(f'  Status: {"★ PASS — B6 SOTA above gate!" if gate_pass else f"short by {0.020-(m_b6-m_b7):.4f}"}')

print(f'\nPer-axis (B6 vs B7):')
for ax in ['faithfulness','coverage','type_appropriateness','cross_document_integration']:
    a6 = sum(idx[(q,B6)]['axis_scores'].get(ax,0) or 0 for q in qids)/n
    a7 = sum(idx[(q,B7)]['axis_scores'].get(ax,0) or 0 for q in qids)/n
    print(f'  {ax}: B6={a6:.4f}  B7={a7:.4f}  Δ={a6-a7:+.4f}')

b6_w=b6_l=tie=0
for q in qids:
    d = idx[(q,B6)]['overall'] - idx[(q,B7)]['overall']
    if d>0.001: b6_w += 1
    elif d<-0.001: b6_l += 1
    else: tie += 1
print(f'\nPaired (B6 vs B7): wins={b6_w}, ties={tie}, losses={b6_l}')

sota = json.load(open('outputs/prototype/judge_scores/all.json.SOTA_v4_post_infra_20260522'))
sidx = {(r['query_id'],r['strategy']):r for r in sota}
print(f'\nDelta vs SOTA backup (pre-scope):')
for s in strats:
    old_m = sum(sidx[(q,s)]['overall'] for q in qids if (q,s) in sidx)/n
    new_m = sum(idx[(q,s)]['overall'] for q in qids if (q,s) in idx)/n
    print(f'  {s:<36}  {old_m:.4f} → {new_m:.4f}  (Δ={new_m-old_m:+.4f})')
PY
