#!/usr/bin/env bash
# Full-265 V4.5 rerun + re-judge + merge into production all.json.
# Triggered manually after smoke validates the design.
#
# Steps:
#   1) Backup viz/all.json + judge_scores/all.json (timestamped)
#   2) Run parallel retry on all 265 qids → /tmp/v45_full/raw.jsonl
#   3) Merge new V4.5 B6 records into outputs/prototype/viz/all.json
#      (replacing S4_AgenticTMGv4_consolidated entries)
#   4) Re-judge ONLY S4_AgenticTMGv4_consolidated entries on the merged
#      viz, reusing cached checklists (judge prompt UNCHANGED)
#   5) Merge new scores into outputs/prototype/judge_scores/all.json
#   6) Compute new B6 mean, gap vs B7
set -euo pipefail
cd /ex_disk2/mhpark/poc/docviz

STAMP=$(date +%Y%m%d_%H%M%S)
FULL_DIR=/tmp/v45_full
mkdir -p "$FULL_DIR"
VIZ_PROD=outputs/prototype/viz/all.json
JUDGE_PROD=outputs/prototype/judge_scores/all.json
CHECKLIST_PROD=outputs/prototype/judge_scores/checklists.json
RAW_PROD=outputs/prototype/viz/raw.jsonl
JUDGE_RAW_PROD=outputs/prototype/judge_scores/raw.jsonl

# 1) Backup
cp "$VIZ_PROD"   "${VIZ_PROD}.bak_pre_v45_${STAMP}"
cp "$JUDGE_PROD" "${JUDGE_PROD}.bak_pre_v45_${STAMP}"
echo "[backup] ${VIZ_PROD}.bak_pre_v45_${STAMP}"
echo "[backup] ${JUDGE_PROD}.bak_pre_v45_${STAMP}"

# 2) Full-265 V4.5 rerun
rm -f "$FULL_DIR/raw.jsonl" "$FULL_DIR/results.json"
DOCVIZ_HOST_MODE=multi PYTHONUNBUFFERED=1 \
python -m code.scripts.retry_v4_cons_parallel \
    --bundles data/prototype/bundles/all.json \
    --queries data/prototype/queries/all.json \
    --targets /tmp/v45_full_targets.json \
    --out "$FULL_DIR/results.json" \
    --write-raw "$FULL_DIR/raw.jsonl" \
    --workers 8 \
    2>&1 | tee "$FULL_DIR/retry.log"

# 3) Merge: replace S4_AgenticTMGv4_consolidated entries in viz/all.json
python3 - <<'PY'
import json
from pathlib import Path

VIZ = Path('outputs/prototype/viz/all.json')
NEW_RAW = Path('/tmp/v45_full/raw.jsonl')
B6 = 'S4_AgenticTMGv4_consolidated'

old = json.loads(VIZ.read_text())
# Build new V4.5 lookup by qid
new_lookup = {}
with NEW_RAW.open() as f:
    for line in f:
        if not line.strip(): continue
        r = json.loads(line)
        if r.get('strategy') == B6:
            new_lookup[r['query_id']] = r
print(f'[merge] new V4.5 records: {len(new_lookup)}')

# Replace B6 entries; keep others
out = []
replaced = 0; unchanged_b6 = 0; nonb6 = 0
for r in old:
    if r['strategy'] == B6:
        if r['query_id'] in new_lookup:
            out.append(new_lookup[r['query_id']]); replaced += 1
        else:
            out.append(r); unchanged_b6 += 1
    else:
        out.append(r); nonb6 += 1
print(f'[merge] replaced B6: {replaced}  unchanged B6: {unchanged_b6}  other strats kept: {nonb6}')
out.sort(key=lambda r: (r['bundle_id'], r['query_type'], r['strategy']))
VIZ.write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(f'[merge] → {VIZ}')
PY

# 4) Re-judge: only S4_AgenticTMGv4_consolidated entries get re-scored.
#    Trick — write a B6-only viz subset, judge that, then merge results.
python3 - <<'PY'
import json
B6='S4_AgenticTMGv4_consolidated'
all_viz = json.load(open('outputs/prototype/viz/all.json'))
b6_subset = [r for r in all_viz if r['strategy']==B6]
print(f'[subset] B6 entries to re-score: {len(b6_subset)}')
json.dump(b6_subset, open('/tmp/v45_full/viz_b6_only.json','w'), indent=2, ensure_ascii=False)
PY

# Judge — force re-score by emptying out the B6 entries in a copy of all.json
python3 - <<'PY'
import json
src=json.load(open('outputs/prototype/judge_scores/all.json'))
non_b6=[r for r in src if r['strategy']!='S4_AgenticTMGv4_consolidated']
json.dump(non_b6, open('/tmp/v45_full/judge_non_b6.json','w'), indent=2, ensure_ascii=False)
print(f'[non-b6 base] {len(non_b6)} records carried over (no re-judge)')
PY

python -m code.judge.run_judge \
    --viz /tmp/v45_full/viz_b6_only.json \
    --bundles data/prototype/bundles/all.json \
    --out /tmp/v45_full/judge_b6_new.json \
    --checklist-cache "$CHECKLIST_PROD" \
    --raw /tmp/v45_full/judge_raw.jsonl \
    --score-workers 6 \
    --checklist-workers 4

# 5) Merge new B6 scores into production judge_scores
python3 - <<'PY'
import json
from pathlib import Path
JS = Path('outputs/prototype/judge_scores/all.json')
old = json.loads(JS.read_text())
new_b6 = json.load(open('/tmp/v45_full/judge_b6_new.json'))
new_b6_by_qid = {r['query_id']: r for r in new_b6}
B6='S4_AgenticTMGv4_consolidated'
out=[]; replaced=0
for r in old:
    if r['strategy']==B6 and r['query_id'] in new_b6_by_qid:
        out.append(new_b6_by_qid[r['query_id']]); replaced += 1
    else:
        out.append(r)
print(f'[merge-judge] replaced {replaced} B6 score records')
out.sort(key=lambda r: (r['bundle_id'], r['query_type'], r['strategy']))
JS.write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(f'[merge-judge] → {JS}')
PY

# 6) Compute new B6 mean + gap
python3 - <<'PY'
import json
from collections import defaultdict
data = json.load(open('outputs/prototype/judge_scores/all.json'))
qids = sorted({r['query_id'] for r in data})
idx = {(r['query_id'], r['strategy']): r for r in data}
B6='S4_AgenticTMGv4_consolidated'; B7='S7_SelfRefine'
n = len(qids)
m_b6 = sum(idx[(q,B6)]['overall'] for q in qids)/n
m_b7 = sum(idx[(q,B7)]['overall'] for q in qids)/n
print(f'\n========= V4.5 RESULTS =========')
print(f'  N = {n}')
print(f'  B6 mean (V4.5): {m_b6:.4f}')
print(f'  B7 mean       : {m_b7:.4f}')
print(f'  B7 - B6 = {(m_b7-m_b6):+.4f}')
print(f'  Gate (+0.020): {"PASS — B6 SOTA above gate" if (m_b6-m_b7)>=0.020 else "still short by " + str(round(0.020-(m_b6-m_b7),4))}')
print(f'\n  Per-axis breakdown:')
for ax in ['faithfulness','coverage','type_appropriateness','cross_document_integration']:
    a6 = sum(idx[(q,B6)]['axis_scores'].get(ax,0) or 0 for q in qids)/n
    a7 = sum(idx[(q,B7)]['axis_scores'].get(ax,0) or 0 for q in qids)/n
    print(f'    {ax}: B6={a6:.4f}  B7={a7:.4f}  Δ={a6-a7:+.4f}')

# Paired Δ (B6 wins/losses/ties)
losses = wins = ties = 0
for q in qids:
    d = idx[(q,B7)]['overall'] - idx[(q,B6)]['overall']
    if d > 0.001: losses += 1
    elif d < -0.001: wins += 1
    else: ties += 1
print(f'\n  Paired: B6 wins={wins}, ties={ties}, losses={losses}')
PY
