# §1 Introduction (v0.3 draft)

> v0.3 amendment compliance:
>   - D3 held-out paradigm framing (T0 / FLAN / InstructBLIP /
>     UnifiedVisual EMNLP 2025 Main precedent)
>   - 6-domain coverage rationale
>   - Image-modal coverage commitment (A5 + M5)

## 1.1 Problem Setting

Query-Grounded Multi-Document Visualization (QG-MDV) is the task of
producing a single visualization that answers a user query using only
facts present in a bundle of 2-N source documents. The task arises
whenever a user asks a question over a heterogeneous information
source — a multi-paper literature review, a 10-K's MD&A + Risk
sections, a multi-cluster news digest — and expects an *answer-shaped*
visualization, not a text summary.

Prior work fragments QG-MDV's challenge across:

- **Visualization generation** (MatPlotAgent, ChartLlama, Plot2Code,
  ChartX, ChartMimic, Text2Vis, ViviBench) assumes single-document or
  table-shaped input.
- **Multi-document reasoning** (MMLongBench-Doc, ZeroSCROLLS,
  LongBench) targets text-shaped answers.
- **Generalist agentic methods** (InstructBLIP, UnifiedVisual) cover
  multi-modal generation but not the multi-doc+visualization
  intersection.

QG-MDV at this intersection has been under-evaluated. We introduce a
training-free generalist pipeline that handles QG-MDV in 6 content
domains and 10 visualization subtypes, with both text-axis and
image-axis evaluation.

## 1.2 Held-Out Generalist Evaluation Paradigm

Following the held-out evaluation paradigm of unified multi-task models
(T0, Sanh et al. 2021; FLAN, Wei et al. 2022; InstructBLIP, Dai et al.
2023; **UnifiedVisual**, EMNLP 2025 Main), we treat Text2Vis,
ViviBench, and Plot2Code as **held-out** tasks evaluating zero-shot
generalization. QG-MDV serves as both a new task definition and our
in-domain primary evaluation.

Unlike instruction-tuned generalists, DocViz-Agent is a
**training-free generalist** achieved through prompting and tool
composition. This removes the training-domain bias that confounds
InstructBLIP-style evaluations: any cross-task gap reflects method
shape, not training-data leakage.

## 1.3 Contributions

1. **QG-MDV task and dataset (§3, §5)** — a 268-record (300 target)
   query-grounded multi-document visualization benchmark spanning 6
   content domains (HotpotQA, MultiNews, arXiv, EDGAR 10-K, GovReport,
   Technical Docs) and 10 visualization subtypes.

2. **DocViz-Agent (B6)** — a 3-pillar training-free pipeline:
   - **CIS** (Contextual Input Selection): doc-step summary +
     bundle-aware retrieval (`search` / `ReadFullDocument`)
   - **TMG** (Type-Mapped Generation): per-query-type viz routing via
     a `generate_viz` tool with 10 type-specific exemplars
   - **SAO** (Source-Attributed Output): per-element source binding

3. **Same-model controlled cross-method comparison (§7)** — 7 baselines
   (B1 MatPlotAgent, B2 NVAGENT, B3 CoDA, B4 ViviDoc-style, B5
   Direct-LLM, B7 SelfRefine, B6 Ours) all running on Qwen3.5-397B
   on-prem, isolating method-shape contribution from model-capability
   variation. Layer A in-domain QG-MDV + Layer B held-out (Text2Vis /
   ViviBench / Plot2Code) + Layer D pillar ablation.

4. **Two-axis evaluation (§6)** — text-axis 4-axis checklist judging
   (faithfulness / coverage / type / search_query_quality) + image-axis
   A5 visual quality (Claude Sonnet) + M5 CLIPScore deterministic
   metric. Cost-efficient two-phase strategy (Qwen trend → closed-API
   headline).

## 1.4 Headline Result

(numbers populate after Phase 7 Layer A batch + Phase 9 trend analysis)

> *"First training-free generalist pipeline for query-grounded
> multi-document visualization across 6 content domains and 10
> visualization subtypes. Competitive with specialist methods on their
> home turfs (within 5-7%p) and substantially superior in the
> previously-uncovered multi-document setting (+X%p), with the best
> cross-task average across 4 evaluation settings, evaluated via both
> text-axis checklist judging (4 axes) and image-axis quality
> assessment (A5 vision judge + M5 CLIPScore)."*
