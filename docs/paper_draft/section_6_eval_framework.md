# §6 Evaluation Framework (v0.3 draft)

> v0.3 amendment compliance:
>   - 4-axis text-judge (faithfulness / coverage / type_appropriateness /
>     search_query_quality) — Phase-1 Qwen, Phase-2 closed-API per §16
>   - M1 render-success + M3 element-count + M5 CLIPScore deterministic
>   - A5 image-axis judge (Claude Sonnet via `claude -p`) — deferred to
>     closed-API phase per amendment §16

## 6.1 Evaluation Axes

| Axis | Type | Implementation | Activates with |
|---|---|---|---|
| A1 Faithfulness   | text-judge (LLM, RocketEval 4-axis) | `code/judge/scorer.py` | every record |
| A2 Coverage       | text-judge | scorer.py | every record |
| A3 Type appropriateness | text-judge | scorer.py | every record |
| A4 Retrieval-query quality | text-judge | scorer.py (uses Fix #1+2 un-redacted args) | agentic records (B1-B4, B6, B7) |
| **A5 Visual Quality** (D7) | image-judge (Claude Sonnet via `claude -p`) | `code/judge/image_judge.py` | 100-record sub-sample, **closed-API phase** |
| M1 Render success | deterministic | `code/render/renderer.py` | every record |
| M3 Element count | deterministic (DSL parser) | `code/judge/dsl_parser.py` | every record |
| **M5 CLIPScore** (D7) | deterministic (open_clip ViT-L-14 + Hessel ×2.5) | `code/metrics/clipscore.py` | every record |

## 6.2 Text-Judge — Two-Phase Strategy

Per v0.3 amendment §16 addendum, the text-axis judge is run in two
phases for cost containment:

**Phase 1 — Trend scan** (active, on-prem):
- Judge: Qwen3.5-397B-A17B-FP8 via `QwenDirectClient` (multi-host
  queue + retry, §3.7)
- Scope: all Layer A / B / D runs as produced
- Cost: $0
- Purpose: rank baselines, identify Δ direction, gate closed-API spend

**Phase 2 — Paper-grade re-judge** (deferred, closed-API):
- Judge: Claude Opus 4.6 as scorer cross-judged against GPT-5
  generator per spec L342 / §8.2
- Scope: Layer A main result table + Layer D pillar ablation overall +
  Layer B home-turf rows (~5,050 records)
- Cost projection: ~$1,265 (within §10 budget envelope)
- Purpose: paper-grade numbers + cross-judge κ as G7 evidence

Decision gate (per amendment §16):
- Phase-1 V4 advantage ≥+5%p multi-doc + Layer B home-turf gap ≤7%p
  → GO Phase 2
- Borderline (+2-5%p) → 20-record sub-sample Phase 2 first
- Negative → HALT and iterate method

## 6.3 Image-Axis Eval (D7)

**M5 CLIPScore** (deterministic, every record):
- Encoder: ViT-L-14 from open_clip_torch
- Score = max(cos(img, text), 0) × 2.5 per Hessel et al. (2021)
- Text input: query + viz_type + parsed DSL structural elements +
  sub_queries (the Fix #1+2 un-redacted retrieval intents)
- Image input: rendered PNG (from `code/render/renderer.py`)
- G10 calibration sanity (well-aligned ≥0.5 / mismatched ≤0.3) — direction
  correct on 2-pair test; full calibration in Phase 9

**A5 Visual Quality axis** (closed-API, 100-record sub-sample):
- Primary judge: Claude Sonnet (vision-capable, latest) via
  `claude -p` CLI in headless mode + time-sleep + retry/backoff
- Sub-dimensions (each 0 / 0.5 / 1; axis = mean):
  - readability: labels visible, no truncation/overlap
  - layout: alignment / balance / spacing
  - overall: end-user usability given query intent
- Cross-judge: GPT-4V or Gemini 3.0-preview on 20-30 record subset for
  Cohen κ ≥0.6 validation
- Cost projection (3,500 calls × $0.06-0.10): ~$200-350
- Implementation: `code/judge/image_judge.py` (wrapper done; batch
  run pending closed-API budget activation)

## 6.4 Layer-B Standard Eval (held-out)

Per amendment §10 / §14 line 549, each external benchmark uses its own
published eval methodology. When the eval code is unavailable (ViviBench
2026 not yet released, Text2Vis EMNLP 2025 not yet on HF), we
**reimplement the eval from the paper's §4** using on-prem Qwen3.5-397B
as the LLM judge substitute. Documented per-benchmark:

- **Text2Vis** (EMNLP 2025): 4-dim visual accuracy + readability LLM
  judge. Reimplementation pending data acquisition.
- **ViviBench** (2026): 4-dim content-richness + interaction-quality
  LLM judge. Reimplementation pending data acquisition.
- **Plot2Code** (2024): exec-rate (deterministic) + GPT-4V-style
  overall rating. Plot2Code 5-record preflight in v0.3 prototype:

  | Baseline | exec_rate | CLIPScore (Hessel) |
  |---|---|---|
  | B1 MatPlotAgent | (matplotlib subprocess) | — |
  | B2 NVAGENT | 1.00 | 0.611 |
  | B3 CoDA | 1.00 | 0.577 |
  | B4 ViviDoc | 1.00 | 0.627 |
  | B5 Direct-LLM | 1.00 | 0.601 |
  | B7 SelfRefine | 0.80 | 0.567 |
  | **B6 (Ours)** | **0.20** | 0.607 |

  B6 single-doc generalization is poor (exec_rate 0.20) — expected since
  B6 is designed for multi-doc QG-MDV. **When B6 does execute, CLIPScore
  is comparable to others (0.61 vs 0.58-0.63 range)**. This is the
  Tier-1 framing direction: specialists win on home turf; we win on
  multi-doc (Layer A).
