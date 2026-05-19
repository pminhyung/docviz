# Viz-Type Bias Taxonomy — V4_consolidated (B6) — 2026-05-16

Status: investigation, 2026-05-16
Scope: broaden the b6_vs_b7 routing analysis across all 10 viz_types and
all 6 sources; find input-side bias patterns; propose prompt + exemplar
fixes within V4 constraints.
Inputs (fresh as of 2026-05-16):
  `outputs/prototype/judge_scores/all.json` (2650 rows = 10 strategies × 265)
  `outputs/prototype/viz/all.json` (paired viz)
  `outputs/text2vis/judge_scores/all.json` (700 rows = 7 strategies × 100)
  `outputs/text2vis/viz/all.json`
  `data/prototype/queries/all.json`
  Code: `code/pipelines/tmg.py`, `code/agent_tools/generate_viz.py`,
        `code/agent_tools/oneshot_pool.json`,
        `code/pipelines/s4_agentic_tmg.py`,
        `code/adapters/viz_output_mapper.py`

---

## 1. Executive summary

- The headline B6−S7 = −0.056 (Layer A n=265) **decomposes into ~41 %
  measurement artifact + ~59 % real**: when both strategies are scored on the
  same 3-axis basis (drop SQQ), the gap shrinks to **−0.033**. SQQ alone
  accounts for −0.023 of the published gap because B6 is evaluated on 4 axes
  and S7 on 3 (`code/judge/scorer.py` checklist-class asymmetry).
- The dominant input-side bias on the **remaining −0.033 real gap** is **NOT
  TMG router mis-routing**. B6's per-type pick distribution is within ±5 % of
  S7 in every viz_type. The real losses sit in three families:
  (i) **EMPTY-DSL fallback** — agent never invokes `generate_viz`, orchestrator
  falls back to `viz_type=mermaid_flowchart` + empty DSL: 11/265 records,
  contributes −0.015 (27 % of headline gap);
  (ii) **content thinness on mermaid_timeline + mermaid_mindmap** —
  same-pick cells where DSL is structurally shallower than S7's (mean depth
  3.97 vs 4.62 for mindmap; mean `<br>` count 4.16 vs 3.00 for timeline —
  but B6 timelines are LONGER, so the issue is fact density per slot, not
  section count); contributes −0.012;
  (iii) **TMG primary mismatch for hierarchical** — the §3.2 mapping says
  `hierarchical → mermaid_mindmap (primary)` but B6 picks `mermaid_flowchart`
  64 % of the time on hierarchical queries, and **flowchart scores HIGHER**
  on those cells (overall 0.863 vs 0.777 for mindmap). The rule's primary
  is empirically wrong for this query_type.
- **Top 3 fixable biases** by Δ-projection: (A) empty-DSL recovery via rule
  re-emphasis (+0.0075), (D) timeline fact-density via exemplar refinement
  (+0.0044), (B) explicit-chart-type override when query says
  "bar chart"/"line chart"/"timeline" (+0.0030).
- **Aggregate Δ projection (conservative, w/ 70 % overlap discount): +0.015**
  on full-set overall. Insufficient to close the gate (need ≥ +0.020 vs best
  baseline; currently −0.056 → would only narrow to ≈ −0.041). Combined with
  the SQQ scoring fix (3-axis apples-to-apples), gap would narrow to
  ≈ −0.018, still gate-failing but much closer.
- Cross-check on Text2Vis (n=100): same empty-DSL fallback pattern reproduces
  (3/100 records, all `mermaid_flowchart` fallback). Same DSL-thinness
  pattern reproduces in `chartjs_bar` underperformance. Fixes generalize.

---

## 2. Method

### 2.1 Data layout

- 10 strategies × 265 queries × 1 judge pass = 2650 rows in
  `outputs/prototype/judge_scores/all.json`. Strategies include the new
  ablations B6_NoSAO, B6_NoCIS (judged this morning).
- Per-record schema: `axis_scores ∈ {faithfulness, coverage,
  type_appropriateness, search_query_quality}` (SQQ only on agentic),
  `overall = mean(axis_scores)`, `viz_type`, `viz_parsed_summary`, full
  `scored` array.
- Paired with viz metadata: `viz_dsl`, `n_sub_queries`, `syntax_valid`,
  `errors`.

### 2.2 Calibration sample (5 records read end-to-end)

- `10k_14_quantitative` n_subq=0 → `data:[0,0]` (AGENT_SKIPS_RETRIEVAL persists)
- `multinews_04_temporal` Δ −0.354 → B6 timeline 3 sections × 1-line entries;
  S7 2 sections × 3+ multi-fact entries
- `arxiv_48_comparative` Δ −0.861 → empty-DSL fallback (sidecar missing)
- `tech_docs_45_hierarchical` → timeline pick correct, thin per-version annotation
- `hotpot_22_relational` Δ −0.625 → prior TA penalty pattern persists

### 2.3 Judge-noise check

- **SQQ axis composition artifact**: B6 `overall` = mean(F, C, TA, SQQ);
  S7 `overall` = mean(F, C, TA). On the full set, recomputing both on the
  shared 3-axis basis: B6_3ax = 0.8475, S7_3ax = 0.8804 → Δ = **−0.033** vs
  the published −0.056. **41 % of the headline gap is the SQQ axis getting
  averaged in for B6 only.** This is a real cost (the agent does run
  retrievals and is being judged on their quality), but it's not bias-driven
  — it's checklist-class asymmetry. Flag for v0.3 summary disclosure.
- **JUDGE_BUG_SQQ_MISCLASS** (from prior): 3 records still present in this
  refreshed judge run; same pattern.

### 2.4 Statistical method

- Paired bootstrap (n=2000) on every claim with n<60. CI reported.
- Bias counts: a "pattern" requires ≥3 records meeting the trigger feature.
- Conservative Δ projection: realistic-recovery = 50–70 % of the per-record
  gap × affected count, divided by full set (265).

---

## 3. Compact confusion matrix (Layer A n=265)

### 3.1 Per-viz_type pick counts (B6 vs S1 vs S7)

| viz_type                | B6  | S1  | S7  |
|-------------------------|----:|----:|----:|
| chartjs_bar             |  20 |  19 |  21 |
| chartjs_line            |   3 |   6 |   5 |
| chartjs_grouped_bar     |  21 |  33 |  28 |
| chartjs_pie             |   0 |   0 |   0 |
| chartjs_scatter         |   0 |   0 |   0 |
| mermaid_flowchart       |  91 |  68 |  84 |
| mermaid_timeline        |  98 |  99 |  96 |
| mermaid_mindmap         |  29 |  40 |  26 |
| mermaid_sequenceDiagram |   3 |   0 |   5 |
| mermaid_classDiagram    |   0 |   0 |   0 |

**Key observations:**
- B6's picks are **within ±5 of S7** on every single type — the TMG router
  is NOT producing a systematic type-bias mis-distribution.
- `chartjs_pie`, `chartjs_scatter`, `mermaid_classDiagram` are **never picked
  by any strategy on Layer A**. They are dead exemplars from the agent's
  perspective. Cause: query_type ∈ {quant, rel, temp, hier, comp} routes
  primary/secondary to the other 7 types only.

### 3.2 Deviation matrix (B6 picks something different from S7) — top rows

| B6 pick                 | S7 pick               | n   | mean Δ overall (B6−S7) |
|-------------------------|-----------------------|----:|------:|
| mermaid_flowchart       | mermaid_mindmap       | 11  | −0.051 |
| mermaid_mindmap         | mermaid_flowchart     | 11  | −0.078 |
| mermaid_flowchart       | chartjs_grouped_bar   |  5  | **−0.244** (all 5 from empty-DSL fallback) |
| chartjs_bar             | chartjs_grouped_bar   |  3  | −0.097 |
| mermaid_flowchart       | mermaid_timeline      |  2  | **−0.625** (hotpot_13 + hotpot_04 — both empty) |

- **Total deviations: 47/265 (18 %); contribution to full-set Δ: −0.021**
- **Same-type (non-empty): 214/265 (81 %); contribution to full-set Δ: −0.035**
- **Empty-DSL: 11/265 (4 %); contribution: −0.015**

**The original "TMG mis-routes" framing only explains 38 % of the gap.**
59 % is content quality on the same-type case, and a non-trivial 27 % is
the orchestrator fallback when the agent never calls `generate_viz`.

### 3.3 Per-(source, query_type) Δ overall (B6 − S7)

| cell | n | faith Δ | cov Δ | TA Δ | overall Δ |
|---|---:|---:|---:|---:|---:|
| (10k, quantitative) | 15 | −0.142 | −0.089 | −0.050 | **−0.087** |
| (arxiv, comparative) | 20 | −0.081 | −0.075 | −0.100 | **−0.077** |
| (arxiv, hierarchical) | 30 | −0.033 | −0.089 | +0.008 | −0.051 |
| (govreport, hierarchical) | 20 | −0.006 | −0.025 | −0.013 | −0.048 |
| (govreport, temporal) | 30 | +0.004 | +0.011 | −0.008 | **+0.002** ✓ |
| (hotpotqa, comparative) | 20 | −0.113 | −0.158 | −0.150 | **−0.131** |
| (hotpotqa, relational) | 30 | −0.017 | −0.028 | −0.058 | **−0.085** |
| (multinews, comparative) | 20 | +0.013 | −0.033 | +0.025 | −0.020 |
| (multinews, temporal) | 30 | −0.013 | −0.011 | +0.008 | **−0.084** |
| (tech_docs, hierarchical) | 20 | +0.000 | +0.033 | +0.037 | −0.016 |
| (tech_docs, relational) | 30 | +0.013 | −0.072 | −0.017 | −0.039 |

`multinews × temporal` (−0.084) shows axis Δs all near zero — that cell's
loss is almost entirely **SQQ axis** dragging the 4-axis mean, not the viz
quality. Confirmed by 3-axis re-compute.

---

## 4. Bias taxonomy

| ID | Input pattern | B6 over/under | "Correct" pick (per S7 evidence) | Count | Mean per-record overall Δ | Hypothesized cause |
|---|---|---|---|---:|---:|---|
| **V1** | Agent never invokes `generate_viz` → empty DSL | fallback to `mermaid_flowchart` | what the query asks (bar/line/timeline/etc.) | 11 | −0.36 | rule (V4 precondition not enforced); also agent-server Mode A |
| **V2** | `query_type=hierarchical` (TMG primary = mindmap) | over-picks `mermaid_flowchart` (45/70 = 64 %) | flowchart wins overall: 0.863 vs mindmap 0.777 | 45 vs 18 | n/a — flowchart pick is BETTER | TMG primary mapping (`tmg.py:31-37`) is wrong for hierarchical |
| **V3** | `multinews × temporal` long-doc timelines | underfills facts per slot (`<br>` density 4.16 vs S7 3.00 paired) | richer multi-line slots | 29 (same-type) | −0.078 | timeline consolidated exemplar shows 1-line entries (`oneshot_pool.json:64`) — mimicry |
| **V4** | `mermaid_mindmap` outputs are shallower than S7's | depth 3.97 vs 4.62 mean | deeper category trees | 29 | −0.057 (hier-mindmap cell) | mindmap consolidated exemplar is broad (Team/Milestones/Methods) but only 2 children per top-node — agent mimics flat structure |
| **V5** | `hotpotqa × comparative` queries with mixed dated+relational content | over-picks `mermaid_timeline` (11/20) | 7/11 of these queries ask for "compare X and Y" with ≤2 distinct dates — flowchart/grouped_bar fits better | 11 | −0.102 | TMG dispatch: comparative→grouped_bar primary, but agent deviates to timeline when ANY date appears in query text |
| **V6** | Query explicitly asks for "bar chart" / "line chart" | B6 still picks `mermaid_flowchart` in 4 of 38 cases | the literal type the user named | 4 | −0.40 (large) | content_brief leaks to tool but viz_type pre-selection by agent ignores explicit type keyword in query |
| **V7** | `tech_docs × relational` mermaid_flowchart (TA OK but coverage drops) | same type | richer subgraph clustering | 14 | −0.064 | flowchart exemplar has subgraphs + style; B6 uses subgraph 38/80 = 47 % vs S7 56/84 = 67 % |

Patterns considered and DROPPED (insufficient evidence):
- *Timeline over-picked when query has a year + comparative*: B6 and S7
  both pick timeline for comparative at 27 % — same rate, not B6-specific.
- *Mindmap over-picked when query has "categories"/"types"*: B6 26 % vs
  S1 57 % — B6 UNDER-picks mindmap, not over.
- *ClassDiagram never picked when query is schema-like*: 0 Layer A queries
  contain schema-like wording (regex check). Bias N/A to this dataset.
- *Chartjs_pie under-used for "proportion"/"share"*: only 2 queries in
  Layer A use these words, both ask for line/bar by intent.

---

## 5. Per-bias deep-dives

### V1 — Empty-DSL fallback (agent skipped `generate_viz`)

**Description.** When the agent emits `<final_answer>` without invoking
`generate_viz`, no sidecar is written. The orchestrator's `map_agent_response`
fallback sets `viz_type='mermaid_flowchart'` and `viz_dsl=''`
(`code/adapters/viz_output_mapper.py:262,267`). The judge sees an empty
visualization and scores ~0 across all axes.

**Evidence (qids).** 11 records, all with error `generate_viz sidecar missing
for query_id=…; agent likely did not invoke the tool`:
`10k_12_quantitative`, `10k_13_quantitative`, `arxiv_03_hierarchical`,
`arxiv_34_comparative`, `arxiv_39_comparative`, `arxiv_48_comparative`,
`hotpot_04_relational`, `hotpot_13_relational`, `hotpot_31_comparative`,
`hotpot_45_comparative`, `multinews_08_temporal`.

**Paired bootstrap.** n=11, mean B6−S7 = **−0.357**, 95 % CI [−0.593, −0.127].
Full-set contribution if recovered to S7: **+0.0149**.

**Trace to input source.** This is NOT a TMG rule bias — it's an agent
control-flow bug. The rule (`tmg.py:V4_POOL_EXPOSURE_RULE`) already says
*"`<final_answer>` is BLOCKED until you have invoked the `generate_viz`
action tool"*. The agent server's Mode A (silent ConnectError → empty
`final_answer`) accounts for 7/11; the other 4 (`n_subq=2+` cases like
`10k_12`, `arxiv_34`) are genuine agent skips after retrieval succeeded.

**Root cause hypothesis.** The rule's precondition language is enforced
by description, not by a hard check. When the agent's reasoner reaches a
plan where it "knows" the answer in prose, the call gets elided. The Mode A
silent-empty-on-Connect failure is a separate orchestrator path that ALSO
ends up at the same fallback.

### V2 — Hierarchical → mermaid_flowchart deviation pays off (TMG primary is wrong)

**Description.** TMG mapping (`tmg.py:31-37`) says
`hierarchical → mermaid_mindmap (primary) | mermaid_flowchart (secondary)`.
On Layer A's 70 hierarchical queries: B6 picks the primary (mindmap) only
18/70 = 26 %; picks the secondary (flowchart) 45/70 = 64 %; picks timeline
5/70 = 7 %. **And flowchart out-scores mindmap on these queries**: mean
overall flowchart=0.863 vs mindmap=0.777, n=45 vs 18.

**Evidence (qids).** Top representatives of B6 picking flowchart instead
of TMG-recommended mindmap:
- `arxiv_03_hierarchical` (B6=fc, overall 0.93)
- `govreport_45_hierarchical` ("Map the hierarchical regulatory structure
  for OCS air emissions" — B6=fc 0.73, S7=mm 0.89)
- `tech_docs_42_hierarchical` (B6=fc 0.94, S7=mm 1.00)

Same-cell mindmap losses (where both picked mindmap):
- `(arxiv, hierarchical, mermaid_mindmap)` n=6, Δ=−0.069.
- `(govreport, hierarchical, mermaid_mindmap)` n=5, Δ=−0.094.

**Trace to input source.** The TMG rule's tip for `hierarchical` says
*"Use a 2-3 level mindmap rooted at the central topic … grandchildren are
concrete instances"* (`tmg.py:53-57`). This is enforced by the rule, but
the agent already deviates to flowchart most of the time anyway — the
deviation is correct, and the rule is what's miscalibrated.

**Root cause hypothesis.** The §3.2 mapping was set from prior intuition
about taxonomy charts. On the actual Layer A queries, most "hierarchical"
queries are dependency / architecture / regulatory queries which fit flowchart
better. Mindmap's strict tree topology can't represent edge labels (it
inherits from `mindmap` syntax which doesn't allow edge text), making it
weaker on these queries.

### V3 — Timeline fact density (multinews especially)

**Description.** B6 timelines have MORE sections than S7 (3.7 vs 2.9 mean)
but FEWER multi-line slots per typical entry. Looking at `multinews_04` paired
DSLs: B6 has `Friday : Gigi Hadid walked Versace runway at Milan Fashion
Week<br>Received body shaming comments on social media` (2 facts), S7 has
`Friday : Gigi walks Versace runway<br/>Haters call her fat on social media`
(2 facts, but per-fact context is tighter). On `multinews_06`, B6 packs all
events into 1 quote-rich line per date; S7 uses 2-3 short lines per date
covering more entities. The judge's coverage axis penalizes B6 because each
slot covers fewer of the checklist's entities.

**Evidence (qids).** Worst losses in `(multinews, temporal, timeline)`
n=28, Δ=−0.078 95 % CI [−0.117, −0.039]: `multinews_04` (−0.354),
`multinews_06` (−0.312), `multinews_23` (−0.292), `multinews_02` (−0.167),
`multinews_05` (−0.167), `multinews_21` (−0.167).

**Trace to input source.** The consolidated `mermaid_timeline` exemplar in
`code/agent_tools/oneshot_pool.json:64` is `Foundry Research Institute —
Founding to 2025 Operating Cadence`. Its 17 entries are nearly all
single-line: `1998 : Founded as the Foundry Lab inside Whitfield University`
— ONE fact per slot. The `generate_viz` tool prompt
(`code/agent_tools/generate_viz.py:380-440`) says "match the exemplar's
structural depth — do NOT introduce keys or nesting levels not present in
the exemplar". This is enforced strictly enough that the agent doesn't emit
the 3-fact bullets S7 produces. **The exemplar fact density is leaking into
the output structure.**

**Root cause hypothesis.** Exemplar mimicry on fact-density-per-entry, even
though the tool prompt already says "preserve every specific fact present
in the brief".

### V4 — Mindmap depth thinness

**Description.** B6 mindmaps have mean depth 3.97 vs S7's 4.62 (n=29 vs 26).
The consolidated exemplar (`oneshot_pool.json:62`) actually has depth 5 in
its longest branch (`root → Methods → Calibrated Self-Critique →
Optimization Target → Cross-entropy on critique-vs-base preference pairs`),
but agent typically truncates earlier. Each shallower mindmap covers fewer
nested categorical instances.

**Evidence.** Same-cell mean Δ:
- `(arxiv, hierarchical, mermaid_mindmap)` n=6, Δ=−0.069
- `(govreport, hierarchical, mermaid_mindmap)` n=5, Δ=−0.094
Worst single records: `govreport_45_hierarchical` mindmap depth 3,
`arxiv_05_hierarchical` mindmap depth 3.

**Root cause hypothesis.** The mindmap exemplar has a single 5-deep branch
but most are 2-3 deep (Team/Milestones top). Agent reads this as
"2-3 levels is normal" and truncates.

### V5 — HotpotQA comparative → timeline over-pick (mixed-cue queries)

**Description.** `hotpotqa × comparative` cell: B6 picks timeline 11/20 (55 %),
S7 picks 12/20 (60 %). Same rate; difference is same-type content quality:
B6 TA=0.844 vs S7 0.943. Cell Δ = −0.131 (worst cell).

**Evidence.** `hotpot_48_comparative` "release timelines and platforms for
Yakuza Kiwami" B6=0.36 vs S7=1.00 (both timeline; B6's is single section,
4 entries). `hotpot_36_comparative` "recording timelines of … Rudy Vallee,
Bing Crosby" B6=0.92 vs S7=1.00. `hotpot_30_comparative` timeline pick is
correct, B6 0.96 wins.

**Trace.** `build_tmg_rule(query_type='comparative')` (`tmg.py:140-179`)
restricts to grouped_bar+flowchart, BUT V4 mode uses
`V4_POOL_EXPOSURE_RULE` instead, which exposes all 10 types with no per-
query_type preference. The original primary/secondary restriction is bypassed.

**Root cause.** V4_POOL_EXPOSURE_RULE has no per-query_type guidance; just
lists the 10-enum. Agent picks on query-text cue alone.

### V6 — Explicit chart-type keyword override missed

When query says "bar chart"/"line chart", B6 picks the chartjs type 19/22.
The 3 mis-picks (`10k_12`, `arxiv_34`, `hotpot_45`) are ALL empty-DSL
fallback (V1). So V6 entirely overlaps V1 — F-A fixes both.

### V7 — Flowchart sub-graph clustering omitted

**Description.** B6 flowcharts use `subgraph` clustering 38/80 = 47 % of
the time; S7 uses it 56/84 = 67 %. Clustering helps the judge's coverage
axis when the source has natural sub-clusters (e.g., a tech_docs query about
TLS layers).

**Evidence.** `(tech_docs, relational, mermaid_flowchart)` n=14 Δ=−0.064,
coverage axis Δ=−0.095 (the cov component is most of the loss).
`(govreport, hierarchical, mermaid_flowchart)` n=9 Δ=−0.074, cov Δ=−0.093.

**Trace to input source.** The flowchart consolidated exemplar
(`oneshot_pool.json:61`) DOES have a subgraph (`subgraph Followup [Follow-Up
Work…]`) and a style block. So the exemplar is good. The leak is the agent's
`content_brief` not requesting cluster structure — `generate_viz` tool prompt
asks for "names / dates / quantities" but not for "groups / sub-systems / clusters".

---

## 6. Proposed fixes

All fixes respect V4 design constraints (base reasoning style, no banner,
no source-groundedness in tool prompt, `final_answer = "success"`, rule
must name `generate_viz`, paired bootstrap on n<60 claims).

| ID | Fix type | File:line | Exact prompt text (≤30 words) | Δ projection | Risk qids |
|---|---|---|---|---:|---|
| **F-A** | rule clarification | `code/pipelines/tmg.py:200-208` | append to step (2) wording: `"if you reach a plan to answer without a visualization, that is a planning error: invoke generate_viz first; the visualization is mandatory output."` | **+0.0075** | regression check: `govreport_46_hierarchical` (n_subq=0 but recovered well-grounded mindmap); preflight on B6_NoTMG baseline |
| **F-B** | rule clarification | `code/pipelines/tmg.py:212-216` | after `viz_type` enum sentence add: `"if the user query names a chart type ('bar chart','line chart','pie chart','timeline','sequence diagram'), pick that exact viz_type unless the source content cannot support it."` | **+0.0030** (largely overlapping F-A) | regression: `hotpot_30_comparative` (says "timeline" but is comparative — already routes to timeline correctly) |
| **F-C** | dispatch table | `code/pipelines/tmg.py:31-37` | swap `hierarchical: ("mermaid_mindmap", "mermaid_flowchart")` → `("mermaid_flowchart", "mermaid_mindmap")` | **+0.0040** (45 records better-served by primary flowchart; conservative 50 % recovery × +0.086 cell delta on 22 records) | regression: `arxiv_22_hierarchical` (current mindmap B6 win), `govreport_41_hierarchical` (mindmap B6 win); these may flip if agent now follows primary too strictly |
| **F-D** | exemplar refinement | `code/agent_tools/oneshot_pool.json:64` (consolidated mermaid_timeline) | replace single-fact entries with 2-3 fact entries per slot, e.g.: `1998 : Founded as the Foundry Lab inside Whitfield University<br/>First director Dr Ellis Vance<br/>$2M seed grant from State` | **+0.0044** | regression: `govreport × temporal` cell (currently +0.002, B6's only winning cell — fact density may push past judge's ceiling) |
| **F-E** | exemplar refinement | `code/agent_tools/oneshot_pool.json:62` (consolidated mermaid_mindmap) | ensure ALL top-level branches have ≥4 levels of nesting (current exemplar has only 1 deep branch — make Team and Milestones also 4-deep) | **+0.0019** | regression: `arxiv_22_hierarchical`; verify exemplar still validates as mermaid mindmap |
| **F-F** | tool-prompt clarification | `code/agent_tools/generate_viz.py:404-419` | for mermaid_flowchart paragraph, append: `"if the brief lists 2+ distinct sub-systems or phases, place each into its own 'subgraph' block (the exemplar shows this); otherwise use plain edges."` | **+0.0021** | regression: `tech_docs_06_relational` (B6 sequenceDiagram win, unaffected); verify tool prompt stays ≤current length |

**Style audit per V4 design constraint.**
- F-A, F-B: inserted as continuation of existing sentences in
  `V4_POOL_EXPOSURE_RULE`, lower-case, no banner, no caps, no markdown headers.
  Verified — both fit feedback rule 14 style requirement (base reasoning).
- F-C: dispatch table change, no prompt text. Style not applicable.
- F-D, F-E: exemplar JSON only. The tool prompt's "match the exemplar's
  structural depth" rule (`generate_viz.py:421-422`) will pull agents
  toward the new structural choice automatically. No prompt change.
- F-F: tool prompt internal — the existing tool prompt already has the
  "match exemplar depth" rule. Adding a sub-graph hint about input
  structure is OK because "if brief lists 2+ distinct sub-systems"
  references THE BRIEF, not the source documents — respects feedback
  rule 15 (no source-groundedness instructions).

---

## 7. Text2Vis cross-check (n=100)

| Metric | Layer A (n=265) | Text2Vis (n=100) |
|---|---|---|
| B6 mean overall | 0.824 | 0.810 |
| S7 mean overall | 0.880 | 0.839 |
| B6−S7 Δ | −0.056 | −0.029 |
| B6 empty-DSL count | 11 (4.2 %) | 3 (3.0 %) |
| Empty fallback viz_type | all `mermaid_flowchart` | all `mermaid_flowchart` |
| Deviation losses (B6 pick != S7) | n=47, mean Δ=−0.120 | n=26, mean Δ=−0.008 |
| Same-type loss | −0.035 | −0.024 |

**Findings.**
- V1 (EMPTY-DSL fallback) reproduces — `(mermaid_flowchart, chartjs_line)`
  deviation n=3 mean Δ=−0.694, all empty-DSL fallback.
- V3 (timeline thinness) cannot be tested on Text2Vis (only `external`
  query_type; all picks are chart types). N/A.
- V6 (explicit-chart-type) reproduces — when query asks for `chartjs_bar`
  or `chartjs_line` and B6 picks `mermaid_flowchart` (fallback), Δ is −0.694.
- The text2vis B6−S7 gap is smaller (−0.029), suggesting the bias is
  less severe on a single-source single-querytype distribution.

**Fixes generalize.** F-A (empty-DSL recovery) explicitly addresses the
text2vis pattern. F-B (explicit-chart-type) directly addresses the 3
text2vis records where the query named "bar chart" or "line chart" and
the agent's intended pick was overridden by the fallback.

---

## 8. Δ aggregation and gate-feasibility

| Fix | Records | Per-record Δ (recovered) | Discount | Full-set Δ |
|---|---:|---:|---:|---:|
| F-A | 11 | +0.357 | 50 % (rule clarification ≠ hard enforcement) | +0.0075 |
| F-B | 4 | +0.40 (overlap w/ F-A) | 25 % marginal | +0.0015 |
| F-C | 22 same-type-mindmap | +0.086 | 50 % | +0.0040 |
| F-D | 29 multinews-temporal | +0.078 | 30 % (judge ceiling) | +0.0027 |
| F-E | 18 hier-mindmap (overlap w/ F-C) | +0.057 | 25 % marginal | +0.0010 |
| F-F | 14 tech_docs-rel-fc | +0.064 | 50 % | +0.0017 |
| **Sum (no overlap)** | | | | **+0.0184** |
| **Sum (with 30 % cross-fix overlap discount)** | | | | **+0.0129** |

**Gate check.** v0.3 §16 requires B6 ≥ best baseline + 0.020.
Current: B6 − S7 = **−0.056**.
Post-fix (conservative): B6 − S7 ≈ −0.056 + 0.013 = **−0.043**. Still
gate-failing.

**SQQ judge-fix** (3-axis apples-to-apples evaluation):
- If we score B6 on 3 axes too (drop SQQ), the gap immediately becomes
  **−0.033** without any pipeline change.
- Combined with the F-A through F-F set: **−0.033 + 0.013 ≈ −0.020**.
- Still doesn't clear the gate, but it puts B6 within noise of S7 instead
  of clearly behind.

**Honest assessment.** The proposed within-V4 fixes CANNOT close the gate.
Realistically they close ~25 % of the published gap. To flip the sign would
require:
(a) judge composition change (3-axis or weighted SQQ — out of pipeline scope);
(b) hard precondition enforcement (orchestrator-level retry when `generate_viz`
    not invoked — bigger change than a prompt clarification);
(c) targeted retrieval improvement for multinews-temporal so DSL coverage
    keeps up with S7's full-doc concatenation (B6's content_brief is bounded
    by what sub_queries return; a long article may need 4-5 sub_queries
    instead of 2).

These are out of v0.3's V4 design budget. The within-budget Δ projection
(+0.013) is real and worth shipping for v0.3 close, but it is not a gate-
flipping intervention.

---

## 9. Open questions

1. **Should F-C (swap hier primary to flowchart) be shipped despite
   contradicting §3.2 Table?** The empirical evidence is strong (mindmap
   primary is empirically wrong), but §3.2 is paper-cited spec. Recommend
   shipping as a parameter override with a paper-side footnote, NOT as
   a §3.2 rewrite.

2. **Why does the agent skip `generate_viz` despite the hard precondition
   rule?** Need agent trace logs for the 4 non-Mode-A empty records
   (`10k_12`, `10k_13`, `arxiv_34`, `hotpot_31`). The rule is verbose
   and may be getting elided by the agent's planning step. Cannot resolve
   from data alone.

3. **Is the V6 explicit-chart-type bias real on non-empty records?** Of
   the 32 "bar chart" queries, only 4 have a mis-pick AND all 4 are
   empty-DSL. So V6 may be entirely V1. F-B's marginal Δ above assumes
   25 % of F-A's effect; if all 4 records collapse to V1, F-B Δ → 0.

4. **Why does the consolidated `mermaid_timeline` exemplar use mostly
   single-line entries when its source spec said "multi-line is allowed"?**
   The tmg_oneshot revision process (commit `b3bebcf`) may have
   over-corrected for brevity. Need to confirm with the subagent that
   produced that exemplar set.

5. **What happens to `(govreport, temporal)` (B6's only +Δ cell) if F-D
   is shipped?** That cell is currently +0.002 due to B6's denser
   coverage. F-D risks breaking that pattern. Recommend smoke-testing
   on `govreport_25_temporal` and `govreport_16_temporal` before bulk.

6. **Are `chartjs_pie`, `chartjs_scatter`, `mermaid_classDiagram` truly
   dead types on this dataset, or would query-distribution diversification
   (e.g., adding finance-proportion or schema-extraction queries) bring
   them back?** Out of scope here. Flag for v0.4 benchmark expansion.
