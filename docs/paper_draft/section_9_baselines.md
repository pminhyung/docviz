# §9 Baseline Matrix (v0.3 draft)

> Amendment §9 line 425 — 7 baselines, removed Layer C, added B7 SelfRefine.

## 9.1 Final 7-Baseline Set

| ID | Name | Method shape | Citation |
|---|---|---|---|
| B1 | MatPlotAgent-adapted | 2-LLM agent: query expansion → plot agent; outputs Python matplotlib code that is subprocess-executed to a PNG | Yang et al., ACL Findings 2024 |
| B2 | NVAGENT-adapted | 2-LLM agent: pseudo-table extraction → viz spec; outputs Chart.js / Mermaid DSL | Wu et al., ACL 2025 |
| B3 | CoDA-adapted | 2-LLM agent: analyzer agent (corpus exploration + angle selection) → viz spec | 2025 |
| B4 | ViviDoc-style | 2-LLM agent: planner (topic + sections + primary_viz) → executor (DSL) | ViviBench/ViviDoc, 2026 |
| B5 | Direct-LLM | Single LLM call: concat docs + query → JSON {viz_type, viz_dsl} | Standard |
| **B7** (NEW v0.3) | SelfRefine | 3-LLM call: initial generation → self-critique → refine. Madaan et al. protocol | Madaan et al., NeurIPS 2023 |
| **B6** | DocViz-Agent (Ours) | Agentic 3-pillar pipeline (CIS + TMG + SAO), 4-step agent loop (doc-summary → search → generate_viz → final_answer) | Ours |

All 7 baselines run on the SAME LLM (Qwen3.5-397B-A17B-FP8 on-prem) to
control for model variance in this prototype. Week-1 scales to 5 LLMs
per amendment §10.

## 9.2 On-Prem Adaptation (no closed-API)

B1-B4 are 2024-2026 papers whose published implementations target
closed-API generators (GPT-3.5 / GPT-4 default). v0.3 amendment §9
"adapted" notation indicates we wrap the input format and redirect each
adapter's `openai.OpenAI` client to our on-prem Qwen3.5-397B vLLM
cluster via `QwenDirectClient` (multi-host queue + retry; §3.7).

This yields **same-model controlled comparison** — a strength for the
paper's framing because it isolates the *method shape* (single-call vs
2-agent vs 3-pillar) from *model capability variation*. Week-1 scales
to multi-model.

Implementation tree:

```
code/pipelines/
├── b1_matplotagent.py    # B1 MatPlotAgent-adapted
├── b2_nvagent.py         # B2 NVAGENT-adapted
├── b3_coda.py            # B3 CoDA-adapted
├── b4_vividoc.py         # B4 ViviDoc-style
├── s1_direct.py          # B5 Direct-LLM
├── s7_self_refine.py     # B7 SelfRefine
└── s4_agentic_tmg.py     # B6 DocViz-Agent (mode='v4_consolidated')
```

## 9.3 Pre-Run Sanity (5-record preflight)

Each baseline was preflight-tested on Plot2Code 5 records before any
Layer A batch. Result (§6.4):

| Baseline | exec_rate | CLIPScore | Status |
|---|---|---|---|
| B1 MatPlotAgent | (matplotlib path) | — | render via subprocess ✓ |
| B2 NVAGENT | 1.0 | 0.611 | ✓ |
| B3 CoDA | 1.0 | 0.577 | ✓ |
| B4 ViviDoc | 1.0 | 0.627 | ✓ |
| B5 Direct-LLM | 1.0 | 0.601 | ✓ |
| B7 SelfRefine | 0.80 | 0.567 | ✓ |
| B6 (Ours) | 0.20 | 0.607 | held-out generalization is poor (expected) |

All 7 adapters integrate cleanly with `code.render` and
`code.judge.scorer`. Layer A batch is ready to launch once D1 dataset
finalizes (Phase 1 in progress).
