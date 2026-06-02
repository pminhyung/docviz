# P0 parser preflight — REPORT

**Date**: 2026-05-30
**Spec**: `docs/IMPLEMENTATION_GUIDE_v0.4.1.md` §7.3 + §14
**Gate**: `chartjs_success ≥ 0.85` AND `mermaid_success ≥ 0.85`
**Verdict**: **✅ PASS — proceed to P1**

---

## Implementation summary

New code (top-level, parallel to harness's `exaone/`):

| Path | Purpose | LOC |
|---|---|---|
| `code/__init__.py` | package marker | 0 |
| `code/metrics/__init__.py` | package docstring | 11 |
| `code/metrics/chart_metrics.py` | Chart.js DSL → `NormalizedTable(chart_type, columns, series, cells)` | 130 |
| `code/metrics/mermaid_metrics.py` | Mermaid DSL → `NormalizedGraph(kind, nodes, edges, extra_lines)` | 130 |
| `scripts/parser_pilot.py` | P0 preflight runner — stratified 30-record sample + per-family success rate | 175 |

**No external vendoring** for P0: the legacy `_legacy/code/judge/dsl_parser.py` regex logic was sufficient; both parsers reuse those patterns and add normalization to v0.4.1 dataclasses. **DiagramEval vendor (§7.2)** is deferred to P4 (production hardening) — pilot results show the regex-based path clears the gate on every paper-pool backbone, so vendor swap is a follow-up optimization, not a P0 blocker.

## Success criterion (per §7.3)

A parse is "successful" when the normalized object is non-None and:
- **Chart.js**: `chart_type` non-empty AND `cells` non-empty (a real row × col × value recoverable).
- **Mermaid**: `kind != "mermaid_unknown"` AND at least one node OR extra_line (for timeline/mindmap where node syntax is degenerate).

Stricter than "no exception thrown" — guards against parsers that swallow malformed DSL into empty placeholders.

## Headline result (paper-pool backbones)

| Backbone | n | chartjs | mermaid | gate |
|---|---|---|---|---|
| **Qwen3.5-397B (seed 42)** | 30 | **100.0 %** | **100.0 %** | ✅ PASS |
| Qwen3.5-397B (seed 43) | 30 | 93.3 % | 100.0 % | ✅ PASS |
| Qwen3.5-397B (seed 44) | 30 | 100.0 % | 100.0 % | ✅ PASS |
| **DeepSeek-V4-Flash (seed 42)** | 30 | **100.0 %** | **100.0 %** | ✅ PASS |
| Baselines mixed (B1-B4, S1, S7 over Qwen) | 30 | 100.0 % | 100.0 % | ✅ PASS |

**All paper-pool backbones (O1 Qwen + O2 DeepSeek) clear the gate at ≥ 86 %** — well above the 85 % threshold.

GPT-5-mini (C1) and Claude Opus 4.8 (C2) outputs do not yet exist; they are produced in P6 and will be re-tested at that time. Since the same DSL grammar is followed regardless of generator, regression is not expected.

## Out-of-pool stress test (non-blocking)

| Backbone | chartjs | mermaid | gate | note |
|---|---|---|---|---|
| Gemma4-31B (seed 42) | 86.7 % | 100 % | ✅ PASS | barely; 2× `zero_cells` failure |
| Gemma3-27B-it (seed 42) | 73.3 % | 100 % | ✗ FAIL | 4× `zero_cells` |

**Not a paper-pool concern** (both Gemmas were dropped from v0.4.1 backbone pool for capacity-related rule-following limits). Recorded only as an internal robustness note.

## Failure mode taxonomy (observed)

| Mode | Count | Diagnosis |
|---|---|---|
| `parse_returned_none` | 1 (Qwen seed 43, 1/15 chartjs) | malformed JSON beyond brace-repair recovery |
| `zero_cells` | 2 (Gemma4), 4 (Gemma3) | valid JSON but `datasets[*].data` empty or missing |
| `unknown_header` | 0 | (mermaid headers always recognized) |
| `no_structural_content` | 0 | (timeline/mindmap fallback always recovers extra_lines) |

For the paper-pool backbones, the only observed failure is one malformed-JSON case (3 % rate). DiagramEval vendor or a beefier JSON-repair pass would close this gap if needed; not necessary at the gate.

## Time spent

- Implementation (parser modules + pilot script): **~25 min**
- Stress test across 6 datasets: **~5 min**
- Reporting: **~10 min**
- **Total: ~40 min** (vs ≤5 h estimate; legacy parser reuse was the accelerant)

## Decision request

**Recommended**: PROCEED to **P1** (tool & prompt port — extend `generate_viz` to multi-artifact, write 4 ablation identity files, `EXAONE_V19_ADAPTER=1` everywhere).

Estimated P1 time: **1–1.5 days** (per IMPLEMENTATION_GUIDE_v0.4.1 §5 + §15.1). Gate: 5 sample records pass tool → render → sidecar chain end-to-end.

If you prefer to harden P0 first by vendoring DiagramEval (per spec §7.2) before proceeding:
- Effort: ~3 h additional (clone + license check + interface adaptation).
- Benefit: insurance against the 1 chartjs failure we saw on Qwen seed 43; otherwise parity with current regex parser.
- Recommendation: defer to P4 when we have the F1 metric tests pushing the parser harder.

---

## Output artifacts

- `outputs/v0.5_harness/p0_parser_pilot.json` — full per-record pilot result (gate input)
- This report
