# DocViz-Agent — One-shot Failure Analysis (Week-0 Post-mortem)

**Scope.** Diagnose *why* TMG one-shot injection (`code/pipelines/tmg.py`) helps the
10k cells (+0.10 / +0.30 faith) but hurts every other cell (−0.13 to −0.26 faith).
Anchor: 60 paired records (S4_Agentic vs S4_AgenticTMG) with judge faith/overall.

**TL;DR.**
- Global mean Δfaith = **−0.10** (60 paired); 19 records drop, 7 records win, 34 tie.
- Hurt cells are **all entity-rich Mermaid types**: hotpotqa relational/comparative,
  arxiv comparative/hierarchical, multinews comparative/temporal.
- Win cells are **all 10k chartjs/timeline**, where the one-shot enforces a JSON
  scaffold the bare model otherwise emits empty or as the wrong viz_type.
- Failure mode is **not one** style-flattening pattern, but **five** distinct
  patterns. Style-flattening (C5 candidate) is real but only #2 in frequency.
  The dominant pattern is **Structure imposition** — the one-shot's
  `4-node flowchart / 4-row timeline / 3-branch mindmap` skeleton overwrites
  the entity inventory the source justifies.

---

## Part 1 — Paired drop catalog

Rows with Δfaith(S4_TMG − S4_Agentic) **< 0**, sorted by drop magnitude.
"INJECTED" column is the verbatim one-shot from `ONE_SHOT_BY_VIZ_TYPE` mapped
via `TYPE_TO_VIZ[query_type][0]`.

| # | query_id | source/type | f4 → fT | Δo | injected primary | viz_type S4 → TMG |
|---|---|---|---|---|---|---|
| 1 | arxiv_00_comparative | arxiv/comparative | 1.00 → 0.00 | −0.54 | chartjs_grouped_bar | mermaid_mindmap → chartjs_grouped_bar |
| 2 | hotpot_04_comparative | hotpotqa/comparative | 1.00 → 0.00 | −1.00 | chartjs_grouped_bar | mermaid_mindmap → ∅ (empty) |
| 3 | hotpot_05_relational | hotpotqa/relational | 1.00 → 0.25 | −0.31 | mermaid_flowchart | mermaid_flowchart → mermaid_flowchart |
| 4 | arxiv_03_hierarchical | arxiv/hierarchical | 1.00 → 0.38 | −0.32 | mermaid_mindmap | mermaid_mindmap → mermaid_mindmap |
| 5 | hotpot_08_comparative | hotpotqa/comparative | 1.00 → 0.38 | −0.28 | chartjs_grouped_bar | chartjs_bar → chartjs_grouped_bar |
| 6 | hotpot_00_relational | hotpotqa/relational | 1.00 → 0.50 | −0.21 | mermaid_flowchart | mermaid_flowchart → mermaid_flowchart |
| 7 | hotpot_02_relational | hotpotqa/relational | 0.75 → 0.25 | −0.38 | mermaid_flowchart | mermaid_flowchart → mermaid_flowchart |
| 8 | hotpot_03_comparative | hotpotqa/comparative | 0.50 → 0.00 | −0.29 | chartjs_grouped_bar | mermaid_mindmap → chartjs_grouped_bar |
| 9 | hotpot_05_comparative | hotpotqa/comparative | 1.00 → 0.50 | +0.29 | chartjs_grouped_bar | mermaid_timeline → mermaid_timeline |
| 10 | multinews_00_comparative | multinews/comparative | 1.00 → 0.50 | −0.21 | chartjs_grouped_bar | mermaid_mindmap → chartjs_grouped_bar |
| 11 | multinews_07_temporal | multinews/temporal | 1.00 → 0.50 | −0.17 | mermaid_timeline | mermaid_timeline → mermaid_timeline |
| 12 | arxiv_01_comparative | arxiv/comparative | 1.00 → 0.75 | −0.06 | chartjs_grouped_bar | mermaid_mindmap → mermaid_mindmap |
| 13 | hotpot_06_comparative | hotpotqa/comparative | 0.50 → 0.25 | −0.10 | chartjs_grouped_bar | mermaid_timeline → chartjs_grouped_bar |
| 14 | hotpot_06_relational | hotpotqa/relational | 0.75 → 0.50 | −0.06 | mermaid_flowchart | mermaid_timeline → mermaid_timeline |
| 15 | hotpot_07_relational | hotpotqa/relational | 0.75 → 0.50 | −0.40 | mermaid_flowchart | mermaid_flowchart → mermaid_flowchart |
| 16 | multinews_00_temporal | multinews/temporal | 1.00 → 0.75 | −0.15 | mermaid_timeline | mermaid_timeline → mermaid_timeline |
| 17 | multinews_03_comparative | multinews/comparative | 0.75 → 0.50 | −0.10 | chartjs_grouped_bar | mermaid_timeline → mermaid_timeline |
| 18 | multinews_05_comparative | multinews/comparative | 1.00 → 0.75 | −0.10 | chartjs_grouped_bar | mermaid_flowchart → mermaid_flowchart |
| 19 | multinews_09_comparative | multinews/comparative | 1.00 → 0.75 | −0.35 | chartjs_grouped_bar | chartjs_grouped_bar → mermaid_flowchart (corrupt) |

### Top-8 drops — full text evidence

#### D1. `arxiv_00_comparative` Δfaith = **−1.00**

> **Q:** Compare the parameter update mechanisms of In-Place TTT and Target Policy Optimization.

`S4_Agentic` (faith 1.00) — used `mermaid_mindmap` SECONDARY route, exploded
the two methods across 5 sub-axes each (Objective / Target Weights / Update
Mechanism / Update Rule / Key Feature) with full math:

```
mindmap
  root((Parameter Update Mechanisms))
    In-Place TTT
      Objective
        Next-Token Prediction (NTP) Alignment
        Self-supervised adaptation
      Target Weights
        Fast Weights
        Final projection matrix (W_down) of MLP blocks
      Update Mechanism
        W_down = W_down + eta * V_hat^T * Z
        ...
    Target Policy Optimization
      Objective
        RL Policy Optimization
        ...
```

`S4_AgenticTMG` (faith 0.00) — TMG forced `chartjs_grouped_bar` (the PRIMARY
for `comparative`), which collapses heterogeneous mechanisms into integer
"levels" 1/2/3:

```
{"type":"bar","data":{"labels":["Update Target","Update Granularity",
   "Objective Function","Gradient Signal","Dependency on Rewards"],
 "datasets":[
   {"label":"In-Place TTT", "data":[1,1,1,1,0]},
   {"label":"Target Policy Optimization","data":[2,2,2,2,1]}]},
 "options":{"scales":{"y":{"max":3,"ticks":{"callback":
   "function(v){return ['','Weight Matrix','Policy Distribution'][v];}"}}}}}
```

`INJECTED`:
```
chartjs_grouped_bar with labels=[Speed,Accuracy,Cost], datasets=Model A/B
```

**Diagnosis:** *Structure imposition.* The query is genuinely qualitative
(comparing *mechanisms*, not *quantities*). The mindmap was the right
representation. The router blindly maps `comparative → chartjs_grouped_bar`,
and the model dutifully invents a 1/2/3 ordinal axis ("Weight Matrix" = 1,
"Policy Distribution" = 2) — fabricated information to fit the schema.

---

#### D2. `hotpot_04_comparative` Δfaith = **−1.00** (catastrophic — empty output)

> **Q:** Compare the film roles of Jean-Claude Van Damme and Scott Adkins in the Universal Soldier franchise.

`S4_Agentic` (faith 1.00):

```
mindmap
  root((Universal Soldier Franchise Roles))
    Jean-Claude Van Damme
      Role: Luc Deveraux
      Status: Original Protagonist
      Timeline: Franchise began in 1992
      Note: Later replaced by Matt Battaglia in the role
    Scott Adkins
      Role: John
      Status: New Protagonist
      Timeline: Later entries (up to 2012)
      Background: Martial Artist
      Significance: Marked shift from Luc Deveraux
```

`S4_AgenticTMG` — `viz_type=""`, `viz_dsl=""`. The agent loop **failed to
emit any output** — total syntactic collapse. Most likely the model tried to
wedge film roles into the `Speed/Accuracy/Cost × Model A/Model B` grid,
discovered nothing fit, and timed out without final_answer.

**Diagnosis:** *Structure imposition + format brittleness.* This is the
pathology: the one-shot tells the model "comparative → numeric bar chart",
the data does not contain numbers, the model cannot reconcile the two and
falls off the rails entirely.

---

#### D3. `hotpot_05_relational` Δfaith = **−0.75**

> **Q:** Show a relationship diagram connecting Jack Lowden, Tommy's Honour, and Old Tom Morris.

`S4_Agentic` (faith 1.00):

```
graph LR
    A[Jack Lowden] -->|Acts in| B[Tommy's Honour]
    B -->|Depicts| C[Old Tom Morris]
    A -->|Plays Young Tom Morris, son of| C
```

`S4_AgenticTMG` (faith 0.25):

```
graph LR
    A[Jack Lowden] -->|stars in| B[Tommy's Honour]
    B -->|depicts| C[Old Tom Morris]
    A -->|portrays son of| C
```

`INJECTED`:
```
graph LR
    A[Founder] -->|founded| B[Acme Corp]
    B -->|acquired| C[Beta Labs]
    C -->|hired| D[Engineer X]
    A -->|advised| C
```

Judge checklist deltas (faith axis):
- "Does the diagram show Jack Lowden portraying **Young Tom Morris**?" — S4 YES, TMG **NO** ("only edge `portrays son of`, omits `Young Tom Morris`")
- "Does the diagram correctly identify Old Tom Morris as **Young Tom Morris's father**?" — S4 YES, TMG **NO**
- "Does the diagram avoid claiming Jack Lowden played Old Tom Morris?" — S4 YES, TMG **NO** ("edge `portrays son of` implies Lowden = the son node = Old Tom Morris")

**Diagnosis:** *Style flattening — semantic loss.* The S4 edge label
`Plays Young Tom Morris, son of` is a *complex two-fact predicate*: it
both (i) asserts the role and (ii) asserts the father-son relationship.
The TMG one-shot's edge labels are bare past-tense verbs (`founded`,
`acquired`, `hired`, `advised`). The model imitates that style, compressing
the rich label into `portrays son of` — which is now syntactically ambiguous
("Lowden portrays the son OF Old Tom Morris" vs. "Lowden, who is a son of,
portrays") and the judge correctly marks both checklist items as failed.
**The lost "Young Tom Morris" string is a key entity that the source
contains and the one-shot suppressed.**

---

#### D4. `arxiv_03_hierarchical` Δfaith = **−0.62**

> **Q:** Map the agent roles in Paper Circle's multi-agent framework to a hierarchical taxonomy.

`S4_Agentic` (faith 1.00) — preserves the `Orchestrator / Tracker` middle
layer that the source explicitly names as the coordinator:

```
mindmap
  root((Paper Circle Multi-Agent Framework))
    Discovery Pipeline
      Orchestrator / Tracker
        Intent Classification Agent
          Web Search Agent
        Paper Search Agent
        Sorting Agent
        Analysis Agent
        Export Agent
    Analysis Pipeline
      Paper Analysis Orchestrator
        Ingestion Layer ...
```

`S4_AgenticTMG` (faith 0.38) — the `Tracker` coordinator layer is **deleted**:

```
mindmap
  root((Paper Circle Multi-Agent Framework))
    Discovery Pipeline
      Intent Classification Agent
      Paper Search Agent
      Sorting Agent
      ...
    Analysis Pipeline
      Ingestion Layer
        ...
```

`INJECTED` (mindmap one-shot — 3 branches × 2 leaves, **strict 2 levels**):
```
mindmap
  root((NLP Methods))
    Supervised
      Classification
      Sequence Labeling
    Self-supervised
      Masked LM
      Contrastive
    RL-based
      RLHF
      DPO
```

Judge checklist deltas:
- "Does the hierarchy include the **Tracker** as coordinator?" — S4 YES, TMG **NO** ("explicitly mentioned in source but completely absent")

**Diagnosis:** *Quantity / depth mismatch.* The injected example has
**exactly 2 hierarchical levels** (branch → leaf). The actual source has
**3 levels** (Pipeline → Orchestrator/Tracker → Agent). The model
over-imitates the depth of the example, *flattens away the middle layer*,
and loses the entity that the judge specifically tests.

---

#### D5. `hotpot_08_comparative` Δfaith = **−0.62**

> **Q:** Compare casualties in the Pound Ridge massacre versus other Kieft's War incidents using a chart.

`S4_Agentic` (faith 1.00, viz_type=`chartjs_bar`):
```
labels: ["Wappinger Confederacy (Killed)", "New Netherland Forces (Killed)",
         "New Netherland Forces (Wounded)"]
datasets: [{label: "Casualties in Pound Ridge Massacre (March 1644)",
            data: [600, 1, 15]}]
```

`S4_AgenticTMG` (faith 0.38, viz_type=`chartjs_grouped_bar` — TMG primary):
```
labels: ["Killed", "Wounded"]
datasets: [{"label":"Wappinger Confederacy","data":[600,0]},
           {"label":"New Netherland Forces","data":[1,15]}]
```

**Diagnosis:** *Schema shape conflict.* The query asks "Pound Ridge vs other
incidents" — but the source only has data for *Pound Ridge*. The S4 output
correctly represents this as a 1-dataset bar over 3 casualty categories.
The TMG primary (`chartjs_grouped_bar` with 2+ datasets) forces the model
to pad a second pseudo-dataset, losing the temporal context (`March 1644`)
and the side-asymmetry (Killed-only vs Killed/Wounded). Side-effect:
date entity dropped from labels.

---

#### D6. `hotpot_00_relational` Δfaith = **−0.50** (the original C5 case)

> **Q:** Map the connection between Iqbal F. Qadir and Dwarka during the 1971 war.

`S4_Agentic` (faith 1.00):
```
graph LR
    A[Iqbal F. Qadir] -->|Retired Pakistan Navy Admiral| B(Pakistan Navy)
    B -->|Participated in 1971 War| C[Flotilla Attack]
    C -->|Target| D[Radar Station in Dwarka]
    D -->|Located in| E[Dwarka, Gujarat, India]
```

`S4_AgenticTMG` (faith 0.50):
```
graph LR
    A[Iqbal F. Qadir] -->|was part of| B[Flotilla]
    B -->|attacked| C[Radar Station in Dwarka]
    C -->|located in| D[Dwarka, India]
    A -->|participated in| E[1971 War]
    B -->|operated during| E
```

`INJECTED`: 4-node founder/acquired/hired/advised flowchart.

Judge checklist (faith) deltas:
- "Vice-Admiral / Pakistan Navy?" — S4 YES (node label `Retired Pakistan Navy Admiral`); TMG **NO** ("rank/branch omitted")
- "Dwarka in **Gujarat**?" — S4 YES (node `Dwarka, Gujarat, India`); TMG **NO** ("state Gujarat omitted")

**Diagnosis:** *Entity loss / phrase compression.* The one-shot uses
short bracketed labels (`[Founder]`, `[Acme Corp]`, `[Beta Labs]`,
`[Engineer X]`) — generic role nouns, not multi-word phrase entities.
The model imitates that label morphology and:
- `[Pakistan Navy]` (entity) → `[Flotilla]` (generic noun) — Pakistan Navy disappears.
- `[Dwarka, Gujarat, India]` (full geo phrase) → `[Dwarka, India]` — state lost.
- `|Retired Pakistan Navy Admiral|` (rich edge label, ≈4 words) → `|was part of|` (3 stopwords).

Two of four faith checklist items break *because the answer string is no
longer in the graph*. This is the canonical C5 mechanism, but note: it
overlaps with **D5's quantity mismatch** (5 nodes → 5 nodes; OK on count,
fail on density).

---

#### D7. `hotpot_02_relational` Δfaith = **−0.50**

> **Q:** Map the connection between Billy Howle and On Chesil Beach.

`S4_Agentic` (faith 0.75) — 5 nodes, 5 edges, includes director, novelist, co-star:
```
graph LR
    A[Billy Howle] -->|Stars in| B[On Chesil Beach]
    B -->|Directed by| C[Dominic Cooke]
    B -->|Based on novella by| D[Ian McEwan]
    A -->|Co-stars with| E[Saoirse Ronan]
    E -->|Stars in| B
```

`S4_AgenticTMG` (faith 0.25) — **TWO nodes total**:
```
graph LR
    A[Billy Howle] -->|stars in| B[On Chesil Beach]
```

**Diagnosis:** *Catastrophic node-pruning.* The one-shot has 4 nodes, but
the model here generated only 2. Hypothesis: the one-shot's tip line
("`5-10 nodes is ideal`" from `TYPE_TIP[relational]`) is overruled by the
prompt's "match the schema exactly, **not the content**" — and the agent
defaults to "minimum viable graph". Three judge checklist items
(director, novelist, premiere date) are now mechanically NO. The verb
"Stars in" → "stars in" is also style-flattened (capitalization).

---

#### D8. `hotpot_03_comparative` Δfaith = **−0.50**

> **Q:** Compare Kool Kojak's production credits with the voice cast of The Lorax film.

`S4_Agentic` (faith 0.50, viz_type=`mermaid_mindmap`) — preserves all named
artists (Flo Rida, Nicki Minaj, Ke$ha, ...) and voice actors:
```
mindmap
  root((Kool Kojak vs The Lorax Cast))
    Kool Kojak Production Credits
      Hit Singles
        Right Round (Flo Rida)
        Va Va Voom (Nicki Minaj)
        Blow (Ke$ha)
      Other Artists
        Sean Paul, Yelle, Waka Flocka Flame, Travis Barker, Britney Spears, ...
    The Lorax Voice Cast ...
```

`S4_AgenticTMG` (faith 0.00, viz_type=`chartjs_grouped_bar`):
```
labels: ["Artists Produced For", "Voice Cast Members"]
datasets: [{"label":"Kool Kojak","data":[16,0]},
           {"label":"The Lorax","data":[0,7]}]
```

**Diagnosis:** *Maximum content suppression.* Reducing 23 named entities
to two integers (16 and 7) destroys *every* checklist item — none of which
ask "how many" but all of which ask "is *X* listed". This is the same
structure-imposition as D1 but the entity count makes the loss starker.

---

## Part 2 — Failure mode taxonomy

I classify all 19 drops along **5 patterns**. Many records exhibit ≥2
patterns simultaneously; I assign the *primary* pattern (largest score
contribution) and list co-occurring secondaries.

| pattern | description | primary count | also present in |
|---|---|---:|---|
| **(a) Style flattening** | rich edge labels / long entity strings collapsed to generic verbs / short labels | 4 | (e), (d) |
| **(b) Quantity mismatch** | one-shot's node/level/dataset count too small; entities pruned to fit | 4 | (a), (e) |
| **(c) Structure imposition** | wrong viz_type primary forced; qualitative content squeezed into numeric grid | 7 | (d), (b) |
| **(d) Content suppression** | source phrases absent from one-shot get dropped (specific dates, modifiers, ranks) | 2 | (a), (c) |
| **(e) Entity loss** | named entity → role noun (e.g., `Pakistan Navy` → `Flotilla`) | 2 | (a) |

### (a) Style flattening — 4 primary

The one-shot's *prose register* dominates. Edge labels in the flowchart
example are 1-2 word past-tense verbs (`founded`, `acquired`, `hired`,
`advised`). When the source has compound, multi-fact edge labels, the
model regresses to that register:

| qid | rich label (S4) | flattened label (S4_TMG) |
|---|---|---|
| hotpot_05_relational | `Plays Young Tom Morris, son of` | `portrays son of` |
| hotpot_00_relational | `Retired Pakistan Navy Admiral` | `was part of` |
| hotpot_07_relational | `Required Technology` (functional dep.) | `used` |
| hotpot_05_comparative | `Pioneering Scottish Golfing Champion : Life and career depicted in film` | `Pioneering Golfing Champion : : Career depicted in film` (drops "Scottish") |

This is the C5 candidate hypothesis. It is **real** but is the *primary*
driver in only ~21 % of drops.

### (b) Quantity mismatch — 4 primary

| qid | one-shot density | source density required | what's lost |
|---|---|---|---|
| arxiv_03_hierarchical | 2 levels (branch/leaf) | 3 levels (Pipeline/Orchestrator/Agent) | the **Tracker** coordinator middle layer |
| hotpot_06_relational | flowchart 4-node example | 3-event timeline | timeline shrinks from 3 events → 1 event |
| hotpot_02_relational | 4 nodes | 5+ nodes (Howle, OCB, Cooke, McEwan, Ronan) | director + novelist + co-star nodes |
| arxiv_01_comparative | 2 datasets × 3 categories | 3 systems × 3 dimensions × ~3 sub-items | 5 sub-leaves dropped (Loss type, frame names, etc.) |

The mindmap one-shot in particular is a *uniformly* shaped 3×2 tree;
the flowchart is 4 nodes. These are upper bounds the model treats as
*targets*.

### (c) Structure imposition — 7 primary (largest bucket)

This is the **biggest** failure mode and is silent in the C5 hypothesis.
The router maps `comparative → chartjs_grouped_bar` as PRIMARY, but
qualitative comparisons (mechanism vs mechanism, role vs role,
discography vs voice cast) are not numeric. The one-shot pulls the
output into a numeric schema, which **either invents fake ordinal axes**
(D1) **or buckets to integer counts** (D8) **or fails to emit at all**
(D2):

- arxiv_00_comparative: invents 1/2/3 ordinal scale
- hotpot_04_comparative: empty output
- hotpot_03_comparative: 23 named artists → 2 integers
- hotpot_06_comparative: missing data → `null` dataset
- multinews_00_comparative: 5 facts (DEA breakdown, AFF growth, IG report) → 2 totals
- hotpot_08_comparative: schema shape conflict (1 dataset → forced 2)
- multinews_05_comparative: subgraph annotations & color hints lost when re-styled

Notice: the *secondary* viz_type for `comparative` is `mermaid_flowchart`,
which would have been a much better fit for D1, D8, and parts of D3 — but
the prompt language ("Recommended viz_type: **{primary}**") strongly biases
toward the primary even though the spec allows secondary.

### (d) Content suppression — 2 primary

When the one-shot has no analog of a key source feature (dates, ranks,
provinces, color codes), the model treats them as "extra content not
in template" and drops:

- multinews_05_comparative: source's `subgraph "Stated Intent"` + 4 color codes (e1f5fe / ffebee) all stripped — the one-shot has no styling.
- multinews_07_temporal: October 4 birthday celebration entry dropped despite being in source — the one-shot's timeline is 4 evenly-spaced years (2018, 2020, 2022, 2024), not multi-event-per-year.

### (e) Entity loss — 2 primary

Specific named entities in the source are replaced by role nouns:

- hotpot_00_relational: `Pakistan Navy` → `Flotilla`; `Dwarka, Gujarat, India` → `Dwarka, India`.
- multinews_00_temporal: `2014: Authorities seize $5 billion` → dropped entirely (no entity-rich event in template).

---

## Part 3 — Win analysis (Δfaith > 0)

7 wins, all in **10k** + two `multinews/temporal` + one `hotpot/comparative`.

### Top wins

| qid | Δfaith | mechanism |
|---|---|---|
| 10k_01_temporal | +1.00 (0.00 → 1.00) | **viz_type rescue** — S4 emitted `mermaid_flowchart` with content `"answer here"` (placeholder string, total format failure). TMG forced `mermaid_timeline` and produced full FY24 vs FY25 revenue breakdown. |
| 10k_04_temporal | +0.50 (0.00 → 0.50) | **viz_type rescue** — S4 emitted empty `viz_dsl=""`. TMG forced `chartjs_line` (secondary for temporal) and produced 2-point line chart for revenue & operating income. |
| 10k_02_quantitative | +0.25 (0.75 → 1.00) | **format enforcement** — S4 returned a clean chartjs_bar already; TMG output is corrupt at the JSON layer (double-nested `viz_dsl` key, `viz_type=mermaid_flowchart` mislabel). The judge still parsed the inner JSON and scored it 1.00. **This is a scoring artefact, not a real win** — the surface is broken. |
| 10k_03_quantitative | +0.25 (0.50 → 0.75) | **schema reshape** — S4 used wide table (FY25/FY26 as labels, OCI/Pre-tax as separate datasets). TMG flipped the axis (OCI/Pre-tax as labels, FY25/FY26 as datasets) which exposed the per-fiscal-year comparison the judge asked about more cleanly. |
| hotpot_02_comparative | +0.25 (0.75 → 1.00) | **explicit-date rescue** — S4 timeline missed the "September 7 World Premiere" detail; TMG one-shot's `2018 : Founded by Alice and Bob` style with explicit date format prompted the model to add `Premiere of On Chesil Beach : Sept 7, 2017`. |
| multinews_02_temporal, multinews_04_temporal | +0.25 each | **same as above** — timeline one-shot's date-prefixed entry shape encourages the model to attach explicit time markers it would have otherwise dropped. |

### Mechanism summary

Wins fall into 3 buckets:
- **(W1) viz_type rescue (2 wins, very large Δ).** Bare model emits empty
  string or wrong type; TMG router *forces* the right type → instant gain.
  Note: for these, the gain is **not from the one-shot example content**;
  it is purely from the *type constraint*. The TYPE_TIP text and the
  one-shot would be replaceable with even a 1-line "Use chartjs_line".
- **(W2) Schema scaffold (3 wins, ~+0.25 Δ).** Model already had the
  data, but the chartjs/timeline scaffold from the one-shot disambiguated
  *how to lay out* the axes/sections. Quantitative + temporal categories
  benefit because their schemas are highly stereotyped.
- **(W3) Scoring artefact (1 win, fake).** 10k_02_quantitative is a
  layered-quoting bug, not a real improvement.

### Why wins concentrate in 10k + temporal

- **10k** = financial 10-K filings → numeric tables → chartjs_bar/line is a
  near-perfect fit, and the placeholder one-shot ("Q1/Q2/Q3/Q4 vs Revenue
  ($B)") matches that domain almost exactly.
- **multinews/temporal** = articles with explicit dates → the one-shot's
  `2018 : Founded by ...` template helpfully reminds the model to attach
  dates as labels instead of as descriptive prose.

The *win* signal is therefore **domain-aligned**, not "TMG works in
general". The hurt cells are exactly those where the placeholder one-shot
*disagrees with* the source domain.

---

## Part 4 — One-shot redesign proposal

### Option A — Domain rotation (per source × query_type)

Rationale: there are at most 8 (source, query_type) cells in our prototype,
and each cell has a stable target schema. Keep TMG's primary→viz_type
routing, but make `ONE_SHOT_BY_VIZ_TYPE` a *function* of `(source,
query_type)` rather than just `viz_type`. Below are the proposed full
one-shots.

#### A.1 (10k, quantitative) → `chartjs_bar` — keep current style, add 2-dataset variant

```json
{"viz_type":"chartjs_bar","viz_dsl":"{\"type\":\"bar\",\"data\":{\"labels\":[\"FY2024\",\"FY2025\"],\"datasets\":[{\"label\":\"Total Revenue ($B)\",\"data\":[245.1,281.7]},{\"label\":\"Operating Income ($B)\",\"data\":[109.4,128.3]}]},\"options\":{\"scales\":{\"y\":{\"beginAtZero\":true,\"title\":{\"display\":true,\"text\":\"Amount ($ Billion)\"}}}}}"}
```

Reason: present cell already wins; adopting a 2-dataset shape mirrors most
real 10-K queries (current Q1-Q4 single-series is a slight under-fit).

#### A.2 (10k, temporal) → `mermaid_timeline` — quarterly section pattern

```
timeline
    title FY2025 Quarterly Revenue Highlights
    section Q1 FY2025
        Revenue $61.9B : Cloud +21% YoY
    section Q2 FY2025
        Revenue $69.6B : Cloud +24% YoY
    section Q3 FY2025
        Revenue $70.1B : Azure +33% YoY
    section Q4 FY2025
        Revenue $80.1B : LinkedIn +9% YoY
```

Reason: 10-K temporal queries always have FY/Q structure, with one numeric
fact per period. Current one-shot ("2018 founded / 2020 Series A / 2022
acquired / 2024 IPO") trains the model on a startup-history register that
mismatches financial reporting register.

#### A.3 (arxiv, comparative) → `mermaid_mindmap` (override secondary as primary for this cell)

```
mindmap
  root((Method Comparison))
    Method-A (e.g., Transformer Hawkes)
      Architecture
        Self-attention encoder
        Hawkes-process intensity head
      Loss
        Imbalance-aware cross-entropy
      Strength
        Handles irregular timestamps
    Method-B (e.g., FairLogue)
      Architecture
        Counterfactual fairness module
        Tabular EHR encoder
      Loss
        Intersectional disparity penalty
      Strength
        Detects compounded bias
```

Reason: arxiv comparative is *qualitative*; numeric grouped bar is the wrong
representation (D1 evidence). Override `TYPE_TO_VIZ` for this cell to use
`mermaid_mindmap` as primary. This requires changing the router to accept
a `(source, query_type) → viz_type` override table.

#### A.4 (arxiv, hierarchical) → `mermaid_mindmap` — 3-level depth

```
mindmap
  root((System Architecture))
    Pipeline-A
      Coordinator/Tracker
        Sub-agent X
        Sub-agent Y
        Sub-agent Z
    Pipeline-B
      Coordinator/Orchestrator
        Layer-1
          Module-α
          Module-β
        Layer-2
          Module-γ
```

Reason: explicitly demonstrates a 3-level structure with a named middle
"Coordinator/Tracker" layer, which is exactly the level D4 dropped.

#### A.5 (hotpotqa, relational) → `mermaid_flowchart` — multi-word labels

```
graph LR
    A[Director, Composer X] -->|"Composed for the film, premiered 1992"| B[Film Title Y]
    B -->|"Adapted from the novel, published 1948"| C[Novelist Z]
    A -->|"Awarded Best Score, 1993 BAFTA"| D[Award Ceremony]
    B -->|"Filmed in Edinburgh, Scotland"| E[Geographic Location, Country]
```

Reason: the *purpose* of the example is to license multi-word, multi-fact
edge labels and entity strings with appositive modifiers. Quote-wrapped
edge labels are valid Mermaid and are required when the label contains
commas or punctuation. Notice the label *style* — present-tense, multi-fact
predicates with dates/geography embedded — directly antagonizes the
flattening pattern in D3, D6, D7.

#### A.6 (hotpotqa, comparative) → `mermaid_flowchart` (override) OR `mermaid_mindmap`

Two columns of named entities, **not** numeric:
```
mindmap
  root((Entity-A vs Entity-B Comparison))
    Entity-A (e.g., Actor Name 1, born 1965)
      Role 1 in Film X (1992)
      Role 2 in Film Y (1995, replaced by another actor in 2009)
      Status: Original Lead
    Entity-B (e.g., Actor Name 2, born 1976)
      Role in Film Z (2012, new protagonist)
      Background: Martial Artist
      Status: Successor Lead
```

Reason: hotpotqa comparative queries are about *named-entity attribute
columns*, not numeric grouped bars. **This is the single biggest cell to
rescue (10 records, current Δ = −0.26).**

#### A.7 (multinews, comparative) → `mermaid_flowchart` (override)

```
graph TD
    A[Stated Goal/Intent] -->|Action taken| B[Concrete Decision]
    B -->|Resulted in| C[Public Reaction or Outcome]

    subgraph "Stated"
        D["Reason 1 for the action"]
        E["Reason 2 for the action"]
    end

    subgraph "Actual Impact"
        F["Effect 1 (with date or actor)"]
        G["Effect 2 (with date or actor)"]
    end

    A --> D
    A --> E
    B --> F
    F --> G
```

Reason: multinews comparative is "stated vs actual" or "side-A vs side-B"
narratives — the existing high-score `multinews_05_comparative` template
already shows this works (overall=1.00). Promote **that very output** as
the canonical template (this is also Option B).

#### A.8 (multinews, temporal) → `mermaid_timeline` — multi-event per year

```
timeline
    title Event Series
    section 2017
        Mid-October : First major milestone (specific date if available)
        Late 2017 : Secondary follow-up event
    section 2018
        Spring : Public statement or interview quote
        October : Anniversary or recurring milestone
    section 2019
        Specific date : Notable ceremony or reaction
        Same month : Related public event
```

Reason: current one-shot has 1 event per year over 4 years. Multinews
sources usually have **multiple events per year** with sub-month
granularity (D11 lost the October 4 birthday because the template implies
"≤1 event per year"). New template encodes the multi-event pattern.

#### Option A pros/cons

| | Pro | Con |
|---|---|---|
| | All cells get a register-matched template | Maintenance burden: 8+ hand-written examples |
| | Style/quantity/structure all addressed at template level | Some cells (e.g. arxiv comparative) require **router override** of `TYPE_TO_VIZ`, not just one-shot swap |
| | Direct counter to each failure mode in §2 | Risk of overfit to the 8 cells in our prototype — generalization to new (source, query_type) pairs untested |

### Option B — High-score S4 outputs as one-shots ("self-bootstrapping")

For each cell, pick the *best-scoring* S4_Agentic record (faith=1.00,
highest overall, highest coverage as tiebreaker) and use its `viz_dsl` as
the new one-shot. **The router would then inject "an output the model
itself produced and the judge approved" as the example.**

#### Candidate per cell (top-1 by overall, then coverage, then type_appropriateness)

| cell | candidate qid | viz_type | overall | preview |
|---|---|---|---|---|
| (10k, quantitative) | `10k_00_quantitative` | chartjs_grouped_bar | 1.00 | Apple FY24 vs FY25 interest-rate impacts, 2 datasets × 2 labels |
| (10k, temporal) | `10k_02_temporal` | mermaid_timeline | 1.00 | TSLA 2024/2025 sections, 2 facts each |
| (arxiv, comparative) | `arxiv_00_comparative` | mermaid_mindmap | 1.00 | 2 methods × 5 sub-axes × full math |
| (arxiv, hierarchical) | `arxiv_01_hierarchical` | mermaid_mindmap | 1.00 | 3 ML challenges × paper title + authors + key focus |
| (hotpotqa, comparative) | `hotpot_01_comparative` | mermaid_timeline | 1.00 | School + show timeline (mixed institutional history) |
| (hotpotqa, relational) | `hotpot_05_relational` | mermaid_flowchart | 1.00 | 3 nodes, multi-fact edge labels including `Plays Young Tom Morris, son of` |
| (multinews, comparative) | `multinews_05_comparative` | mermaid_flowchart | 1.00 | Stated-intent vs actual-impact subgraph layout with style colors |
| (multinews, temporal) | `multinews_05_temporal` | mermaid_timeline | 1.00 | Background / Backlash / Apology sections with multi-line `<br>` event descriptions |

Number of viable candidates per cell (all faith=1.00):

```
('10k', 'quantitative')        n=3
('10k', 'temporal')            n=3
('arxiv', 'comparative')       n=4
('arxiv', 'hierarchical')      n=3
('hotpotqa', 'comparative')    n=6
('hotpotqa', 'relational')     n=5
('multinews', 'comparative')   n=5
('multinews', 'temporal')      n=5
```

Plenty of headroom — we can rotate or A/B different candidates.

#### Notable property — primary viz_type often disagrees with TYPE_TO_VIZ

| cell | TYPE_TO_VIZ primary | best S4 actual viz_type | implication |
|---|---|---|---|
| (10k, quantitative) | chartjs_bar | chartjs_grouped_bar | minor |
| (arxiv, comparative) | chartjs_grouped_bar | **mermaid_mindmap** | router needs override |
| (arxiv, hierarchical) | mermaid_mindmap | mermaid_mindmap | OK |
| (hotpotqa, comparative) | chartjs_grouped_bar | **mermaid_timeline** | router needs override |
| (hotpotqa, relational) | mermaid_flowchart | mermaid_flowchart | OK |
| (multinews, comparative) | chartjs_grouped_bar | **mermaid_flowchart** | router needs override |
| (multinews, temporal) | mermaid_timeline | mermaid_timeline | OK |

This is independent confirmation of §2(c): the `TYPE_TO_VIZ` mapping
itself is wrong for arxiv/comparative, hotpotqa/comparative,
multinews/comparative — *the model already knows the right viz_type when
TMG isn't constraining it*. Self-bootstrapping fixes both the example AND
the router simultaneously.

#### Option B pros/cons

| | Pro | Con |
|---|---|---|
| | Automatically domain-matched, no manual writing | Self-amplification: model imitates its own quirks (verbose `<br/>` line breaks, redundant style blocks) |
| | Natural variance across cells; multiple candidates per cell allow ablation | "Train on judge YES" loop — risk that the judge's biases get baked into the example, and we're training on noise |
| | Reveals viz_type routing errors (table above) | Paper-honesty: harder to defend "we picked the example" vs. "we hand-wrote the schema illustrations" — needs careful framing in §3.2 |
| | Cheap: pure post-processing of existing outputs, no new generation | If S4_Agentic high-score sample contains an error the judge missed (cf. 10k_02_quantitative scoring artefact), error propagates |

#### Hybrid recommendation

Use **Option B for the 5 well-formed cells** (10k both, arxiv hierarchical,
hotpotqa relational, multinews temporal) and **Option A for the 3 cells
where current TYPE_TO_VIZ is wrong** (arxiv/comparative,
hotpotqa/comparative, multinews/comparative — all forced to
chartjs_grouped_bar today).

This requires one router change in `tmg.py`:

```python
# pseudo — DO NOT IMPLEMENT in this report; just sketch
TYPE_TO_VIZ_OVERRIDE: Dict[Tuple[str, str], str] = {
    ("arxiv",     "comparative"): "mermaid_mindmap",
    ("hotpotqa",  "comparative"): "mermaid_timeline",  # or mermaid_mindmap
    ("multinews", "comparative"): "mermaid_flowchart",
}
def primary_viz_type(source: str, query_type: str) -> str:
    if (source, query_type) in TYPE_TO_VIZ_OVERRIDE:
        return TYPE_TO_VIZ_OVERRIDE[(source, query_type)]
    return TYPE_TO_VIZ.get(query_type, ("mermaid_flowchart", ""))[0]
```

(Note: this would couple TMG to `source`. Spec-wise that means TMG is no
longer a pure query-type router — it becomes a query-type × source router.
This is a real design choice and is worth explicit discussion in the
revised §3.2.)

---

## Part 5 — Counterfactual prediction (no measurement, prior for isolation experiment)

For each ablation variant, predict the per-cell faith mean. Variant 0
(current) is observed; the rest are predictions with reasoning.

### Variant 0 — current placeholder one-shot (observed)

Reproduced from §1 aggregate table:

| cell | S4 faith | S4_TMG faith |
|---|---:|---:|
| (10k, quantitative) | 0.85 | **0.95** |
| (10k, temporal) | 0.60 | **0.90** |
| (arxiv, comparative) | 0.95 | **0.70** |
| (arxiv, hierarchical) | 0.85 | **0.73** |
| (hotpotqa, comparative) | 0.85 | **0.59** |
| (hotpotqa, relational) | 0.78 | **0.55** |
| (multinews, comparative) | 0.83 | **0.70** |
| (multinews, temporal) | 0.83 | **0.80** |

Mean S4_TMG faith ≈ **0.71**.

### Variant 1 — no one-shot (TYPE_TIP only, no example)

Strip the `Reference output for this type` block in `build_tmg_rule()`,
keep the `Recommended viz_type` + `Generation tip`. Removes patterns
(a)/(b)/(d) (no example to imitate); keeps (c) (router still forces wrong
type).

| cell | predicted faith | reasoning |
|---|---:|---|
| (10k, quantitative) | 0.85–0.90 | loses W1/W2 wins (no scaffold) but no harm; ≈ S4 baseline |
| (10k, temporal) | 0.65–0.75 | partial loss of W1 wins (the empty-output case relies on viz_type forcing — TIP alone may be enough; bare model still struggles with date format) |
| (arxiv, comparative) | 0.85–0.95 | router still says `chartjs_grouped_bar` PRIMARY, so structure imposition partially survives — but without example, model is more likely to fall back to mindmap as `secondary` is also listed |
| (arxiv, hierarchical) | 0.85–0.90 | recovers to ≈ S4 (the one-shot's 2-level depth was the culprit) |
| (hotpotqa, comparative) | 0.75–0.85 | recovers most of the way; primary still mistargeted but no example to suppress entities |
| (hotpotqa, relational) | 0.75–0.80 | recovers to ≈ S4 (style flattening was example-driven) |
| (multinews, comparative) | 0.80–0.85 | recovers to ≈ S4 |
| (multinews, temporal) | 0.80–0.85 | ≈ S4 |

**Predicted overall S4_TMG faith mean: ~0.81–0.85** (vs. observed 0.71 and
S4 baseline 0.82). This would already vindicate "the example is the
problem", regardless of redesign.

### Variant 2 — same length/specificity, generic domain

Replace the one-shot with a *more elaborate* generic example (5 nodes,
multi-word edge labels, multi-level depth) but still domain-neutral
(no real entities). Removes patterns (a) and (b); keeps (c) and partly (d).

| cell | predicted faith | reasoning |
|---|---:|---|
| (10k, quantitative) | 0.90 | small loss vs V0 (the matched financial register helped a touch) |
| (10k, temporal) | 0.85 | mostly retained — viz_type forcing dominates here |
| (arxiv, comparative) | 0.75–0.85 | partial recovery: structure imposition still hurts but flattening less |
| (arxiv, hierarchical) | 0.85 | ≈ V1 |
| (hotpotqa, comparative) | 0.70–0.80 | structure imposition still dominant (router); modest recovery |
| (hotpotqa, relational) | 0.78 | flattening → mostly fixed; ≈ S4 |
| (multinews, comparative) | 0.78 | small recovery |
| (multinews, temporal) | 0.83 | recovers slightly via better date pattern |

**Predicted overall: ~0.81.**

### Variant 3 — Option A, domain rotation

Hand-written domain-matched one-shots + router override for 3 misrouted
cells. Removes (a), (b), (c), (d), (e) at the cell level.

| cell | predicted faith | reasoning |
|---|---:|---|
| (10k, quantitative) | 0.92–0.97 | retains W1/W2; tweaks `chartjs_bar` → `chartjs_grouped_bar` to match richer queries |
| (10k, temporal) | 0.92–0.96 | quarterly template better matches FY/Q sources |
| (arxiv, comparative) | **0.85–0.93** | mindmap override removes structure imposition (D1 case); 5-axis depth template prevents D4-style flattening |
| (arxiv, hierarchical) | 0.88–0.93 | 3-level template addresses D4 directly |
| (hotpotqa, comparative) | **0.78–0.88** | mindmap override removes structure imposition; biggest recovery cell |
| (hotpotqa, relational) | **0.80–0.88** | multi-word label template addresses D3/D6/D7 |
| (multinews, comparative) | **0.83–0.90** | flowchart override addresses D8/D10/D17/D18/D19 |
| (multinews, temporal) | 0.85–0.90 | multi-event-per-year template addresses D11/D16 |

**Predicted overall: ~0.87 (Δ = +0.16 vs V0 = 0.71, +0.05 vs S4 = 0.82).**

This is the variant that delivers the paper's "TMG > no-TMG" claim
*honestly*, because all three pillars are now improving signals.

### Variant 4 — Option B, self-bootstrapping (best S4 → one-shot)

Use top-1 faith=1.00 S4 output per cell. Same coverage of failure modes as
V3, plus implicit router correction (because viz_type matches what the
model actually emitted).

| cell | predicted faith | reasoning |
|---|---:|---|
| (10k, quantitative) | 0.92–0.97 | ≈ V3 |
| (10k, temporal) | 0.92–0.96 | ≈ V3 |
| (arxiv, comparative) | 0.88–0.95 | mindmap example with full math + nested 3-level structure exceeds V3's hand-written depth |
| (arxiv, hierarchical) | 0.88–0.93 | ≈ V3 |
| (hotpotqa, comparative) | 0.80–0.88 | timeline example may not always fit comparative semantics (cell has 10 queries, not all timeline-shaped); slight risk |
| (hotpotqa, relational) | 0.82–0.92 | hotpot_05_relational `Plays Young Tom Morris, son of` style is exactly the antidote to D3/D6/D7 |
| (multinews, comparative) | 0.85–0.92 | multinews_05_comparative subgraph layout reusable verbatim |
| (multinews, temporal) | 0.88–0.95 | multinews_05_temporal section pattern with `<br>` multi-fact lines exceeds V3 |

**Predicted overall: ~0.88–0.90 (Δ ≈ +0.18 vs V0).**

Caveat: V4's gain over V3 is small and partly within prediction noise;
the *real* win of V4 vs V3 is **methodological economy** (no manual
writing) and **automatic routing correction**. In paper terms, V3 is more
defensible as method, V4 is more defensible as ablation result.

### Summary table

| variant | predicted faith mean | mechanism | expected best cell | expected worst cell |
|---|---:|---|---|---|
| V0 (current) | 0.71 | observed | (10k, temporal) 0.90 | (hotpotqa, relational) 0.55 |
| V1 (no one-shot) | 0.81–0.85 | removes (a)(b)(d) | (10k, temporal) 0.70 | (arxiv, comp.) 0.85 |
| V2 (richer generic) | ~0.81 | removes (a)(b) | (10k, q.) 0.90 | (hotpotqa, comp.) 0.75 |
| V3 (Option A) | ~0.87 | removes (a)(b)(c)(d)(e) at cell level | (arxiv, comp.) 0.90 | (hotpotqa, relational) 0.84 |
| V4 (Option B) | 0.88–0.90 | same as V3 + auto-routing | (multinews, temporal) 0.92 | (hotpotqa, comp.) 0.84 |

### What this implies for the isolation experiment (Week-1 action 3)

These predictions form the **prior** for the isolation experiment. The
critical comparisons are:

1. **V0 vs V1.** Tests "is the example doing harm beyond the router?"
   — predicted ΔV1−V0 = +0.10 to +0.14. If observed Δ < +0.05, the C5
   hypothesis is *wrong* and the harm is from `TYPE_TO_VIZ` itself.
2. **V1 vs V2.** Tests "does length/specificity matching help without
   domain matching?" — predicted ΔV2−V1 ≈ 0. If observed Δ ≥ +0.03,
   length is a real confound and the C5 framing as "style flattening"
   is too narrow.
3. **V3 vs V4.** Tests "is hand-written better than self-bootstrap?"
   — predicted ΔV4−V3 = 0 to +0.02. Whichever wins, run it.

Expected **causal decomposition**:

| pattern | contribution to V0 hurt (out of −0.10 mean) |
|---|---:|
| (c) Structure imposition | ≈ −0.05 |
| (a) Style flattening | ≈ −0.025 |
| (b) Quantity mismatch | ≈ −0.015 |
| (d) Content suppression | ≈ −0.005 |
| (e) Entity loss | ≈ −0.005 |

Style flattening is real and measurable, but is **half the story at most**.
The other half is the router's primary-viz_type mapping for `comparative`
queries on non-financial sources, which forces qualitative content into a
numeric grid.

---

## Closing notes for the reviewer

- The C5 finding ("style flattening") is *partially* validated by D3, D6,
  D7 (concrete edge-label compression). It is **not** the dominant
  failure mode; structure imposition is.
- The single biggest design lever is to **decouple `TYPE_TO_VIZ` from
  `comparative`** — that one routing rule causes 7 of 19 drops.
- Option B is unusually attractive here because the prototype already
  contains 3-6 faith=1.00 candidates per cell, *and* the candidates'
  `viz_type` values reveal the routing bug independently.
- Paper-honesty trade-off: A is "designed templates", B is "demonstration
  outputs from prior runs". Both are defensible; B should be framed as
  "few-shot bootstrapping" rather than "we cherry-picked our own outputs",
  with a clear ablation showing V3 ≈ V4.
- For Week-1 isolation experiment, run **all 5 variants** on the 19-record
  drop subset first (cheap, 19×4 = 76 new generations) before scaling.
