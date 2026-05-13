# §2 Related Work (v0.3 draft)

> v0.3 amendment compliance:
>   - 5-paradigm reference table (ChartLlama / ChartX / InstructBLIP /
>     METAL / UnifiedVisual)
>   - MMLongBench-Doc precedent for 6-domain coverage
>   - SciDoc2 / MatPlotAgent / Plot2Code precedent for image-level eval

## 2.1 Visualization Generation Methods

QG-MDV sits between visualization generation and multi-document
question answering. Prior visualization-generation work targets either
chart-shaped data or single-document instructions:

| Paradigm | Representative work | Input | Output | Multi-doc? |
|---|---|---|---|---|
| Direct LLM | ChartLlama (CVPR 2024) | table + query | Chart.js | × |
| Agentic codegen | MatPlotAgent (ACL Findings 2024) | NL instruction | Python matplotlib | × |
| Tabular-VL | NVAGENT (ACL 2025) | table-like text | Vega-Lite VQL | × |
| Data-analyst agent | CoDA (2025) | text dataset | analyzer + spec | × (CSV-shaped) |
| Document-viz | ViviDoc (2026) | document | interactive viz | × |
| Instruction-tuned generalist | UnifiedVisual (EMNLP 2025 Main) | multi-task | unified output | partial |
| **QG-MDV (Ours)** | DocViz-Agent | **query + multi-doc bundle** | DSL + image | **✓** |

Our method targets the multi-document setting explicitly — the 6
source domains in §5.1 produce bundles with 2-4 distinct documents per
query, and the 3-pillar pipeline (§3.5) is designed around this
heterogeneous-input structure.

## 2.2 Multi-Document Benchmarks

QG-MDV's multi-document framing draws on the long-document QA
literature:

| Benchmark | Year | Domain count | Multi-doc per record? | Visualization? |
|---|---|---|---|---|
| HotpotQA | 2018 | encyclopedic | 2-3 supporting paragraphs | text |
| MultiNews | 2019 | news | 2-5 articles per cluster | text |
| LongBench | 2023 | multi | varies | text |
| ZeroSCROLLS | 2023 | **7 domains** | varies | text |
| MMLongBench-Doc | NeurIPS 2024 D&B | **7 domains** | single long doc | text |
| InfiniteBench | 2024 | multi | varies | text |
| **QG-MDV (Ours)** | 2026 | **6 domains** | **✓ 2-4 per record** | **✓ (10 viz subtypes)** |

We use HotpotQA / MultiNews / arXiv / 10-K / GovReport / Tech Docs as
source domains (§5.1). The 6-domain count is calibrated to ZeroSCROLLS
and MMLongBench-Doc precedent (per amendment D2).

## 2.3 Image-Level Visualization Evaluation

Per amendment §7.0 / §16 R3, image-level visualization evaluation is
the de facto standard in 9 of 10 surveyed peer benchmarks:

| Paper | Venue | Image-level eval |
|---|---|---|
| SciDoc2-MAF | EMNLP Findings 2024 | GPT-4V Layout/Faithfulness Likert + CLIPScore |
| MatPlotAgent | ACL Findings 2024 | GPT-4V automatic evaluation |
| Plot2Code | 2024 | GPT-4V overall rating |
| ChartLlama | CVPR 2024 Highlight | GPT-4V quality assessment |
| ChartMimic | NeurIPS 2024 | image fidelity / visual similarity |
| METAL | ACL 2025 | visual critique agent |
| Text2Vis | EMNLP 2025 Main | visual accuracy + readability |
| ViviBench | 2026 | LLM-as-judge content + interaction (image) |
| VisJudge-Bench | ICLR 2026 | 6-dimensional visual quality |
| DiagramEval | EMNLP 2025 Main | partial (text-graph oriented) |

We include both **A5** vision-judge (Claude Sonnet via `claude -p`) on
a 100-record sub-sample and **M5** CLIPScore deterministic on every
record. The two-axis (text + image) protocol matches the peer-paper
precedent.

## 2.4 Held-Out Generalist Evaluation

Per amendment D3, we adopt the held-out evaluation paradigm of unified
multi-task models:

| Paradigm | Representative | Trains across tasks | Held-out eval |
|---|---|---|---|
| T0 | Sanh et al. 2021 | ✓ | ✓ |
| FLAN | Wei et al. 2022 | ✓ | ✓ |
| InstructBLIP | Dai et al. 2023 | ✓ | ✓ |
| UnifiedVisual | EMNLP 2025 Main | ✓ | ✓ |
| **DocViz-Agent (Ours)** | this work | **× (training-free)** | ✓ |

Unlike T0/FLAN/InstructBLIP/UnifiedVisual, our method is
**training-free** — generalization comes from prompting and tool
composition, not multi-task fine-tuning. Held-out evaluation on
Text2Vis / ViviBench / Plot2Code measures zero-shot transfer
explicitly.

## 2.5 Two-Phase Judge Strategy

The cost-efficient two-phase judge strategy (amendment §16 addendum;
paper §6.2):
- Phase 1: on-prem Qwen3.5-397B-A17B-FP8 (deterministic at T=0) for
  trend signal
- Phase 2: Claude Opus 4.6 scorer + GPT-5 cross-judge for paper-grade
  numbers on headline cells

This protocol balances cost containment (Phase 1 free, Phase 2 ~$1,265)
against paper-grade rigor (Phase 2 establishes cross-judge κ as
validity evidence). Precedent: SciDoc2-MAF and Text2Vis report both
self-judge and cross-judge κ; we extend with explicit cost-tier
separation.
