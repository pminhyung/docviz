# `chartjs_line` exemplar pool — revision v1

**Date**: 2026-05-10
**Status**: revision v1 (supersedes the `chartjs_line` portion of
`docs/analysis/tmg_oneshot_pool_draft.md` v0). v0 archived for paired
diff evidence; do **not** edit it.

**Changes vs v0** (driven by `tmg_oneshot_pool_review.md`):
- LINE-A unchanged (only `Lakeshore Foundation` reused — kept here, swapped
  out of GBAR-B; see `chartjs_grouped_bar.md`).
- LINE-B unchanged (paper-methods archetype, hand-written, anchored on
  `arxiv_00_comparative` faith 1.00).
- Must-fix #1: LINE-C `Acme Industries` → `Verdant Aerospace`.
- Added consolidated variant (V4_consolidated measurement); see §2.

**Cell-data-starvation note**: `chartjs_line` has only 1 record in the
180-record prototype pool that reaches `faith ≥ 0.75` (LINE-A's anchor).
LINE-B and LINE-C are therefore hand-written and explicitly disclosed.

---

## 1. Pool variant (V4_pool measurement)

3 exemplars covering distinct `chartjs_line` syntactic shapes.

### LINE-A — yearly single-series, financial-philanthropy archetype

```json
{"viz_type": "chartjs_line", "viz_dsl": "{\"type\":\"line\",\"data\":{\"labels\":[\"2018\",\"2019\",\"2020\",\"2021\",\"2022\",\"2023\"],\"datasets\":[{\"label\":\"Lakeshore Foundation Annual Endowment Disbursements (Millions USD)\",\"data\":[412,468,521,602,718,805],\"borderColor\":\"rgb(75, 192, 192)\",\"backgroundColor\":\"rgba(75, 192, 192, 0.2)\",\"tension\":0.1}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Disbursement (Millions USD)\"}},\"x\":{\"title\":{\"display\":true,\"text\":\"Calendar Year\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Lakeshore Foundation Endowment Disbursements, 2018–2023\"}}}}"}
```

- **Anchor**: `multinews_09_temporal` / S1_Direct (faith 0.75, overall 0.92);
  rewritten with 6 yearly points instead of 3 to extend the trend; lifted
  to a fictional foundation.
- **Syntactic feature**: 1 series / 6 yearly points / monotone trend /
  date-range title.
- **Domain archetype**: news / financial-philanthropy.
- **Why faith**: gives a clean **single-trend metric** template with
  unit-explicit dataset label embedded in the legend (rather than a bare
  `"Active Users (M)"`) — the pattern that survives Mermaid-side flattening.

### LINE-B — multi-series 5-year compare, paper-methods archetype

```json
{"viz_type": "chartjs_line", "viz_dsl": "{\"type\":\"line\",\"data\":{\"labels\":[\"2019\",\"2020\",\"2021\",\"2022\",\"2023\"],\"datasets\":[{\"label\":\"Encoder-only (Top-1 Accuracy %)\",\"data\":[71.2,74.5,77.0,78.4,79.1],\"borderColor\":\"rgb(54, 162, 235)\",\"backgroundColor\":\"rgba(54, 162, 235, 0.2)\",\"tension\":0.2},{\"label\":\"Decoder-only (Top-1 Accuracy %)\",\"data\":[68.0,72.8,76.5,80.2,83.4],\"borderColor\":\"rgb(255, 99, 132)\",\"backgroundColor\":\"rgba(255, 99, 132, 0.2)\",\"tension\":0.2}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":false,\"title\":{\"display\":true,\"text\":\"Top-1 Accuracy on ImageNet-1k Eval Slice (%)\"}},\"x\":{\"title\":{\"display\":true,\"text\":\"Publication Year\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Vision Backbone Family Accuracy Trajectories on ImageNet-1k (2019–2023)\"},\"legend\":{\"display\":true,\"position\":\"top\"}}}}"}
```

- **Source**: hand-written (no multi-series chartjs_line anchor met
  threshold); content style anchored on `arxiv_00_comparative` mindmap label
  patterns (faith 1.00) and on the LINE-A label format.
- **Syntactic feature**: 2 series / 5 yearly points / comparison trend /
  `beginAtZero: false` to expose mid-range deltas / top legend.
- **Domain archetype**: paper-methods.
- **Why faith**: trains the agent that line-chart series labels can carry
  a **named evaluation slice** (`"Top-1 Accuracy on ImageNet-1k Eval
  Slice"`) and that the x-axis can name a calendar cadence
  (`"Publication Year"`) — guards against collapsing to bare integer labels.

### LINE-C — cumulative-metric 7-point, financial archetype

```json
{"viz_type": "chartjs_line", "viz_dsl": "{\"type\":\"line\",\"data\":{\"labels\":[\"FY2017\",\"FY2018\",\"FY2019\",\"FY2020\",\"FY2021\",\"FY2022\",\"FY2023\"],\"datasets\":[{\"label\":\"Cumulative R&D Capitalization (Billions USD)\",\"data\":[3.1,7.4,12.8,19.6,27.9,38.4,51.2],\"borderColor\":\"rgb(153, 102, 255)\",\"backgroundColor\":\"rgba(153, 102, 255, 0.25)\",\"fill\":true,\"tension\":0.15}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Cumulative Capitalization (Billions USD)\"}},\"x\":{\"title\":{\"display\":true,\"text\":\"Fiscal Year\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Verdant Aerospace Cumulative R&D Capitalization, FY2017–FY2023\"},\"legend\":{\"display\":false}}}}"}
```

- **Source**: hand-written, anchored on `10k_*_quantitative` content-style
  patterns (faith 1.00 in BAR-A and BAR-B anchors).
- **Syntactic feature**: 1 series / 7 fiscal-year points / **cumulative**
  (monotone increasing) shape / area-fill on / fiscal-year label cadence.
- **Domain archetype**: financial (aerospace 10-K analog).
- **Why faith**: covers the **cumulative trajectory** sub-shape (vs LINE-A's
  flow trend and LINE-B's compare trend) — without this, the agent has no
  template for "running total" metrics that 10-K queries occasionally need.

---

## 2. Consolidated variant (V4_consolidated measurement)

A single integrated example combining every `chartjs_line` sub-pattern:

- **multi-series compare** (2 lines)
- one line is a **flow trend** (raw metric, monotone-ish)
- the other is a **cumulative trajectory** (`fill: true`, monotone)
- **mixed cadence labels**: the x-axis uses fiscal-year (`FY2018`-style)
  labels — the agent learns FY-Q labels are valid `chartjs_line` x-tick text
- **named evaluation slice** in series labels
- explicit unit-bearing axis title with **two y-axes** style (one cumulative,
  one rate) — but expressed as a single `y` axis carrying both metrics in
  the same units, since chartjs_line is single-y by paper convention; the
  consolidation comes from showing both flow-style and cumulative-style
  series **drawn as one chart** with a shared scale.

```json
{"viz_type": "chartjs_line", "viz_dsl": "{\"type\":\"line\",\"data\":{\"labels\":[\"FY2018\",\"FY2019\",\"FY2020\",\"FY2021\",\"FY2022\",\"FY2023\"],\"datasets\":[{\"label\":\"Annual Capital Expenditure (Billions USD)\",\"data\":[2.4,2.9,3.6,4.1,5.0,5.8],\"borderColor\":\"rgb(54, 162, 235)\",\"backgroundColor\":\"rgba(54, 162, 235, 0.15)\",\"fill\":false,\"tension\":0.15},{\"label\":\"Cumulative Capital Expenditure since FY2018 (Billions USD)\",\"data\":[2.4,5.3,8.9,13.0,18.0,23.8],\"borderColor\":\"rgb(255, 99, 132)\",\"backgroundColor\":\"rgba(255, 99, 132, 0.20)\",\"fill\":true,\"tension\":0.10}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Capital Expenditure (Billions USD)\"}},\"x\":{\"title\":{\"display\":true,\"text\":\"Fiscal Year (Pemberton Charitable Trust Capital Programme)\"}}},\"plugins\":{\"title\":{\"display\":true,\"text\":\"Pemberton Charitable Trust Capital Programme — Annual vs Cumulative Capex Trajectories, FY2018–FY2023\"},\"legend\":{\"display\":true,\"position\":\"top\"}}}}"}
```

- **Source**: hand-written; anchored on `multinews_09_temporal` (LINE-A
  faith 0.75) for the date-range title, and on the cumulative-trajectory
  pattern from BAR-style 10-K anchors.
- **Domain archetype**: financial-philanthropy (distinct from LINE-A's
  endowment-disbursement narrative and LINE-B's paper-methods compare).
- **Integrated patterns**: 2 series in one chart / one series flow-trend
  (`fill: false`) / one series cumulative (`fill: true`) / FY-cadence labels
  / unit-explicit shared y-axis / parenthetical scope on x-axis title /
  date-range narrative title / top legend.
- **Length budget**: 1100 chars ≈ ~290 tokens.
- **Intent**: V4_consolidated independent measurement; paired Δ vs V4_pool
  on the same 60-record subset.

---

## 3. Python literal — drop-in for `tmg.py`

### 3.1 Pool literal

```python
ONE_SHOT_POOL_BY_VIZ_TYPE["chartjs_line"] = [
    # LINE-A — yearly single-series, financial-philanthropy archetype (Lakeshore Foundation)
    '{"viz_type": "chartjs_line", "viz_dsl": "{\\"type\\":\\"line\\",\\"data\\":{\\"labels\\":[\\"2018\\",\\"2019\\",\\"2020\\",\\"2021\\",\\"2022\\",\\"2023\\"],\\"datasets\\":[{\\"label\\":\\"Lakeshore Foundation Annual Endowment Disbursements (Millions USD)\\",\\"data\\":[412,468,521,602,718,805],\\"borderColor\\":\\"rgb(75, 192, 192)\\",\\"backgroundColor\\":\\"rgba(75, 192, 192, 0.2)\\",\\"tension\\":0.1}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Disbursement (Millions USD)\\"}},\\"x\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Calendar Year\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Lakeshore Foundation Endowment Disbursements, 2018–2023\\"}}}}"}',
    # LINE-B — multi-series 5-year compare, paper-methods archetype (hand-written)
    '{"viz_type": "chartjs_line", "viz_dsl": "{\\"type\\":\\"line\\",\\"data\\":{\\"labels\\":[\\"2019\\",\\"2020\\",\\"2021\\",\\"2022\\",\\"2023\\"],\\"datasets\\":[{\\"label\\":\\"Encoder-only (Top-1 Accuracy %)\\",\\"data\\":[71.2,74.5,77.0,78.4,79.1],\\"borderColor\\":\\"rgb(54, 162, 235)\\",\\"backgroundColor\\":\\"rgba(54, 162, 235, 0.2)\\",\\"tension\\":0.2},{\\"label\\":\\"Decoder-only (Top-1 Accuracy %)\\",\\"data\\":[68.0,72.8,76.5,80.2,83.4],\\"borderColor\\":\\"rgb(255, 99, 132)\\",\\"backgroundColor\\":\\"rgba(255, 99, 132, 0.2)\\",\\"tension\\":0.2}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":false,\\"title\\":{\\"display\\":true,\\"text\\":\\"Top-1 Accuracy on ImageNet-1k Eval Slice (%)\\"}},\\"x\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Publication Year\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Vision Backbone Family Accuracy Trajectories on ImageNet-1k (2019–2023)\\"},\\"legend\\":{\\"display\\":true,\\"position\\":\\"top\\"}}}}"}',
    # LINE-C — cumulative-metric 7-point, financial archetype (Verdant Aerospace)
    '{"viz_type": "chartjs_line", "viz_dsl": "{\\"type\\":\\"line\\",\\"data\\":{\\"labels\\":[\\"FY2017\\",\\"FY2018\\",\\"FY2019\\",\\"FY2020\\",\\"FY2021\\",\\"FY2022\\",\\"FY2023\\"],\\"datasets\\":[{\\"label\\":\\"Cumulative R&D Capitalization (Billions USD)\\",\\"data\\":[3.1,7.4,12.8,19.6,27.9,38.4,51.2],\\"borderColor\\":\\"rgb(153, 102, 255)\\",\\"backgroundColor\\":\\"rgba(153, 102, 255, 0.25)\\",\\"fill\\":true,\\"tension\\":0.15}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Cumulative Capitalization (Billions USD)\\"}},\\"x\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Fiscal Year\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Verdant Aerospace Cumulative R&D Capitalization, FY2017–FY2023\\"},\\"legend\\":{\\"display\\":false}}}}"}',
]
```

### 3.2 Consolidated literal

```python
ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE["chartjs_line"] = (
    '{"viz_type": "chartjs_line", "viz_dsl": "{\\"type\\":\\"line\\",\\"data\\":{\\"labels\\":[\\"FY2018\\",\\"FY2019\\",\\"FY2020\\",\\"FY2021\\",\\"FY2022\\",\\"FY2023\\"],\\"datasets\\":[{\\"label\\":\\"Annual Capital Expenditure (Billions USD)\\",\\"data\\":[2.4,2.9,3.6,4.1,5.0,5.8],\\"borderColor\\":\\"rgb(54, 162, 235)\\",\\"backgroundColor\\":\\"rgba(54, 162, 235, 0.15)\\",\\"fill\\":false,\\"tension\\":0.15},{\\"label\\":\\"Cumulative Capital Expenditure since FY2018 (Billions USD)\\",\\"data\\":[2.4,5.3,8.9,13.0,18.0,23.8],\\"borderColor\\":\\"rgb(255, 99, 132)\\",\\"backgroundColor\\":\\"rgba(255, 99, 132, 0.20)\\",\\"fill\\":true,\\"tension\\":0.10}]},\\"options\\":{\\"scales\\":{\\"y\\":{\\"beginAtZero\\":true,\\"title\\":{\\"display\\":true,\\"text\\":\\"Capital Expenditure (Billions USD)\\"}},\\"x\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Fiscal Year (Pemberton Charitable Trust Capital Programme)\\"}}},\\"plugins\\":{\\"title\\":{\\"display\\":true,\\"text\\":\\"Pemberton Charitable Trust Capital Programme — Annual vs Cumulative Capex Trajectories, FY2018–FY2023\\"},\\"legend\\":{\\"display\\":true,\\"position\\":\\"top\\"}}}}"}'
)
```

---

## 4. 검수 체크리스트

- [x] **Syntactic spread of 3 pool exemplars**:
  - LINE-A: 1 series / 6 yearly points / flow trend / no fill
  - LINE-B: 2 series / 5 yearly points / compare / `beginAtZero: false`
  - LINE-C: 1 series / 7 FY points / cumulative / `fill: true`
  → covers (1 vs 2 series) × (6 vs 5 vs 7 points) × (flow vs compare vs
  cumulative) × (calendar-year vs FY) × (zero-baseline vs not).
- [x] **Anchor authenticity**: LINE-A anchored (faith 0.75); LINE-B / LINE-C
  hand-written and **explicitly disclosed**; the cell-data starvation note
  is preserved at the top of this file. v0 reviewer note 4.1#1 carries
  forward — recommend a 5-query line-only smoke pilot before paper batch.
- [x] **Placeholder regression check**: no `Acme*` (was BAR-A's pattern, also
  removed from LINE-C → `Verdant Aerospace`), no `Founder/Engineer X`, no
  `Active Users (M)` minimal label. All entity names fictional generic-
  domain (Lakeshore Foundation / Verdant Aerospace / Pemberton Charitable
  Trust). Lakeshore appears only in LINE-A here (GBAR-B in v0 also reused
  Lakeshore — see `chartjs_grouped_bar.md` for the GBAR-B swap).
- [x] **Consolidated variant integration**: a single coherent chart that
  combines (multi-series) × (flow-trend dataset) × (cumulative dataset with
  `fill: true`) × (FY-cadence labels) × (named scope on x-axis) × (date-range
  narrative title). One chart, one shared y-axis.
- [x] **JSON round-trip**: all 4 strings parse via `json.loads`; inner
  `viz_dsl` value also parses (chartjs schema preserved); `viz_type ==
  "chartjs_line"` for all.
- [x] **Token budget for consolidated**: ~1100 chars ≈ ~290 tokens.
