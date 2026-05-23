#!/usr/bin/env bash
# Merge 5 infra-recovered B6 records into production, re-judge, measure.
set -euo pipefail
cd /ex_disk2/mhpark/poc/docviz

STAMP=$(date +%Y%m%d_%H%M%S)
INFRA_DIR=/tmp/v45_infra
VIZ_PROD=outputs/prototype/viz/all.json
JUDGE_PROD=outputs/prototype/judge_scores/all.json
CHECKLIST_PROD=outputs/prototype/judge_scores/checklists.json

# Backup
cp "$VIZ_PROD"   "${VIZ_PROD}.bak_pre_infra_${STAMP}"
cp "$JUDGE_PROD" "${JUDGE_PROD}.bak_pre_infra_${STAMP}"
echo "[backup] ${VIZ_PROD}.bak_pre_infra_${STAMP}"
echo "[backup] ${JUDGE_PROD}.bak_pre_infra_${STAMP}"

# Merge new viz records (replace B6 entries for those 5 qids)
python3 - <<'PY'
import json
from pathlib import Path
VIZ = Path('outputs/prototype/viz/all.json')
NEW = Path('/tmp/v45_infra/raw.jsonl')
B6 = 'S4_AgenticTMGv4_consolidated'

old = json.loads(VIZ.read_text())
new_lookup = {}
with NEW.open() as f:
    for line in f:
        if not line.strip(): continue
        r = json.loads(line)
        if r.get('strategy') == B6:
            new_lookup[r['query_id']] = r
print(f'[merge] new V4 records: {len(new_lookup)} qids={list(new_lookup.keys())}')

out = []; replaced=0
for r in old:
    if r['strategy']==B6 and r['query_id'] in new_lookup:
        out.append(new_lookup[r['query_id']]); replaced += 1
    else:
        out.append(r)
print(f'[merge] replaced B6 entries: {replaced}')
out.sort(key=lambda r: (r['bundle_id'], r['query_type'], r['strategy']))
VIZ.write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(f'[merge] → {VIZ}')

# Subset for judge
b6_5 = [r for r in out if r['strategy']==B6 and r['query_id'] in new_lookup]
json.dump(b6_5, open('/tmp/v45_infra/viz_b6_5.json','w'), indent=2, ensure_ascii=False)
print(f'[subset] {len(b6_5)} B6 records → /tmp/v45_infra/viz_b6_5.json')
PY

# Re-judge those 5
python -m code.judge.run_judge \
    --viz /tmp/v45_infra/viz_b6_5.json \
    --bundles data/prototype/bundles/all.json \
    --out /tmp/v45_infra/judge_b6_5.json \
    --checklist-cache "$CHECKLIST_PROD" \
    --raw /tmp/v45_infra/judge_raw.jsonl \
    --score-workers 5 \
    --force

# Merge into production judge_scores
python3 - <<'PY'
import json
from pathlib import Path
JS = Path('outputs/prototype/judge_scores/all.json')
old = json.loads(JS.read_text())
new_b6 = json.load(open('/tmp/v45_infra/judge_b6_5.json'))
new_lookup = {r['query_id']: r for r in new_b6}
B6 = 'S4_AgenticTMGv4_consolidated'

out=[]; replaced=0
for r in old:
    if r['strategy']==B6 and r['query_id'] in new_lookup:
        out.append(new_lookup[r['query_id']]); replaced+=1
    else:
        out.append(r)
print(f'[merge-judge] replaced {replaced} B6 score records')
out.sort(key=lambda r: (r['bundle_id'], r['query_type'], r['strategy']))
JS.write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(f'[merge-judge] → {JS}')
PY

# Final measurement
python3 - <<'PY'
import json
data = json.load(open('outputs/prototype/judge_scores/all.json'))
qids = sorted({r['query_id'] for r in data})
idx = {(r['query_id'], r['strategy']): r for r in data}
B6='S4_AgenticTMGv4_consolidated'; B7='S7_SelfRefine'
n = len(qids)
m_b6 = sum(idx[(q,B6)]['overall'] for q in qids)/n
m_b7 = sum(idx[(q,B7)]['overall'] for q in qids)/n
print(f'\n========= POST INFRA-RETRY =========')
print(f'  N = {n}')
print(f'  B6 mean : {m_b6:.4f}')
print(f'  B7 mean : {m_b7:.4f}')
print(f'  B7 - B6 = {(m_b7-m_b6):+.4f}')
gap = m_b6 - m_b7
print(f'  B6 - B7 = {gap:+.4f}  (gate +0.020: {"PASS" if gap>=0.020 else "still " + str(round(0.020-gap, 4)) + " short"})')
print(f'\n  Per-axis means:')
for ax in ['faithfulness','coverage','type_appropriateness','cross_document_integration']:
    a6 = sum(idx[(q,B6)]['axis_scores'].get(ax,0) or 0 for q in qids)/n
    a7 = sum(idx[(q,B7)]['axis_scores'].get(ax,0) or 0 for q in qids)/n
    print(f'    {ax}: B6={a6:.4f}  B7={a7:.4f}  Δ={a6-a7:+.4f}')

# Paired
losses=wins=ties=0
for q in qids:
    d = idx[(q,B7)]['overall'] - idx[(q,B6)]['overall']
    if d>0.001: losses+=1
    elif d<-0.001: wins+=1
    else: ties+=1
print(f'\n  Paired: B6 wins={wins}, ties={ties}, losses={losses}')
PY
