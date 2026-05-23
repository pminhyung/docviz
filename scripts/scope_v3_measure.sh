#!/usr/bin/env bash
# After /tmp/scope_v3/judge.json completes, measure B6 vs B7 effect of
# coverage scope rule (without merging to production yet — pending full
# baseline re-judge for fair comparison).
set -euo pipefail
cd /ex_disk2/mhpark/poc/docviz

python3 - <<'PY'
import json

# Load new scope-rule scores (B6+B7 only)
new = json.load(open('/tmp/scope_v3/judge.json'))
new_lookup = {(r['query_id'], r['strategy']): r for r in new}

# Load current production (V4 + 5 infra retry, no scope rule)
old = json.load(open('outputs/prototype/judge_scores/all.json'))
old_lookup = {(r['query_id'], r['strategy']): r for r in old}

B6 = 'S4_AgenticTMGv4_consolidated'
B7 = 'S7_SelfRefine'
qids = sorted({k[0] for k in new_lookup if k[1] == B6})
n = len(qids)

def mean(strategy, lookup):
    return sum(lookup[(q, strategy)]['overall'] for q in qids) / n

def axis_mean(strategy, lookup, ax):
    return sum((lookup[(q, strategy)]['axis_scores'].get(ax, 0) or 0) for q in qids) / n

print('=' * 70)
print('COVERAGE SCOPE RULE EFFECT (B6+B7 only, n={})'.format(n))
print('=' * 70)
print()
print(f"{'':25s}  {'OLD (no scope)':>15s}  {'NEW (with scope)':>17s}  {'Δ':>8s}")
print('-' * 70)

old_b6 = mean(B6, old_lookup); new_b6 = mean(B6, new_lookup)
old_b7 = mean(B7, old_lookup); new_b7 = mean(B7, new_lookup)
print(f"{'B6 mean overall':25s}  {old_b6:>15.4f}  {new_b6:>17.4f}  {new_b6-old_b6:>+8.4f}")
print(f"{'B7 mean overall':25s}  {old_b7:>15.4f}  {new_b7:>17.4f}  {new_b7-old_b7:>+8.4f}")
print(f"{'Gap (B6 - B7)':25s}  {old_b6-old_b7:>+15.4f}  {new_b6-new_b7:>+17.4f}  {(new_b6-new_b7)-(old_b6-old_b7):>+8.4f}")
print()
print(f"Strict +0.020 gate vs B7: {'PASS ✓' if (new_b6-new_b7) >= 0.020 else f'short by {0.020-(new_b6-new_b7):.4f}'}")
print()
print('Per-axis:')
for ax in ['faithfulness','coverage','type_appropriateness','cross_document_integration']:
    o6 = axis_mean(B6, old_lookup, ax); n6 = axis_mean(B6, new_lookup, ax)
    o7 = axis_mean(B7, old_lookup, ax); n7 = axis_mean(B7, new_lookup, ax)
    print(f"  {ax}:")
    print(f"    B6: {o6:.4f} → {n6:.4f}  (Δ={n6-o6:+.4f})")
    print(f"    B7: {o7:.4f} → {n7:.4f}  (Δ={n7-o7:+.4f})")
    print(f"    gap (B6-B7): {o6-o7:+.4f} → {n6-n7:+.4f}  (Δ={(n6-n7)-(o6-o7):+.4f})")

# Paired counts
b6_w = b6_l = tie = 0
for q in qids:
    d = new_lookup[(q,B6)]['overall'] - new_lookup[(q,B7)]['overall']
    if d > 0.001: b6_w += 1
    elif d < -0.001: b6_l += 1
    else: tie += 1
print(f"\nPaired (new): B6 wins {b6_w}, ties {tie}, B6 losses {b6_l}")

# Old paired for comparison
b6_w_old = b6_l_old = tie_old = 0
for q in qids:
    d = old_lookup[(q,B6)]['overall'] - old_lookup[(q,B7)]['overall']
    if d > 0.001: b6_w_old += 1
    elif d < -0.001: b6_l_old += 1
    else: tie_old += 1
print(f"Paired (old): B6 wins {b6_w_old}, ties {tie_old}, B6 losses {b6_l_old}")

# Decision signal
print()
gap_change = (new_b6-new_b7) - (old_b6-old_b7)
b6_lift = new_b6 - old_b6
b7_lift = new_b7 - old_b7
if gap_change > 0.001 and b6_lift > b7_lift:
    print(f"★ POSITIVE TREND — scope rule lifts B6 more than B7 (Δ_gap = +{gap_change:.4f})")
    print(f"  → Proceed to FULL re-judge (B1-B4, S1) for fair baseline ranking")
elif gap_change < -0.001:
    print(f"✗ NEGATIVE — gap shrank by {-gap_change:.4f}; scope rule does not help B6")
else:
    print(f"○ NEUTRAL — gap change {gap_change:+.4f} within noise; not worth full re-judge")
PY
