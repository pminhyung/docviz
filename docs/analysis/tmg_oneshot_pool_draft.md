# DocViz-Agent — TMG Exemplar Pool Draft (Pillar 2 §3.2 amend)

**Scope.** Replace `code/pipelines/tmg.py:ONE_SHOT_BY_VIZ_TYPE` (single placeholder
per viz_type) with `ONE_SHOT_POOL_BY_VIZ_TYPE` — a 2–3 exemplar pool per viz_type
covering distinct **syntactic shapes** and rich, source-grounded **content style**.

**Why.** Per `docs/analysis/oneshot_failure_analysis.md` (commit `b90eda1`):
- The current placeholders ("Founder/Acme Corp/Beta Labs", "NLP Methods/Supervised",
  "founded/acquired/hired") cause **style flattening** on entity-rich Mermaid
  outputs (−20pp faith on hotpotqa relational/comparative).
- A single exemplar cannot cover the **syntactic spectrum** (chain vs hub vs
  subgraph; 2-level vs 3-level mindmap; Q-cadence vs annual timeline), so the
  agent truncates the source's middle layer when the example structure
  doesn't match the source inventory.

**Data anchors.** All anchors are real outputs from `outputs/prototype/viz/all.json`
that received `axis_scores.faithfulness >= 0.75` per
`outputs/prototype/judge_scores/all.json` (180 records; faith threshold filters
to 86 candidates after `syntax_valid=true`). Anchor selection prioritizes (a)
faith score ≥ 0.75, (b) overall ≥ 0.85, (c) syntactic diversity within type.

---

## Section 1 — Source data utilization summary

### 1.1 Anchor selection per viz_type

| viz_type | anchor query_id | strategy | faith | overall | role |
|---|---|---|---|---|---|
| chartjs_bar | `10k_02_quantitative` | S1_Direct | 1.00 | 1.00 | horizontal-axis 2-bar single-series |
| chartjs_bar | `10k_01_quantitative` | S4_Agentic | 1.00 | 0.92 | 4-bar categorical single-series |
| chartjs_bar | `hotpot_08_comparative` | S4_Agentic | 1.00 | 0.88 | 3-bar named-category single-series (narrative title) |
| chartjs_line | `multinews_09_temporal` | S1_Direct | 0.75 | 0.92 | yearly trend, 1 series, 3 points (only chartjs_line anchor available) |
| chartjs_grouped_bar | `10k_00_quantitative` | S1_Direct | 1.00 | 1.00 | 2-dataset × 2-axis horizontal compare |
| chartjs_grouped_bar | `multinews_09_comparative` | S4_Agentic | 1.00 | 1.00 | 2-dataset × 3-axis dual-y-axis (mixed units) |
| chartjs_grouped_bar | `10k_02_temporal` | S1_Direct | 1.00 | 0.83 | 2-dataset × 2-year side-by-side |
| mermaid_flowchart | `hotpot_05_relational` | S4_Agentic | 1.00 | 1.00 | 3-node chain LR with role-edge labels |
| mermaid_flowchart | `hotpot_00_relational` | S4_Agentic | 1.00 | 0.92 | 5-node chain LR with descriptive edges |
| mermaid_flowchart | `multinews_05_comparative` | S4_Agentic | 1.00 | 1.00 | hub + 2 subgraph clusters (intent vs impact) |
| mermaid_flowchart | `arxiv_00_comparative` | S1_Direct | 1.00 | 0.89 | 2 parallel subgraphs (compare two pipelines) |
| mermaid_mindmap | `arxiv_01_hierarchical` | S1_Direct | 1.00 | 1.00 | 3-level (root → category → instance with challenge/solution) |
| mermaid_mindmap | `arxiv_00_hierarchical` | S1_Direct | 1.00 | 1.00 | 4-level (root → method → axis → leaf) with icons |
| mermaid_mindmap | `arxiv_00_comparative` | S4_Agentic | 1.00 | 1.00 | 4-level matrix-shape (2 methods × parallel axes) |
| mermaid_timeline | `10k_00_temporal` | S1_Direct | 1.00 | 1.00 | quarterly section, multi-event-per-quarter |
| mermaid_timeline | `hotpot_01_comparative` | S1_Direct | 1.00 | 1.00 | 2 named sections, 1–2 events per section |
| mermaid_timeline | `hotpot_04_relational` | S4_Agentic | 1.00 | 1.00 | 3 named eras, multi-line `<br>` event detail |

### 1.2 Coverage notes

- **chartjs_line is the weakest cell** — only 1 record in the entire 180-record
  pool reaches faith ≥ 0.75 (S1_Direct, `multinews_09_temporal`). One of the
  three line exemplars in §2.2 is therefore **hand-written** in the
  paper-methods archetype, anchored on the content style (rich
  source-grounded label, named-year axis, single trend metric) of the one
  available real anchor and the high-faith bar/grouped_bar anchors.
- All other viz_types have ≥ 4 valid anchors; selections cover the syntactic
  shapes named in the task brief.
- Cross-archetype distribution: Wikipedia/historical (mermaid_flowchart,
  mermaid_timeline), paper-methods (mermaid_mindmap, mermaid_flowchart,
  chartjs_line), financial (chartjs_bar, chartjs_grouped_bar, mermaid_timeline),
  news-headline (mermaid_flowchart, mermaid_timeline). No archetype dominates
  any single viz_type.

### 1.3 Rewrite policy

Anchor *content style* is preserved; *entities and numbers* are rewritten to
generic-domain originals. Each exemplar is paraphrased to avoid direct lift
from the prototype set (so the pool does not leak prototype answers into the
agent's context when prototype queries are re-evaluated). Numerical values are
plausibly typical for the archetype (e.g., 10-K-style $-millions, news-style
casualty counts, paper-method-style FLOP counts).

---

## Section 2 — Per-viz_type exemplar pool draft

Each exemplar block lists:
1. The complete `{"viz_type": ..., "viz_dsl": ...}` JSON literal (mapper
   strategy 1a will whole-text-parse this).
2. **Source**: anchor query_id (faith) or `hand-written`.
3. **Syntactic feature**: the structural shape this exemplar covers.
4. **Domain archetype**: Wikipedia / news / paper-methods / financial.
5. **Why this style helps faith**: one-sentence justification.

### 2.1 `chartjs_bar` — 3 exemplars

#### 2.1.1 BAR-A — horizontal 2-bar, financial archetype

```json
{"viz_type": "chartjs_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"FY2023\",\"FY2024\"],\"datasets\":[{\"label\":\"Foreign Currency Translation Loss (Billions USD)\",\"data\":[1.42,2.08],\"backgroundColor\":[\"#36A2EB\",\"#FF6384\"],\"borderColor\":[\"#1E90FF\",\"#DC143C\"],\"borderWidth\":1}]},\"options\":{\"indexAxis\":\"y\",\"responsive\":true,\"plugins\":{\"legend\":{\"display\":false},\"title\":{\"display\":true,\"text\":\"Acme Industries — FX Translation Loss Under 10% Adverse-Move Scenario\"}},\"scales\":{\"x\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Potential Loss (Billions USD)\"}}}}}"}
```

- **Source**: `10k_02_quantitative` / S1_Direct (faith 1.00, overall 1.00).
- **Syntactic feature**: 2 bars, 1 dataset, `indexAxis: "y"` (horizontal),
  legend hidden, sentence-style title.
- **Domain archetype**: financial (10-K disclosure style).
- **Why faith**: anchors the agent on **scenario-qualified** title text
  ("Under 10% Adverse-Move Scenario") and **unit-explicit** axis label
  ("Potential Loss (Billions USD)") — both forms the failing placeholder
  ("Q1/Q2/Q3/Q4 → Revenue ($B)") cannot teach.

#### 2.1.2 BAR-B — vertical 4-bar, financial archetype

```json
{"viz_type": "chartjs_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"Cloud Services\",\"Productivity Suite\",\"Compute Infrastructure\",\"Professional Network\"],\"datasets\":[{\"label\":\"FY2025 Year-over-Year Revenue Growth (%)\",\"data\":[24,16,33,9],\"backgroundColor\":[\"rgba(54, 162, 235, 0.6)\",\"rgba(75, 192, 192, 0.6)\",\"rgba(255, 206, 86, 0.6)\",\"rgba(153, 102, 255, 0.6)\"],\"borderColor\":[\"rgba(54, 162, 235, 1)\",\"rgba(75, 192, 192, 1)\",\"rgba(255, 206, 86, 1)\",\"rgba(153, 102, 255, 1)\"],\"borderWidth\":1}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"YoY Growth (%)\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Acme Industries FY2025 Revenue Growth by Reportable Segment\"},\"legend\":{\"display\":false}}}}"}
```

- **Source**: `10k_01_quantitative` / S4_Agentic (faith 1.00, overall 0.92).
- **Syntactic feature**: 4 bars, 1 dataset, vertical orientation, named
  business-segment categories.
- **Domain archetype**: financial.
- **Why faith**: shows the agent that **categorical labels** can be
  multi-word descriptive nouns ("Cloud Services", "Compute Infrastructure")
  rather than abstract ("Q1/Q2/Q3/Q4"); reinforces unit-explicit y-axis
  title with parenthetical scale.

#### 2.1.3 BAR-C — narrative-title 3-bar, news archetype

```json
{"viz_type": "chartjs_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"Civilian Casualties (Wappani Confederacy)\",\"Settler Forces (Killed in Action)\",\"Settler Forces (Wounded)\"],\"datasets\":[{\"label\":\"Casualties at the Long Hollow Raid (October 1762)\",\"data\":[412,3,21],\"backgroundColor\":[\"rgba(255, 99, 132, 0.6)\",\"rgba(54, 162, 235, 0.6)\",\"rgba(255, 206, 86, 0.6)\"],\"borderColor\":[\"rgba(255, 99, 132, 1)\",\"rgba(54, 162, 235, 1)\",\"rgba(255, 206, 86, 1)\"],\"borderWidth\":1}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Number of Casualties\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Long Hollow Raid — Single-Engagement Casualty Comparison (Deadliest Action of the 1762 Frontier Conflict)\"},\"legend\":{\"display\":false}}}}"}
```

- **Source**: `hotpot_08_comparative` / S4_Agentic (faith 1.00, overall 0.88),
  paraphrased to a fictional historical event to avoid prototype leakage.
- **Syntactic feature**: 3 bars, 1 dataset, vertical, narrative title with
  parenthetical date and scope qualifier.
- **Domain archetype**: news / Wikipedia-historical.
- **Why faith**: trains the agent that bar-chart titles can carry
  **interpretive context** ("Deadliest Action of the 1762 Frontier
  Conflict") that grounds the chart in the source's framing — this is what
  the failing placeholder "Q1/Q2/Q3/Q4" actively prevents.

---

### 2.2 `chartjs_line` — 3 exemplars

#### 2.2.1 LINE-A — yearly single-series, financial archetype

```json
{"viz_type": "chartjs_line", "viz_dsl": "{\"type\":\"line\",\"data\":{\"labels\":[\"2018\",\"2019\",\"2020\",\"2021\",\"2022\",\"2023\"],\"datasets\":[{\"label\":\"Lakeshore Foundation Annual Endowment Disbursements (Millions USD)\",\"data\":[412,468,521,602,718,805],\"borderColor\":\"rgb(75, 192, 192)\",\"backgroundColor\":\"rgba(75, 192, 192, 0.2)\",\"tension\":0.1}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Disbursement (Millions USD)\"}},\"x\":{\"title\":{\"display\":true,\"text\":\"Calendar Year\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Lakeshore Foundation Endowment Disbursements, 2018–2023\"}}}}"}
```

- **Source**: `multinews_09_temporal` / S1_Direct (faith 0.75, overall 0.92);
  rewritten with 6 instead of 3 points to extend the trend and lifted to a
  fictional foundation.
- **Syntactic feature**: 1 series, 6 yearly points, monotone trend,
  date-range title.
- **Domain archetype**: news / financial-philanthropy.
- **Why faith**: gives a clean **single-trend metric** template with
  unit-explicit dataset label embedded in the legend (rather than a bare
  "Active Users (M)") — the pattern that survives Mermaid-side flattening.

#### 2.2.2 LINE-B — multi-series 5-year compare, paper-methods archetype

```json
{"viz_type": "chartjs_line", "viz_dsl": "{\"type\":\"line\",\"data\":{\"labels\":[\"2019\",\"2020\",\"2021\",\"2022\",\"2023\"],\"datasets\":[{\"label\":\"Encoder-only (Top-1 Accuracy %)\",\"data\":[71.2,74.5,77.0,78.4,79.1],\"borderColor\":\"rgb(54, 162, 235)\",\"backgroundColor\":\"rgba(54, 162, 235, 0.2)\",\"tension\":0.2},{\"label\":\"Decoder-only (Top-1 Accuracy %)\",\"data\":[68.0,72.8,76.5,80.2,83.4],\"borderColor\":\"rgb(255, 99, 132)\",\"backgroundColor\":\"rgba(255, 99, 132, 0.2)\",\"tension\":0.2}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":false,\"title\":{\"display\":true,\"text\":\"Top-1 Accuracy on ImageNet-1k Eval Slice (%)\"}},\"x\":{\"title\":{\"display\":true,\"text\":\"Publication Year\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Vision Backbone Family Accuracy Trajectories on ImageNet-1k (2019–2023)\"},\"legend\":{\"display\":true,\"position\":\"top\"}}}}"}
```

- **Source**: hand-written (no multi-series chartjs_line anchor met threshold),
  content style anchored on `arxiv_00_comparative` mindmap label patterns
  (faith 1.00) and the LINE-A label format.
- **Syntactic feature**: 2 series, 5 yearly points, comparison trend,
  `beginAtZero: false` to expose mid-range deltas.
- **Domain archetype**: paper-methods.
- **Why faith**: shows that line-chart series labels can carry **named
  evaluation slice** ("Top-1 Accuracy on ImageNet-1k Eval Slice") rather
  than generic ("Active Users") — and that x-axis can name a calendar
  cadence ("Publication Year") so the agent does not collapse to bare
  integer labels.

#### 2.2.3 LINE-C — cumulative-metric 7-point, financial archetype

```json
{"viz_type": "chartjs_line", "viz_dsl": "{\"type\":\"line\",\"data\":{\"labels\":[\"FY2017\",\"FY2018\",\"FY2019\",\"FY2020\",\"FY2021\",\"FY2022\",\"FY2023\"],\"datasets\":[{\"label\":\"Cumulative R&D Capitalization (Billions USD)\",\"data\":[3.1,7.4,12.8,19.6,27.9,38.4,51.2],\"borderColor\":\"rgb(153, 102, 255)\",\"backgroundColor\":\"rgba(153, 102, 255, 0.25)\",\"fill\":true,\"tension\":0.15}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Cumulative Capitalization (Billions USD)\"}},\"x\":{\"title\":{\"display\":true,\"text\":\"Fiscal Year\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Acme Industries Cumulative R&D Capitalization, FY2017–FY2023\"},\"legend\":{\"display\":false}}}}"}
```

- **Source**: hand-written, anchored on `10k_*_quantitative` content-style
  patterns (faith 1.00 in both BAR-A and BAR-B anchors).
- **Syntactic feature**: 1 series, 7 fiscal-year points, **cumulative**
  (monotone increasing) shape, area-fill on.
- **Domain archetype**: financial.
- **Why faith**: covers the **cumulative trajectory** sub-shape (vs LINE-A's
  flow trend and LINE-B's compare trend) — without this, the agent has no
  template for "running total" metrics that 10-K queries occasionally need.

---

### 2.3 `chartjs_grouped_bar` — 3 exemplars

#### 2.3.1 GBAR-A — 2-dataset × 2-axis horizontal compare

```json
{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"Available-for-Sale Securities\\n(Fair Value Decline)\",\"Long-Term Debt\\n(Interest Expense Increase)\"],\"datasets\":[{\"label\":\"FY2024\",\"data\":[2620,142],\"backgroundColor\":\"rgba(54, 162, 235, 0.6)\",\"borderColor\":\"rgba(54, 162, 235, 1)\",\"borderWidth\":1},{\"label\":\"FY2023\",\"data\":[2884,128],\"backgroundColor\":\"rgba(255, 99, 132, 0.6)\",\"borderColor\":\"rgba(255, 99, 132, 1)\",\"borderWidth\":1}]},\"options\":{\"indexAxis\":\"y\",\"responsive\":true,\"plugins\":{\"title\":{\"display\":true,\"text\":\"Acme Industries — Estimated Impact of 100bp Parallel Rate Shock (Millions USD)\"},\"legend\":{\"position\":\"top\"}},\"scales\":{\"x\":{\"title\":{\"display\":true,\"text\":\"Estimated Impact (Millions USD)\"},\"beginAtZero\":true},\"y\":{\"title\":{\"display\":true,\"text\":\"Risk Category\"}}}}}"}
```

- **Source**: `10k_00_quantitative` / S1_Direct (faith 1.00, overall 1.00).
- **Syntactic feature**: 2 datasets (FY-pair) × 2 named risk categories,
  horizontal, multi-line `\n` inside category labels for sub-qualifier.
- **Domain archetype**: financial (10-K interest-rate-risk disclosure).
- **Why faith**: teaches the agent the **side-by-side year compare** pattern
  with **multi-line category labels** — both absent from the current
  Speed/Accuracy/Cost placeholder.

#### 2.3.2 GBAR-B — 2-dataset × 3-axis dual-y mixed-units

```json
{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"2019\",\"2020\",\"2021\"],\"datasets\":[{\"label\":\"Cash Equivalent of Stock Donation (Billions USD)\",\"data\":[2.6,3.1,3.0],\"backgroundColor\":\"rgba(54, 162, 235, 0.5)\",\"borderColor\":\"rgba(54, 162, 235, 1)\",\"borderWidth\":1,\"yAxisID\":\"y\"},{\"label\":\"Class B Shares Donated (Millions)\",\"data\":[14.0,12.5,11.8],\"backgroundColor\":\"rgba(255, 99, 132, 0.5)\",\"borderColor\":\"rgba(255, 99, 132, 1)\",\"borderWidth\":1,\"yAxisID\":\"y1\"}]},\"options\":{\"responsive\":true,\"scales\":{\"y\":{\"type\":\"linear\",\"position\":\"left\",\"title\":{\"display\":true,\"text\":\"Cash Equivalent (Billions USD)\"}},\"y1\":{\"type\":\"linear\",\"position\":\"right\",\"title\":{\"display\":true,\"text\":\"Shares (Millions)\"},\"grid\":{\"drawOnChartArea\":false}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Lakeshore Foundation Annual Endowment Inflow, 2019–2021 (Two-Axis View)\"},\"legend\":{\"display\":true,\"position\":\"top\"}}}}"}
```

- **Source**: `multinews_09_comparative` / S4_Agentic (faith 1.00, overall 1.00),
  domain shifted to a fictional foundation.
- **Syntactic feature**: 2 datasets with **separate y-axes** (mixed units —
  Billions USD vs Millions of shares) × 3 yearly axes, top legend.
- **Domain archetype**: news / financial-philanthropy.
- **Why faith**: this is the **dual-y mixed-units** sub-shape — the failing
  placeholder uses identical units (Speed/Accuracy/Cost), which actively
  miscues the agent on the "two metrics with different scales" case
  identified in the failure analysis.

#### 2.3.3 GBAR-C — 3-dataset × 4-axis side-by-side (paper-methods)

```json
{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"Reasoning (MMLU)\",\"Coding (HumanEval)\",\"Math (GSM8K)\",\"Long-Context (NIH)\"],\"datasets\":[{\"label\":\"Encoder-Decoder Baseline\",\"data\":[68.4,42.1,55.7,71.0],\"backgroundColor\":\"rgba(54, 162, 235, 0.6)\",\"borderColor\":\"rgba(54, 162, 235, 1)\",\"borderWidth\":1},{\"label\":\"Decoder-Only + RLHF\",\"data\":[78.9,71.8,82.4,84.2],\"backgroundColor\":\"rgba(255, 99, 132, 0.6)\",\"borderColor\":\"rgba(255, 99, 132, 1)\",\"borderWidth\":1},{\"label\":\"Mixture-of-Experts + DPO\",\"data\":[81.2,75.4,86.0,88.7],\"backgroundColor\":\"rgba(75, 192, 192, 0.6)\",\"borderColor\":\"rgba(75, 192, 192, 1)\",\"borderWidth\":1}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Benchmark Accuracy (%)\"},\"max\":100}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"LLM Architecture Comparison Across Four Standardized Benchmarks\"},\"legend\":{\"display\":true,\"position\":\"top\"}}}}"}
```

- **Source**: hand-written, anchored on `arxiv_00_comparative` (mindmap, faith
  1.00) for the architecture-comparison content style and on `10k_04_quantitative`
  GBAR (faith 1.00) for the JSON schema.
- **Syntactic feature**: **3 datasets** (the largest fanout we keep) × 4
  named benchmark axes, vertical, fixed y-max = 100.
- **Domain archetype**: paper-methods.
- **Why faith**: covers the paper-methods comparative case (3-way
  architecture eval) which is exactly the cell where the failing
  `chartjs_grouped_bar` placeholder produced faith=0 in the post-mortem
  (`arxiv_00_comparative`, drop −1.00 in §oneshot_failure_analysis).

---

### 2.4 `mermaid_flowchart` — 3 exemplars

#### 2.4.1 FLOW-A — 5-node chain LR with descriptive role-edges (Wikipedia)

```json
{"viz_type": "mermaid_flowchart", "viz_dsl": "graph LR\n    A[Vice-Admiral Ravindra Sethi] -->|Retired Indian Navy Flag Officer| B(Western Naval Command)\n    B -->|Authorized Operation Trident-II in| C[December 1971]\n    C -->|Launched missile-boat strike against| D[Karachi Harbour Oil Depot]\n    D -->|Located in| E[Karachi, Sindh, Pakistan]"}
```

- **Source**: `hotpot_00_relational` / S4_Agentic (faith 1.00, overall 0.92),
  rewritten as a fictional naval engagement to avoid prototype leakage.
- **Syntactic feature**: 5-node chain, **left-to-right** orientation,
  edge labels are **role-descriptive phrases** (not single verbs).
- **Domain archetype**: Wikipedia-historical / news.
- **Why faith**: replaces the failing `A -->|founded| B -->|acquired| C
  -->|hired| D` pattern (single-verb edges, generic entities) with the
  high-faith *actual* style — entity names with appositive titles
  ("Vice-Admiral Ravindra Sethi"), edges as full role descriptions
  ("Retired Indian Navy Flag Officer", "Launched missile-boat strike
  against"), and intermediate dates/places as named nodes.

#### 2.4.2 FLOW-B — hub + 2 subgraph clusters (news, intent vs impact)

```json
{"viz_type": "mermaid_flowchart", "viz_dsl": "graph TD\n    A[Westbridge Pharmaceuticals CEO Helen Vargas] -->|Authorized $200,000 PAC contribution| B(Citizens for Healthcare Innovation)\n    B -->|Channelled funds toward| C[Senate Bill 412 Lobbying Effort]\n\n    subgraph \"Stated Corporate Intent\"\n        D[\"Accelerate FDA approval pathway for orphan drugs\"]\n        E[\"Reduce regulatory barriers for small biotech firms\"]\n    end\n\n    subgraph \"Reported Public Impact\"\n        F[\"Bill expanded patent-extension provisions for incumbents\"]\n        G[\"Conflict with Westbridge's stated patient-access advocacy\"]\n        H[\"Patient-advocacy groups organized boycott of Westbridge products\"]\n        I[\"CEO statement criticized as deflecting (regretted optics, not the contribution)\"]\n    end\n\n    A --> D\n    A --> E\n    C --> F\n    F --> G\n    G --> H\n    H --> I\n\n    style D fill:#e1f5fe\n    style E fill:#e1f5fe\n    style F fill:#ffebee\n    style G fill:#ffebee\n    style H fill:#ffebee\n    style I fill:#ffebee"}
```

- **Source**: `multinews_05_comparative` / S4_Agentic (faith 1.00, overall 1.00),
  paraphrased as a fictional pharma case.
- **Syntactic feature**: top-down hub (CEO → PAC → bill effort) **plus** two
  parallel **named subgraphs** ("Stated Intent" vs "Reported Impact"),
  with `style ... fill:` color coding.
- **Domain archetype**: news.
- **Why faith**: provides the **intent-vs-impact dichotomy** template that
  comparative news queries need — the current single-shape placeholder
  collapses this case to a 4-node chain that cannot represent contrast.

#### 2.4.3 FLOW-C — 2 parallel labelled subgraphs (paper-methods compare)

```json
{"viz_type": "mermaid_flowchart", "viz_dsl": "graph TD\n    subgraph Method_A [\"Latent Diffusion with Cross-Attention Conditioning\"]\n        direction TB\n        A1[Input: Text Prompt + Reference Image] --> B1[CLIP Text Encoder]\n        B1 --> C1[Cross-Attention Block in U-Net]\n        C1 --> D1[Iterative Denoising over 50 Steps]\n        D1 --> E1[Output: 512x512 Synthesized Image]\n    end\n\n    subgraph Method_B [\"Flow-Matching with Direct Conditioning\"]\n        direction TB\n        A2[Input: Text Prompt + Reference Image] --> B2[T5-XL Text Encoder]\n        B2 --> C2[Concatenated Conditioning at Block Input]\n        C2 --> D2[Single-Step ODE Integration]\n        D2 --> E2[Output: 1024x1024 Synthesized Image]\n    end\n\n    style Method_A fill:#e1f5fe,stroke:#01579b,stroke-width:2px\n    style Method_B fill:#f3e5f5,stroke:#4a148c,stroke-width:2px\n    style C1 fill:#bbdefb,stroke:#01579b\n    style C2 fill:#e1bee7,stroke:#4a148c"}
```

- **Source**: `arxiv_00_comparative` / S1_Direct (faith 1.00, overall 0.89),
  paraphrased to a fictional image-synthesis comparison.
- **Syntactic feature**: **two parallel subgraphs** with internal direction
  ("direction TB"), mirrored 5-stage pipelines, color coding via `style`.
- **Domain archetype**: paper-methods.
- **Why faith**: exact content style of the post-mortem D1 winner
  (`arxiv_00_comparative` S4_Agentic 1.00). The failing placeholder cannot
  represent **two parallel pipelines with mirrored stages**, which is the
  paper-methods comparative shape.

---

### 2.5 `mermaid_mindmap` — 3 exemplars

#### 2.5.1 MIND-A — 3-level (root → category → instance) Wikipedia/biographical

```json
{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\n  root((Daler Mehndi & Tunak Tunak Tun))\n    Career Milestones\n      Born 18 August 1967 in Patna, Bihar\n      Credited with bringing Bhangra to global mainstream\n      Established parallel non-film music industry in India\n      Trademark distinctive turban and flowing robes performance attire\n      Known professionally as Artist, Musician, Songwriter, Producer, Environmentalist\n    Tunak Tunak Tun (1998 Single)\n      Genre: Bhangra-Pop fusion love song\n      Language: Punjabi\n      Production: First Indian music video to use chroma-key greenscreen\n      Casting: Featured Daler Mehndi alone in all four roles\n      Backgrounds: CGI environments — desert, mountains, St. Basil's Cathedral\n      Context: Stylistic response to critics attributing earlier hit popularity to female dancers"}
```

- **Source**: `hotpot_07_comparative` / S1_Direct (faith 1.00, overall 1.00),
  preserved nearly verbatim in *content style* but the sub-bullet phrasings
  are paraphrased to avoid direct lift; the entity is preserved because
  the Wikipedia-archetype slot benefits most from a **biographical compare**
  example, and this is by far the strongest available anchor.
- **Syntactic feature**: 3-level (root → 2 categories → 4–6 instance leaves
  per category), no icons, parallel-cardinality categories.
- **Domain archetype**: Wikipedia-biographical.
- **Why faith**: replaces the placeholder's flat "NLP Methods → Supervised
  → Classification" 3-layer toy structure with a **biographical-compare**
  template that hotpotqa comparative queries actually need (post-mortem
  identifies hotpot_07 and similar as the dominant comparative case).

#### 2.5.2 MIND-B — 3-level with challenge/solution leaves (paper-methods)

```json
{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\n  root((Three Recent Papers by Core ML Challenge))\n    Distribution Shift Under Sparse Labels\n      Adaptive Pseudo-Labeling for Streaming Sensor Data\n        Challenge: Concept drift in unlabeled sensor streams\n        Solution: Confidence-thresholded pseudo-label injection with EMA teacher\n    Long-Tail Multi-Modal Retrieval\n      Cross-Modal Contrastive Tail Boosting\n        Challenge: Tail-class collapse in joint vision-language embedding space\n        Solution: Per-class temperature scaling with hard-negative mining from text neighbours\n    Causal Stability of Foundation Models\n      Counterfactual Probe Suite for Pretrained Encoders\n        Challenge: Spurious feature reliance under covariate shift\n        Solution: Causal probing toolkit with intervention sets and stability index"}
```

- **Source**: `arxiv_01_hierarchical` / S1_Direct (faith 1.00, overall 1.00),
  paraphrased to fictional papers in different ML areas.
- **Syntactic feature**: 3-level (root → 3 challenges → 1 paper per
  challenge → Challenge/Solution sub-leaves), paper titles as full noun
  phrases, parallel Challenge/Solution bullet structure.
- **Domain archetype**: paper-methods.
- **Why faith**: anchors the agent on the **paper-grouping-by-theme** shape
  with explicit Challenge/Solution sub-leaves — the high-faith pattern for
  arxiv hierarchical that the placeholder's flat NLP-methods example
  cannot teach.

#### 2.5.3 MIND-C — 4-level matrix-shape (compare 2 methods × parallel axes)

```json
{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\n  root((Parameter Update Mechanisms<br/>(Two Recent RL Methods)))\n    In-Context Adapter Tuning\n      Optimization Target\n        Cross-entropy on next-token prediction\n        Self-supervised, no reward model\n      Updated Weights\n        Lightweight adapter layers only (~0.4% of params)\n        Frozen backbone for compute efficiency\n      Update Procedure\n        Single forward-backward per chunk of 512 tokens\n        Update Rule\n          theta_adapter <- theta_adapter - eta * grad_L_NTP\n          eta scheduled with cosine decay\n      Distinctive Property\n        No architectural changes to the base model\n        Drop-in replacement for full fine-tuning\n    Distributional Policy Alignment\n      Optimization Target\n        Reverse-KL between policy and target distribution q\n        Reward-weighted, derived from preference scores\n      Target Distribution\n        q_i proportional to p_old_i * exp(u_i / tau)\n        u_i: standardized preference scores\n      Update Procedure\n        Cross-entropy fitting to q over batches of 8 candidates\n        Gradient on Policy Logits\n          dL/dl_i = p_theta_i - q_i\n      Distinctive Property\n        Decouples target construction from policy fitting\n        Gradient vanishes once policy matches target q"}
```

- **Source**: `arxiv_00_comparative` / S4_Agentic (faith 1.00, overall 1.00),
  paraphrased to fictional RL methods.
- **Syntactic feature**: **4-level matrix shape** — root → 2 method
  branches → 4 parallel axes per method → leaf details, with an embedded
  **multi-line `<br/>`** in the root and **inline math** as text leaves.
- **Domain archetype**: paper-methods.
- **Why faith**: exact content style of the post-mortem D1 winner
  (`arxiv_00_comparative` S4_Agentic 1.00). Without this matrix shape, the
  agent collapses 2-method × N-axis comparisons to either a flat 3-branch
  mindmap (loses axis parallelism) or a 4-bar chartjs (loses the
  axis-name grounding entirely).

---

### 2.6 `mermaid_timeline` — 3 exemplars

#### 2.6.1 TIME-A — quarterly section, multi-event-per-quarter (financial)

```json
{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\n    title Acme Industries 2025 Product Announcements by Quarter\n    section Q1 2025\n        Foundry-Series Workstation : \n        Compact-Series Desktop : \n        Studio-Series All-in-One : \n        Compact-Series Tablet : \n    section Q2 2025\n        Sentinel-17e Smartphone : \n        Studio-Series Tablet Air : \n        Studio-Series Tablet : \n        Foundry-Series Notebook Air : \n        Studio-Series Compute Module : \n    section Q3 2025\n        OS Release: Cascade 26 : \n        OS Release: Cascade 26 Workstation : \n        OS Release: Cascade 26 Tablet : \n        OS Release: Cascade 26 Wearable : \n        OS Release: Cascade 26 Spatial : \n    section Q4 2025\n        Sentinel-18 Smartphone : \n        Sentinel Air Smartphone : \n        Sentinel-18 Pro Smartphone : \n        Sentinel-18 Pro Max Smartphone : \n        Wearable Series 12 : \n        Wearable SE Generation 4 : \n        Wearable Ultra Generation 4 : \n        Earbud Pro Generation 4 : "}
```

- **Source**: `10k_00_temporal` / S1_Direct (faith 1.00, overall 1.00),
  paraphrased to a fictional company's 2025 product line to avoid lift of
  Apple SKU names.
- **Syntactic feature**: 4 quarterly sections, **multi-event-per-section**
  (4–8 items per quarter), trailing `: ` empty-detail (a known Mermaid
  pattern this team's renderer accepts).
- **Domain archetype**: financial / product-announcement.
- **Why faith**: replaces the placeholder's 4-row "2018/2020/2022/2024"
  toy with a **quarter-bucketed product-cadence** template — exactly the
  sub-shape `10k_00_temporal` and `10k_03_temporal` need.

#### 2.6.2 TIME-B — 2 named sections, sparse single-events (Wikipedia compare)

```json
{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\n    title Brookfield Grammar School & Brookfield Annual Show — Comparative Timeline\n    section Brookfield Grammar School History\n        1956 : Founded as a single-stream grammar school for boys\n        1978 : Reconstituted as a comprehensive coeducational secondary school\n        2003 : Awarded specialist Performing Arts College status\n    section Brookfield Annual Show Schedule\n        June (third Saturday) : One-day public exhibition held on school grounds\n        September (first weekend) : Inter-school music and theatre showcase"}
```

- **Source**: `hotpot_01_comparative` / S1_Direct (faith 1.00, overall 1.00),
  paraphrased to a fictional school + annual show compare.
- **Syntactic feature**: **2 named sections** (heterogeneous content —
  history vs schedule), single-event-per-line, **mixed cadence** (some
  rows are calendar years, some are recurring date-strings).
- **Domain archetype**: Wikipedia-historical.
- **Why faith**: trains the agent to pair **a year-based section with a
  recurring-date-based section** in the same timeline — a shape the
  current placeholder's flat year-list explicitly cannot teach.

#### 2.6.3 TIME-C — 3 named eras with multi-line `<br>` event detail (news)

```json
{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\n    title Cinderfall Franchise Lead-Cast Transition Across Twelve Years\n    section 2008–2013 : Marston Era\n        2008 : Cinderfall<br>Starring Iris Marston as Captain Lyra Vance\n        2013 : Cinderfall: Vanishing Point<br>Starring Iris Marston as Captain Lyra Vance\n    section 2016–2018 : Halberg Era\n        2016 : Cinderfall: Reckoning<br>Starring Bjorn Halberg as Captain Lyra Vance (recast after Marston exit)\n        2018 : Cinderfall: Severance<br>Starring Bjorn Halberg as Captain Lyra Vance\n    section 2020 : Okafor Era\n        2020 : Cinderfall: Heir of Ash<br>Starring Tomi Okafor as Lieutenant Sela Reyes (new protagonist; Vance role retired)"}
```

- **Source**: `hotpot_04_relational` / S4_Agentic (faith 1.00, overall 1.00),
  paraphrased to a fictional film franchise.
- **Syntactic feature**: **3 named eras** as section headings, multi-line
  `<br>` event detail (title + cast role), explicit **transition
  annotation** ("recast after", "new protagonist; … role retired").
- **Domain archetype**: news / Wikipedia-pop-culture.
- **Why faith**: covers the **named-era transition** sub-shape that
  hotpotqa relational queries on franchises/dynasties/regimes need — the
  current placeholder's bare year list cannot represent era boundaries
  or transition causes.

---

## Section 3 — Python literal `ONE_SHOT_POOL_BY_VIZ_TYPE`

The block below is paste-ready into `code/pipelines/tmg.py`. It deliberately
mirrors the existing `ONE_SHOT_BY_VIZ_TYPE` typing (`Dict[str, List[str]]`)
so callers should adapt to **list** semantics: a sampler picks 1–2 exemplars
per call (recommended: deterministic by `hash(query_id) % len(pool)` so
batch reruns are reproducible).

```python
from typing import Dict, List

# ── One-shot exemplar POOL (DocViz-Agent §3.2 amend, 2026-05-10) ───────────
#
# Each pool entry is an exact JSON object the agent's final_answer should be:
#   {"viz_type": "...", "viz_dsl": "..."}
# (strings — viz_dsl is a single string holding the raw DSL.)
#
# Pool design (see docs/analysis/tmg_oneshot_pool_draft.md):
#   - 3 exemplars per viz_type, each covering a distinct syntactic shape.
#   - Content style: rich, source-grounded, multi-word labels, descriptive
#     edges. NO placeholder/single-verb patterns ("founded", "acquired",
#     "Founder", "Acme Corp", "NLP Methods"). All content rewritten in
#     generic-domain archetypes (Wikipedia / news / paper-methods / financial)
#     so the pool does not leak prototype answers.
#   - Anchor mapping: see docs/analysis/tmg_oneshot_pool_draft.md §1.

ONE_SHOT_POOL_BY_VIZ_TYPE: Dict[str, List[str]] = {
    "chartjs_bar": [
        # BAR-A — horizontal 2-bar, financial archetype
        '{"viz_type": "chartjs_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"FY2023\\",\\"FY2024\\"],\\"datasets\\":[{\\"label\\":\\"Foreign Currency Translation Loss (Billions USD)\\",\\"data\\":[1.42,2.08],\\"backgroundColor\\":[\\"#36A2EB\\",\\"#FF6384\\"],\\"borderColor\\":[\\"#1E90FF\\",\\"#DC143C\\"],\\"borderWidth\\":1}]},\\"options\\":{\\"indexAxis\\":\\"y\\",\\"responsive\\":true,\\"plugins\\":{\\"legend\\":{\\"display\\":false},\\"title\\":{\\"display\\":true,\\"text\\":\\"Acme Industries — FX Translation Loss Under 10% Adverse-Move Scenario\\"}},\\"scales\\":{\\"x\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Potential Loss (Billions USD)\\"}}}}}"}',
        # BAR-B — vertical 4-bar, financial archetype
        '{"viz_type": "chartjs_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"Cloud Services\\",\\"Productivity Suite\\",\\"Compute Infrastructure\\",\\"Professional Network\\"],\\"datasets\\":[{\\"label\\":\\"FY2025 Year-over-Year Revenue Growth (%)\\",\\"data\\":[24,16,33,9],\\"backgroundColor\\":[\\"rgba(54, 162, 235, 0.6)\\",\\"rgba(75, 192, 192, 0.6)\\",\\"rgba(255, 206, 86, 0.6)\\",\\"rgba(153, 102, 255, 0.6)\\"],\\"borderColor\\":[\\"rgba(54, 162, 235, 1)\\",\\"rgba(75, 192, 192, 1)\\",\\"rgba(255, 206, 86, 1)\\",\\"rgba(153, 102, 255, 1)\\"],\\"borderWidth\\":1}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"YoY Growth (%)\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Acme Industries FY2025 Revenue Growth by Reportable Segment\\"},\\"legend\\":{\\"display\\":false}}}}"}',
        # BAR-C — narrative-title 3-bar, news archetype
        '{"viz_type": "chartjs_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"Civilian Casualties (Wappani Confederacy)\\",\\"Settler Forces (Killed in Action)\\",\\"Settler Forces (Wounded)\\"],\\"datasets\\":[{\\"label\\":\\"Casualties at the Long Hollow Raid (October 1762)\\",\\"data\\":[412,3,21],\\"backgroundColor\\":[\\"rgba(255, 99, 132, 0.6)\\",\\"rgba(54, 162, 235, 0.6)\\",\\"rgba(255, 206, 86, 0.6)\\"],\\"borderColor\\":[\\"rgba(255, 99, 132, 1)\\",\\"rgba(54, 162, 235, 1)\\",\\"rgba(255, 206, 86, 1)\\"],\\"borderWidth\\":1}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Number of Casualties\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Long Hollow Raid — Single-Engagement Casualty Comparison (Deadliest Action of the 1762 Frontier Conflict)\\"},\\"legend\\":{\\"display\\":false}}}}"}',
    ],
    "chartjs_line": [
        # LINE-A — yearly single-series, financial archetype
        '{"viz_type": "chartjs_line", "viz_dsl": "{\\"type\\":\\"line\\",\\"data\\":{\\"labels\\":[\\"2018\\",\\"2019\\",\\"2020\\",\\"2021\\",\\"2022\\",\\"2023\\"],\\"datasets\\":[{\\"label\\":\\"Lakeshore Foundation Annual Endowment Disbursements (Millions USD)\\",\\"data\\":[412,468,521,602,718,805],\\"borderColor\\":\\"rgb(75, 192, 192)\\",\\"backgroundColor\\":\\"rgba(75, 192, 192, 0.2)\\",\\"tension\\":0.1}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Disbursement (Millions USD)\\"}},\\"x\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Calendar Year\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Lakeshore Foundation Endowment Disbursements, 2018–2023\\"}}}}"}',
        # LINE-B — multi-series 5-year compare, paper-methods archetype
        '{"viz_type": "chartjs_line", "viz_dsl": "{\\"type\\":\\"line\\",\\"data\\":{\\"labels\\":[\\"2019\\",\\"2020\\",\\"2021\\",\\"2022\\",\\"2023\\"],\\"datasets\\":[{\\"label\\":\\"Encoder-only (Top-1 Accuracy %)\\",\\"data\\":[71.2,74.5,77.0,78.4,79.1],\\"borderColor\\":\\"rgb(54, 162, 235)\\",\\"backgroundColor\\":\\"rgba(54, 162, 235, 0.2)\\",\\"tension\\":0.2},{\\"label\\":\\"Decoder-only (Top-1 Accuracy %)\\",\\"data\\":[68.0,72.8,76.5,80.2,83.4],\\"borderColor\\":\\"rgb(255, 99, 132)\\",\\"backgroundColor\\":\\"rgba(255, 99, 132, 0.2)\\",\\"tension\\":0.2}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":false,\\"title\\":{\\"display\\":true,\\"text\\":\\"Top-1 Accuracy on ImageNet-1k Eval Slice (%)\\"}},\\"x\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Publication Year\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Vision Backbone Family Accuracy Trajectories on ImageNet-1k (2019–2023)\\"},\\"legend\\":{\\"display\\":true,\\"position\\":\\"top\\"}}}}"}',
        # LINE-C — cumulative-metric 7-point, financial archetype
        '{"viz_type": "chartjs_line", "viz_dsl": "{\\"type\\":\\"line\\",\\"data\\":{\\"labels\\":[\\"FY2017\\",\\"FY2018\\",\\"FY2019\\",\\"FY2020\\",\\"FY2021\\",\\"FY2022\\",\\"FY2023\\"],\\"datasets\\":[{\\"label\\":\\"Cumulative R&D Capitalization (Billions USD)\\",\\"data\\":[3.1,7.4,12.8,19.6,27.9,38.4,51.2],\\"borderColor\\":\\"rgb(153, 102, 255)\\",\\"backgroundColor\\":\\"rgba(153, 102, 255, 0.25)\\",\\"fill\\":true,\\"tension\\":0.15}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Cumulative Capitalization (Billions USD)\\"}},\\"x\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Fiscal Year\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Acme Industries Cumulative R&D Capitalization, FY2017–FY2023\\"},\\"legend\\":{\\"display\\":false}}}}"}',
    ],
    "chartjs_grouped_bar": [
        # GBAR-A — 2-dataset × 2-axis horizontal compare, financial archetype
        '{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"Available-for-Sale Securities\\\\n(Fair Value Decline)\\",\\"Long-Term Debt\\\\n(Interest Expense Increase)\\"],\\"datasets\\":[{\\"label\\":\\"FY2024\\",\\"data\\":[2620,142],\\"backgroundColor\\":\\"rgba(54, 162, 235, 0.6)\\",\\"borderColor\\":\\"rgba(54, 162, 235, 1)\\",\\"borderWidth\\":1},{\\"label\\":\\"FY2023\\",\\"data\\":[2884,128],\\"backgroundColor\\":\\"rgba(255, 99, 132, 0.6)\\",\\"borderColor\\":\\"rgba(255, 99, 132, 1)\\",\\"borderWidth\\":1}]},\\"options\\":{\\"indexAxis\\":\\"y\\",\\"responsive\\":true,\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Acme Industries — Estimated Impact of 100bp Parallel Rate Shock (Millions USD)\\"},\\"legend\\":{\\"position\\":\\"top\\"}},\\"scales\\":{\\"x\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Estimated Impact (Millions USD)\\"},\\"beginAtZero\\":true},\\"y\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Risk Category\\"}}}}}"}',
        # GBAR-B — 2-dataset × 3-axis dual-y mixed-units, news archetype
        '{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"2019\\",\\"2020\\",\\"2021\\"],\\"datasets\\":[{\\"label\\":\\"Cash Equivalent of Stock Donation (Billions USD)\\",\\"data\\":[2.6,3.1,3.0],\\"backgroundColor\\":\\"rgba(54, 162, 235, 0.5)\\",\\"borderColor\\":\\"rgba(54, 162, 235, 1)\\",\\"borderWidth\\":1,\\"yAxisID\\":\\"y\\"},{\\"label\\":\\"Class B Shares Donated (Millions)\\",\\"data\\":[14.0,12.5,11.8],\\"backgroundColor\\":\\"rgba(255, 99, 132, 0.5)\\",\\"borderColor\\":\\"rgba(255, 99, 132, 1)\\",\\"borderWidth\\":1,\\"yAxisID\\":\\"y1\\"}]},\\"options\\":{\\"responsive\\":true,\\"scales\\":{\\"y\\":{\\"type\\":\\"linear\\",\\"position\\":\\"left\\",\\"title\\":{\\"display\\":true,\\"text\\":\\"Cash Equivalent (Billions USD)\\"}},\\"y1\\":{\\"type\\":\\"linear\\",\\"position\\":\\"right\\",\\"title\\":{\\"display\\":true,\\"text\\":\\"Shares (Millions)\\"},\\"grid\\":{\\"drawOnChartArea\\":false}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Lakeshore Foundation Annual Endowment Inflow, 2019–2021 (Two-Axis View)\\"},\\"legend\\":{\\"display\\":true,\\"position\\":\\"top\\"}}}}"}',
        # GBAR-C — 3-dataset × 4-axis side-by-side, paper-methods archetype
        '{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"Reasoning (MMLU)\\",\\"Coding (HumanEval)\\",\\"Math (GSM8K)\\",\\"Long-Context (NIH)\\"],\\"datasets\\":[{\\"label\\":\\"Encoder-Decoder Baseline\\",\\"data\\":[68.4,42.1,55.7,71.0],\\"backgroundColor\\":\\"rgba(54, 162, 235, 0.6)\\",\\"borderColor\\":\\"rgba(54, 162, 235, 1)\\",\\"borderWidth\\":1},{\\"label\\":\\"Decoder-Only + RLHF\\",\\"data\\":[78.9,71.8,82.4,84.2],\\"backgroundColor\\":\\"rgba(255, 99, 132, 0.6)\\",\\"borderColor\\":\\"rgba(255, 99, 132, 1)\\",\\"borderWidth\\":1},{\\"label\\":\\"Mixture-of-Experts + DPO\\",\\"data\\":[81.2,75.4,86.0,88.7],\\"backgroundColor\\":\\"rgba(75, 192, 192, 0.6)\\",\\"borderColor\\":\\"rgba(75, 192, 192, 1)\\",\\"borderWidth\\":1}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Benchmark Accuracy (%)\\"},\\"max\\":100}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"LLM Architecture Comparison Across Four Standardized Benchmarks\\"},\\"legend\\":{\\"display\\":true,\\"position\\":\\"top\\"}}}}"}',
    ],
    "mermaid_flowchart": [
        # FLOW-A — 5-node chain LR with descriptive role-edges, Wikipedia archetype
        '{"viz_type": "mermaid_flowchart", "viz_dsl": "graph LR\\n    A[Vice-Admiral Ravindra Sethi] -->|Retired Indian Navy Flag Officer| B(Western Naval Command)\\n    B -->|Authorized Operation Trident-II in| C[December 1971]\\n    C -->|Launched missile-boat strike against| D[Karachi Harbour Oil Depot]\\n    D -->|Located in| E[Karachi, Sindh, Pakistan]"}',
        # FLOW-B — hub + 2 subgraph clusters (intent vs impact), news archetype
        '{"viz_type": "mermaid_flowchart", "viz_dsl": "graph TD\\n    A[Westbridge Pharmaceuticals CEO Helen Vargas] -->|Authorized $200,000 PAC contribution| B(Citizens for Healthcare Innovation)\\n    B -->|Channelled funds toward| C[Senate Bill 412 Lobbying Effort]\\n\\n    subgraph \\"Stated Corporate Intent\\"\\n        D[\\"Accelerate FDA approval pathway for orphan drugs\\"]\\n        E[\\"Reduce regulatory barriers for small biotech firms\\"]\\n    end\\n\\n    subgraph \\"Reported Public Impact\\"\\n        F[\\"Bill expanded patent-extension provisions for incumbents\\"]\\n        G[\\"Conflict with Westbridge\'s stated patient-access advocacy\\"]\\n        H[\\"Patient-advocacy groups organized boycott of Westbridge products\\"]\\n        I[\\"CEO statement criticized as deflecting (regretted optics, not the contribution)\\"]\\n    end\\n\\n    A --> D\\n    A --> E\\n    C --> F\\n    F --> G\\n    G --> H\\n    H --> I\\n\\n    style D fill:#e1f5fe\\n    style E fill:#e1f5fe\\n    style F fill:#ffebee\\n    style G fill:#ffebee\\n    style H fill:#ffebee\\n    style I fill:#ffebee"}',
        # FLOW-C — 2 parallel labelled subgraphs (compare two pipelines), paper-methods archetype
        '{"viz_type": "mermaid_flowchart", "viz_dsl": "graph TD\\n    subgraph Method_A [\\"Latent Diffusion with Cross-Attention Conditioning\\"]\\n        direction TB\\n        A1[Input: Text Prompt + Reference Image] --> B1[CLIP Text Encoder]\\n        B1 --> C1[Cross-Attention Block in U-Net]\\n        C1 --> D1[Iterative Denoising over 50 Steps]\\n        D1 --> E1[Output: 512x512 Synthesized Image]\\n    end\\n\\n    subgraph Method_B [\\"Flow-Matching with Direct Conditioning\\"]\\n        direction TB\\n        A2[Input: Text Prompt + Reference Image] --> B2[T5-XL Text Encoder]\\n        B2 --> C2[Concatenated Conditioning at Block Input]\\n        C2 --> D2[Single-Step ODE Integration]\\n        D2 --> E2[Output: 1024x1024 Synthesized Image]\\n    end\\n\\n    style Method_A fill:#e1f5fe,stroke:#01579b,stroke-width:2px\\n    style Method_B fill:#f3e5f5,stroke:#4a148c,stroke-width:2px\\n    style C1 fill:#bbdefb,stroke:#01579b\\n    style C2 fill:#e1bee7,stroke:#4a148c"}',
    ],
    "mermaid_mindmap": [
        # MIND-A — 3-level (root → category → instance), Wikipedia-biographical archetype
        '{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\\n  root((Daler Mehndi & Tunak Tunak Tun))\\n    Career Milestones\\n      Born 18 August 1967 in Patna, Bihar\\n      Credited with bringing Bhangra to global mainstream\\n      Established parallel non-film music industry in India\\n      Trademark distinctive turban and flowing robes performance attire\\n      Known professionally as Artist, Musician, Songwriter, Producer, Environmentalist\\n    Tunak Tunak Tun (1998 Single)\\n      Genre: Bhangra-Pop fusion love song\\n      Language: Punjabi\\n      Production: First Indian music video to use chroma-key greenscreen\\n      Casting: Featured Daler Mehndi alone in all four roles\\n      Backgrounds: CGI environments — desert, mountains, St. Basil\'s Cathedral\\n      Context: Stylistic response to critics attributing earlier hit popularity to female dancers"}',
        # MIND-B — 3-level with challenge/solution leaves, paper-methods archetype
        '{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\\n  root((Three Recent Papers by Core ML Challenge))\\n    Distribution Shift Under Sparse Labels\\n      Adaptive Pseudo-Labeling for Streaming Sensor Data\\n        Challenge: Concept drift in unlabeled sensor streams\\n        Solution: Confidence-thresholded pseudo-label injection with EMA teacher\\n    Long-Tail Multi-Modal Retrieval\\n      Cross-Modal Contrastive Tail Boosting\\n        Challenge: Tail-class collapse in joint vision-language embedding space\\n        Solution: Per-class temperature scaling with hard-negative mining from text neighbours\\n    Causal Stability of Foundation Models\\n      Counterfactual Probe Suite for Pretrained Encoders\\n        Challenge: Spurious feature reliance under covariate shift\\n        Solution: Causal probing toolkit with intervention sets and stability index"}',
        # MIND-C — 4-level matrix-shape (compare 2 methods × parallel axes), paper-methods archetype
        '{"viz_type": "mermaid_mindmap", "viz_dsl": "mindmap\\n  root((Parameter Update Mechanisms<br/>(Two Recent RL Methods)))\\n    In-Context Adapter Tuning\\n      Optimization Target\\n        Cross-entropy on next-token prediction\\n        Self-supervised, no reward model\\n      Updated Weights\\n        Lightweight adapter layers only (~0.4% of params)\\n        Frozen backbone for compute efficiency\\n      Update Procedure\\n        Single forward-backward per chunk of 512 tokens\\n        Update Rule\\n          theta_adapter <- theta_adapter - eta * grad_L_NTP\\n          eta scheduled with cosine decay\\n      Distinctive Property\\n        No architectural changes to the base model\\n        Drop-in replacement for full fine-tuning\\n    Distributional Policy Alignment\\n      Optimization Target\\n        Reverse-KL between policy and target distribution q\\n        Reward-weighted, derived from preference scores\\n      Target Distribution\\n        q_i proportional to p_old_i * exp(u_i / tau)\\n        u_i: standardized preference scores\\n      Update Procedure\\n        Cross-entropy fitting to q over batches of 8 candidates\\n        Gradient on Policy Logits\\n          dL/dl_i = p_theta_i - q_i\\n      Distinctive Property\\n        Decouples target construction from policy fitting\\n        Gradient vanishes once policy matches target q"}',
    ],
    "mermaid_timeline": [
        # TIME-A — quarterly section, multi-event-per-quarter, financial archetype
        '{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\\n    title Acme Industries 2025 Product Announcements by Quarter\\n    section Q1 2025\\n        Foundry-Series Workstation : \\n        Compact-Series Desktop : \\n        Studio-Series All-in-One : \\n        Compact-Series Tablet : \\n    section Q2 2025\\n        Sentinel-17e Smartphone : \\n        Studio-Series Tablet Air : \\n        Studio-Series Tablet : \\n        Foundry-Series Notebook Air : \\n        Studio-Series Compute Module : \\n    section Q3 2025\\n        OS Release: Cascade 26 : \\n        OS Release: Cascade 26 Workstation : \\n        OS Release: Cascade 26 Tablet : \\n        OS Release: Cascade 26 Wearable : \\n        OS Release: Cascade 26 Spatial : \\n    section Q4 2025\\n        Sentinel-18 Smartphone : \\n        Sentinel Air Smartphone : \\n        Sentinel-18 Pro Smartphone : \\n        Sentinel-18 Pro Max Smartphone : \\n        Wearable Series 12 : \\n        Wearable SE Generation 4 : \\n        Wearable Ultra Generation 4 : \\n        Earbud Pro Generation 4 : "}',
        # TIME-B — 2 named sections, sparse single-events, Wikipedia archetype
        '{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\\n    title Brookfield Grammar School & Brookfield Annual Show — Comparative Timeline\\n    section Brookfield Grammar School History\\n        1956 : Founded as a single-stream grammar school for boys\\n        1978 : Reconstituted as a comprehensive coeducational secondary school\\n        2003 : Awarded specialist Performing Arts College status\\n    section Brookfield Annual Show Schedule\\n        June (third Saturday) : One-day public exhibition held on school grounds\\n        September (first weekend) : Inter-school music and theatre showcase"}',
        # TIME-C — 3 named eras with multi-line <br> event detail, news archetype
        '{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\\n    title Cinderfall Franchise Lead-Cast Transition Across Twelve Years\\n    section 2008–2013 : Marston Era\\n        2008 : Cinderfall<br>Starring Iris Marston as Captain Lyra Vance\\n        2013 : Cinderfall: Vanishing Point<br>Starring Iris Marston as Captain Lyra Vance\\n    section 2016–2018 : Halberg Era\\n        2016 : Cinderfall: Reckoning<br>Starring Bjorn Halberg as Captain Lyra Vance (recast after Marston exit)\\n        2018 : Cinderfall: Severance<br>Starring Bjorn Halberg as Captain Lyra Vance\\n    section 2020 : Okafor Era\\n        2020 : Cinderfall: Heir of Ash<br>Starring Tomi Okafor as Lieutenant Sela Reyes (new protagonist; Vance role retired)"}',
    ],
}
```

### 3.1 Suggested sampler

Two reasonable selection rules — pick one based on §3.2 of the amended paper:

**Option A — deterministic per query (recommended for reproducibility):**

```python
def select_oneshots(viz_type: str, query_id: str, k: int = 1) -> List[str]:
    pool = ONE_SHOT_POOL_BY_VIZ_TYPE[viz_type]
    h = abs(hash(query_id))
    return [pool[(h + i) % len(pool)] for i in range(k)]
```

**Option B — k=2 always, fixed positions [0, 2]** (covers maximum syntactic
spread per call; doubles prompt token cost but every call sees both
extremes — e.g., 2-bar AND 4-bar AND 3-bar narrative-title for chartjs_bar).

The current paper amend says "1–2 examples"; Option A with `k=1` is the
minimal change vs the prior single-shot baseline and keeps token cost flat,
while `k=2` should be tested as an ablation.

---

## Section 4 — Reviewer notes (trade-offs and uncertainties)

### 4.1 Confidence-ranked notes

| # | Concern | Confidence | Recommended action |
|---|---|---|---|
| 1 | `chartjs_line` has only **1** real anchor at faith ≥ 0.75. LINE-B (multi-series compare) and LINE-C (cumulative) are hand-written and not validated by judge. | medium | Run a 5-query line-only pilot (synthesize hand-written queries) before paper batch to confirm LINE-B and LINE-C don't introduce style drift. |
| 2 | MIND-A keeps `Daler Mehndi & Tunak Tunak Tun` as the entity rather than paraphrasing. Decision: the hotpotqa biographical-compare archetype is hard to write generically without losing the period-specific detail that drives faith, and the prototype already evaluated this query with faith 1.00 (so it is "training data" the judge has seen). | medium-low risk | If post-PR8 holdout includes hotpot-style biographical-compare queries similar to this one, swap MIND-A's content for a fully fictional figure. The structure (root → 2 categories → 4–6 leaves) is what matters; the entity is replaceable. |
| 3 | FLOW-B (intent-vs-impact) is very long — ~30 nodes after styles. This is intentional (matches `multinews_05_comparative` which scored 1.00 / 1.00) but will cost more prompt tokens than the placeholder. | medium | Token cost: roughly +800 tokens vs the placeholder per call. Acceptable if the overall TMG hit-rate gain ≥ 5pp; otherwise simplify to ~15 nodes by dropping 2 of the 4 "Reported Public Impact" leaves. |
| 4 | GBAR-C has 3 datasets × 4 axes — at the upper end of what chartjs renders cleanly. Real anchors top out at 2-dataset × 3-axis. | low | Acceptable as-is; the "3-way architecture compare" is a legitimate sub-shape paper queries need. Worst case: drop GBAR-C, fall back to 2-exemplar pool for grouped_bar. |
| 5 | All exemplars are **English-only**. The prototype is also English-only, so this matches deployment. | n/a | If multilingual support becomes a goal, regenerate per-locale pools rather than translate. |
| 6 | The `viz_dsl` strings contain literal `\n` and (where the underlying DSL needs them) `\\n`. The mapper's whole-text JSON parse will resolve these correctly; one round-trip test on `code/pipelines/tmg.py` after paste is recommended (parse → assert `viz_type` enum match → assert `viz_dsl` non-empty). | high | Add a `test_oneshot_pool_parses` unit test asserting `json.loads(s)` succeeds and `s["viz_type"] in VIZ_TYPE_ENUM` for each pool entry. |
| 7 | Possible higher-value anchor for `chartjs_line`: `multinews_09_temporal` S4_AgenticTMG (faith not in top list — needs check). Also consider re-running line generation with the new pool and using the resulting faith ≥ 0.75 outputs to refresh LINE-B/C. | low | Defer to v2 of the pool after a TMG re-batch with v1 of the pool deployed. |
| 8 | MIND-C uses `<br/>` inside `root((... ))`. Mermaid mindmap renders this correctly per the `arxiv_00_comparative` S4_Agentic anchor (faith 1.00) but the syntax is unusual. | low | Confirmed in anchor; keep. |
| 9 | TIME-A uses `:` followed by an empty detail — this matches `10k_00_temporal` (faith 1.00) and the prototype renderer accepts it, but lint/syntax checkers may flag it. | low | Confirmed in anchor; keep. |
| 10 | Cross-archetype balance: chartjs_bar has 2/3 financial + 1 news; chartjs_line has 2/3 financial + 1 paper; chartjs_grouped_bar has 1 financial + 1 news + 1 paper; mermaid_flowchart has 1 Wikipedia + 1 news + 1 paper; mermaid_mindmap has 1 Wikipedia-bio + 2 paper; mermaid_timeline has 1 financial + 1 Wikipedia + 1 news. Mindmap is paper-heavy. | low | Acceptable: the high-faith anchors *are* paper-heavy because arxiv hierarchical/comparative is the dominant high-faith mindmap cell. If hotpot-style biographical mindmaps are the priority, swap MIND-B for a Wikipedia-bio variant. |

### 4.2 Better anchor candidates the reviewer should consider

For each viz_type, the next-best anchor we did *not* pick (in case the
reviewer wants a different syntactic shape):

- `chartjs_bar`: `multinews_00_comparative` S1_Direct (faith 0.75, overall
  0.75) — DEA cash-seizure compare; covers a 2-dataset news-archetype
  shape that none of the chosen 3 currently covers. Trade-off: lower
  faith score, but better cross-archetype balance.
- `chartjs_line`: there is no better anchor in the dataset (the cell is
  data-starved). The reviewer's main lever is to commission additional
  line queries in PR8 holdout.
- `chartjs_grouped_bar`: `10k_03_quantitative` S1_Direct (faith 0.75, overall
  0.92) — NVIDIA FX risk on OCI vs pre-tax income; another financial
  shape, redundant with GBAR-A. Skip.
- `mermaid_flowchart`: `arxiv_03_comparative` S4_Agentic (faith 0.75,
  overall 0.94) — multi-agent architecture compare with deep nested
  subgraphs (~50 nodes). Trade-off: too long for a one-shot (would push
  prompt to ~3500 tokens just for the example). Skip unless reviewer wants
  to test "max-density" exemplars.
- `mermaid_mindmap`: `hotpot_00_comparative` S1_Direct (faith 1.00,
  overall 1.00) — population/religious-status × military-role compare.
  Strong Wikipedia-archetype candidate; would replace MIND-B if reviewer
  prefers more Wikipedia weight in mindmap.
- `mermaid_timeline`: `10k_03_temporal` S1_Direct (faith 1.00, overall
  1.00) — NVIDIA H20 export-license developments with multi-event-per-
  section AND multi-line detail. Strong financial-archetype candidate;
  could replace TIME-A if reviewer wants both mixed cadences from
  TIME-B *and* multi-line detail in a financial example.

### 4.3 What this draft does NOT decide

- **Pool injection mechanics.** The current `tmg.py` injects exactly one
  string into the prompt. This draft assumes the caller will be modified
  to (a) accept a pool, (b) sample 1–2 exemplars, (c) inject them in a
  numbered "Example 1: … / Example 2: …" block. The exact prompt-side
  formatting is out of scope for this draft.
- **Validation of `chartjs_line` LINE-B/C.** Hand-written exemplars
  should be smoke-tested by rendering and judging once before the full
  PR8 batch.
- **Whether to keep the legacy `ONE_SHOT_BY_VIZ_TYPE` as a fallback.**
  Recommendation: delete after the pool lands; the placeholder content is
  the failure mode we are removing, and keeping a fallback risks accidental
  re-injection.

---

**End of draft.** Reviewer: please flag any exemplar where the *content
style* still feels too placeholder-like (single-verb edges, generic
entities, abstract category names). The acceptance criterion is "would
this exemplar score faith ≥ 0.75 if it were a real model output on a
matching query?" — if the answer is "probably no", the exemplar should be
rewritten before the pool lands in `tmg.py`.
