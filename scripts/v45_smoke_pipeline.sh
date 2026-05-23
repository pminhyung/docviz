#!/usr/bin/env bash
# After retry_v4_cons_repair finishes, build viz.json from raw.jsonl,
# run the judge with cached checklists, then dump a per-record axis delta
# comparison vs the production scores.
set -euo pipefail

SMOKE_DIR=/tmp/v45_smoke
PROD_JUDGE=/ex_disk2/mhpark/poc/docviz/outputs/prototype/judge_scores/all.json
PROD_CHECKLIST=/ex_disk2/mhpark/poc/docviz/outputs/prototype/judge_scores/checklists.json
TARGETS=/tmp/v45_smoke_targets.json
BUNDLES=/ex_disk2/mhpark/poc/docviz/data/prototype/bundles/all.json

cd /ex_disk2/mhpark/poc/docviz

# 1) raw.jsonl  →  viz.json (only S4 V4_consolidated entries for target qids)
python3 - <<'PY'
import json, sys
targets = set(json.load(open('/tmp/v45_smoke_targets.json')))
out=[]
with open('/tmp/v45_smoke/raw.jsonl') as f:
    for line in f:
        if not line.strip(): continue
        r = json.loads(line)
        if r.get('strategy') != 'S4_AgenticTMGv4_consolidated': continue
        if r.get('query_id') not in targets: continue
        out.append(r)
# Sort by query_id for stable diff
out.sort(key=lambda r:r['query_id'])
print(f'[viz-build] {len(out)} records (target count={len(targets)})')
json.dump(out, open('/tmp/v45_smoke/viz.json','w'), indent=2, ensure_ascii=False)
PY

# 2) Judge re-run on smoke viz, reusing cached checklists (no judge prompt change!)
#    --raw must be a separate path to avoid touching production
python -m code.judge.run_judge \
    --viz /tmp/v45_smoke/viz.json \
    --bundles "$BUNDLES" \
    --out /tmp/v45_smoke/judge.json \
    --checklist-cache "$PROD_CHECKLIST" \
    --raw /tmp/v45_smoke/judge_raw.jsonl \
    --score-workers 4 \
    --checklist-workers 4

# 3) Compare new vs old (production) per-record axis scores
python3 - <<'PY'
import json
new = {r['query_id']: r for r in json.load(open('/tmp/v45_smoke/judge.json'))}
old_all = json.load(open('/ex_disk2/mhpark/poc/docviz/outputs/prototype/judge_scores/all.json'))
B6 = 'S4_AgenticTMGv4_consolidated'; B7='S7_SelfRefine'
old = {r['query_id']: r for r in old_all if r['strategy']==B6}
b7  = {r['query_id']: r for r in old_all if r['strategy']==B7}

axes = ['faithfulness','coverage','type_appropriateness','cross_document_integration']
print('\n=== Per-record old→new axis deltas (B6 V4 vs V4.5) ===')
print(f"{'qid':<32} {'old':>5} {'new':>5} {'Δov':>6} {'b7':>5}  {'fΔ':>5} {'cΔ':>5} {'tΔ':>5} {'iΔ':>5}")
sum_old=sum_new=0
for q in sorted(new):
    o, n = old.get(q), new[q]; b = b7.get(q)
    if not o: continue
    oo=o['overall']; nn=n['overall']; bo=b['overall'] if b else 0.0
    ds = []
    for ax in axes:
        ov = o['axis_scores'].get(ax,0) or 0
        nv = n['axis_scores'].get(ax,0) or 0
        ds.append(nv-ov)
    sum_old += oo; sum_new += nn
    print(f"{q:<32} {oo:>5.2f} {nn:>5.2f} {nn-oo:>+6.2f} {bo:>5.2f}  {ds[0]:>+5.2f} {ds[1]:>+5.2f} {ds[2]:>+5.2f} {ds[3]:>+5.2f}")

n = len(new)
print(f"\nMean overall on these {n} records:  V4={sum_old/n:.4f}  V4.5={sum_new/n:.4f}  Δ={(sum_new-sum_old)/n:+.4f}")
# Project full-265 effect: assume off-target 238 records unchanged
old_b6_total = sum(r['overall'] for r in old_all if r['strategy']==B6)
old_b7_total = sum(r['overall'] for r in old_all if r['strategy']==B7)
delta_on_targets = sum_new - sum_old
new_b6_total = old_b6_total + delta_on_targets
N=265
print(f'Projected full-265 means: B6_new={new_b6_total/N:.4f}  B7={old_b7_total/N:.4f}')
print(f'Projected gap (B7-B6_new): {(old_b7_total - new_b6_total)/N:+.4f}  (gate PASS = <= -0.020)')
PY
