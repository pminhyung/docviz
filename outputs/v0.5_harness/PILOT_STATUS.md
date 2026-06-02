# v0.4.1 50-Pilot — Status & Next Steps

**Date**: 2026-06-02
**Branch**: feat/source-loaders
**Last commit**: `d0a1bfd` (P4 chart + mermaid evaluators)

## Phases completed

| Phase | Status | Output |
|---|---|---|
| P0 parser preflight | ✅ DONE | chartjs/mermaid 100% on Qwen seed42; report at `outputs/v0.5_harness/P0_REPORT.md` |
| P1 tool/prompt port | ✅ DONE | `exaone/viz_tools/handle_generate_viz.py` + 4 identity files (full/-CIS/-SAO/-TMG) + style + tool description |
| P2 query gen (50) | ✅ DONE | `data/queries/pilot_50.jsonl` — 50/50 success, balanced 10-per-challenge-type |
| P3 gold extraction (50) | ✅ DONE | `data/gold/pilot_50.jsonl` — 50/50 success, single-Qwen-extractor, no Prolific |
| P4 deterministic metrics | ✅ DONE | `code/metrics/` — chart_metrics + mermaid_metrics + evidence_metrics + hungarian_intent; self-as-gold smoke gives F1=1.0 |

Key fix used in P2/P3: `chat_template_kwargs={"enable_thinking": False}` via OpenAI `extra_body` — Qwen3.5's default chat template emits `<think>` block that burns the token budget on structured-JSON tasks.

## Phases remaining

| Phase | Effort | Wall-clock |
|---|---|---|
| Bundle → pdf_index converter | ~30 min code | <5 min run |
| Bundle → batch_runner JSONL | ~30 min code | <1 min run |
| End-to-end smoke (1 record, B6, Qwen) | ~30 min | ~2 min |
| **P6 50-record measurement (3 backbones × 3 strategies × 1 seed)** | already wired | **~3-4 hours** |
| Aggregation + diagnostic | ~1 hour | minutes |

## Critical path to first diagnostic data (per user's Goal)

```
[NEXT 1] scripts/bundles_to_pdf_index.py    (NEW, ~150 LOC)
  → outputs/v0.5_harness/docai_out/   (EXAONE_PARSED_ROOT for ir-shim Mode A)

[NEXT 2] scripts/bundles_to_jsonl.py        (NEW, ~80 LOC)
  → data/queries/pilot_50_runner.jsonl
     (each row: {prompt, attachments[], qa_mode="docviz", ...})

[NEXT 3] End-to-end smoke
  EXAONE_PARSED_ROOT=outputs/v0.5_harness/docai_out \
  HERMES_EXAONE_AGENT=1 uv run python exaone/batch_runner_pool.py \
    --dataset_file=data/queries/pilot_50_runner.jsonl \
    --batch_size=1 --max_samples=1 \
    --run_name=smoke_b6_qwen \
    --host_config=configs/hosts-eval-qwen.yaml
  → verify sidecars + trajectories.jsonl

[NEXT 4] P6 measurement (3 strategies × 3 backbones)
  For each backbone in {qwen, deepseek, gpt5mini}:
    For each strategy in {S1_Direct, S7_SelfRefine, B6_full}:
      run batch_runner_pool with --host_config + --dataset_file=pilot_50_runner.jsonl
      seed=42 only for pilot (3-seed reserved for scale-up)

  Wall-clock: ~3-4 hours for all 9 combos (32 worker pool).

[NEXT 5] Aggregate via code/eval/build_paper_tables.py (NEW, ~200 LOC)
  reads each run's trajectories.jsonl,
  emits ArtifactSpec per record,
  calls evaluate_chartjs/evaluate_mermaid/evaluate_evidence/hungarian_match
  against data/gold/pilot_50.jsonl,
  writes per-backbone × per-strategy × per-metric table to
  outputs/v0.5_harness/PILOT_RESULTS.md

[NEXT 6] Diagnostic per user's Goal
  - Check: B6 vs best-baseline-mean on each frontier backbone (Qwen + DeepSeek + GPT-5-mini)
  - If gap < target (+0.020 Evidence F1, ≥3/4 metric wins):
      - Identify lowest-performing B6 samples (B6 score < best_baseline_mean)
      - Diagnose: data design (query/gold ambiguity) vs eval artifact (parser bug)
        vs B6 module weakness (which pillar/step fails)
      - Survey top-conf papers for relevant remediation
      - Design novel fix
      - Re-run pilot → verify SOTA consistency
  - If SOTA consistent → scale to 300 records
```

## Backbone budget

| Backbone | Cost for 50-pilot × 3 strategies × 1 seed | Status |
|---|---|---|
| Qwen3.5-397B (local, 8 hosts) | $0 | ready, configs/hosts-eval-qwen.yaml |
| DeepSeek-V4-Flash (local, 2 hosts) | $0 | ready, configs/hosts-eval-deepseek.yaml |
| GPT-5-mini (closed API) | ~$10 | needs OpenAI API key wiring in batch_runner_pool |
| Claude Opus 4.8 (closed API) | ~$15 | EXCLUDED from pilot per user (3-backbone scope) |

## Files added in this push series

```
code/__init__.py
code/metrics/__init__.py
code/metrics/chart_metrics.py             P0 parser + P4 evaluate_chartjs
code/metrics/mermaid_metrics.py           P0 parser + P4 evaluate_mermaid
code/metrics/evidence_metrics.py          P4 evaluate_evidence (explicit + implicit)
code/metrics/hungarian_intent.py          P4 Hungarian assignment + ROUGE-L
exaone/viz_tools/handle_generate_viz.py   P1 generate_viz tool handler
exaone/viz_tools/__init__.py
exaone/prompts/identities/docviz.txt      P1 B6 full identity
exaone/prompts/identities/docviz_nocis.txt    P1 ablation
exaone/prompts/identities/docviz_nosao.txt    P1 ablation
exaone/prompts/identities/docviz_notmg.txt    P1 ablation
exaone/prompts/style/docviz.txt           P1 docviz style
exaone/prompts/tools/generate_viz.txt     P1 tool description
exaone/sft_gen/docviz/__init__.py
exaone/sft_gen/docviz/query_schema.py     P2 Query + Intent dataclasses
exaone/sft_gen/docviz/quota.py            P2 source × challenge matrix
exaone/sft_gen/docviz/generate_queries.py P2 query gen (multi-host)
exaone/sft_gen/docviz/gold_schema.py      P3 Gold/Evidence/Fact/Table/Graph dataclasses
exaone/sft_gen/docviz/gold_builder.py     P3 gold extraction pipeline
exaone/sft_gen/docviz/prompts/query_gen/base.txt
exaone/sft_gen/docviz/prompts/gold_extraction/base.txt
scripts/parser_pilot.py                   P0 30-record pilot runner
configs/hosts-eval-qwen.yaml              Qwen 8-host pool config
configs/hosts-eval-deepseek.yaml          DeepSeek 2-host pool config
data/queries/pilot_50.jsonl               P2 output
data/gold/pilot_50.jsonl                  P3 output
outputs/v0.5_harness/P0_REPORT.md         P0 report
outputs/v0.5_harness/PILOT_STATUS.md      this file
```

Edited:
```
exaone/qa_modes.py    + docviz qa_mode + DOCVIZ_VARIANT env resolution
exaone/tools.py       + viz_tools group + _register_viz_tools()
.gitignore            + outputs/v0.5_harness exception + data/queries/gold exception
```

## Next session resume command

```bash
cd /ex_disk2/mhpark/poc/docviz
git pull origin feat/source-loaders   # ensure latest
# Continue with NEXT 1-6 from "Critical path" above.
```

Resume from this snapshot. All P0-P4 infrastructure validated.
