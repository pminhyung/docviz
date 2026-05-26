#!/usr/bin/env bash
# v0.4 NEW dataset full pipeline orchestrator.
#
# Prerequisites:
#   - All 6 loaders' bundles built (data/prototype/bundles/{src}.json)
#   - Multi-host Qwen agent server running on :9024
#   - 6 Qwen vLLM hosts (147,148,163-166) healthy
#
# Stages:
#   0. env + merge bundles + sanity check (all.json target: 300 bundles)
#   1. generate queries (300 queries, dep-type taxonomy)
#   2. B6 V4_cons × seed42 (300 records, ~20-30 min on 6-host)
#   3. baselines (S1, B1-B4, S7_SelfRefine) + ablations (B6_NoTMG/NoSAO/NoCIS), seed42
#   4. B6 V4_cons × seed43, seed44 (3-seed reporting per §13)
#   5. Held-out: Text2Vis B6 native run (n=100)
#   6. Judge: scope-v3 4-axis re-judge on all outputs
#   7. Generate v0.4 results report
#
# Usage:
#   bash code/scripts/run_v04_pipeline.sh [stage]
#     stage = all (default) | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7

set -uo pipefail

# ── env ──────────────────────────────────────────────────────────────────────
export DOCVIZ_AGENT_URL="http://localhost:9024"
export DOCVIZ_HOST_MODE="multi"
export QWEN_HOSTS="10.1.211.147:8000,10.1.211.148:8000,10.1.211.163:8000,10.1.211.164:8000,10.1.211.165:8000,10.1.211.166:8000"
export QWEN_BASE_URL="http://10.1.211.147:8000/v1"
export QWEN_MODEL="Qwen3.5-397B-A17B-FP8"
export PYTHONUNBUFFERED=1

REPO="/ex_disk2/mhpark/poc/docviz"
cd "$REPO"

OUT_BASE="$REPO/outputs/v0.4"
LOG_DIR="/tmp/v04_logs"
mkdir -p "$OUT_BASE/viz" "$OUT_BASE/judge" "$OUT_BASE/reports" "$LOG_DIR"

STAGE="${1:-all}"
stamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[v04 $(stamp)] $*"; }

# ── stages ───────────────────────────────────────────────────────────────────

stage_0() {
  log "Stage 0 — merge bundles + sanity"
  python -m code.utils.merge_bundles 2>&1 | tee "$LOG_DIR/0_merge.log"
  python3 -c "
import json, statistics
b = json.load(open('data/prototype/bundles/all.json'))
src = {}
for x in b:
    s = x['source']
    src[s] = src.get(s,0)+1
print(f'per-source: {src}')
print(f'total: {len(b)}')
assert len(b) >= 300, f'expected 300 bundles, got {len(b)}'
print('[ok]')
"
}

stage_1() {
  log "Stage 1 — generate queries (dep-type, 1/bundle)"
  python -m code.utils.generate_queries \
    --bundles data/prototype/bundles/all.json \
    --out data/prototype/queries/all.json \
    --raw data/prototype/queries/raw.jsonl \
    2>&1 | tee "$LOG_DIR/1_queries.log"
  python3 -c "
import json
q = json.load(open('data/prototype/queries/all.json'))
ok = sum(1 for x in q if x['filter_passed'])
print(f'queries: {len(q)}, filter_passed: {ok}/{len(q)} ({ok/len(q)*100:.1f}%)')
"
}

stage_2() {
  log "Stage 2 — B6 V4_cons seed42 (300 records, multi-host)"
  QWEN_SEED=42 python -m code.run_prototype \
    --strategies S4_TMGv4_consolidated \
    --bundles data/prototype/bundles/all.json \
    --queries data/prototype/queries/all.json \
    --out "$OUT_BASE/viz/b6_seed42.json" \
    --raw "$OUT_BASE/viz/b6_seed42.raw.jsonl" \
    --s4-workers 6 \
    2>&1 | tee "$LOG_DIR/2_b6_seed42.log"
}

stage_3() {
  log "Stage 3 — baselines + ablations (seed42, in parallel)"
  QWEN_SEED=42 nohup python -m code.run_prototype \
    --strategies S1,B1,B2,B3,B4,S7_SelfRefine \
    --bundles data/prototype/bundles/all.json \
    --queries data/prototype/queries/all.json \
    --out "$OUT_BASE/viz/baselines.json" \
    --raw "$OUT_BASE/viz/baselines.raw.jsonl" \
    --s1-workers 6 \
    --s4-workers 4 \
    > "$LOG_DIR/3_baselines.log" 2>&1 &
  BL_PID=$!
  log "  baselines bg PID=$BL_PID"

  QWEN_SEED=42 nohup python -m code.run_prototype \
    --strategies B6_Full,B6_NoTMG,B6_NoSAO,B6_NoCIS \
    --bundles data/prototype/bundles/all.json \
    --queries data/prototype/queries/all.json \
    --out "$OUT_BASE/viz/ablations.json" \
    --raw "$OUT_BASE/viz/ablations.raw.jsonl" \
    --s4-workers 4 \
    > "$LOG_DIR/3_ablations.log" 2>&1 &
  AB_PID=$!
  log "  ablations bg PID=$AB_PID"

  wait $BL_PID $AB_PID
  log "Stage 3 done"
}

stage_4() {
  log "Stage 4 — B6 V4_cons seed43 + seed44"
  for SEED in 43 44; do
    QWEN_SEED=$SEED python -m code.run_prototype \
      --strategies S4_TMGv4_consolidated \
      --bundles data/prototype/bundles/all.json \
      --queries data/prototype/queries/all.json \
      --out "$OUT_BASE/viz/b6_seed${SEED}.json" \
      --raw "$OUT_BASE/viz/b6_seed${SEED}.raw.jsonl" \
      --s4-workers 6 \
      2>&1 | tee "$LOG_DIR/4_b6_seed${SEED}.log"
  done
}

stage_5() {
  log "Stage 5 — Text2Vis held-out (B6 native, n=100)"
  QWEN_SEED=42 python -m code.run_prototype \
    --strategies S4_TMGv4_consolidated \
    --bundles data/prototype/bundles/text2vis.json \
    --queries data/prototype/queries/text2vis.json \
    --out "$OUT_BASE/viz/text2vis_b6.json" \
    --raw "$OUT_BASE/viz/text2vis_b6.raw.jsonl" \
    --s4-workers 6 \
    2>&1 | tee "$LOG_DIR/5_text2vis.log"
}

stage_6() {
  log "Stage 6 — judge scope-v3 (4-axis) on all outputs"
  for in_file in b6_seed42 b6_seed43 b6_seed44 baselines ablations; do
    if [ -f "$OUT_BASE/viz/${in_file}.json" ]; then
      python -m code.judge.run_judge \
        --viz "$OUT_BASE/viz/${in_file}.json" \
        --bundles data/prototype/bundles/all.json \
        --out "$OUT_BASE/judge/${in_file}.json" \
        --checklist-cache "$OUT_BASE/judge/checklists.json" \
        --raw "$OUT_BASE/judge/${in_file}.raw.jsonl" \
        --checklist-workers 6 --score-workers 6 \
        2>&1 | tee "$LOG_DIR/6_judge_${in_file}.log"
    fi
  done
  # Text2Vis held-out judge uses its own bundle file
  if [ -f "$OUT_BASE/viz/text2vis_b6.json" ]; then
    python -m code.judge.run_judge \
      --viz "$OUT_BASE/viz/text2vis_b6.json" \
      --bundles data/prototype/bundles/text2vis.json \
      --out "$OUT_BASE/judge/text2vis_b6.json" \
      --checklist-cache "$OUT_BASE/judge/text2vis_checklists.json" \
      --raw "$OUT_BASE/judge/text2vis_b6.raw.jsonl" \
      --checklist-workers 6 --score-workers 6 \
      2>&1 | tee "$LOG_DIR/6_judge_text2vis_b6.log"
  fi
}

stage_7() {
  log "Stage 7 — generate v0.4 results report"
  # Aggregate 3-seed mean±std, per-axis/per-source/per-query-type breakdown,
  # Δ vs baselines, ablation magnitude.
  python -m code.scripts.aggregate_v04_results \
    --judge-dir "$OUT_BASE/judge" \
    --out "$OUT_BASE/reports/v04_summary.md" \
    2>&1 | tee "$LOG_DIR/7_report.log" || log "  [WARN] aggregator not implemented yet"
}

# ── dispatch ─────────────────────────────────────────────────────────────────

case "$STAGE" in
  0) stage_0 ;;
  1) stage_1 ;;
  2) stage_2 ;;
  3) stage_3 ;;
  4) stage_4 ;;
  5) stage_5 ;;
  6) stage_6 ;;
  7) stage_7 ;;
  all)
    stage_0
    stage_1
    stage_2
    stage_3
    stage_4
    stage_5
    stage_6
    stage_7
    log "v0.4 pipeline complete"
    ;;
  *) log "unknown stage: $STAGE"; exit 1 ;;
esac
