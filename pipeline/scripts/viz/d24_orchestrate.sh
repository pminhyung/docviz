#!/usr/bin/env bash
# D24 orchestrator — run after rank_subtypes_v2 completes 539 rows.
#
# Sequence:
#   1. Hungarian balance assignment      (balance_chart_subtypes.py)
#   2. Update corpus + queries + delete  (regen_swapped_charts.py)
#      stale chart artefacts for swapped docs
#   3. Re-fill queries.jsonl chart_spec  (subtype_assigner --only-chart-spec)
#   4. Re-generate gold/chart            (step2_generate_gold --viz chart)
#   5. Re-generate model_outputs/chart   (step3_generate_models / sonnet --viz chart)
#   6. Re-render chart PNGs              (handled inside step3 already)
#   7. Re-compute structural metrics     (step4_structural_metrics)
#   8. Re-compute VLM judge              (step5_vlm_judge --all --parallel 8)
#   9. Re-aggregate                      (step6_aggregate)
#  10. Re-run orthogonality analysis     (analyze_orthogonality)
#
# Each step logs to logs/d24_<step>.log. Aborts on first failure.
set -euo pipefail

# NOTE (docviz): step4/5/6_*.py and scripts.audit.* are NOT included
# in docviz (eval-side, out of scope). Generation steps (01-06) work;
# 07-10 will fail until the eval pipeline is rewired.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${DOCVIZ_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
cd "$ROOT"
LOG_DIR="${DOCVIZ_LOGS_DIR:-$ROOT/logs}"
mkdir -p "$LOG_DIR"

run() {
    local STEP="$1"; shift
    local LOG="$LOG_DIR/d24_${STEP}.log"
    echo "[d24] === step ${STEP} === starting at $(date +%H:%M:%S)"
    echo "[d24] cmd: $*"
    if "$@" > "$LOG" 2>&1; then
        echo "[d24] === step ${STEP} === OK (log: $LOG)"
    else
        echo "[d24] === step ${STEP} === FAIL (log: $LOG)"
        tail -25 "$LOG" >&2
        exit 1
    fi
}

run 01_balance         python -m scripts.viz.balance_chart_subtypes
run 02_regen_setup     python -m scripts.viz.regen_swapped_charts
# subtype_assigner is doc_id-keyed and would (a) reuse stale chart_spec for
# the OLD subtype and (b) write_back_corpus the OLD subtype, undoing the
# Hungarian balance. regen_chart_specs_for_swapped surgically updates only
# swapped docs and trusts the v2 assignment.
run 03_subtype_specs   python -m scripts.viz.regen_chart_specs_for_swapped --workers 8
run 04_gold_chart      python -m scripts.step2_generate_gold --viz-type chart
# Free GPU 8-15 (Qwen3.6 ranker host) before launching llama4_scout
# which needs TP=8 on the same GPUs.
echo "[d24] === stopping Qwen3.6-27B vLLM (frees GPU 8-15 for llama4_scout) ==="
bash "$SCRIPT_DIR/stop_qwen_vllm.sh" 9200 9201 || true
run 05_model_chart     python -m scripts.step3_generate_models --all-local --viz-type chart
run 06_sonnet_chart    python -m scripts.step3_generate_claude_sonnet --viz chart --max-docs 0 --workers 8
run 07_step4           python -m scripts.step4_structural_metrics
run 07b_step4_semantic python -m scripts.step4_structural_metrics --match-mode semantic
run 08_step5           python -m scripts.step5_vlm_judge --all --parallel 8
run 09_step6           python -m scripts.step6_aggregate
run 10_orthog          python -m scripts.audit.analyze_orthogonality

echo "[d24] === ALL STEPS COMPLETE === $(date +%H:%M:%S)"
