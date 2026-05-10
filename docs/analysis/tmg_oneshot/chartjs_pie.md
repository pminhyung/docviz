# `chartjs_pie` exemplar pool — revision v2 (NEW type)

**Date**: 2026-05-10
**Status**: revision v2 (newly introduced viz_type; no v0/v1 predecessor in
this directory). Added as part of the 6 → 10 viz_type enum extension
(High priority — ChartQA standard, share/proportion comparative queries).

**Provenance honesty**: this viz_type has **no historical anchor** in
`outputs/prototype/judge_scores/all.json` (the prototype dataset was
generated under the 6-type enum). All 4 exemplars in this file are
**hand-written**. Content style anchors borrow conventions from the v1
`chartjs_bar` pool (multi-word categorical labels; narrative,
scope-qualified titles; unit-explicit dataset labels) so that the
agent transfers the same faith-1.00 conventions across the chart family.

---

## 1. Pool variant (V4_pool measurement)

3 exemplars covering distinct `chartjs_pie` syntactic shapes:
**3-5 slices simple proportion** (PIE-A) /
**6-8 slices longer-tail allocation** (PIE-B) /
**doughnut variant with `cutout`** (PIE-C).

### PIE-A — 3 slices simple proportion, financial / news archetype

```json
{"viz_type": "chartjs_pie", "viz_dsl": "{\"type\": \"pie\", \"data\": {\"labels\": [\"Crystallight Studios\", \"Northbridge Energy\", \"Independent Operators\"], \"datasets\": [{\"label\": \"Q4 2024 North American Box Office Distribution Share (%)\", \"data\": [42, 33, 25], \"backgroundColor\": [\"rgba(255, 99, 132, 0.7)\", \"rgba(54, 162, 235, 0.7)\", \"rgba(255, 206, 86, 0.7)\"], \"borderColor\": [\"rgba(255, 99, 132, 1)\", \"rgba(54, 162, 235, 1)\", \"rgba(255, 206, 86, 1)\"], \"borderWidth\": 1}]}, \"options\": {\"responsive\": true, \"plugins\": {\"legend\": {\"position\": \"right\", \"title\": {\"display\": true, \"text\": \"Distributor\"}}, \"title\": {\"display\": true, \"text\": \"Q4 2024 North American Theatrical Distribution Share — Top Three Distributors (Excluding Direct-to-Streaming Releases)\"}}}}"}
```

- **Source**: hand-written (no v0/v1 predecessor; first PIE exemplar).
- **Syntactic feature**: 3 slices / `type: "pie"` (vanilla, no cutout) /
  legend on the right with its own legend title (`"Distributor"`) /
  narrative title with parenthetical scope qualifier (`"Excluding
  Direct-to-Streaming Releases"`).
- **Domain archetype**: financial / news (market-share reporting).
- **Why faith intent**: trains the agent on the **simplest pie shape**
  (≤5 slices) with a **named-entity** label set and a **scope-qualified
  narrative title**. Matches the BAR-A / BAR-C convention from v1 so
  the agent generalises chart-family title conventions across `pie`.

### PIE-B — 7 slices longer-tail allocation, financial archetype

```json
{"viz_type": "chartjs_pie", "viz_dsl": "{\"type\": \"pie\", \"data\": {\"labels\": [\"Personnel & Faculty Salaries\", \"Sponsored Research Awards\", \"Student Financial Aid\", \"Facilities & Plant Operations\", \"Information Technology\", \"Library & Academic Resources\", \"Administration & General\"], \"datasets\": [{\"label\": \"FY2024 Operating Expenditure Allocation (USD millions)\", \"data\": [612, 348, 211, 184, 92, 47, 76], \"backgroundColor\": [\"rgba(54, 162, 235, 0.7)\", \"rgba(75, 192, 192, 0.7)\", \"rgba(255, 206, 86, 0.7)\", \"rgba(153, 102, 255, 0.7)\", \"rgba(255, 159, 64, 0.7)\", \"rgba(199, 199, 199, 0.7)\", \"rgba(255, 99, 132, 0.7)\"], \"borderColor\": \"#ffffff\", \"borderWidth\": 2}]}, \"options\": {\"responsive\": true, \"plugins\": {\"legend\": {\"position\": \"right\"}, \"title\": {\"display\": true, \"text\": \"Halverson Bancorp Foundation Endowed Universities — FY2024 Operating Expenditure Allocation by Functional Category (USD Millions)\"}}}}"}
```

- **Source**: hand-written.
- **Syntactic feature**: 7 slices (longer-tail; smallest slice is 47/1570 ≈
  3%) / `type: "pie"` / shared `borderColor: "#ffffff"` for white
  inter-slice gap / multi-word **functional-category** labels
  (`"Personnel & Faculty Salaries"`, `"Library & Academic Resources"`).
- **Domain archetype**: financial (institutional budget allocation; reuses
  the **Halverson Bancorp** entity family from v1 GBAR-A — entity continuity
  inside the consolidated 10-type design, not a v0 placeholder regression).
- **Why faith intent**: trains the agent that pies can carry **6-8 slice
  budget-allocation** shape with multi-word labels — the long-tail case
  that single-color generic-label placeholders (`Item 1` / `Item 2`)
  cannot teach.

### PIE-C — 5 slices doughnut variant (cutout), news archetype

```json
{"viz_type": "chartjs_pie", "viz_dsl": "{\"type\": \"doughnut\", \"data\": {\"labels\": [\"Progressive Renewal Coalition\", \"National Stewardship Party\", \"Civic Liberty Front\", \"Mountain Heritage Alliance\", \"Independent & Write-In\"], \"datasets\": [{\"label\": \"Cantonal Election 2024 — Vote Share (%)\", \"data\": [38.2, 31.5, 17.4, 8.6, 4.3], \"backgroundColor\": [\"rgba(54, 162, 235, 0.75)\", \"rgba(255, 99, 132, 0.75)\", \"rgba(255, 206, 86, 0.75)\", \"rgba(75, 192, 192, 0.75)\", \"rgba(199, 199, 199, 0.75)\"], \"borderColor\": \"#ffffff\", \"borderWidth\": 2}]}, \"options\": {\"responsive\": true, \"cutout\": \"55%\", \"plugins\": {\"legend\": {\"position\": \"bottom\"}, \"title\": {\"display\": true, \"text\": \"Canton of Saint-Verronet 2024 Legislative Election — Final Certified Vote Share by Party (Turnout 71.3%)\"}}}}"}
```

- **Source**: hand-written; fictional canton/parties (no real political-
  entity leak).
- **Syntactic feature**: 5 slices / **`type: "doughnut"`** + `cutout: "55%"`
  (the semi-doughnut variant — Chart.js supports doughnut as the cutout
  generalisation of pie) / **fractional percentages** in `data` (38.2,
  31.5, …) demonstrating decimal-precision share / legend at the bottom.
- **Domain archetype**: news (election reporting; reuses the v1 narrative-
  title convention with **turnout qualifier** in parentheses).
- **Why faith intent**: covers the **`doughnut`/`cutout` sub-pattern**
  (Chart.js treats this as the same chart family as `pie`; the proposal
  `chartjs_pie` covers both). Without this exemplar the agent would emit
  doughnut requests as raw `pie` and lose the cutout option.

---

## 2. Consolidated variant (V4_consolidated measurement)

A **single integrated example** that combines every `chartjs_pie`
sub-pattern the agent should learn from one shot:

- **doughnut variant** (`type: "doughnut"` + `cutout`) covering the v1
  `chartjs_pie`-vs-`chartjs_doughnut` family unification
- **6-slice longer-tail allocation** (between PIE-A's 3 and PIE-B's 7)
- multi-word **named-category** labels with parenthetical sub-qualifier
  (`"Hydropower (Run-of-River)"`, `"Battery Storage (4-hour)"`-style)
- **fractional percentages** with one-decimal precision (mirrors PIE-C)
- **legend with its own legend title** (mirrors PIE-A)
- **narrative title with two parenthetical qualifiers** (date + exclusion
  scope — mirrors v1 BAR-CONS convention)
- shared `borderColor: "#ffffff"` for white inter-slice gap

The integration is **coherent** — one chart, one dataset, one domain — not
a stitch of separate examples. The Cape Halverton domain re-uses the v1
BAR-CONS through-line so an evaluator measuring V4_consolidated can do
cross-chart-family transfer comparison.

```json
{"viz_type": "chartjs_pie", "viz_dsl": "{\"type\": \"doughnut\", \"data\": {\"labels\": [\"Hydropower (Run-of-River)\", \"Onshore Wind\", \"Utility-Scale Solar Photovoltaic\", \"Natural Gas Combined-Cycle\", \"Imported Interconnector Power\", \"Demand-Side Response & Storage\"], \"datasets\": [{\"label\": \"Cape Halverton Grid — 2024 Annual Energy Mix (% of Net Generation)\", \"data\": [34.1, 22.8, 18.5, 14.3, 6.8, 3.5], \"backgroundColor\": [\"rgba(54, 162, 235, 0.75)\", \"rgba(75, 192, 192, 0.75)\", \"rgba(255, 206, 86, 0.75)\", \"rgba(255, 99, 132, 0.75)\", \"rgba(153, 102, 255, 0.75)\", \"rgba(255, 159, 64, 0.75)\"], \"borderColor\": \"#ffffff\", \"borderWidth\": 2}]}, \"options\": {\"responsive\": true, \"cutout\": \"50%\", \"plugins\": {\"legend\": {\"position\": \"right\", \"title\": {\"display\": true, \"text\": \"Generation Source\"}}, \"title\": {\"display\": true, \"text\": \"Cape Halverton Integrated Resource Plan — 2024 Annual Energy Mix by Generation Source (Excludes Behind-the-Meter Distributed Solar)\"}}}}"}
```

- **Source**: hand-written; Cape Halverton domain through-line carried over
  from v1 BAR-CONS / GBAR-CONS for cross-chart-family transfer.
- **Domain archetype**: financial / utility-planning (distinct from PIE-A
  news-finance and PIE-B institutional-finance archetypes — the
  consolidated covers utility-planning, so an evaluator can compare
  cross-archetype transfer the same way v1 BAR-CONS does).
- **Integrated patterns**: doughnut with `cutout: "50%"` / 6-slice
  long-tail / fractional percentages (one decimal) / multi-word labels
  with parenthetical sub-qualifier / legend on the right with its own
  legend title / narrative title with date qualifier and exclusion-scope
  qualifier in parentheses / shared white inter-slice gap.
- **Length budget**: 1039 chars outer, 917 chars inner DSL (≈ 240 tokens
  inner). Consolidated:pool ratio = 917 / 871 (PIE-B) = **1.05×** — well
  inside the v1 envelope (BAR was 1.4×; mindmap was 1.2×). Pie consolidates
  efficiently because every sub-pattern lives in the same single chart.
- **Intent**: V4_consolidated independent measurement. Score on the same
  60-record subset as V4_pool; paired Δ = V4_cons − V4_pool.

---

## 3. Python literal — drop-in for `tmg.py`

### 3.1 Pool literal

```python
ONE_SHOT_POOL_BY_VIZ_TYPE["chartjs_pie"] = [
    # PIE-A — 3 slices simple proportion (Crystallight Studios distribution share)
    '{"viz_type": "chartjs_pie", "viz_dsl": "{\\"type\\": \\"pie\\", \\"data\\": {\\"labels\\": [\\"Crystallight Studios\\", \\"Northbridge Energy\\", \\"Independent Operators\\"], \\"datasets\\": [{\\"label\\": \\"Q4 2024 North American Box Office Distribution Share (%)\\", \\"data\\": [42, 33, 25], \\"backgroundColor\\": [\\"rgba(255, 99, 132, 0.7)\\", \\"rgba(54, 162, 235, 0.7)\\", \\"rgba(255, 206, 86, 0.7)\\"], \\"borderColor\\": [\\"rgba(255, 99, 132, 1)\\", \\"rgba(54, 162, 235, 1)\\", \\"rgba(255, 206, 86, 1)\\"], \\"borderWidth\\": 1}]}, \\"options\\": {\\"responsive\\": true, \\"plugins\\": {\\"legend\\": {\\"position\\": \\"right\\", \\"title\\": {\\"display\\": true, \\"text\\": \\"Distributor\\"}}, \\"title\\": {\\"display\\": true, \\"text\\": \\"Q4 2024 North American Theatrical Distribution Share — Top Three Distributors (Excluding Direct-to-Streaming Releases)\\"}}}}"}',
    # PIE-B — 7 slices longer-tail (Halverson Bancorp Foundation budget allocation)
    '{"viz_type": "chartjs_pie", "viz_dsl": "{\\"type\\": \\"pie\\", \\"data\\": {\\"labels\\": [\\"Personnel & Faculty Salaries\\", \\"Sponsored Research Awards\\", \\"Student Financial Aid\\", \\"Facilities & Plant Operations\\", \\"Information Technology\\", \\"Library & Academic Resources\\", \\"Administration & General\\"], \\"datasets\\": [{\\"label\\": \\"FY2024 Operating Expenditure Allocation (USD millions)\\", \\"data\\": [612, 348, 211, 184, 92, 47, 76], \\"backgroundColor\\": [\\"rgba(54, 162, 235, 0.7)\\", \\"rgba(75, 192, 192, 0.7)\\", \\"rgba(255, 206, 86, 0.7)\\", \\"rgba(153, 102, 255, 0.7)\\", \\"rgba(255, 159, 64, 0.7)\\", \\"rgba(199, 199, 199, 0.7)\\", \\"rgba(255, 99, 132, 0.7)\\"], \\"borderColor\\": \\"#ffffff\\", \\"borderWidth\\": 2}]}, \\"options\\": {\\"responsive\\": true, \\"plugins\\": {\\"legend\\": {\\"position\\": \\"right\\"}, \\"title\\": {\\"display\\": true, \\"text\\": \\"Halverson Bancorp Foundation Endowed Universities — FY2024 Operating Expenditure Allocation by Functional Category (USD Millions)\\"}}}}"}',
    # PIE-C — 5 slices doughnut/cutout (Saint-Verronet 2024 election vote share)
    '{"viz_type": "chartjs_pie", "viz_dsl": "{\\"type\\": \\"doughnut\\", \\"data\\": {\\"labels\\": [\\"Progressive Renewal Coalition\\", \\"National Stewardship Party\\", \\"Civic Liberty Front\\", \\"Mountain Heritage Alliance\\", \\"Independent & Write-In\\"], \\"datasets\\": [{\\"label\\": \\"Cantonal Election 2024 — Vote Share (%)\\", \\"data\\": [38.2, 31.5, 17.4, 8.6, 4.3], \\"backgroundColor\\": [\\"rgba(54, 162, 235, 0.75)\\", \\"rgba(255, 99, 132, 0.75)\\", \\"rgba(255, 206, 86, 0.75)\\", \\"rgba(75, 192, 192, 0.75)\\", \\"rgba(199, 199, 199, 0.75)\\"], \\"borderColor\\": \\"#ffffff\\", \\"borderWidth\\": 2}]}, \\"options\\": {\\"responsive\\": true, \\"cutout\\": \\"55%\\", \\"plugins\\": {\\"legend\\": {\\"position\\": \\"bottom\\"}, \\"title\\": {\\"display\\": true, \\"text\\": \\"Canton of Saint-Verronet 2024 Legislative Election — Final Certified Vote Share by Party (Turnout 71.3%)\\"}}}}"}',
]
```

### 3.2 Consolidated literal

```python
ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE["chartjs_pie"] = (
    '{"viz_type": "chartjs_pie", "viz_dsl": "{\\"type\\": \\"doughnut\\", \\"data\\": {\\"labels\\": [\\"Hydropower (Run-of-River)\\", \\"Onshore Wind\\", \\"Utility-Scale Solar Photovoltaic\\", \\"Natural Gas Combined-Cycle\\", \\"Imported Interconnector Power\\", \\"Demand-Side Response & Storage\\"], \\"datasets\\": [{\\"label\\": \\"Cape Halverton Grid — 2024 Annual Energy Mix (% of Net Generation)\\", \\"data\\": [34.1, 22.8, 18.5, 14.3, 6.8, 3.5], \\"backgroundColor\\": [\\"rgba(54, 162, 235, 0.75)\\", \\"rgba(75, 192, 192, 0.75)\\", \\"rgba(255, 206, 86, 0.75)\\", \\"rgba(255, 99, 132, 0.75)\\", \\"rgba(153, 102, 255, 0.75)\\", \\"rgba(255, 159, 64, 0.75)\\"], \\"borderColor\\": \\"#ffffff\\", \\"borderWidth\\": 2}]}, \\"options\\": {\\"responsive\\": true, \\"cutout\\": \\"50%\\", \\"plugins\\": {\\"legend\\": {\\"position\\": \\"right\\", \\"title\\": {\\"display\\": true, \\"text\\": \\"Generation Source\\"}}, \\"title\\": {\\"display\\": true, \\"text\\": \\"Cape Halverton Integrated Resource Plan — 2024 Annual Energy Mix by Generation Source (Excludes Behind-the-Meter Distributed Solar)\\"}}}}"}'
)
```

> **Note on Python literal escapes**: the `—` em-dash inside titles is a
> UTF-8 character — keep the file UTF-8 (Python 3 default). The double
> backslashes `\\"` inside the literal are correct: the outer Python string
> contains `\"` which JSON parses as a literal `"` inside the inner
> `viz_dsl` JSON string. The chartjs DSL itself is a JSON-string-encoded
> JSON object (same convention as v1 chartjs_bar / chartjs_line / chartjs_grouped_bar).

---

## 4. 검수 체크리스트 (mentor risk #5 + risk #2 alignment)

- [x] **Syntactic spread of 3 pool exemplars**:
  - PIE-A: 3 slices / `type: "pie"` / no cutout / right-positioned legend
    with its own legend title / scope-qualified narrative title
  - PIE-B: 7 slices (longer-tail) / `type: "pie"` / shared white border /
    multi-word functional-category labels
  - PIE-C: 5 slices / `type: "doughnut"` + `cutout: "55%"` (the semi-
    doughnut variant) / fractional percentages / bottom legend
  → covers (slice-count × pie-vs-doughnut × legend-position × decimal-vs-
  integer data) cube.
- [x] **All hand-written — honest disclosure**: this viz_type has **no
  historical anchor** in the prototype pool (the prototype was generated
  under the 6-type enum). All 4 exemplars are explicitly disclosed as
  hand-written. Content style anchored on v1 BAR-A / BAR-C conventions
  (multi-word categories; narrative scope-qualified titles) so the agent
  inherits the same faith-1.00 conventions transitively.
- [x] **Placeholder regression check**: no `Acme*`, no `Founder/Engineer X`,
  no `Q1/Q2/Q3/Q4`, no `Item 1/Item 2/Item 3`, no `$X / $Y / $Z` minimal
  style. All entity names are fictional generic-domain (Crystallight
  Studios / Cape Halverton / Saint-Verronet / Halverson Bancorp Foundation).
  The Halverson re-use is **intentional cross-chart-family entity
  continuity** (consistent with v1 GBAR-A `Halverson Bancorp` swap), not a
  placeholder regression.
- [x] **Consolidated variant integration**: a single coherent doughnut
  chart that carries (doughnut/cutout sub-pattern) × (longer-tail 6-slice
  shape) × (multi-word categories with parenthetical sub-qualifiers) ×
  (fractional percentages) × (right-position legend with legend title) ×
  (narrative title with date + exclusion-scope qualifiers). No stitching;
  one dataset / one chart.
- [x] **JSON round-trip**: all 4 strings (3 pool + 1 consolidated) parse
  via `json.loads`; inner `viz_dsl` value also parses via `json.loads`
  (chartjs schema preserved); `viz_type == "chartjs_pie"` for all; inner
  `type ∈ {"pie", "doughnut"}` (both Chart.js-legal under the
  `chartjs_pie` family).
- [x] **Token budget**: pool max = 871 chars (PIE-B) ≈ 220 tokens;
  consolidated = 917 chars ≈ 240 tokens (1.05× pool max — efficient
  consolidation because pie sub-patterns share infrastructure).
- [x] **Self-validation result**: PASS. All 4 exemplars round-trip via
  `json.loads`; inner JSON parses for all 4; no placeholder substring;
  consolidated:pool char ratio = 1.05×.
