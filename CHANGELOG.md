# Changelog

## v0.3 — 2026-05-08 — Action-level amendment with cost reduction and domain expansion

### Six decisions (operational source: AMENDMENT_v0.3_ACTION_SPEC.md)

- **D1 In-domain test set 700 → 300 records** (60 per query type). Aligns with method-paper precedent (Plot2Code 132, MatPlotBench 100, ViviBench 101, SciDoc2 1,080). Saves ~$1,140 in Layer A API cost.
- **D2 Source domains 4 → 6**: add **GovReport** (ZeroSCROLLS standard, US Congressional reports) and **Technical Documentation** (default: Wikipedia long technical articles; alternates: Software docs, IETF RFC). Matches MMLongBench-Doc (NeurIPS 2024 D&B, 7 domains) and ZeroSCROLLS (7 domains) precedent. Defends against "why only 4 domains" reviewer attack.
- **D3 Adopt held-out evaluation paradigm framing**: T0 / FLAN / InstructBLIP / UnifiedVisual (EMNLP 2025 Main) cited; QG-MDV as in-domain primary, Text2Vis / ViviBench / Plot2Code as held-out tasks for zero-shot generalist evaluation.
- **D4 Remove Layer C** (within-method ablation S4_ZS / S4_FS / S4_SR / S4_Full): S4_ZS redundant with B5 Direct-LLM, S4_FS ill-fit for multi-doc. **Keep only S4_SelfRefine, promote to B7 baseline**. Saves ~$325 and removes redundancy.
- **D5 Viz subtypes 6 → 10**: add **chartjs_pie, chartjs_scatter, mermaid_sequenceDiagram, mermaid_classDiagram**. Matches ChartQA / VisJudge-Bench peer benchmark coverage.
- **D6 Replace calendar timeline with priority structure**: P0 anchors / P1 core experiments / P2 validation / P3 writing. Dependencies marked, parallelization opportunities noted.

### New baseline matrix (7 baselines + 3 specialists)

- B1 MatPlotAgent-adapted, B2 NVAGENT-adapted, B3 CoDA-adapted, B4 ViviDoc-style, B5 Direct-LLM, **B7 SelfRefine (NEW)**, B6 DocViz-Agent (Ours)
- Specialists on home turfs only: B8_Text2Vis-orig, B9_ViviDoc-orig, B10_MatPlotAgent

### Experiment matrix updated

- Layer A in-domain QG-MDV: 7 baselines × 5 LLMs × 300 records = 10,500 generations
- Layer B held-out external: Text2Vis 100 + ViviBench 101 + Plot2Code 50 (optional) = ~10,000 generations
- Layer D pillar ablation: 4 variants × 5 LLMs × 300 records = 6,000 generations
- Layer E human eval: 50 viz × 3 raters + 20 cross-judge
- Layer F failure mode: 30 manual sample
- **Total: ~26,580 generations + 190 human ratings, ~$1,500-1,800** (vs v0.2's ~$2,680)

### Files added in v0.3

- `AMENDMENT_v0.3_ACTION_SPEC.md` — operational source of truth for action-level execution (14 sections, includes priority structure, dependency graph, verification gates)
- `CHANGELOG.md` — updated with v0.3 entry

### Master spec sections to update (operationalized in v0.3 amendment)

- §1, §2, §3.6, §4, §5.1, §5.2, §5.3, §7, §9, §10, §14 (timeline → priority), §16, §18.1, §19

### Critical non-negotiables added in v0.3

- 6-domain coverage match MMLongBench-Doc precedent
- 10-viz-subtype enumeration with reasons
- Held-out paradigm framing with EMNLP-Main precedent (UnifiedVisual)
- **Image-level evaluation included (A5 axis + M5 CLIPScore)** — text-only evaluation is below precedent (SciDoc2 / MatPlotAgent / Plot2Code all use image-level)
- **Claude Sonnet primary via `claude -p` CLI for A5 image judging** — pay-per-call image API forbidden unless CLI unavailable

### D7 — Image-level Visual Quality Evaluation (added to v0.3 mid-cycle)

- **A5 axis** (Visual Rendering Quality, 3 sub-dim: readability / layout / overall) applied to 100-record sub-sample × 7 baselines × 5 LLMs = 3,500 image judge calls
- **M5 CLIPScore** (deterministic, text-image semantic alignment) applied to all viz across all settings
- **Judge config**: Claude Sonnet primary via `claude -p` CLI with time-sleep + retry (cost-efficient via subscription path); cross-judge GPT-4V or Gemini 3.0-preview (final choice TBD by human researcher before D7.3)
- **Precedent matching**: SciDoc2-MAF (GPT-4V Likert + CLIPScore), MatPlotAgent (GPT-4V eval), Plot2Code (GPT-4V overall rating), ChartLlama (GPT-4V quality)
- **Cost impact**: +$220 for A5 + cross-judge spot; $0 for M5 CLIPScore; **v0.3 total budget = ~$1,720-2,020 (still below v0.2's ~$2,680)**
- **New verification gates**: G9 (A5 judge sanity), G10 (CLIPScore sanity), G11 (A5 cross-judge κ ≥ 0.6)
- **New action items**: A9 (Claude Sonnet `claude -p` wrapper), A10 (CLIPScore pipeline), B4 (A5 image judge run), B5 (M5 CLIPScore run), C4 (A5 cross-judge agreement)

## v0.2 — 2026-05-08 — Q1-Q5 decisions reflected

### Resolved open questions (former §18.2)

- **Q1 Entry point + Return format**: External benchmark eval repos (vis-nlp/Text2Vis, thunlp/MatPlotAgent, TencentARC/Plot2Code) used as input/output format anchors. Internally, all baselines and DocViz-Agent emit a common `VizOutput` dataclass — see PAPER_MASTER_SPEC §3.6.
- **Q2 Web search**: Disabled in all paper experiments (`web_search=False`). Mentioned only in §8 Discussion as deployment-time future work. See PAPER_MASTER_SPEC §3.5 and §19.
- **Q3 Deterministic mode**: temperature=0, seed=42 default. Three-seed run (42, 43, 44) for all key result cells, mean ± std reported. See PAPER_MASTER_SPEC §3.5 and §19.
- **Q4 DSL-only output**: Pipeline runs in DSL-only mode (Chart.js JSON or Mermaid markdown). SVG / PNG / free-text excluded. Scope explicitly stated in PAPER_MASTER_SPEC §4.3 and §19.
- **Q5 Multi-doc bundle composition**: Source-internal only (HotpotQA / MultiNews / arXiv / 10-K each in separate bundles). No cross-source mixing. Per-source breakdown reported in §7. See PAPER_MASTER_SPEC §5.1 and §19.

### Spec sections updated

- §3.5 Implementation notes — added web search exclusion, deterministic settings, DSL-only enforcement
- §3.6 (new) Common output schema — `VizOutput` dataclass definition
- §4.3 (new) Output scope — explicit DSL-only limitation
- §5.1 — added Bundling principle, Bundle/Doc schema, per-source raw→bundle conversion logic
- §14 Week 1-2 — added external benchmark eval repo clones and source loader builds as Week 1 deliverables
- §18.1 — moved Q1-Q5 from open questions to confirmed
- §18.2 — narrowed remaining open questions to API budget, deadline, and ViviBench code release status
- §19 — added 4 new critical principles (DSL-only scope, source-internal bundles, web search disabled, three-seed reporting)

### Files

- `PAPER_MASTER_SPEC.md` — updated
- `CHANGELOG.md` — this file (new)
- Other files unchanged

## v0.1 — 2026-05-07 — Initial master spec

- 20-section paper master specification covering framing (Specialist vs Generalist), 5 contributions, 3 pipeline pillars (CIS / TMG / SAO), data setup (350 bundles, 700 queries, 150 gold), model pool (5 LLM + sanity), baseline matrix (B1-B6), evaluation framework (adapted RocketEval + 6-layer evidence chain), experiment matrix, success criteria, risk register, result scenarios, 11-12 week timeline, page allocation, reviewer attack defense
- Week 0 action guide (separate file)
- README, .gitignore, PR template, push instructions
