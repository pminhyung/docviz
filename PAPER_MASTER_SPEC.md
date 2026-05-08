# DocViz-Agent — Final Master Specification for Research Agent

> **This document is the operational source of truth for the entire project.**
> Last updated: 2026-05-07
> Target submission: EMNLP 2026 (main attempt → findings auto-fallback)
> Project handle: docviz

---

## 0. PROJECT IDENTITY

### 0.1 Brand

> **DocViz-Agent: First Generalist Pipeline for Query-Grounded Multi-Document Visualization**

### 0.2 One-paragraph positioning

We present DocViz-Agent, the first generalist pipeline for query-grounded document visualization, supporting charts, diagrams, and mindmaps in both single-context and multi-document settings. While each prior method (Text2Vis-original, ViviDoc, MatPlotAgent, NVAGENT, CoDA) achieves strong performance on its target benchmark by design, none generalizes across settings. DocViz-Agent achieves (a) performance within 5–7%p of each specialist on their home turfs (Text2Vis, ViviBench, Plot2Code), (b) substantial advantage (+8%p+) in the previously-uncovered multi-document query-grounded setting (QG-MDV, our new benchmark), and (c) the best cross-task average across 4 settings — establishing the value of unified visualization generation. We further provide a doc-grounded checklist evaluation framework validated against human ratings (r ≥ 0.65) and reveal a systematic multi-document grounding gap that persists across all pipelines.

### 0.3 Target outcomes

- **Primary**: EMNLP 2026 main accept (target probability 30–45%)
- **Secondary**: EMNLP 2026 Findings auto-fallback (target probability ≥ 70%)
- **Tertiary**: Industry track if production deployment evidence emerges

---

## 1. STRATEGIC STANCE — Specialist vs Generalist

### 1.1 The fundamental positioning

We do NOT claim SOTA on any external benchmark where a specialist exists. We claim:
1. **Competitive on home turfs**: within 5–7%p of each specialist on their target benchmark
2. **Substantial win on uncovered turf**: +8%p on QG-MDV multi-doc setting
3. **Best cross-task average**: average across 4 settings exceeds best specialist by 8%p+

This positions DocViz-Agent as a generalist analogous to T0, FLAN, Galactica, InstructBLIP — accepted contribution category in ML/NLP venues.

### 1.2 What we never claim

- "SOTA on Text2Vis" — Text2Vis-original was designed for it
- "SOTA on ViviBench" — ViviDoc was designed for it
- "SOTA on Plot2Code" — MatPlotAgent was designed for it
- "Beats every baseline on every metric" — overpromise, reviewer-dismissed

### 1.3 What we always claim

- "First unified pipeline addressing multi-doc + query + multi-viz combined setting"
- "Competitive generalist on specialist home turfs"
- "Substantially superior on multi-doc query-grounded setting"
- "Best cross-task average performance"
- "Reveals fundamental multi-doc grounding gap that persists across all pipelines"

---

## 2. CONTRIBUTIONS (5)

### 2.1 Contribution structure

| # | Contribution | Form | Paper section |
|---|---|---|---|
| C1 | First generalist pipeline (DocViz-Agent) for multi-doc query-grounded multi-viz generation, built on three design pillars (CIS, TMG, SAO) | Method | §4 (1.50 page) |
| C2 | QG-MDV task formalization + benchmark (350 multi-doc bundles, 700 queries, 5 query-type taxonomy, 150 human-verified gold) | Task + Resource | §3 (0.75 page) + §5 (0.75 page) |
| C3 | Doc-grounded checklist evaluation framework (adapted RocketEval, 4 axes, validated against human r ≥ 0.65) | Eval infrastructure | §6 (0.5 page) |
| C4 | Setting-stratified comparison across 4 benchmarks: Tier 1 (home turf draws), Tier 2 (our turf wins), Tier 3 (cross-task average best) | Empirical study | §7 (2.0 page) |
| C5 | Empirical finding: multi-doc grounding gap and long-context paradox persist across all pipelines and LLMs | Diagnostic finding | §8 (0.75 page) |

### 2.2 Why this contribution structure passes EMNLP main bar

- C1 (method) addresses a real gap (no prior unified multi-doc viz pipeline exists)
- C2 (task + benchmark) is community resource
- C4 (3-tier comparison) is novel evaluation paradigm + honest framing
- C5 (finding) provides diagnostic value beyond pipeline performance

This is the ChartMuseum + InstructBLIP hybrid model — task novelty + method + benchmark + finding combined.

---

## 3. PIPELINE DESIGN — Three Pillars (DocViz-Agent)

### 3.1 Pillar 1: Cross-doc Iterative Search (CIS)

**Mechanism**: Iterative search-query-driven retrieval across all source documents until information sufficiency is reached.

**Algorithmic outline**:
- Initialize state with empty retrieved chunks list and empty synthesized context
- For each step (max 5 steps):
  - Generate next sub-query from (original query, current state) using LLM
  - Retrieve top-k chunks across all source documents (cross-doc retrieval, not within single doc)
  - Append (sub-query, retrieved chunks, source attribution) to state
  - Update synthesized context
  - Check sufficiency via LLM judge — if sufficient, exit
- Output: state with cumulative retrievals + sub-query trace

**Why this differentiates from baselines**:
- B1 MatPlotAgent: single-shot, no retrieval over multiple docs
- B2 NVAGENT: assumes data table input
- B3 CoDA: structured dataset assumption
- B4 ViviDoc: topic-driven, no doc retrieval
- B5 Direct-LLM: concatenates all docs, no retrieval

**Ablation** ("- CIS"): Replace iterative search with single-shot retrieval (baseline B5 equivalent). Expected drop: -5~10%p on multi-doc faithfulness.

### 3.2 Pillar 2: Type-aware Multi-Viz Generation (TMG)

**Mechanism**: Query-type classifier routes to appropriate visualization type.

**Mapping table**:
- Quantitative → Chart.js bar/line
- Relational → Mermaid flowchart
- Temporal → Mermaid timeline / Chart.js line
- Hierarchical → Mermaid mindmap
- Comparative → Mermaid flowchart / Chart.js grouped bar

**Why this differentiates from baselines**:
- B1, B2, B3: chart-only output
- B4: mindmap-style only
- B5: no type-aware routing
- Ours: 5 query types × 3 viz primitives = unified coverage

**Ablation** ("- TMG"): Use fixed viz type (e.g., always flowchart). Expected drop: -3~6%p on type-appropriateness axis.

### 3.3 Pillar 3: Source-Attributed DSL Output (SAO)

**Mechanism**: Each visual element (node, edge, data point) carries metadata pointing to source document and chunk.

**Output schema**:
- viz_type: one of {chartjs_bar, chartjs_line, chartjs_grouped_bar, mermaid_flowchart, mermaid_timeline, mermaid_mindmap}
- viz_dsl: rendered DSL code (Chart.js JSON or Mermaid markdown)
- source_attribution: list of {element_id, source_doc_id, chunk_id, evidence_span} entries

**Why this differentiates**:
- All 5 baselines lack source attribution metadata
- Enables automatic cross-doc claim verification (deterministic metric M3)
- Supports post-hoc editing and traceability (industry deployment angle)

**Ablation** ("- SAO"): Remove source attribution. Expected drop: -10~15%p on cross-doc claim attribution accuracy (I2).

### 3.4 Pillar interaction

The three pillars compose as follows: CIS produces source-tagged retrieval chunks; TMG decides viz type from query; SAO grounds each visual element back to source documents. Each pillar is necessary; the full ablation removing all three drops to baseline B5 Direct-LLM level (-15.6%p average).

### 3.5 Implementation notes for the research agent

- The agentic loop in CIS already exists in the user's working pipeline. Wire that as Pillar 1.
- TMG requires building a query-type classifier (5-class). Use few-shot LLM classification with the 5-type taxonomy.
- SAO requires augmenting the existing pipeline to emit source attribution metadata alongside the DSL output. This may require pipeline modification — preserve the original pipeline's behavior and add attribution as a side channel.
- Multi-document input format: standardize to a flat list of dicts with fields {doc_id, page_id, content}. This aligns with standard multi-doc QA benchmarks (HotpotQA, MultiNews) and simplifies downstream tooling.
- Web search tool is to be removed from the agent's toolset for the paper experiments. Keep doc-only retrieval to ensure fair comparison and reproducibility. Web search may be added back as an ablation if time permits.

---

## 4. TASK FORMALIZATION (QG-MDV)

### 4.1 Definition

Given a user query Q (natural language) and a multi-document corpus D = {D_1, ..., D_n} (n ≥ 1), generate a visualization V such that:
- V is expressed in a deterministic DSL (Chart.js JSON or Mermaid markdown)
- Every visual claim in V is grounded in at least one document in D
- V addresses the information needs implied by Q
- V uses a visualization type appropriate for the information being conveyed

### 4.2 Five query-type taxonomy

- **Quantitative**: Numerical comparison or trend analysis
- **Relational**: Entity-entity dependency, causal, or interaction relations
- **Temporal**: Time-ordered events or sequences
- **Hierarchical**: Categorization, taxonomy, or compositional structure
- **Comparative**: Multi-entity feature comparison

Each query is classified into exactly one type. Some queries naturally fit multiple types — assign the dominant one.

---

## 5. DATA SETUP

### 5.1 Document corpus (350 multi-doc bundles)

- **HotpotQA**: 100 bundles, each = 1 question + 2-3 supporting Wikipedia paragraphs. Source: HotpotQA dev distractor set. Query type focus: Relational, Comparative.
- **MultiNews**: 90 bundles, each = cluster of 2-5 news articles. Source: MultiNews validation split. Query type focus: Temporal, Comparative.
- **arXiv**: 80 bundles, each = 3-5 paper abstracts from same conference track. Source: arXiv API for last 24 months in NLP/ML topics. Query type focus: Hierarchical, Comparative.
- **EDGAR 10-K**: 80 bundles, each = 1 company's Item-7 (MD&A) + Item-7A (Risk Factors). Source: SEC EDGAR for top 80 SP500 companies. Query type focus: Quantitative, Temporal.

Total: 350 bundles, average 3-4 docs per bundle, total tokens per bundle 15-50K.

### 5.2 Query generation (700 queries total)

Per bundle, generate 2 queries (one for each of 2 type assignments). Type assignment by source:
- HotpotQA: {Relational, Comparative}
- MultiNews: {Temporal, Comparative}
- arXiv: {Hierarchical, Comparative}
- 10-K: {Quantitative, Temporal}

Generation protocol:
- Use GPT-4o-mini (cost-efficient) for query generation with explicit type prompting
- Provide bundle content as context, request a natural query of specified type
- Filter: query length ≤ 25 words, references at least one bundle entity
- Cross-validate naturalness with Claude Opus 4.6 on 50 sample (Spearman r ≥ 0.7 with GPT-4o-mini ratings expected)

### 5.3 Gold subset (150 queries, human-verified)

Subset of 150 queries (30 per type) sent to Prolific for verification:
- Naturalness rating (5-point Likert): mean ≥ 4.0
- Answerability binary (does the query have a determinate answer in the bundle?): ≥ 95% yes
- 3 raters per query, inter-rater Cohen's κ ≥ 0.6

Estimated cost: ~$280 ($120 naturalness + $80 answerability + $80 buffer).

### 5.4 External benchmarks (for Tier 1 home-turf evaluation)

- **Text2Vis (EMNLP 2025)**: 100-sample subset (random with seed). Evaluation metric: Text2Vis published 4-axis (answer correctness, chart correctness, chart readability, visual accuracy).
- **ViviBench (2026)**: 101 topics (full set). Evaluation metric: ViviBench published 4-dim framework with human r > 0.84.
- **Plot2Code (2024)** (optional, time-permitting): 50-sample subset. Evaluation metric: Plot2Code text similarity + execution accuracy.

For each external benchmark, adapt our DocViz-Agent input by treating the benchmark's input (e.g., text + table for Text2Vis, topic for ViviBench) as a single-document case. This is the special case n=1 of our QG-MDV task.

---

## 6. MODEL POOL (5 LLM + 1 sanity)

| Model | Tier | Use | Note |
|---|---|---|---|
| GPT-5 | Closed flagship | Primary backbone for all baselines + DocViz-Agent | Latest as of submission; verify version at experiment runtime |
| Claude Opus 4.6 | Closed flagship | Primary backbone + cross-judge for evaluation | Latest |
| Gemini 2.5 Pro | Closed flagship | Vendor diversity + Tier 1 robustness | Latest |
| Qwen3-Coder-30B-A3B | Open large | DSL fluency + open-source reproducibility | Latest open frontier with code/DSL strength |
| DeepSeek V3.5 | Open frontier | Cost-efficient baseline + open-source diversity | Latest |
| Template-based heuristic | Sanity floor | Non-LLM baseline (e.g., entity-frequency → bar chart) | Demonstrates task is non-trivial |

All models are used for both baseline strategies (B1-B5) and DocViz-Agent (B6) where applicable. Each strategy × LLM combination is a separate experimental cell.

Model versions and pricing must be verified via web search at experiment runtime; this document does not lock specific versions.

---

## 7. BASELINE MATRIX (6 + 1 external)

| ID | Name | Adaptation | Coverage |
|---|---|---|---|
| B1 | MatPlotAgent-adapted | Concat all docs into context, pass with query to MatPlotAgent | All 4 settings |
| B2 | NVAGENT-adapted | Concat docs, extract pseudo-table, pass to NVAGENT | All 4 settings |
| B3 | CoDA-adapted | Treat docs as text dataset, run CoDA's analyzer agent | All 4 settings |
| B4 | ViviDoc-style | Use query as topic, pass to ViviDoc-style planner-executor | All 4 settings |
| B5 | Direct-LLM | Concat docs + query → LLM → DSL output (no agentic loop) | All 4 settings |
| B6 | DocViz-Agent (ours) | Full pipeline with CIS + TMG + SAO | All 4 settings |
| B7 | Text2Vis-original (specialist) | Run Text2Vis-original method on Text2Vis benchmark only | Text2Vis only |
| B8 | ViviDoc-original (specialist) | Run ViviDoc-original method on ViviBench only | ViviBench only |
| B9 | MatPlotAgent-original (specialist) | Run MatPlotAgent on Plot2Code only | Plot2Code only |

Notes:
- B7, B8, B9 are the original specialist methods on their home turfs only. They serve as Tier 1 reference for the "competitive within 5-7%p" claim.
- B1-B6 run on all 4 settings (QG-MDV + Text2Vis + ViviBench + Plot2Code).
- All adaptations should be thin wrappers around the original method's open-source code; do not re-implement.

---

## 8. EVALUATION FRAMEWORK

### 8.1 Primary metric: Adapted RocketEval Checklist Judge

Per-instance dynamic checklist generation followed by item-by-item scoring across 4 axes:
- **A1 Faithfulness**: each visual claim has support in source documents
- **A2 Coverage**: query's information needs are addressed by the visualization
- **A3 Type Appropriateness**: visualization type fits the query type and content
- **A4 Search Query Quality**: applies only to agentic strategies (B6) — sub-query trace quality

Checklist generation: 10-14 yes/no questions per instance, distributed across 4 axes (e.g., 4-3-2-3).
Scoring: each item scored as YES (1.0) / PARTIAL (0.5) / NO (0.0).
Per-axis score: average of axis items.

### 8.2 Cross-judge protocol

- Checklist generator: GPT-5 (default)
- Scorer: Claude Opus 4.6 (cross-model to avoid self-bias)
- Cross-judge agreement validation: 200 viz × 4 axis × 2 judges, target Cohen's κ ≥ 0.70

### 8.3 Six-layer evidence chain (anchors)

| Layer | Mechanism | Validation target |
|---|---|---|
| 1. Self-built primary | QG-MDV checklist judge results | DocViz-Agent +8%p over best non-ours baseline on multi-doc setting |
| 2. Human anchor | 50 viz × 3 Prolific × 4 axis = 600 ratings | Spearman r ≥ 0.65 between judge and human |
| 3. Deterministic anchor | M1 render success, M2 numeric exactness, M3 entity coverage, M4 structural validity | Cross-rank Spearman ≥ 0.5 with judge |
| 4. Reverse-direction QA | GPT-5 answers query using only the generated viz; accuracy measured | DocViz-Agent viz +5-12%p useful vs baselines |
| 5. Replicate existing finding | ChartMuseum-style visual reasoning drop reproduced in our framework | drop ≥ 30% on visual subset |
| 6. External published benchmark | Text2Vis 4-axis + ViviBench 4-dim + (optional) Plot2Code metrics | Within 5-7%p of specialist on each home turf |

---

## 9. EXPERIMENT MATRIX

### 9.1 Main Result Table (Setting × Baseline × Model)

Rows: 4 settings (QG-MDV, Text2Vis, ViviBench, Plot2Code-optional)
Columns: 6 baselines (B1-B6) on each setting + B7/B8/B9 specialists on respective home turfs
Sub-columns per cell: 5 LLMs averaged + std

Total cells (excluding specialist rows):
- 4 settings × 6 baselines × 5 LLMs = 120 cells
- + Tier 1 specialist columns: 3 (B7 Text2Vis, B8 ViviBench, B9 Plot2Code)
- + sanity floor (Template) on QG-MDV: 1 row

For QG-MDV: 700 queries × 6 baselines × 5 LLMs = 21,000 generations
For Text2Vis: 100 samples × 6 baselines × 5 LLMs = 3,000 generations
For ViviBench: 101 samples × 6 baselines × 5 LLMs = 3,030 generations
For Plot2Code (optional): 50 samples × 6 baselines × 5 LLMs = 1,500 generations

Grand total: ~28,500 generations.

### 9.2 Multi-doc Scaling Experiment

For QG-MDV setting only:
- Doc count variations: 1, 2, 3, 5 docs (subset to bundles where original count ≥ 5)
- 5 LLMs × 6 baselines × 4 doc-counts × 100 sample subset = 12,000 generations
- Plot: faithfulness vs doc count, separate curves per baseline

### 9.3 Long-context Paradox Experiment

For QG-MDV bundles with full doc length ≥ 32K tokens:
- Context lengths: 8K (truncated), 32K (truncated), 128K (full or near-full)
- 5 LLMs × 6 baselines × 3 lengths × 50 sample subset = 4,500 generations
- Plot: faithfulness vs context length

### 9.4 Ablation Study (DocViz-Agent only)

- Full DocViz-Agent (B6)
- - CIS (replace with single-shot retrieval)
- - TMG (replace with fixed viz type)
- - SAO (remove source attribution)
- - All three (degenerate to B5 Direct-LLM)

5 LLMs × 5 ablation variants × 200 query subset (balanced across types) = 5,000 generations.

Expected drops:
- - CIS: -5~10%p on multi-doc faithfulness
- - TMG: -3~6%p on type-appropriateness
- - SAO: -10~15%p on cross-doc attribution
- - All: -15~20%p (back to B5 baseline level)

### 9.5 Failure Mode Analysis

Manual analysis of 30 sample failures from B6 on QG-MDV (10 from each query type, weighted toward worst-performing categories):
- Categorize by failure type: cross-doc fact mixing, single-doc bias, coverage collapse, type mismatch, render failure
- Report distribution and provide qualitative examples in appendix

### 9.6 Estimated total experiment scale

- Total generations: ~50,000
- API cost (GPT-5 + Claude Opus 4.6 + Gemini 2.5 Pro + Qwen3-Coder + DeepSeek V3.5 average): ~$1,800
- Judge calls (checklist gen + scoring): ~$600
- Human eval (Prolific): ~$280
- Total: ~$2,680

---

## 10. SUCCESS CRITERIA — Tier-by-Tier

### 10.1 Tier 1 (Home turf draws): Target — within 5-7%p

| Setting | Specialist | Specialist score | DocViz-Agent target | Status |
|---|---|---|---|---|
| Text2Vis | B7 Text2Vis-orig | ~55% (Text2Vis paper reports actor-critic 42%; new specialist may be higher) | DocViz-Agent ≥ 48% | Tier 1 pass if within -7%p |
| ViviBench | B8 ViviDoc-orig | ~65% (ViviDoc reports 4-dim averaged) | DocViz-Agent ≥ 58% | Tier 1 pass |
| Plot2Code | B9 MatPlotAgent | ~62% (Plot2Code paper) | DocViz-Agent ≥ 55% | Tier 1 pass |

If Tier 1 fails (DocViz-Agent < specialist - 10%p on any home turf): reframe as "trade-off" paper or downgrade to Findings.

### 10.2 Tier 2 (Our turf wins): Target — +8%p over best baseline

QG-MDV setting:
- DocViz-Agent average over 4 axes ≥ best non-ours baseline + 8%p
- Per-query-type breakdown: DocViz-Agent best in ≥ 4 of 5 types
- Multi-doc scaling: DocViz-Agent drop (1→5 docs) ≤ half of baseline drop

If Tier 2 fails (gap < 5%p): re-examine pipeline implementation, possibly pivot to "diagnostic finding" paper.

### 10.3 Tier 3 (Cross-task average): Target — best by 8%p+

Average across 4 settings (QG-MDV + Text2Vis + ViviBench + Plot2Code) for each baseline:
- DocViz-Agent average ≥ best specialist average + 8%p
- This is the headline cross-task generalist claim

### 10.4 Improvement axes (I1-I5) — quantitative targets

| Axis | Metric | Best baseline target | DocViz-Agent target | Gap |
|---|---|---|---|---|
| I1 | Multi-doc faithfulness (5-doc) | ≤ 70% | ≥ 78% | +8%p |
| I2 | Cross-doc claim attribution | ≤ 65% | ≥ 80% | +15%p |
| I3 | Type-content fit | ≤ 75% | ≥ 82% | +7%p |
| I4 | Render success rate | 70-85% | ≥ 95% | +10%p |
| I5 | Reverse-QA usability | ≤ 60% | ≥ 68% | +8%p |

### 10.5 Validation (Layer 2-6 anchors) — minimum thresholds

- Layer 2 (Human): Spearman r ≥ 0.65 on faithfulness + coverage axes
- Layer 3 (Deterministic): Cross-rank Spearman ≥ 0.5 with judge
- Layer 4 (Reverse-QA): Effect direction positive
- Layer 5 (Replicate): Visual reasoning drop ≥ 30% reproduced
- Layer 6 (External): Within 5-7%p of specialist on Text2Vis + ViviBench

---

## 11. EXPECTED RESULT PATTERNS — What good looks like

### 11.1 Main Result Table — expected pattern

Rows = baselines, Columns = 4 settings + cross-task average:
- B7 Text2Vis-orig: ★ on Text2Vis, weak elsewhere, lowest cross-task avg
- B8 ViviDoc-orig: ★ on ViviBench, weak elsewhere, lowest cross-task avg
- B9 MatPlotAgent: ★ on Plot2Code, weak elsewhere, lowest cross-task avg
- B5 Direct-LLM: middle on all settings, middle cross-task avg
- B6 DocViz-Agent: ★ on QG-MDV, within -5~7%p on others, ★ on cross-task average

### 11.2 Multi-doc Scaling Curve — expected pattern

Faithfulness on Y axis, doc count (1, 2, 3, 5) on X axis:
- All baselines: monotonic decrease, drop -15~25%p from 1 to 5 docs
- DocViz-Agent: smaller drop -8~12%p, gap to baselines widens with doc count
- Crossover point: at 3+ docs DocViz-Agent surpasses all baselines

### 11.3 Per-query-type Heatmap — expected pattern

Rows = baselines, Columns = 5 query types:
- Each specialist baseline strong in ~1 query type (e.g., NVAGENT in quantitative)
- DocViz-Agent: strong in ≥ 4 of 5 types, best in ≥ 3
- Hierarchical and Relational types show largest DocViz-Agent advantage (multi-viz unification)

### 11.4 Ablation Table — expected pattern

| Variant | I1 | I2 | I3 | I4 | I5 | Avg |
|---|---|---|---|---|---|---|
| Full DocViz-Agent | ★ | ★ | ★ | ★ | ★ | ★ |
| - CIS | -5~10%p | -2%p | 0 | 0 | -3%p | -4 |
| - TMG | -2%p | -1%p | -3~6%p | 0 | -2%p | -3 |
| - SAO | -2%p | -10~15%p | 0 | 0 | -3%p | -5 |
| - All | -10%p | -15%p | -7%p | -5%p | -10%p | -10 |

Each pillar contributes meaningfully; full ablation drops to baseline level.

### 11.5 Long-context Paradox — expected pattern

- All baselines: faithfulness flat or declining as context grows from 8K to 128K
- DocViz-Agent: slight improvement with longer context (CIS uses information efficiently)
- Headline finding: "more context does not help baselines, only DocViz-Agent benefits modestly"

---

## 12. RISK REGISTER

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| User pipeline interface incompatible with specified format | Medium | High | Day 1 wire-up: spend 2-4 hours adapting interface |
| Multi-doc input format change breaks existing pipeline | Medium | Medium | Use thin adapter; preserve original behavior |
| GPT-5 / Claude rate limits during 28K+ generations | Medium | Medium | Use batch APIs (50% discount, slower); spread across 2 weeks |
| Mermaid render failures > 10% | Medium | Medium | Add format validation in prompt; allow 2 retries; log failures |
| Judge-Human Spearman < 0.5 in Week 0 | Medium | High | Try cross-judge swap; simplify checklist to 6 items; if still < 0.5 fall back to mixed metric |
| Tier 1 fails (DocViz-Agent > -10%p of specialist) | Medium | High | Reframe as "trade-off paper" or downgrade to Findings |
| Tier 2 weak (gap < 5%p) | Low-Medium | High | Investigate pipeline pillars; if no fix, pivot to diagnostic finding paper |
| External benchmark adaptation introduces noise | Medium | Medium | Document adaptation transparently; report as caveat in paper |
| Long-context experiment (128K) cost spike | Low | Medium | Sample subset; use Gemini 2.5 Pro long-context efficiency |
| Prolific human eval delayed | Low | Low | Start in Week 4; allow 1.5 weeks turnaround |
| User pipeline non-deterministic between runs | Medium | Medium | Fix seed where possible; report mean over 3 runs for key cells |

---

## 13. RESULT SCENARIOS — Backup paper titles

| Scenario | Tier 1 | Tier 2 | Tier 3 | Title | Venue |
|---|---|---|---|---|---|
| Best | within -5%p | +10%p | +12%p | "DocViz-Agent: First Generalist Pipeline for Query-Grounded Multi-Document Visualization" | EMNLP main |
| Good | within -7%p | +8%p | +8%p | Same as best | EMNLP main / Findings |
| Modest | within -10%p | +5-8%p | +5%p | "Toward Generalist Document Visualization: A Comparative Study" | Findings |
| Weak Tier 2 | within -7%p | +3-5%p | +5%p | "Multi-Document Visualization Benchmark and Setting-Stratified Analysis" | Findings (resource paper) |
| Tier 1 fails | -15%p+ | +5%p+ | low | "Specialization vs Generalization in Document Visualization" | Findings (analysis paper) |
| All weak | low | low | low | "Multi-Doc Grounding Gap: Diagnostic Findings on Frontier LLMs" | Findings (finding paper) |

In every scenario, the paper is publishable. Worst case = Findings finding-paper.

---

## 14. TIMELINE (11-12 weeks)

### Week 0 (Prototype, already specified separately)
30-bundle prototype with B5 + B6 to validate (a) judge-human r ≥ 0.5, (b) effect direction. Decision gate: GO / REFRAME / JUDGE-FIX / PIVOT.

### Week 1-2 (Benchmark construction)
- Scale doc corpus from 30 to 350 bundles
- Generate 700 queries with 5-type taxonomy
- Run Prolific naturalness verification on 150 gold subset
- Build deterministic metrics M1-M4 (render-check, numeric, entity-coverage, structural)

### Week 3-4 (Baseline + DocViz-Agent implementation)
- Implement adapted baselines B1-B5
- Wire DocViz-Agent (B6) using user's existing pipeline + 3 pillars
- Verify pillar implementations match spec (CIS / TMG / SAO)

### Week 5-6 (Main experiments)
- Run full Main Result Table on QG-MDV (21,000 generations)
- Run external benchmarks: Text2Vis (3,000), ViviBench (3,030)
- Compute checklist judge scores across all cells
- Run M1-M4 deterministic anchors

### Week 7 (Sub-experiments)
- Multi-doc scaling experiment (12,000 generations)
- Long-context paradox experiment (4,500 generations)
- Reverse-QA evaluation (Layer 4 anchor)

### Week 8 (Ablation + Finding analysis)
- Ablation study (5,000 generations)
- Failure mode taxonomy (30 manual sample analysis)
- Replicate-finding analysis (Layer 5 anchor)

### Week 9 (Validation + Cross-judge)
- Human alignment Prolific (Layer 2 anchor)
- Cross-judge agreement check (Layer 3)
- All anchor numbers finalized

### Week 10-11 (Writing)
- Draft paper sections
- Internal review
- Reviewer simulation
- Iterate on weakest sections

### Week 12 (Buffer + submission)
- Final polish
- Reproducibility check
- Submit

---

## 15. PAGE ALLOCATION (8-page main format)

```
§1 Introduction              0.75 page
§2 Related Work              0.75 page  ← 8 prior method spectrum, gap diagram
§3 Task Formalization        0.75 page  ← QG-MDV definition, 5 query types
§4 DocViz-Agent              1.50 page  ← C1, 3 pillars
§5 Benchmark + 4 Settings    0.75 page  ← QG-MDV + 3 external
§6 Evaluation Framework      0.50 page  ← C3 (infrastructure)
§7 Setting-Stratified Results 2.00 page ← C4, Tier 1 / 2 / 3
§8 Findings & Discussion     0.75 page  ← C5, multi-doc gap finding
References                   -
Appendix                     (V1-V4 + ablations + prompts + extended tables)
```

DocViz-Agent occupies 1.50 page (19%) as main method. Setting-stratified results occupy 2.00 page (25%) as paper face. Together 44% — appropriate for method + empirical contribution paper.

---

## 16. REVIEWER ATTACK DEFENSE — Pre-emptive answers

| Attack | Defense |
|---|---|
| "Why doesn't DocViz-Agent beat Text2Vis-original on Text2Vis?" | Text2Vis-original was designed for Text2Vis. Specialists win their home turf by design. We claim generalist value: within -5%p on home turf, +8%p on uncovered turf, +8%p on cross-task average. |
| "Self-built benchmark is not validated by community" | We provide 6 layers of evidence: human anchor (r ≥ 0.65), deterministic metrics agreement, reverse-QA usability, replicate ChartMuseum finding, AND external Text2Vis + ViviBench evaluation. |
| "Multi-doc grounding gap is pipeline-dependent" | Finding holds across all 6 baselines × 5 LLMs × all settings (§7 E0 Pipeline-Independence Test). It is task-inherent, not method-induced. |
| "Method novelty is just combination of existing techniques" | First combination addressing this combined setting (multi-doc + query + multi-viz). 8 prior methods all setting-mismatched. Combination novelty justified by 4-layer rationale (no prior covers, components grounded, empirical validation, replicability). |
| "Synthetic queries are not natural" | Naturalness Prolific verified mean ≥ 4.0 / 5, Cohen κ ≥ 0.6 on 150 sample. |
| "DSL coverage too narrow (only Chart.js + Mermaid)" | Explicit scope: declarative visualization DSLs covering 3 canonical primitives (charts, diagrams, mindmaps). Production deployment uses these (Notion, GitBook, Slack canvas). Free-form SVG/PNG is future work. |
| "Why not include more LLMs?" | 5 LLMs cover closed flagship × 3 + open large × 2. Reference papers (ChartMuseum, FlowVQA) use 5-19 models; ours sits within range. |
| "Doc count scaling shows confounding factors" | Sub-experiment with same query, same total tokens, varying doc count → faithfulness drop is doc-count effect, not length effect. Long-context paradox experiment separates length from count. |
| "Cost analysis missing" | Per-baseline API cost reported in cost-Pareto plot (§7). DocViz-Agent costs more than B5 Direct but achieves Pareto-frontier quality. |

---

## 17. DELIVERABLES

### 17.1 Paper artifacts

- 8-page main paper (LaTeX, ACL/EMNLP style)
- Appendix with extended tables, prompts, validation details
- Submission-ready PDF

### 17.2 Code artifacts

- DocViz-Agent pipeline (open-source, Apache 2.0)
- Adapted baseline wrappers (B1-B5)
- Evaluation framework (checklist judge + 4 deterministic metrics)
- Reproducibility scripts (one-command rerun on QG-MDV)

### 17.3 Data artifacts

- QG-MDV benchmark on Hugging Face (350 bundles + 700 queries + 150 gold ratings)
- All 50,000 generated visualizations (with judge scores) on Hugging Face
- Per-experiment result spreadsheets

### 17.4 Documentation

- Paper master spec (this document)
- Week 0 prototype guide (separate)
- Per-week reports in repo docs/

---

## 18. PRE-START PREREQUISITES

### 18.1 Confirmed by user

- User pipeline exists and produces (multi-doc, query) → viz output
- Web search tool will be removed from agent toolset for paper experiments
- Multi-doc input format will be standardized to flat list of dicts with {doc_id, page_id, content}
- Workspace is connected to GitHub repo at https://github.com/pminhyung/docviz.git
- Research agent works in separate environment, pushes to repo; advisor pulls and provides feedback

### 18.2 Open questions for user (confirm before Week 1)

- User pipeline's exact entry point (function signature) — needed for B6 wiring
- User pipeline's deterministic mode (fixed seed) — needed for reproducibility
- User pipeline's expected output format compatibility with DSL-only output (Chart.js JSON or Mermaid markdown) — verify or add adapter
- API budget cap per week — for monitoring spend
- Submission deadline confirmation (EMNLP 2026 main cycle) — check ARR vs direct submit

### 18.3 Research agent first-day checklist

- Confirm access to all 5 LLM APIs (GPT-5, Claude Opus 4.6, Gemini 2.5 Pro, Qwen3-Coder-30B, DeepSeek V3.5) with sufficient credit
- Verify model versions via web search at experiment runtime
- Set up Mermaid CLI and Chart.js renderer for I4 metric
- Set up Prolific account for human eval (Week 1 + Week 9)
- Read user pipeline code; write adapter spec before implementing B6
- Read this document end to end before starting any task

---

## 19. CRITICAL DESIGN PRINCIPLES (DO NOT VIOLATE)

These are the inviolable principles that preserve the paper's integrity:

- **Specialist vs Generalist framing**: Never claim SOTA on external benchmarks. Always frame as "competitive on home turf, win on uncovered turf, best on cross-task average."
- **3 Pillars must coexist**: CIS, TMG, SAO are interdependent. Removing any one collapses the contribution. All three must be in the implementation.
- **No circular evaluation**: Checklist generator and scorer must be different LLMs. Judges must not also be generators of the same instance.
- **Pipeline-independence**: Multi-doc grounding gap finding (C5) must be reproduced across all 6 baselines × 5 LLMs to claim task-inherent (not method-induced).
- **Honest reporting**: If Tier 1 fails (DocViz-Agent significantly worse than specialist on home turf), report honestly. Reframe paper rather than hide.
- **Latest model versions**: Verify model versions at runtime via web search. Use latest. No outdated models.
- **External anchor honesty**: Text2Vis and ViviBench results reported even if unfavorable. These are reviewer-trusted external surfaces.
- **Reproducibility**: All code, data, prompts released. Random seeds fixed. One-command rerun on QG-MDV.

---

## 20. CONTACT POINTS FOR DECISION-MAKING

When the research agent encounters a decision not specified in this document, escalate to the human researcher. Do not improvise on:

- Major scope changes (adding/removing experiments, baselines, datasets)
- Pipeline architectural changes that affect any of the 3 pillars
- Evaluation framework changes (judge model swap, axis redefinition)
- Submission venue changes
- Budget/timeline changes exceeding 20% of original

For minor implementation decisions (prompt tuning, hyperparameter choices, data parsing edge cases), proceed with documented rationale in the relevant weekly report.

---

## END OF MASTER SPEC

This document is comprehensive. The research agent should be able to operate Week 1 onward referencing this document plus the Week 0 action guide. Update this document only with explicit human approval; track changes in a CHANGELOG.

The headline message of this paper, in one sentence:

> **First generalist pipeline for query-grounded multi-document visualization, achieving competitive performance with specialist methods on their home turfs and substantial advantage in the previously-uncovered multi-doc setting, with a 6-layer evidence chain anchoring the result objectively.**
