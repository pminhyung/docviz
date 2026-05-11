# `chartjs_grouped_bar` exemplar pool — revision v1

**Date**: 2026-05-10
**Status**: revision v1 (supersedes the `chartjs_grouped_bar` portion of
`docs/analysis/tmg_oneshot_pool_draft.md` v0). v0 archived; do **not**
edit it.

**Changes vs v0** (driven by `tmg_oneshot_pool_review.md`):
- Must-fix #1: GBAR-A `Acme Industries` → `Halverson Bancorp`.
- Must-fix #1 (Lakeshore reuse-disperse): GBAR-B `Lakeshore Foundation`
  → `Pemberton Charitable Trust` (Lakeshore is now used only by LINE-A).
- GBAR-C unchanged (paper-methods archetype, hand-written).
- Added consolidated variant (V4_consolidated measurement); see §2.

---

## 1. Pool variant (V4_pool measurement)

3 exemplars covering distinct `chartjs_grouped_bar` syntactic shapes.

### GBAR-A — 2-dataset × 2-axis horizontal compare, financial archetype

```json
{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"Available-for-Sale Securities\\n(Fair Value Decline)\",\"Long-Term Debt\\n(Interest Expense Increase)\"],\"datasets\":[{\"label\":\"FY2024\",\"data\":[2620,142],\"backgroundColor\":\"rgba(54, 162, 235, 0.6)\",\"borderColor\":\"rgba(54, 162, 235, 1)\",\"borderWidth\":1},{\"label\":\"FY2023\",\"data\":[2884,128],\"backgroundColor\":\"rgba(255, 99, 132, 0.6)\",\"borderColor\":\"rgba(255, 99, 132, 1)\",\"borderWidth\":1}]},\"options\":{\"indexAxis\":\"y\",\"responsive\":true,\"plugins\":{\"title\":{\"display\":true,\"text\":\"Halverson Bancorp — Estimated Impact of 100bp Parallel Rate Shock (Millions USD)\"},\"legend\":{\"position\":\"top\"}},\"scales\":{\"x\":{\"title\":{\"display\":true,\"text\":\"Estimated Impact (Millions USD)\"},\"beginAtZero\":true},\"y\":{\"title\":{\"display\":true,\"text\":\"Risk Category\"}}}}}"}
```

- **Anchor**: `10k_00_quantitative` / S1_Direct (faith 1.00, overall 1.00).
- **Syntactic feature**: 2 datasets (FY-pair) × 2 named risk categories /
  horizontal (`indexAxis: "y"`) / multi-line `\n` inside category labels for
  sub-qualifier.
- **Domain archetype**: financial (10-K interest-rate-risk disclosure).
- **Why faith**: teaches the agent the **side-by-side year compare** with
  **multi-line category labels** — both absent from the failing
  Speed/Accuracy/Cost placeholder.

### GBAR-B — 2-dataset × 3-axis dual-y mixed-units, news archetype

```json
{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"2019\",\"2020\",\"2021\"],\"datasets\":[{\"label\":\"Cash Equivalent of Stock Donation (Billions USD)\",\"data\":[2.6,3.1,3.0],\"backgroundColor\":\"rgba(54, 162, 235, 0.5)\",\"borderColor\":\"rgba(54, 162, 235, 1)\",\"borderWidth\":1,\"yAxisID\":\"y\"},{\"label\":\"Class B Shares Donated (Millions)\",\"data\":[14.0,12.5,11.8],\"backgroundColor\":\"rgba(255, 99, 132, 0.5)\",\"borderColor\":\"rgba(255, 99, 132, 1)\",\"borderWidth\":1,\"yAxisID\":\"y1\"}]},\"options\":{\"responsive\":true,\"scales\":{\"y\":{\"type\":\"linear\",\"position\":\"left\",\"title\":{\"display\":true,\"text\":\"Cash Equivalent (Billions USD)\"}},\"y1\":{\"type\":\"linear\",\"position\":\"right\",\"title\":{\"display\":true,\"text\":\"Shares (Millions)\"},\"grid\":{\"drawOnChartArea\":false}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Pemberton Charitable Trust Annual Endowment Inflow, 2019–2021 (Two-Axis View)\"},\"legend\":{\"display\":true,\"position\":\"top\"}}}}"}
```

- **Anchor**: `multinews_09_comparative` / S4_Agentic (faith 1.00, overall
  1.00); domain shifted to a fictional charitable trust.
- **Syntactic feature**: 2 datasets with **separate y-axes** (mixed units —
  Billions USD vs Millions of shares) × 3 yearly axes / top legend / right
  axis hides grid lines.
- **Domain archetype**: news / financial-philanthropy (distinct entity from
  LINE-A).
- **Why faith**: this is the **dual-y mixed-units** sub-shape — the failing
  placeholder uses identical units (Speed/Accuracy/Cost), which actively
  miscues the agent on the "two metrics with different scales" case.

### GBAR-C — 3-dataset × 4-axis side-by-side, paper-methods archetype

```json
{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"Reasoning (MMLU)\",\"Coding (HumanEval)\",\"Math (GSM8K)\",\"Long-Context (NIH)\"],\"datasets\":[{\"label\":\"Encoder-Decoder Baseline\",\"data\":[68.4,42.1,55.7,71.0],\"backgroundColor\":\"rgba(54, 162, 235, 0.6)\",\"borderColor\":\"rgba(54, 162, 235, 1)\",\"borderWidth\":1},{\"label\":\"Decoder-Only + RLHF\",\"data\":[78.9,71.8,82.4,84.2],\"backgroundColor\":\"rgba(255, 99, 132, 0.6)\",\"borderColor\":\"rgba(255, 99, 132, 1)\",\"borderWidth\":1},{\"label\":\"Mixture-of-Experts + DPO\",\"data\":[81.2,75.4,86.0,88.7],\"backgroundColor\":\"rgba(75, 192, 192, 0.6)\",\"borderColor\":\"rgba(75, 192, 192, 1)\",\"borderWidth\":1}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Benchmark Accuracy (%)\"},\"max\":100}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"LLM Architecture Comparison Across Four Standardized Benchmarks\"},\"legend\":{\"display\":true,\"position\":\"top\"}}}}"}
```

- **Source**: hand-written; anchored on `arxiv_00_comparative` (mindmap, faith
  1.00) for the architecture-comparison content style and on
  `10k_*_quantitative` GBAR (faith 1.00) for the JSON schema.
- **Syntactic feature**: **3 datasets** (largest fanout we keep) × 4 named
  benchmark axes / vertical / fixed `y.max: 100`.
- **Domain archetype**: paper-methods.
- **Why faith**: covers the paper-methods comparative case (3-way
  architecture eval) — exactly the cell where the failing placeholder
  produced faith=0 in the post-mortem (`arxiv_00_comparative` GBAR).

---

## 2. Consolidated variant (V4_consolidated measurement)

A single integrated example combining every `chartjs_grouped_bar` sub-pattern:

- **3 datasets** (compare 3 portfolios, not 2)
- **4 named non-temporal categories** with **multi-line `\n` sub-qualifier**
  inside each label (sector + sub-line)
- **horizontal orientation** (`indexAxis: "y"`)
- **single shared y-axis** with explicit unit (the dual-y mixed-units shape
  is hard to combine with 3 datasets on one chart and stays cleaner in
  GBAR-B; consolidated keeps shared-axis to maintain readability)
- **scope-qualified narrative title** with parenthetical exclusion clause
- top legend
- **explicit grid + `borderWidth: 1` per dataset** (matches GBAR-A style)

```json
{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"Equities\\n(Public Listed)\",\"Fixed Income\\n(Investment Grade)\",\"Real Assets\\n(Infrastructure & Real Estate)\",\"Private Markets\\n(PE / VC / Private Credit)\"],\"datasets\":[{\"label\":\"Conservative Mandate (FY2024)\",\"data\":[34,46,12,8],\"backgroundColor\":\"rgba(54, 162, 235, 0.6)\",\"borderColor\":\"rgba(54, 162, 235, 1)\",\"borderWidth\":1},{\"label\":\"Balanced Mandate (FY2024)\",\"data\":[52,28,11,9],\"backgroundColor\":\"rgba(255, 206, 86, 0.6)\",\"borderColor\":\"rgba(255, 206, 86, 1)\",\"borderWidth\":1},{\"label\":\"Growth Mandate (FY2024)\",\"data\":[64,14,10,12],\"backgroundColor\":\"rgba(255, 99, 132, 0.6)\",\"borderColor\":\"rgba(255, 99, 132, 1)\",\"borderWidth\":1}]},\"options\":{\"indexAxis\":\"y\",\"responsive\":true,\"scales\":{\"x\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Allocation Weight (% of Total Portfolio)\"},\"max\":100},\"y\":{\"title\":{\"display\":true,\"text\":\"Asset Class (Cape Halverton State Pension Strategic Allocation)\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Cape Halverton State Pension — FY2024 Strategic Allocation Across Three Mandate Tiers (Excludes Cash & Hedge Overlay)\"},\"legend\":{\"display\":true,\"position\":\"top\"}}}}"}
```

- **Source**: hand-written; anchored on `10k_00_quantitative` for the multi-
  line `\n` category-label pattern and on `arxiv_00_comparative` for the
  3-way comparative content style.
- **Domain archetype**: pension / asset-allocation (distinct from
  GBAR-A/B/C archetypes).
- **Integrated patterns**: 3 datasets × 4 categories / horizontal / multi-
  line `\n` sub-qualifiers in category labels / shared x-axis with `max:
  100` / scope-aware y-axis title / narrative title with two parenthetical
  qualifiers (FY + exclusion scope) / per-dataset distinct color / 1-px
  borders.
- **Length budget**: 1320 chars ≈ ~340 tokens.
- **Intent**: V4_consolidated independent measurement.

---

## 3. Python literal — drop-in for `tmg.py`

### 3.1 Pool literal

```python
ONE_SHOT_POOL_BY_VIZ_TYPE["chartjs_grouped_bar"] = [
    # GBAR-A — 2-dataset × 2-axis horizontal compare, financial archetype (Halverson Bancorp)
    '{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"Available-for-Sale Securities\\\\n(Fair Value Decline)\\",\\"Long-Term Debt\\\\n(Interest Expense Increase)\\"],\\"datasets\\":[{\\"label\\":\\"FY2024\\",\\"data\\":[2620,142],\\"backgroundColor\\":\\"rgba(54, 162, 235, 0.6)\\",\\"borderColor\\":\\"rgba(54, 162, 235, 1)\\",\\"borderWidth\\":1},{\\"label\\":\\"FY2023\\",\\"data\\":[2884,128],\\"backgroundColor\\":\\"rgba(255, 99, 132, 0.6)\\",\\"borderColor\\":\\"rgba(255, 99, 132, 1)\\",\\"borderWidth\\":1}]},\\"options\\":{\\"indexAxis\\":\\"y\\",\\"responsive\\":true,\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Halverson Bancorp — Estimated Impact of 100bp Parallel Rate Shock (Millions USD)\\"},\\"legend\\":{\\"position\\":\\"top\\"}},\\"scales\\":{\\"x\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Estimated Impact (Millions USD)\\"},\\"beginAtZero\\":true},\\"y\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Risk Category\\"}}}}}"}',
    # GBAR-B — 2-dataset × 3-axis dual-y mixed-units, news archetype (Pemberton Charitable Trust)
    '{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"2019\\",\\"2020\\",\\"2021\\"],\\"datasets\\":[{\\"label\\":\\"Cash Equivalent of Stock Donation (Billions USD)\\",\\"data\\":[2.6,3.1,3.0],\\"backgroundColor\\":\\"rgba(54, 162, 235, 0.5)\\",\\"borderColor\\":\\"rgba(54, 162, 235, 1)\\",\\"borderWidth\\":1,\\"yAxisID\\":\\"y\\"},{\\"label\\":\\"Class B Shares Donated (Millions)\\",\\"data\\":[14.0,12.5,11.8],\\"backgroundColor\\":\\"rgba(255, 99, 132, 0.5)\\",\\"borderColor\\":\\"rgba(255, 99, 132, 1)\\",\\"borderWidth\\":1,\\"yAxisID\\":\\"y1\\"}]},\\"options\\":{\\"responsive\\":true,\\"scales\\":{\\"y\\":{\\"type\\":\\"linear\\",\\"position\\":\\"left\\",\\"title\\":{\\"display\\":true,\\"text\\":\\"Cash Equivalent (Billions USD)\\"}},\\"y1\\":{\\"type\\":\\"linear\\",\\"position\\":\\"right\\",\\"title\\":{\\"display\\":true,\\"text\\":\\"Shares (Millions)\\"},\\"grid\\":{\\"drawOnChartArea\\":false}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Pemberton Charitable Trust Annual Endowment Inflow, 2019–2021 (Two-Axis View)\\"},\\"legend\\":{\\"display\\":true,\\"position\\":\\"top\\"}}}}"}',
    # GBAR-C — 3-dataset × 4-axis side-by-side, paper-methods archetype (hand-written)
    '{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"Reasoning (MMLU)\\",\\"Coding (HumanEval)\\",\\"Math (GSM8K)\\",\\"Long-Context (NIH)\\"],\\"datasets\\":[{\\"label\\":\\"Encoder-Decoder Baseline\\",\\"data\\":[68.4,42.1,55.7,71.0],\\"backgroundColor\\":\\"rgba(54, 162, 235, 0.6)\\",\\"borderColor\\":\\"rgba(54, 162, 235, 1)\\",\\"borderWidth\\":1},{\\"label\\":\\"Decoder-Only + RLHF\\",\\"data\\":[78.9,71.8,82.4,84.2],\\"backgroundColor\\":\\"rgba(255, 99, 132, 0.6)\\",\\"borderColor\\":\\"rgba(255, 99, 132, 1)\\",\\"borderWidth\\":1},{\\"label\\":\\"Mixture-of-Experts + DPO\\",\\"data\\":[81.2,75.4,86.0,88.7],\\"backgroundColor\\":\\"rgba(75, 192, 192, 0.6)\\",\\"borderColor\\":\\"rgba(75, 192, 192, 1)\\",\\"borderWidth\\":1}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Benchmark Accuracy (%)\\"},\\"max\\":100}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"LLM Architecture Comparison Across Four Standardized Benchmarks\\"},\\"legend\\":{\\"display\\":true,\\"position\\":\\"top\\"}}}}"}',
]
```

### 3.2 Consolidated literal

```python
ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE["chartjs_grouped_bar"] = (
    '{"viz_type": "chartjs_grouped_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"Equities\\\\n(Public Listed)\\",\\"Fixed Income\\\\n(Investment Grade)\\",\\"Real Assets\\\\n(Infrastructure & Real Estate)\\",\\"Private Markets\\\\n(PE / VC / Private Credit)\\"],\\"datasets\\":[{\\"label\\":\\"Conservative Mandate (FY2024)\\",\\"data\\":[34,46,12,8],\\"backgroundColor\\":\\"rgba(54, 162, 235, 0.6)\\",\\"borderColor\\":\\"rgba(54, 162, 235, 1)\\",\\"borderWidth\\":1},{\\"label\\":\\"Balanced Mandate (FY2024)\\",\\"data\\":[52,28,11,9],\\"backgroundColor\\":\\"rgba(255, 206, 86, 0.6)\\",\\"borderColor\\":\\"rgba(255, 206, 86, 1)\\",\\"borderWidth\\":1},{\\"label\\":\\"Growth Mandate (FY2024)\\",\\"data\\":[64,14,10,12],\\"backgroundColor\\":\\"rgba(255, 99, 132, 0.6)\\",\\"borderColor\\":\\"rgba(255, 99, 132, 1)\\",\\"borderWidth\\":1}]},\\"options\\":{\\"indexAxis\\":\\"y\\",\\"responsive\\":true,\\"scales\\":{\\"x\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Allocation Weight (% of Total Portfolio)\\"},\\"max\\":100},\\"y\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Asset Class (Cape Halverton State Pension Strategic Allocation)\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Cape Halverton State Pension — FY2024 Strategic Allocation Across Three Mandate Tiers (Excludes Cash & Hedge Overlay)\\"},\\"legend\\":{\\"display\\":true,\\"position\\":\\"top\\"}}}}"}'
)
```

---

## 4. 검수 체크리스트

- [x] **Syntactic spread of 3 pool exemplars**:
  - GBAR-A: 2 datasets × 2 categories / horizontal / multi-line labels
  - GBAR-B: 2 datasets × 3 yearly categories / vertical / **dual-y mixed
    units**
  - GBAR-C: 3 datasets × 4 named benchmark categories / vertical / fixed
    `y.max`
  → covers (2 vs 3 datasets) × (2 vs 3 vs 4 categories) × (horizontal vs
  vertical) × (single vs dual y-axis) × (multi-line vs single-line labels).
- [x] **Anchor authenticity**: GBAR-A and GBAR-B anchored (faith 1.00 each);
  GBAR-C hand-written and **explicitly disclosed**.
- [x] **Placeholder regression check**: no `Acme*` (GBAR-A swapped to
  Halverson Bancorp), no `Lakeshore` reuse from LINE-A (GBAR-B swapped to
  Pemberton Charitable Trust), no Speed/Accuracy/Cost minimal style. All
  fictional generic-domain.
- [x] **Consolidated variant integration**: a single coherent chart that
  combines (3 datasets) × (4 multi-line `\n` category labels) × (horizontal)
  × (shared x-axis with `max: 100`) × (scope-aware y-axis title) ×
  (parenthetical-qualifier narrative title). No stitching.
- [x] **JSON round-trip**: all 4 strings parse via `json.loads`; inner
  `viz_dsl` value also parses (chartjs schema preserved); `viz_type ==
  "chartjs_grouped_bar"` for all.
- [x] **Token budget for consolidated**: ~1320 chars ≈ ~340 tokens (largest
  consolidated of all 6 types because grouped_bar legitimately needs
  3 datasets × 4 categories to demonstrate the comparative shape).
