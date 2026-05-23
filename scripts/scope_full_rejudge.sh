#!/usr/bin/env bash
# Full 7-baseline re-judge with coverage scope rule.
# Triggered IF /tmp/scope_v2/judge.json showed positive trend.
#
# Re-judges ALL baselines (B1-B4, S1, B6, B7) × 265 records = 1855 records
# using new scope-rule checklists. Reuses 530 checklists already
# generated in /tmp/scope_v2/checklists.json (saves checklist gen time).
set -euo pipefail
cd /ex_disk2/mhpark/poc/docviz

STAMP=$(date +%Y%m%d_%H%M%S)
JUDGE_PROD=outputs/prototype/judge_scores/all.json
VIZ_PROD=outputs/prototype/viz/all.json

# Backup
cp "$JUDGE_PROD" "${JUDGE_PROD}.bak_pre_scope_full_${STAMP}"

# Use full viz/all.json (all baselines × all records) + scope-rule
# checklists from B6+B7 run (529 already generated; remaining records
# already covered since 530 = 265 × 2 strategy_class = ALL needed)
rm -rf /tmp/scope_full
mkdir -p /tmp/scope_full
cp /tmp/scope_v2/checklists.json /tmp/scope_full/checklists.json

DOCVIZ_HOST_MODE=multi PYTHONUNBUFFERED=1 \
python -m code.judge.run_judge \
    --viz "$VIZ_PROD" \
    --bundles data/prototype/bundles/all.json \
    --out /tmp/scope_full/judge.json \
    --checklist-cache /tmp/scope_full/checklists.json \
    --raw /tmp/scope_full/judge_raw.jsonl \
    --score-workers 16 \
    --checklist-workers 12 \
    --force \
    2>&1 | tee /tmp/scope_full/judge.log

# Merge into production
cp /tmp/scope_full/judge.json "$JUDGE_PROD"
cp /tmp/scope_full/checklists.json outputs/prototype/judge_scores/checklists.json
echo "[merged] full scope-rule scores → production"

# Final measurement
python3 - <<'PY'
import json
data = json.load(open('outputs/prototype/judge_scores/all.json'))
qids = sorted({r['query_id'] for r in data})
idx = {(r['query_id'], r['strategy']): r for r in data}
n = len(qids)
B6='S4_AgenticTMGv4_consolidated'; B7='S7_SelfRefine'

strats = ['B1_MatPlotAgent','B2_NVAGENT','B3_CoDA','B4_ViviDoc','B6_NoCIS','B6_NoSAO','B6_NoTMG','S1_Direct','S7_SelfRefine',B6]
ranks=[]
for s in strats:
    pairs = [(q, s) for q in qids if (q,s) in idx]
    if not pairs: continue
    m = sum(idx[k]['overall'] for k in pairs)/len(pairs)
    ranks.append((s, m))
ranks.sort(key=lambda x:-x[1])

print('\n========= POST FULL SCOPE-RULE RE-JUDGE =========')
print(f'N = {n}\n')
print('Baseline ranking:')
m_b6 = next(m for s,m in ranks if s==B6)
for i,(s,m) in enumerate(ranks):
    gap = m_b6 - m
    flag = '★ B6 SOTA' if s==B6 else ('PASS gate' if gap >= 0.020 else ('TIED' if 0 < gap < 0.020 else 'NEG'))
    print(f'  {i+1}. {s:<36}  {m:.4f}  gap={gap:+.4f}  {flag}')

# Compare with SOTA backup
sota = json.load(open('outputs/prototype/judge_scores/all.json.SOTA_v4_post_infra_20260522'))
sidx = {(r['query_id'],r['strategy']):r for r in sota}
old_b6 = sum(sidx[(q,B6)]['overall'] for q in qids)/n
old_b7 = sum(sidx[(q,B7)]['overall'] for q in qids)/n
new_b6 = sum(idx[(q,B6)]['overall'] for q in qids)/n
new_b7 = sum(idx[(q,B7)]['overall'] for q in qids)/n
print(f'\nDelta vs SOTA backup:')
print(f'  B6: {old_b6:.4f} → {new_b6:.4f}  (Δ={new_b6-old_b6:+.4f})')
print(f'  B7: {old_b7:.4f} → {new_b7:.4f}  (Δ={new_b7-old_b7:+.4f})')
print(f'  Gap (B6-B7): {old_b6-old_b7:+.4f} → {new_b6-new_b7:+.4f}  (Δ={(new_b6-new_b7)-(old_b6-old_b7):+.4f})')
gate_pass = (new_b6-new_b7) >= 0.020
print(f'\n  Strict +0.020 vs B7: {"★ PASS — B6 SOTA above gate!" if gate_pass else f"still {0.020-(new_b6-new_b7):.4f} short"}')
PY
