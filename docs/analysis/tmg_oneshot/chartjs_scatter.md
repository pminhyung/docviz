# `chartjs_scatter` exemplar pool — revision v2 (NEW type)

**Date**: 2026-05-10
**Status**: revision v2 (newly introduced viz_type; no v0/v1 predecessor in
this directory). Added as part of the 6 → 10 viz_type enum extension
(High priority — quantitative correlation queries that the bar/line family
cannot represent natively).

**Provenance honesty**: this viz_type has **no historical anchor** in
`outputs/prototype/judge_scores/all.json` (the prototype dataset was
generated under the 6-type enum). All 4 exemplars in this file are
**hand-written**. Content style anchors borrow conventions from the v1
`chartjs_line` pool (paper-methods quantitative style; log-scale axes;
multi-series with discriminating legend) so that the agent transfers the
faith-1.00 line-chart conventions to its scatter-chart sibling.

---

## 1. Pool variant (V4_pool measurement)

3 exemplars covering distinct `chartjs_scatter` syntactic shapes:
**single-series 2D correlation** (SCAT-A) /
**multi-series with 2 groups** (SCAT-B) /
**bubble variant with 3rd-dim radius** (SCAT-C).

### SCAT-A — single-series 2D scatter, paper-methods archetype

```json
{"viz_type": "chartjs_scatter", "viz_dsl": "{\"type\": \"scatter\", \"data\": {\"datasets\": [{\"label\": \"Reported MMLU Accuracy vs Parameter Count (Open-Weight Models, July 2024 Survey)\", \"data\": [{\"x\": 7, \"y\": 0.421}, {\"x\": 13, \"y\": 0.527}, {\"x\": 34, \"y\": 0.612}, {\"x\": 70, \"y\": 0.698}, {\"x\": 141, \"y\": 0.741}, {\"x\": 405, \"y\": 0.793}], \"backgroundColor\": \"rgba(54, 162, 235, 0.7)\", \"borderColor\": \"rgba(54, 162, 235, 1)\", \"pointRadius\": 6}]}, \"options\": {\"responsive\": true, \"plugins\": {\"legend\": {\"display\": false}, \"title\": {\"display\": true, \"text\": \"Open-Weight Model MMLU Accuracy vs Parameter Count (Halverson Group July 2024 Survey, n=6 Released Models)\"}}, \"scales\": {\"x\": {\"type\": \"logarithmic\", \"title\": {\"display\": true, \"text\": \"Parameter Count (Billions, log scale)\"}}, \"y\": {\"beginAtZero\": false, \"title\": {\"display\": true, \"text\": \"MMLU 5-Shot Accuracy\"}}}}}"}
```

- **Source**: hand-written.
- **Syntactic feature**: 1 dataset / 6 points / `data` is an **array of
  `{x, y}` objects** (the canonical scatter shape, distinct from line's
  `data: [number, ...]` parallel-array shape) / **logarithmic x-scale**
  (`scales.x.type: "logarithmic"`) / **`pointRadius: 6`** for visible
  markers / legend hidden (single dataset).
- **Domain archetype**: paper-methods (model-vs-metric correlation).
- **Why faith intent**: trains the agent that scatter's `data` items are
  **objects with `x` and `y` keys** — not parallel arrays. This is the #1
  syntactic risk for `chartjs_scatter` (a v1-trained agent may emit line-
  style `data: [num, num, ...]` for scatter, which Chart.js silently
  renders as evenly-spaced points and loses the correlation). Also
  introduces the **log-scale x-axis** convention paper-methods queries
  routinely require.

### SCAT-B — multi-series scatter (2 groups), paper-methods archetype

```json
{"viz_type": "chartjs_scatter", "viz_dsl": "{\"type\": \"scatter\", \"data\": {\"datasets\": [{\"label\": \"Direct Preference Optimization (DPO)\", \"data\": [{\"x\": 1.0, \"y\": 0.521}, {\"x\": 2.0, \"y\": 0.598}, {\"x\": 4.0, \"y\": 0.642}, {\"x\": 8.0, \"y\": 0.671}], \"backgroundColor\": \"rgba(54, 162, 235, 0.7)\", \"borderColor\": \"rgba(54, 162, 235, 1)\", \"pointRadius\": 6}, {\"label\": \"PPO with Reward Model (RLHF)\", \"data\": [{\"x\": 1.0, \"y\": 0.539}, {\"x\": 2.0, \"y\": 0.611}, {\"x\": 4.0, \"y\": 0.658}, {\"x\": 8.0, \"y\": 0.682}], \"backgroundColor\": \"rgba(75, 192, 192, 0.7)\", \"borderColor\": \"rgba(75, 192, 192, 1)\", \"pointRadius\": 6}]}, \"options\": {\"responsive\": true, \"plugins\": {\"legend\": {\"position\": \"bottom\", \"title\": {\"display\": true, \"text\": \"Alignment Method\"}}, \"title\": {\"display\": true, \"text\": \"Helpful-Harmless Win-Rate vs Preference-Pair Budget — DPO vs PPO-RLHF on a 7B Base Model (Held-Out Eval Set)\"}}, \"scales\": {\"x\": {\"type\": \"logarithmic\", \"title\": {\"display\": true, \"text\": \"Preference-Pair Training Budget (Thousands, log scale)\"}}, \"y\": {\"beginAtZero\": false, \"title\": {\"display\": true, \"text\": \"Helpful-Harmless Win-Rate (vs SFT Baseline)\"}}}}}"}
```

- **Source**: hand-written.
- **Syntactic feature**: 2 datasets (per-group color separation) / 4 points
  each at matched x-positions (paired comparison) / **legend visible at
  bottom** with its own legend title (`"Alignment Method"`) / log-scale
  x-axis / `beginAtZero: false` y-axis (because the meaningful range is
  ~0.48-0.69, not 0-1).
- **Domain archetype**: paper-methods (alignment-method comparison).
- **Why faith intent**: trains the agent on **multi-series scatter**, where
  group identity is encoded by **dataset label + dataset color** (rather
  than embedded in the data array). Also reinforces the **paired-x scatter**
  convention papers use to compare methods at matched compute budgets.

### SCAT-C — bubble variant (3rd-dim radius), financial archetype

```json
{"viz_type": "chartjs_scatter", "viz_dsl": "{\"type\": \"bubble\", \"data\": {\"datasets\": [{\"label\": \"London Metal Exchange — 2024 Average Daily Spot Price vs Open Interest (Bubble Size = Notional Market Cap, USD Billions)\", \"data\": [{\"x\": 9420, \"y\": 412000, \"r\": 28}, {\"x\": 2715, \"y\": 287000, \"r\": 19}, {\"x\": 8150, \"y\": 198000, \"r\": 22}, {\"x\": 22300, \"y\": 64000, \"r\": 14}, {\"x\": 31.4, \"y\": 521000, \"r\": 9}], \"backgroundColor\": [\"rgba(255, 99, 132, 0.6)\", \"rgba(54, 162, 235, 0.6)\", \"rgba(255, 206, 86, 0.6)\", \"rgba(75, 192, 192, 0.6)\", \"rgba(153, 102, 255, 0.6)\"], \"borderColor\": [\"rgba(255, 99, 132, 1)\", \"rgba(54, 162, 235, 1)\", \"rgba(255, 206, 86, 1)\", \"rgba(75, 192, 192, 1)\", \"rgba(153, 102, 255, 1)\"]}]}, \"options\": {\"responsive\": true, \"plugins\": {\"legend\": {\"display\": false}, \"title\": {\"display\": true, \"text\": \"London Metal Exchange 2024 — Spot Price vs Open Interest for Five Base Metals (Bubble Radius Proportional to Notional Market Cap)\"}}, \"scales\": {\"x\": {\"type\": \"logarithmic\", \"title\": {\"display\": true, \"text\": \"Average 2024 Spot Price (USD per Tonne, log scale)\"}}, \"y\": {\"title\": {\"display\": true, \"text\": \"Average 2024 Open Interest (Lots Outstanding)\"}}}}}"}
```

- **Source**: hand-written.
- **Syntactic feature**: **`type: "bubble"`** (Chart.js's 3rd-dim variant of
  scatter — same family) / 5 points / `data` items have **`{x, y, r}`** (3
  fields, the bubble shape) / per-point color array / log-scale x-axis
  spanning ~31 to ~22 300 USD/tonne (4 orders of magnitude — log scale is
  load-bearing).
- **Domain archetype**: financial / commodities.
- **Why faith intent**: covers the **bubble (3rd-dim radius) sub-pattern**.
  Without this exemplar the agent will emit `r` as data when bubble is
  requested, or downgrade bubble to plain scatter and lose a dimension.
  The narrative dataset label spells out what the radius dimension encodes
  (`"Bubble Size = Notional Market Cap, USD Billions"`) — a convention the
  failing placeholder cannot teach.

---

## 2. Consolidated variant (V4_consolidated measurement)

A **single integrated example** that combines every `chartjs_scatter`
sub-pattern the agent should learn from one shot:

- **multi-series** (3 datasets — covers the SCAT-B group-separation case)
- **per-point variable marker radius** via `pointRadius: [n, n, n, n]` per
  dataset — the scatter-native way to encode a 3rd dimension *without*
  switching to `type: "bubble"` (so the agent learns both bubble-style
  radius encoding and scatter-with-pointRadius encoding)
- **log-scale x-axis** (covers SCAT-A and SCAT-B)
- **`beginAtZero: false` y-axis** (covers SCAT-B's meaningful-range
  convention)
- **legend visible at bottom with its own legend title** (covers SCAT-B)
- **narrative title** that spells out the marker-size encoding
- **3 architecturally distinct families** as datasets — a cross-family
  comparison that quantitative paper queries naturally produce

The integration is **coherent** — one chart, one domain (model survey) —
not a stitch of separate examples. Cross-pattern unification is achieved
by using `pointRadius: [array]` (which encodes per-point radius the same
way bubble's `r` field does) so the consolidated demonstrates 3rd-dim
encoding without leaving the `scatter` type.

```json
{"viz_type": "chartjs_scatter", "viz_dsl": "{\"type\": \"scatter\", \"data\": {\"datasets\": [{\"label\": \"Dense Transformer Models (Halverson 2024 Survey)\", \"data\": [{\"x\": 7, \"y\": 0.421, \"r\": 5}, {\"x\": 13, \"y\": 0.527, \"r\": 6}, {\"x\": 70, \"y\": 0.698, \"r\": 9}, {\"x\": 405, \"y\": 0.793, \"r\": 14}], \"backgroundColor\": \"rgba(54, 162, 235, 0.65)\", \"borderColor\": \"rgba(54, 162, 235, 1)\", \"pointRadius\": [5, 6, 9, 14]}, {\"label\": \"Mixture-of-Experts Models (Active-Param Reported)\", \"data\": [{\"x\": 8, \"y\": 0.503, \"r\": 6}, {\"x\": 22, \"y\": 0.612, \"r\": 8}, {\"x\": 47, \"y\": 0.701, \"r\": 11}, {\"x\": 132, \"y\": 0.764, \"r\": 16}], \"backgroundColor\": \"rgba(255, 99, 132, 0.65)\", \"borderColor\": \"rgba(255, 99, 132, 1)\", \"pointRadius\": [6, 8, 11, 16]}, {\"label\": \"Distilled / Pruned Variants\", \"data\": [{\"x\": 1.5, \"y\": 0.348, \"r\": 4}, {\"x\": 3.8, \"y\": 0.412, \"r\": 5}, {\"x\": 9.2, \"y\": 0.498, \"r\": 7}], \"backgroundColor\": \"rgba(75, 192, 192, 0.65)\", \"borderColor\": \"rgba(75, 192, 192, 1)\", \"pointRadius\": [4, 5, 7]}]}, \"options\": {\"responsive\": true, \"plugins\": {\"legend\": {\"position\": \"bottom\", \"title\": {\"display\": true, \"text\": \"Model Family (Marker Radius Proportional to Reported Throughput, tokens/sec)\"}}, \"title\": {\"display\": true, \"text\": \"Open-Weight Model MMLU Accuracy vs Active Parameter Count Across Three Architecture Families (Halverson 2024 Survey, Marker Size Encodes Decoded-Throughput)\"}}, \"scales\": {\"x\": {\"type\": \"logarithmic\", \"title\": {\"display\": true, \"text\": \"Active Parameter Count at Inference (Billions, log scale)\"}}, \"y\": {\"beginAtZero\": false, \"title\": {\"display\": true, \"text\": \"MMLU 5-Shot Accuracy\"}}}}}"}
```

- **Source**: hand-written; the Halverson 2024 model-survey domain
  through-line extends SCAT-A — the consolidated essentially elaborates
  SCAT-A into the multi-architecture, marker-sized form.
- **Domain archetype**: paper-methods (the dominant archetype for scatter;
  SCAT-C's financial archetype is intentionally *not* repeated here so
  the consolidated lives in the same archetype as the bulk of expected
  V4 traffic).
- **Integrated patterns**: 3 datasets (multi-series) / per-point variable
  `pointRadius` array (3rd-dim encoding without switching to bubble) /
  data items also carry an `r` field (still valid in scatter — Chart.js
  ignores it but it matches the bubble convention so the agent learns the
  union) / log-scale x-axis / `beginAtZero: false` y-axis / bottom legend
  with legend title that **explains the marker-size encoding** /
  narrative title with parenthetical qualifier and explicit encoding
  call-out / 6-band rgba colors with alpha for overlap legibility.
- **Length budget**: 1781 chars outer, 1557 chars inner DSL (≈ 400 tokens
  inner). Consolidated:pool ratio = 1557 / 1130 (SCAT-C) = **1.4×** —
  matches the v1 BAR (1.4×) and FLOW (1.4×) envelopes. Higher than pie
  because scatter consolidation requires multiple datasets (group
  separation cannot fold into 1 dataset the way pie's slices can).
- **Intent**: V4_consolidated independent measurement. Score on the same
  60-record subset as V4_pool; paired Δ = V4_cons − V4_pool.

---

## 3. Python literal — drop-in for `tmg.py`

### 3.1 Pool literal

```python
ONE_SHOT_POOL_BY_VIZ_TYPE["chartjs_scatter"] = [
    # SCAT-A — single-series 2D, paper-methods (MMLU vs param count)
    '{"viz_type": "chartjs_scatter", "viz_dsl": "{\\"type\\": \\"scatter\\", \\"data\\": {\\"datasets\\": [{\\"label\\": \\"Reported MMLU Accuracy vs Parameter Count (Open-Weight Models, July 2024 Survey)\\", \\"data\\": [{\\"x\\": 7, \\"y\\": 0.421}, {\\"x\\": 13, \\"y\\": 0.527}, {\\"x\\": 34, \\"y\\": 0.612}, {\\"x\\": 70, \\"y\\": 0.698}, {\\"x\\": 141, \\"y\\": 0.741}, {\\"x\\": 405, \\"y\\": 0.793}], \\"backgroundColor\\": \\"rgba(54, 162, 235, 0.7)\\", \\"borderColor\\": \\"rgba(54, 162, 235, 1)\\", \\"pointRadius\\": 6}]}, \\"options\\": {\\"responsive\\": true, \\"plugins\\": {\\"legend\\": {\\"display\\": false}, \\"title\\": {\\"display\\": true, \\"text\\": \\"Open-Weight Model MMLU Accuracy vs Parameter Count (Halverson Group July 2024 Survey, n=6 Released Models)\\"}}, \\"scales\\": {\\"x\\": {\\"type\\": \\"logarithmic\\", \\"title\\": {\\"display\\": true, \\"text\\": \\"Parameter Count (Billions, log scale)\\"}}, \\"y\\": {\\"beginAtZero\\": false, \\"title\\": {\\"display\\": true, \\"text\\": \\"MMLU 5-Shot Accuracy\\"}}}}}"}',
    # SCAT-B — 2-series scatter, paper-methods (DPO vs PPO-RLHF win-rate)
    '{"viz_type": "chartjs_scatter", "viz_dsl": "{\\"type\\": \\"scatter\\", \\"data\\": {\\"datasets\\": [{\\"label\\": \\"Direct Preference Optimization (DPO)\\", \\"data\\": [{\\"x\\": 1.0, \\"y\\": 0.521}, {\\"x\\": 2.0, \\"y\\": 0.598}, {\\"x\\": 4.0, \\"y\\": 0.642}, {\\"x\\": 8.0, \\"y\\": 0.671}], \\"backgroundColor\\": \\"rgba(54, 162, 235, 0.7)\\", \\"borderColor\\": \\"rgba(54, 162, 235, 1)\\", \\"pointRadius\\": 6}, {\\"label\\": \\"PPO with Reward Model (RLHF)\\", \\"data\\": [{\\"x\\": 1.0, \\"y\\": 0.539}, {\\"x\\": 2.0, \\"y\\": 0.611}, {\\"x\\": 4.0, \\"y\\": 0.658}, {\\"x\\": 8.0, \\"y\\": 0.682}], \\"backgroundColor\\": \\"rgba(75, 192, 192, 0.7)\\", \\"borderColor\\": \\"rgba(75, 192, 192, 1)\\", \\"pointRadius\\": 6}]}, \\"options\\": {\\"responsive\\": true, \\"plugins\\": {\\"legend\\": {\\"position\\": \\"bottom\\", \\"title\\": {\\"display\\": true, \\"text\\": \\"Alignment Method\\"}}, \\"title\\": {\\"display\\": true, \\"text\\": \\"Helpful-Harmless Win-Rate vs Preference-Pair Budget — DPO vs PPO-RLHF on a 7B Base Model (Held-Out Eval Set)\\"}}, \\"scales\\": {\\"x\\": {\\"type\\": \\"logarithmic\\", \\"title\\": {\\"display\\": true, \\"text\\": \\"Preference-Pair Training Budget (Thousands, log scale)\\"}}, \\"y\\": {\\"beginAtZero\\": false, \\"title\\": {\\"display\\": true, \\"text\\": \\"Helpful-Harmless Win-Rate (vs SFT Baseline)\\"}}}}}"}',
    # SCAT-C — bubble (3rd-dim r), financial (LME spot vs open interest)
    '{"viz_type": "chartjs_scatter", "viz_dsl": "{\\"type\\": \\"bubble\\", \\"data\\": {\\"datasets\\": [{\\"label\\": \\"London Metal Exchange — 2024 Average Daily Spot Price vs Open Interest (Bubble Size = Notional Market Cap, USD Billions)\\", \\"data\\": [{\\"x\\": 9420, \\"y\\": 412000, \\"r\\": 28}, {\\"x\\": 2715, \\"y\\": 287000, \\"r\\": 19}, {\\"x\\": 8150, \\"y\\": 198000, \\"r\\": 22}, {\\"x\\": 22300, \\"y\\": 64000, \\"r\\": 14}, {\\"x\\": 31.4, \\"y\\": 521000, \\"r\\": 9}], \\"backgroundColor\\": [\\"rgba(255, 99, 132, 0.6)\\", \\"rgba(54, 162, 235, 0.6)\\", \\"rgba(255, 206, 86, 0.6)\\", \\"rgba(75, 192, 192, 0.6)\\", \\"rgba(153, 102, 255, 0.6)\\"], \\"borderColor\\": [\\"rgba(255, 99, 132, 1)\\", \\"rgba(54, 162, 235, 1)\\", \\"rgba(255, 206, 86, 1)\\", \\"rgba(75, 192, 192, 1)\\", \\"rgba(153, 102, 255, 1)\\"]}]}, \\"options\\": {\\"responsive\\": true, \\"plugins\\": {\\"legend\\": {\\"display\\": false}, \\"title\\": {\\"display\\": true, \\"text\\": \\"London Metal Exchange 2024 — Spot Price vs Open Interest for Five Base Metals (Bubble Radius Proportional to Notional Market Cap)\\"}}, \\"scales\\": {\\"x\\": {\\"type\\": \\"logarithmic\\", \\"title\\": {\\"display\\": true, \\"text\\": \\"Average 2024 Spot Price (USD per Tonne, log scale)\\"}}, \\"y\\": {\\"title\\": {\\"display\\": true, \\"text\\": \\"Average 2024 Open Interest (Lots Outstanding)\\"}}}}}"}',
]
```

### 3.2 Consolidated literal

```python
ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE["chartjs_scatter"] = (
    '{"viz_type": "chartjs_scatter", "viz_dsl": "{\\"type\\": \\"scatter\\", \\"data\\": {\\"datasets\\": [{\\"label\\": \\"Dense Transformer Models (Halverson 2024 Survey)\\", \\"data\\": [{\\"x\\": 7, \\"y\\": 0.421, \\"r\\": 5}, {\\"x\\": 13, \\"y\\": 0.527, \\"r\\": 6}, {\\"x\\": 70, \\"y\\": 0.698, \\"r\\": 9}, {\\"x\\": 405, \\"y\\": 0.793, \\"r\\": 14}], \\"backgroundColor\\": \\"rgba(54, 162, 235, 0.65)\\", \\"borderColor\\": \\"rgba(54, 162, 235, 1)\\", \\"pointRadius\\": [5, 6, 9, 14]}, {\\"label\\": \\"Mixture-of-Experts Models (Active-Param Reported)\\", \\"data\\": [{\\"x\\": 8, \\"y\\": 0.503, \\"r\\": 6}, {\\"x\\": 22, \\"y\\": 0.612, \\"r\\": 8}, {\\"x\\": 47, \\"y\\": 0.701, \\"r\\": 11}, {\\"x\\": 132, \\"y\\": 0.764, \\"r\\": 16}], \\"backgroundColor\\": \\"rgba(255, 99, 132, 0.65)\\", \\"borderColor\\": \\"rgba(255, 99, 132, 1)\\", \\"pointRadius\\": [6, 8, 11, 16]}, {\\"label\\": \\"Distilled / Pruned Variants\\", \\"data\\": [{\\"x\\": 1.5, \\"y\\": 0.348, \\"r\\": 4}, {\\"x\\": 3.8, \\"y\\": 0.412, \\"r\\": 5}, {\\"x\\": 9.2, \\"y\\": 0.498, \\"r\\": 7}], \\"backgroundColor\\": \\"rgba(75, 192, 192, 0.65)\\", \\"borderColor\\": \\"rgba(75, 192, 192, 1)\\", \\"pointRadius\\": [4, 5, 7]}]}, \\"options\\": {\\"responsive\\": true, \\"plugins\\": {\\"legend\\": {\\"position\\": \\"bottom\\", \\"title\\": {\\"display\\": true, \\"text\\": \\"Model Family (Marker Radius Proportional to Reported Throughput, tokens/sec)\\"}}, \\"title\\": {\\"display\\": true, \\"text\\": \\"Open-Weight Model MMLU Accuracy vs Active Parameter Count Across Three Architecture Families (Halverson 2024 Survey, Marker Size Encodes Decoded-Throughput)\\"}}, \\"scales\\": {\\"x\\": {\\"type\\": \\"logarithmic\\", \\"title\\": {\\"display\\": true, \\"text\\": \\"Active Parameter Count at Inference (Billions, log scale)\\"}}, \\"y\\": {\\"beginAtZero\\": false, \\"title\\": {\\"display\\": true, \\"text\\": \\"MMLU 5-Shot Accuracy\\"}}}}}"}'
)
```

> **Note on Python literal escapes**: same convention as v1 chartjs_*: the
> outer Python string contains `\"` which JSON parses as a literal `"`
> inside the inner `viz_dsl` JSON string. The chartjs DSL itself is a
> JSON-string-encoded JSON object. The `data` array items are objects
> (`{"x": ..., "y": ...}`) — NOT parallel arrays — this is the load-
> bearing scatter convention.

---

## 4. 검수 체크리스트 (mentor risk #5 + risk #2 alignment)

- [x] **Syntactic spread of 3 pool exemplars**:
  - SCAT-A: 1 dataset / 6 points / `{x, y}` items / log x-scale / hidden
    legend
  - SCAT-B: 2 datasets / 4 points each at matched x / `{x, y}` items /
    log x-scale / `beginAtZero: false` y / bottom legend with legend title
  - SCAT-C: `type: "bubble"` / 1 dataset / 5 points / `{x, y, r}` items /
    log x-scale spanning 4 orders of magnitude / per-point color array
  → covers (single-vs-multi-series × type-scatter-vs-type-bubble × log-x ×
  legend-position) cube. Specifically covers the **`data` items are
  objects** convention (vs line's parallel-array convention) — the #1
  scatter syntactic risk.
- [x] **All hand-written — honest disclosure**: this viz_type has **no
  historical anchor** in the prototype pool. All 4 exemplars are
  explicitly disclosed as hand-written. Content style anchored on v1
  chartjs_line conventions (paper-methods quantitative; log-scale axes;
  multi-series with discriminating legend) so the agent inherits the same
  faith-1.00 conventions transitively across the chart family.
- [x] **Placeholder regression check**: no `Acme*`, no `Founder/Engineer X`,
  no `Q1/Q2/Q3/Q4`, no `(0,0)/(1,1)/(2,2)` toy-data style. All entity
  names are fictional generic-domain (Halverson Group / London Metal
  Exchange — generic real exchange used as setting; fictional models DPO/
  PPO-RLHF are the **technique names**, not entity placeholders).
- [x] **Consolidated variant integration**: a single coherent scatter chart
  that carries (multi-series 3-dataset) × (per-point variable marker
  radius via `pointRadius: [array]`) × (data items also carry `r` field
  for bubble-style union) × (log x-scale) × (`beginAtZero: false` y) ×
  (bottom legend with encoding-explaining legend title) × (narrative
  title with explicit marker-size encoding call-out). No stitching; one
  chart / 3 datasets in the same family.
- [x] **JSON round-trip**: all 4 strings (3 pool + 1 consolidated) parse
  via `json.loads`; inner `viz_dsl` value also parses via `json.loads`
  (chartjs schema preserved); `viz_type == "chartjs_scatter"` for all;
  inner `type ∈ {"scatter", "bubble"}` (both Chart.js-legal under the
  `chartjs_scatter` family); inner `data.datasets[*].data[*]` items all
  contain `x` and `y` keys (asserted by spec — see §1 commentary).
- [x] **Token budget**: pool max = 1130 chars (SCAT-C) ≈ 290 tokens;
  consolidated = 1557 chars ≈ 400 tokens (1.4× pool max — matches v1
  BAR/FLOW envelope; higher than pie because group-separation requires
  multiple datasets).
- [x] **Self-validation result**: PASS. All 4 exemplars round-trip via
  `json.loads`; inner JSON parses for all 4; every inner data item has
  `x` and `y`; SCAT-C / SCAT-CONS additionally carry `r`; no placeholder
  substring; consolidated:pool char ratio = 1.4×.
