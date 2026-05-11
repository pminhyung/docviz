# `mermaid_timeline` exemplar pool — revision v1

**Date**: 2026-05-10
**Status**: revision v1 (supersedes the `mermaid_timeline` portion of
`docs/analysis/tmg_oneshot_pool_draft.md` v0). v0 archived; do **not**
edit it.

**Changes vs v0** (driven by `tmg_oneshot_pool_review.md`):
- Must-fix #1: TIME-A `Acme Industries` → `Atlas Robotics`.
- TIME-B unchanged (Brookfield Grammar School & Annual Show fictional
  compare; Wikipedia archetype; anchored on `hotpot_01_comparative` faith
  1.00).
- TIME-C unchanged (Cinderfall Franchise era-transition; news/Wikipedia-
  pop-culture archetype; anchored on `hotpot_04_relational` faith 1.00).
- Added consolidated variant (V4_consolidated measurement); see §2.

---

## 1. Pool variant (V4_pool measurement)

3 exemplars covering distinct `mermaid_timeline` cadence shapes:
**quarterly multi-event-per-section** (TIME-A) / **2 named heterogeneous
sections** (TIME-B) / **named eras with multi-line `<br>` event detail**
(TIME-C).

### TIME-A — quarterly section, multi-event-per-quarter, financial archetype

```json
{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\n    title Atlas Robotics 2025 Product Announcements by Quarter\n    section Q1 2025\n        Foundry-Series Workstation : \n        Compact-Series Desktop : \n        Studio-Series All-in-One : \n        Compact-Series Tablet : \n    section Q2 2025\n        Sentinel-17e Smartphone : \n        Studio-Series Tablet Air : \n        Studio-Series Tablet : \n        Foundry-Series Notebook Air : \n        Studio-Series Compute Module : \n    section Q3 2025\n        OS Release: Cascade 26 : \n        OS Release: Cascade 26 Workstation : \n        OS Release: Cascade 26 Tablet : \n        OS Release: Cascade 26 Wearable : \n        OS Release: Cascade 26 Spatial : \n    section Q4 2025\n        Sentinel-18 Smartphone : \n        Sentinel Air Smartphone : \n        Sentinel-18 Pro Smartphone : \n        Sentinel-18 Pro Max Smartphone : \n        Wearable Series 12 : \n        Wearable SE Generation 4 : \n        Wearable Ultra Generation 4 : \n        Earbud Pro Generation 4 : "}
```

- **Anchor**: `10k_00_temporal` / S1_Direct (faith 1.00, overall 1.00);
  paraphrased to a fictional robotics company's 2025 product line to avoid
  lift of Apple SKU names.
- **Syntactic feature**: 4 quarterly sections / **multi-event-per-section**
  (4–8 items per quarter) / trailing `: ` empty-detail (a known Mermaid
  pattern this team's renderer accepts).
- **Domain archetype**: financial / product-announcement.
- **Why faith**: replaces the placeholder's 4-row `2018/2020/2022/2024`
  toy with a **quarter-bucketed product-cadence** template — exactly the
  sub-shape `10k_00_temporal` and `10k_03_temporal` need.

### TIME-B — 2 named sections, sparse single-events, Wikipedia archetype

```json
{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\n    title Brookfield Grammar School & Brookfield Annual Show — Comparative Timeline\n    section Brookfield Grammar School History\n        1956 : Founded as a single-stream grammar school for boys\n        1978 : Reconstituted as a comprehensive coeducational secondary school\n        2003 : Awarded specialist Performing Arts College status\n    section Brookfield Annual Show Schedule\n        June (third Saturday) : One-day public exhibition held on school grounds\n        September (first weekend) : Inter-school music and theatre showcase"}
```

- **Anchor**: `hotpot_01_comparative` / S1_Direct (faith 1.00, overall 1.00);
  paraphrased to a fictional school + annual show compare.
- **Syntactic feature**: **2 named sections** (heterogeneous content —
  history vs schedule) / single-event-per-line / **mixed cadence**: one
  section uses calendar years, the other uses recurring-date-strings.
- **Domain archetype**: Wikipedia-historical.
- **Why faith**: trains the agent to pair **a year-based section with a
  recurring-date-based section** in the same timeline — a shape the
  current placeholder's flat year-list cannot teach.

### TIME-C — 3 named eras with multi-line `<br>` event detail, news archetype

```json
{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\n    title Cinderfall Franchise Lead-Cast Transition Across Twelve Years\n    section 2008–2013 : Marston Era\n        2008 : Cinderfall<br>Starring Iris Marston as Captain Lyra Vance\n        2013 : Cinderfall: Vanishing Point<br>Starring Iris Marston as Captain Lyra Vance\n    section 2016–2018 : Halberg Era\n        2016 : Cinderfall: Reckoning<br>Starring Bjorn Halberg as Captain Lyra Vance (recast after Marston exit)\n        2018 : Cinderfall: Severance<br>Starring Bjorn Halberg as Captain Lyra Vance\n    section 2020 : Okafor Era\n        2020 : Cinderfall: Heir of Ash<br>Starring Tomi Okafor as Lieutenant Sela Reyes (new protagonist; Vance role retired)"}
```

- **Anchor**: `hotpot_04_relational` / S4_Agentic (faith 1.00, overall 1.00);
  paraphrased to a fictional film franchise.
- **Syntactic feature**: **3 named eras** as section headings / multi-line
  `<br>` event detail (title + cast role) / explicit **transition
  annotation** (`"recast after"`, `"new protagonist; … role retired"`).
- **Domain archetype**: news / Wikipedia-pop-culture.
- **Why faith**: covers the **named-era transition** sub-shape that
  hotpotqa relational queries on franchises/dynasties/regimes need — the
  placeholder's bare year list cannot represent era boundaries or
  transition causes.

---

## 2. Consolidated variant (V4_consolidated measurement)

A single integrated `mermaid_timeline` that, **inside one coherent
timeline rooted at one title**, exhibits:

- a **named-era section** (date-range era heading)
- a **calendar-year section** with single events per year
- a **quarter-bucketed section** with **multi-event-per-quarter** entries
- a **recurring-date-string section** (mixed cadence)
- **multi-line `<br>` event detail** on at least one entry
- **transition-annotation** on at least one entry

The integration is achieved by using **one consistent domain** (a single
fictional research lab's history rendered through 4 cadence styles, since
real institutional histories naturally span eras, calendar years, intra-
year quarters, and recurring annual events).

```json
{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\n    title Foundry Research Institute — Founding to 2025 Operating Cadence\n    section 1998–2007 : Founding Era\n        1998 : Founded as the Foundry Lab inside Whitfield University\n        2003 : Spun out as an independent 501(c)(3) research institute\n        2007 : Moved to its current Bay Campus<br>Endowment crossed $40M for the first time\n    section 2014 : Expansion Year\n        Opened Cape Halverton satellite office\n        Hired first VP of Research<br>Dr. Naomi Castellan recruited from Stanford\n        Launched Open Science Programme\n    section 2024 by Quarter\n        Q1 2024 : Calibrated Self-Critique v2.0 Public Release\n        Q1 2024 : csc-eval Conformance Test Suite\n        Q2 2024 : Quarterly Public Audit Report — Spring Edition\n        Q3 2024 : Refusal-Aware RM Workshop at NeurIPS\n        Q4 2024 : Quarterly Public Audit Report — Winter Edition\n    section Annual Recurring Cadence\n        First Monday of February : Annual Research Symposium (closed-door)\n        Last Friday of June : Open-House Demonstration Day\n        Mid-October : Independent Reviewer Panel rotation"}
```

- **Source**: hand-written; content style anchored on TIME-A (quarterly
  multi-event), TIME-B (mixed-cadence sections), TIME-C (named-era with
  `<br>` detail and transition annotation).
- **Domain archetype**: research-institute provenance (one consistent
  organisational history, not a stitch of unrelated examples).
- **Integrated patterns**:
  - section 1: **named-era** (`1998–2007 : Founding Era`) with calendar-
    year events, one with `<br>` multi-line detail
  - section 2: **single-year intra-year** section (`2014 : Expansion Year`)
    with multiple bullet events under one year, one with `<br>` and
    transition annotation (recruitment from Stanford)
  - section 3: **quarterly** section with multiple events per quarter
  - section 4: **recurring-date-string** section (mixed cadence — annual
    rituals)
  - title carries date-range context
- **Length budget**: 1180 chars ≈ ~310 tokens.
- **Intent**: V4_consolidated independent measurement.

---

## 3. Python literal — drop-in for `tmg.py`

### 3.1 Pool literal

```python
ONE_SHOT_POOL_BY_VIZ_TYPE["mermaid_timeline"] = [
    # TIME-A — quarterly section, multi-event-per-quarter, financial archetype (Atlas Robotics)
    '{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\\n    title Atlas Robotics 2025 Product Announcements by Quarter\\n    section Q1 2025\\n        Foundry-Series Workstation : \\n        Compact-Series Desktop : \\n        Studio-Series All-in-One : \\n        Compact-Series Tablet : \\n    section Q2 2025\\n        Sentinel-17e Smartphone : \\n        Studio-Series Tablet Air : \\n        Studio-Series Tablet : \\n        Foundry-Series Notebook Air : \\n        Studio-Series Compute Module : \\n    section Q3 2025\\n        OS Release: Cascade 26 : \\n        OS Release: Cascade 26 Workstation : \\n        OS Release: Cascade 26 Tablet : \\n        OS Release: Cascade 26 Wearable : \\n        OS Release: Cascade 26 Spatial : \\n    section Q4 2025\\n        Sentinel-18 Smartphone : \\n        Sentinel Air Smartphone : \\n        Sentinel-18 Pro Smartphone : \\n        Sentinel-18 Pro Max Smartphone : \\n        Wearable Series 12 : \\n        Wearable SE Generation 4 : \\n        Wearable Ultra Generation 4 : \\n        Earbud Pro Generation 4 : "}',
    # TIME-B — 2 named sections, sparse single-events, Wikipedia archetype
    '{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\\n    title Brookfield Grammar School & Brookfield Annual Show \\u2014 Comparative Timeline\\n    section Brookfield Grammar School History\\n        1956 : Founded as a single-stream grammar school for boys\\n        1978 : Reconstituted as a comprehensive coeducational secondary school\\n        2003 : Awarded specialist Performing Arts College status\\n    section Brookfield Annual Show Schedule\\n        June (third Saturday) : One-day public exhibition held on school grounds\\n        September (first weekend) : Inter-school music and theatre showcase"}',
    # TIME-C — 3 named eras with multi-line <br> event detail, news archetype
    '{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\\n    title Cinderfall Franchise Lead-Cast Transition Across Twelve Years\\n    section 2008\\u20132013 : Marston Era\\n        2008 : Cinderfall<br>Starring Iris Marston as Captain Lyra Vance\\n        2013 : Cinderfall: Vanishing Point<br>Starring Iris Marston as Captain Lyra Vance\\n    section 2016\\u20132018 : Halberg Era\\n        2016 : Cinderfall: Reckoning<br>Starring Bjorn Halberg as Captain Lyra Vance (recast after Marston exit)\\n        2018 : Cinderfall: Severance<br>Starring Bjorn Halberg as Captain Lyra Vance\\n    section 2020 : Okafor Era\\n        2020 : Cinderfall: Heir of Ash<br>Starring Tomi Okafor as Lieutenant Sela Reyes (new protagonist; Vance role retired)"}',
]
```

### 3.2 Consolidated literal

```python
ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE["mermaid_timeline"] = (
    '{"viz_type": "mermaid_timeline", "viz_dsl": "timeline\\n    title Foundry Research Institute \\u2014 Founding to 2025 Operating Cadence\\n    section 1998\\u20132007 : Founding Era\\n        1998 : Founded as the Foundry Lab inside Whitfield University\\n        2003 : Spun out as an independent 501(c)(3) research institute\\n        2007 : Moved to its current Bay Campus<br>Endowment crossed $40M for the first time\\n    section 2014 : Expansion Year\\n        Opened Cape Halverton satellite office\\n        Hired first VP of Research<br>Dr. Naomi Castellan recruited from Stanford\\n        Launched Open Science Programme\\n    section 2024 by Quarter\\n        Q1 2024 : Calibrated Self-Critique v2.0 Public Release\\n        Q1 2024 : csc-eval Conformance Test Suite\\n        Q2 2024 : Quarterly Public Audit Report \\u2014 Spring Edition\\n        Q3 2024 : Refusal-Aware RM Workshop at NeurIPS\\n        Q4 2024 : Quarterly Public Audit Report \\u2014 Winter Edition\\n    section Annual Recurring Cadence\\n        First Monday of February : Annual Research Symposium (closed-door)\\n        Last Friday of June : Open-House Demonstration Day\\n        Mid-October : Independent Reviewer Panel rotation"}'
)
```

---

## 4. 검수 체크리스트

- [x] **Syntactic spread of 3 pool exemplars**:
  - TIME-A: 4 quarterly sections / 4–8 events per section / trailing-empty
    detail
  - TIME-B: 2 sections / mixed cadence (year vs recurring-date-string) /
    1 event per line
  - TIME-C: 3 named-era sections with date-range headings / `<br>` multi-
    line event detail / transition annotation
  → covers (1 vs many events per section) × (calendar-year vs recurring-
  date-string vs era-range) × (with `<br>` vs without) × (transition
  annotation present vs absent).
- [x] **Anchor authenticity**: TIME-A, TIME-B, TIME-C all anchored on real
  faith-1.00 records.
- [x] **Placeholder regression check**: no `Acme Corp` (TIME-A swapped to
  Atlas Robotics), no `2018/2020/2022/2024` flat-year-list pattern, no
  `Founded by Alice and Bob` placeholder phrasing. All entities fictional
  generic-domain.
- [x] **Consolidated variant integration**: a single coherent timeline
  rooted at one title, with 4 sections at 4 cadence styles (named era /
  single-year intra-year / quarterly / recurring-date-string), all
  describing the same fictional institute's history.
- [x] **JSON round-trip**: all 4 strings parse via `json.loads`; `viz_type
  == "mermaid_timeline"` for all; `viz_dsl` value starts with `timeline\n
  title `.
- [x] **Token budget for consolidated**: ~1180 chars ≈ ~310 tokens.
