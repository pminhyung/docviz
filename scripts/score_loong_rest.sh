#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
export DGEVAL_CLUSTER=h100
G=data/gold/loong_phase2_working.jsonl
R=outputs/v0.5_harness

# wait for b3 (launched separately) to finish
until [ -f $R/dgeval_b3_loong.json ] || ! pgrep -f 'diagrameval_score.*b3' >/dev/null; do sleep 20; done
pkill -9 -f mmdc 2>/dev/null || true; pkill -9 -f chrome 2>/dev/null || true; sleep 2

echo "=== b4 ==="
python -u code/judge/diagrameval_score.py --recovered $R/b4_loong_s42.json --gold $G --out $R/dgeval_b4_loong.json --workers 14
pkill -9 -f mmdc 2>/dev/null || true; pkill -9 -f chrome 2>/dev/null || true; sleep 2

echo "=== b1 PNG ==="
python -u code/judge/diagrameval_png.py --baseline-out $R/b1_loong_s42.json --gold $G --out $R/dgeval_b1_loong.json --workers 14
pkill -9 -f mmdc 2>/dev/null || true; pkill -9 -f chrome 2>/dev/null || true

echo "=== LOONG B1-B7 FULL TABLE ==="
python - <<'PY'
import json, statistics as st
arms=[('B1 MatPlotAgent','dgeval_b1_loong'),('B2 NVAGENT','dgeval_b2_loong'),('B3 CoDA','dgeval_b3_loong'),('B4 ViviDoc','dgeval_b4_loong'),('B5 Direct','dgeval_b5_s42'),('B7 SelfRefine','dgeval_b7_s42'),('B6 DocViz(ours)','dgeval_full_s42')]
print(f'{"arm":18}{"node":>7}{"path":>7}  ok/n')
for n,f in arms:
    try:
        d=json.load(open(f'outputs/v0.5_harness/{f}.json')); ok=[r for r in d.values() if r['ok']]
        nf=st.mean([r['node_f1'] for r in ok]) if ok else 0; pf=st.mean([r['path_f1'] for r in ok]) if ok else 0
        print(f'{n:18}{nf:7.3f}{pf:7.3f}  {len(ok)}/{len(d)}')
    except Exception as e: print(f'{n:18}  미완')
PY
echo LOONGTABLEDONE
