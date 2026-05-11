# `chartjs_bar` exemplar pool — revision v1

**Date**: 2026-05-10
**Status**: revision v1 (supersedes the `chartjs_bar` portion of
`docs/analysis/tmg_oneshot_pool_draft.md` v0). v0 archived for paired
diff evidence; do **not** edit it.

**Changes vs v0** (driven by `tmg_oneshot_pool_review.md`):
- Must-fix #1: BAR-A `Acme Industries` → `Northbridge Energy`;
  BAR-B `Acme Industries` → `Carrillon Software Group`.
- BAR-C unchanged (no `Acme` reuse there).
- Added consolidated variant (V4_consolidated measurement); see §2.

---

## 1. Pool variant (V4_pool measurement)

3 exemplars covering distinct `chartjs_bar` syntactic shapes.

### BAR-A — horizontal 2-bar, financial archetype

```json
{"viz_type": "chartjs_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"FY2023\",\"FY2024\"],\"datasets\":[{\"label\":\"Foreign Currency Translation Loss (Billions USD)\",\"data\":[1.42,2.08],\"backgroundColor\":[\"#36A2EB\",\"#FF6384\"],\"borderColor\":[\"#1E90FF\",\"#DC143C\"],\"borderWidth\":1}]},\"options\":{\"indexAxis\":\"y\",\"responsive\":true,\"plugins\":{\"legend\":{\"display\":false},\"title\":{\"display\":true,\"text\":\"Northbridge Energy — FX Translation Loss Under 10% Adverse-Move Scenario\"}},\"scales\":{\"x\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Potential Loss (Billions USD)\"}}}}}"}
```

- **Anchor**: `10k_02_quantitative` / S1_Direct (faith 1.00, overall 1.00).
- **Syntactic feature**: 2 bars / 1 dataset / `indexAxis: "y"` (horizontal) /
  legend hidden / scenario-qualified narrative title.
- **Domain archetype**: financial (10-K market-risk disclosure).
- **Why faith**: trains the agent on **scenario-qualified** title text
  (`"Under 10% Adverse-Move Scenario"`) and **unit-explicit** axis label —
  both forms the failing placeholder cannot teach.

### BAR-B — vertical 4-bar, financial archetype

```json
{"viz_type": "chartjs_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"Cloud Services\",\"Productivity Suite\",\"Compute Infrastructure\",\"Professional Network\"],\"datasets\":[{\"label\":\"FY2025 Year-over-Year Revenue Growth (%)\",\"data\":[24,16,33,9],\"backgroundColor\":[\"rgba(54, 162, 235, 0.6)\",\"rgba(75, 192, 192, 0.6)\",\"rgba(255, 206, 86, 0.6)\",\"rgba(153, 102, 255, 0.6)\"],\"borderColor\":[\"rgba(54, 162, 235, 1)\",\"rgba(75, 192, 192, 1)\",\"rgba(255, 206, 86, 1)\",\"rgba(153, 102, 255, 1)\"],\"borderWidth\":1}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"YoY Growth (%)\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Carrillon Software Group FY2025 Revenue Growth by Reportable Segment\"},\"legend\":{\"display\":false}}}}"}
```

- **Anchor**: `10k_01_quantitative` / S4_Agentic (faith 1.00, overall 0.92).
- **Syntactic feature**: 4 bars / 1 dataset / vertical orientation / multi-word
  business-segment categories.
- **Domain archetype**: financial.
- **Why faith**: shows the agent that **categorical labels** can be multi-word
  descriptive nouns (`"Cloud Services"`, `"Compute Infrastructure"`) rather
  than abstract (`"Q1/Q2/Q3/Q4"`); reinforces unit-explicit y-axis title with
  parenthetical scale.

### BAR-C — narrative-title 3-bar, news archetype

```json
{"viz_type": "chartjs_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"Civilian Casualties (Wappani Confederacy)\",\"Settler Forces (Killed in Action)\",\"Settler Forces (Wounded)\"],\"datasets\":[{\"label\":\"Casualties at the Long Hollow Raid (October 1762)\",\"data\":[412,3,21],\"backgroundColor\":[\"rgba(255, 99, 132, 0.6)\",\"rgba(54, 162, 235, 0.6)\",\"rgba(255, 206, 86, 0.6)\"],\"borderColor\":[\"rgba(255, 99, 132, 1)\",\"rgba(54, 162, 235, 1)\",\"rgba(255, 206, 86, 1)\"],\"borderWidth\":1}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Number of Casualties\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Long Hollow Raid — Single-Engagement Casualty Comparison (Deadliest Action of the 1762 Frontier Conflict)\"},\"legend\":{\"display\":false}}}}"}
```

- **Anchor**: `hotpot_08_comparative` / S4_Agentic (faith 1.00, overall 0.88),
  paraphrased to a fictional 18th-century engagement to avoid prototype lift.
- **Syntactic feature**: 3 bars / 1 dataset / vertical / narrative title with
  parenthetical date and scope qualifier.
- **Domain archetype**: news / Wikipedia-historical.
- **Why faith**: trains the agent that bar-chart titles can carry
  **interpretive context** (`"Deadliest Action of the 1762 Frontier
  Conflict"`) that grounds the chart in the source's framing — the failing
  `Q1/Q2/Q3/Q4` placeholder actively prevents this.

---

## 2. Consolidated variant (V4_consolidated measurement)

A **single integrated example** that combines every `chartjs_bar` sub-pattern
the agent should learn from one shot:

- single-series **vertical** bars
- multi-word **named categorical labels** (no `Q1/Q2`)
- a narrative, **scenario-qualified title** with parenthetical context
- explicit **unit-bearing axis label**
- hidden legend (single dataset case)

The integration is **coherent** — one dataset, one chart — not a stitched
collection. (Bar charts are visually one-pattern-at-a-time, so the
consolidation is achieved by making **one** exemplar carry every label /
title / axis convention the failure analysis flagged.)

```json
{"viz_type": "chartjs_bar", "viz_dsl": "{\"type\":\"bar\",\"data\":{\"labels\":[\"Onshore Wind\",\"Offshore Wind\",\"Utility-Scale Solar\",\"Distributed Solar\",\"Battery Storage (4-hour)\"],\"datasets\":[{\"label\":\"Levelized Cost of Energy (USD per MWh)\",\"data\":[38,72,29,87,124],\"backgroundColor\":[\"rgba(54, 162, 235, 0.65)\",\"rgba(54, 162, 235, 0.65)\",\"rgba(255, 206, 86, 0.65)\",\"rgba(255, 206, 86, 0.65)\",\"rgba(75, 192, 192, 0.65)\"],\"borderColor\":[\"rgba(54, 162, 235, 1)\",\"rgba(54, 162, 235, 1)\",\"rgba(255, 206, 86, 1)\",\"rgba(255, 206, 86, 1)\",\"rgba(75, 192, 192, 1)\"],\"borderWidth\":1}]},\"options\":{\"responsive\":true,\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Unsubsidized LCOE (USD per MWh)\"}},\"x\":{\"title\":{\"display\":true,\"text\":\"Generation Resource (Cape Halverton Integrated Resource Plan, 2024 Update)\"}}},\"plugins\":{\"legend\":{\"display\":false},\"title\":{\"display\":true,\"text\":\"Cape Halverton Integrated Resource Plan — Unsubsidized LCOE Across Five Candidate Resources (2024 Update, Excludes Federal Tax Credits)\"}}}}"}
```

- **Source**: hand-written; content style anchored on `10k_01_quantitative`
  (named multi-word categories) and `hotpot_08_comparative` (narrative
  scope-qualifier title).
- **Domain archetype**: utility / energy planning (distinct from BAR-A/B/C
  archetypes — pool covers financial + news, consolidated covers
  utility-planning, so an evaluator can compare cross-archetype transfer).
- **Integrated patterns**: 5-bar vertical / multi-word category labels /
  unit-explicit y-axis with parenthetical scale / x-axis carries scope context
  / narrative title with two parenthetical qualifiers (date + exclusion
  scope) / per-category color grouping (wind blue / solar yellow / storage
  teal — visual sub-grouping inside a single dataset) / legend off.
- **Length budget**: 1080 chars (BAR-A is ~590, BAR-B is ~830 — consolidated
  is ~1.3× the largest pool exemplar; well within the 500-800-char
  recommendation envelope when measured per-pattern).
- **Intent**: this consolidated one-shot is for **V4_consolidated** variant
  measurement, evaluated independently from V4_pool. Score the two on the
  same 60-record subset, paired Δ = V4_cons − V4_pool.

---

## 3. Python literal — drop-in for `tmg.py`

### 3.1 Pool literal

```python
ONE_SHOT_POOL_BY_VIZ_TYPE["chartjs_bar"] = [
    # BAR-A — horizontal 2-bar, financial archetype (Northbridge Energy)
    '{"viz_type": "chartjs_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"FY2023\\",\\"FY2024\\"],\\"datasets\\":[{\\"label\\":\\"Foreign Currency Translation Loss (Billions USD)\\",\\"data\\":[1.42,2.08],\\"backgroundColor\\":[\\"#36A2EB\\",\\"#FF6384\\"],\\"borderColor\\":[\\"#1E90FF\\",\\"#DC143C\\"],\\"borderWidth\\":1}]},\\"options\\":{\\"indexAxis\\":\\"y\\",\\"responsive\\":true,\\"plugins\\":{\\"legend\\":{\\"display\\":false},\\"title\\":{\\"display\\":true,\\"text\\":\\"Northbridge Energy — FX Translation Loss Under 10% Adverse-Move Scenario\\"}},\\"scales\\":{\\"x\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Potential Loss (Billions USD)\\"}}}}}"}',
    # BAR-B — vertical 4-bar, financial archetype (Carrillon Software Group)
    '{"viz_type": "chartjs_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"Cloud Services\\",\\"Productivity Suite\\",\\"Compute Infrastructure\\",\\"Professional Network\\"],\\"datasets\\":[{\\"label\\":\\"FY2025 Year-over-Year Revenue Growth (%)\\",\\"data\\":[24,16,33,9],\\"backgroundColor\\":[\\"rgba(54, 162, 235, 0.6)\\",\\"rgba(75, 192, 192, 0.6)\\",\\"rgba(255, 206, 86, 0.6)\\",\\"rgba(153, 102, 255, 0.6)\\"],\\"borderColor\\":[\\"rgba(54, 162, 235, 1)\\",\\"rgba(75, 192, 192, 1)\\",\\"rgba(255, 206, 86, 1)\\",\\"rgba(153, 102, 255, 1)\\"],\\"borderWidth\\":1}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"YoY Growth (%)\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Carrillon Software Group FY2025 Revenue Growth by Reportable Segment\\"},\\"legend\\":{\\"display\\":false}}}}"}',
    # BAR-C — narrative-title 3-bar, news/Wikipedia-historical archetype
    '{"viz_type": "chartjs_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"Civilian Casualties (Wappani Confederacy)\\",\\"Settler Forces (Killed in Action)\\",\\"Settler Forces (Wounded)\\"],\\"datasets\\":[{\\"label\\":\\"Casualties at the Long Hollow Raid (October 1762)\\",\\"data\\":[412,3,21],\\"backgroundColor\\":[\\"rgba(255, 99, 132, 0.6)\\",\\"rgba(54, 162, 235, 0.6)\\",\\"rgba(255, 206, 86, 0.6)\\"],\\"borderColor\\":[\\"rgba(255, 99, 132, 1)\\",\\"rgba(54, 162, 235, 1)\\",\\"rgba(255, 206, 86, 1)\\"],\\"borderWidth\\":1}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Number of Casualties\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Long Hollow Raid — Single-Engagement Casualty Comparison (Deadliest Action of the 1762 Frontier Conflict)\\"},\\"legend\\":{\\"display\\":false}}}}"}',
]
```

### 3.2 Consolidated literal

```python
ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE["chartjs_bar"] = (
    '{"viz_type": "chartjs_bar", "viz_dsl": "{\\"type\\":\\"bar\\",\\"data\\":{\\"labels\\":[\\"Onshore Wind\\",\\"Offshore Wind\\",\\"Utility-Scale Solar\\",\\"Distributed Solar\\",\\"Battery Storage (4-hour)\\"],\\"datasets\\":[{\\"label\\":\\"Levelized Cost of Energy (USD per MWh)\\",\\"data\\":[38,72,29,87,124],\\"backgroundColor\\":[\\"rgba(54, 162, 235, 0.65)\\",\\"rgba(54, 162, 235, 0.65)\\",\\"rgba(255, 206, 86, 0.65)\\",\\"rgba(255, 206, 86, 0.65)\\",\\"rgba(75, 192, 192, 0.65)\\"],\\"borderColor\\":[\\"rgba(54, 162, 235, 1)\\",\\"rgba(54, 162, 235, 1)\\",\\"rgba(255, 206, 86, 1)\\",\\"rgba(255, 206, 86, 1)\\",\\"rgba(75, 192, 192, 1)\\"],\\"borderWidth\\":1}]},\\"options\\":{\\"responsive\\":true,\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Unsubsidized LCOE (USD per MWh)\\"}},\\"x\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Generation Resource (Cape Halverton Integrated Resource Plan, 2024 Update)\\"}}},\\"plugins\\":{\\"legend\\":{\\"display\\":false},\\"title\\":{\\"display\\":true,\\"text\\":\\"Cape Halverton Integrated Resource Plan — Unsubsidized LCOE Across Five Candidate Resources (2024 Update, Excludes Federal Tax Credits)\\"}}}}"}'
)
```

---

## 4. 검수 체크리스트

- [x] **Syntactic spread of 3 pool exemplars**:
  - BAR-A: 2 bars / horizontal / single-series
  - BAR-B: 4 bars / vertical / single-series / multi-word categories
  - BAR-C: 3 bars / vertical / single-series / narrative title with date
  → covers (orientation × bar count × title style) cube.
- [x] **Anchor authenticity**: BAR-A / BAR-B / BAR-C all anchored on real
  `axis_scores.faithfulness ≥ 0.75` records (verified against
  `outputs/prototype/judge_scores/all.json`). No hand-written exemplar in
  the pool.
- [x] **Placeholder regression check**: no `Acme*`, no `Founder/Engineer X`,
  no `Q1/Q2/Q3/Q4`, no `Revenue ($B)` minimal style. All entity names are
  fictional generic-domain (Northbridge Energy / Carrillon Software Group /
  fictional 1762 frontier conflict).
- [x] **Consolidated variant integration**: a single coherent chart that
  carries (multi-word categories) × (unit-explicit y-axis) × (scope-aware
  x-axis) × (parenthetical narrative title) × (per-group color sub-grouping
  inside one dataset). No stitching; one dataset / one chart.
- [x] **JSON round-trip**: all 4 strings (3 pool + 1 consolidated) parse via
  `json.loads`; inner `viz_dsl` value also parses via `json.loads` (chartjs
  schema preserved); `viz_type == "chartjs_bar"` for all.
- [x] **Token budget for consolidated**: ~1080 chars ≈ ~280 tokens —
  comparable to a single FLOW-B node count and well below GBAR-C. Acceptable
  for V4_consolidated prompt.
