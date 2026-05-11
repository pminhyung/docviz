# Why no-TMG wins — V4 vs S4 mechanism analysis

**Scope.** Diagnose *why every variant of TMG one-shot injection (V0, V1, V4_pool,
V4_consolidated) is net-negative on faithfulness against the no-TMG baseline (S4)
on the Week-0 prototype*, with particular focus on V4_consolidated — the strongest
TMG variant and yet still −0.16 faith vs S4 on the drop subset.

**Anchor data.** `outputs/prototype/viz/all.json` (360 records, 60 query_ids × 6
strategies) + `outputs/prototype/judge_scores/all.json` (axis_scores +
per-checklist `scored` items + tokens/duration). All numbers below are computed
directly from these two files.

---

## 0. TL;DR

The dominant cause of TMG net-negativity is **NOT the one-shot exemplar's
content** (placeholder vs. curated does not move S4-vs-TMG much) and **NOT
viz_type forcing** (V4_consolidated agrees with S4's chosen viz_type on 13/19
drop records — "wrong type" is rarely the bug). The dominant cause is a
**generation-budget shift** introduced by the *whole TMG architecture*: TMG
inflates the agent's planning loop (V4 mean **n_sub_queries = 3.15 vs. S4 1.63**;
mean **tokens_out = 37,409 vs. S4 19,913** — both ≈ 2x) which **trades source
verification cycles for protocol/format cycles**. V4_consolidated regresses on
exactly the items S4 nails: **specific dates, amounts, ranks, modifiers,
qualifying clauses, and inverse-relationship axes** — entity-rich micro-content
that requires a final source-grounded "did I include X?" pass which V4 no longer
has budget for. The exemplar style nudge (Pillar 2's hypothesized mechanism) is a
*third-tier* effect — real but ≤ 20% of the gap.

| hypothesis | label | support strength (1-5) |
|---|---|---|
| **(a) Token-budget override → source-grounded reasoning weakened** | architecture cost | **5/5** dominant |
| **(d) Tool-call protocol overhead consuming step budget** | architecture cost | **5/5** dominant |
| **(e) Schema-template adherence flattens nuance** | exemplar style | **3/5** real but secondary |
| **(b) Style mimicry from exemplars** | exemplar style | **2/5** real for V0 only, near-0 for V4 |
| **(c) viz_type forcing** | router | **1/5** rejected — V4_cons mostly agrees with S4 type |

Paper-level implication: **TMG-as-currently-defined has a generation-cost
problem, not an exemplar-design problem**. Pillar 2's framing must shift from
"the right exemplar makes the model emit better DSL" to "type routing must NOT
add net agent steps". Week-1 priority: **measure the V4-vs-S4 sub-query gap is
causal** (cap V4's sub-query budget at 1.6 = S4's mean and re-measure faith).

---

## 1. Setup + 데이터 source

### 1.1 Strategies and what each isolates

| strategy | rule routing | one-shot | tool call | what it isolates |
|---|---|---|---|---|
| `S4_Agentic` | — | — | — | baseline (Pillar 1+3 only, no Pillar 2) |
| `S4_AgenticTMG` (V0) | yes | placeholder (Founder/Acme) | — | original Pillar 2 |
| `S4_AgenticTMGv1noshot` (V1) | yes | — | — | router alone, no exemplar |
| `S4_AgenticTMGv4_pool` (V4p) | agent-inferred | per-type curated pool (3 each) | yes | full Pillar 2 |
| `S4_AgenticTMGv4_consolidated` (V4c) | agent-inferred | single rich consolidated exemplar | yes | full Pillar 2 |

Drop subset (n = 19) = records where V0 faith < S4 faith. This is the
diagnostic set throughout.

### 1.2 Faith means already established

From `docs/analysis/v4_paired_results.md` and re-verified:

| | drop-subset faith mean | full-set faith mean |
|---|---:|---:|
| 🟢 S4 | **0.954** | 0.825 |
| V4_cons | 0.789 | 0.779 |
| V4_pool | 0.789 | 0.788 |
| V1 | 0.724 | 0.733 |
| 🔴 V0 | 0.480 | 0.721 |

V4_cons − S4 (drop subset) = **−0.165**, BCa CI [−0.283, −0.066], Cohen's d
= −0.68 (medium-large; CI excludes 0). Every TMG variant is below S4.

### 1.3 Cost / budget side-by-side

Computed from `tokens_out`, `duration_seconds`, `n_sub_queries` in viz/all.json:

| strategy | mean tokens_out (full / drop) | mean duration_s (full) | mean n_sub_queries (full / drop) | syntax_valid % (full) |
|---|---:|---:|---:|---:|
| S4_Agentic | 19,913 / 16,407 | 178.8 | **1.63 / 1.58** | **93%** |
| S4_AgenticTMG (V0) | 16,784 / 14,878 | 205.8 | 1.42 / 1.42 | 92% |
| S4_AgenticTMGv1noshot (V1) | 16,450 / 16,636 | 189.6 | 1.43 / 1.68 | 93% |
| S4_AgenticTMGv4_pool | 35,149 / 27,559 | 252.1 | 2.97 / 2.68 | 85% |
| **S4_AgenticTMGv4_consolidated** | **37,409 / 33,753** | **255.9** | **3.15 / 3.00** | **85%** |

Two facts that anchor everything below:
- **V4 doubles the agent's planning loop** (sub-queries × 1.9, tokens_out × 1.9,
  duration × 1.4) compared to S4 — almost the entire delta is the
  `generate_viz` tool call protocol.
- **V4 cannot reliably emit valid DSL.** S4 = 93%, V0/V1 = 92-93%, V4 drops to
  85% — the tool-call layer introduces *new* failure modes (free-text answers,
  parse failures) that the bare agent loop didn't have.

Note `tokens_in = 0` for all records — input tokens were not tracked in the
Week-0 batch instrumentation, so hypothesis (a) "prompt-side budget" cannot be
measured directly. We test it indirectly via output-side proxies (sub-queries,
viz_dsl validity) below.

---

## 2. Side-by-side: S4 vs V4_cons vs V0 (10 records, drop subset)

For each record we quote the verbatim `viz_dsl` (truncated for length) plus the
faithfulness sub-score. Records ordered by S4 − V4_cons faith gap (largest gap
first).

### 2.1 `hotpot_02_relational` — S4 0.75 → V4c 0.00 (Δ = −0.75, the worst V4 regression)

**Q.** Map the connection between Billy Howle and On Chesil Beach.

`S4_Agentic` (faith 0.75, viz_type=`mermaid_flowchart`):
```
graph LR
    A[Billy Howle] -->|Stars in| B[On Chesil Beach]
    B -->|Directed by| C[Dominic Cooke]
    B -->|Based on novella by| D[Ian McEwan]
    A -->|Co-stars with| E[Saoirse Ronan]
    E -->|Stars in| B
```
5 nodes, 5 edges; covers director, novelist, co-star.

`S4_AgenticTMG` (V0, faith 0.25, `mermaid_flowchart`):
```
graph LR
    A[Billy Howle] -->|stars in| B[On Chesil Beach]
```
Catastrophic node-pruning to 2 nodes.

`S4_AgenticTMGv4_consolidated` (faith **0.00**, viz_type field = `mermaid_flowchart`
but `syntax_valid=false`, `syntax_check_kind=mermaid_header:miss`):
```
The connection between Billy Howle and *On Chesil Beach* is that **Billy Howle stars in the film**.

*   **Billy Howle** is an actor who plays a lead role in the 2017 British drama film *On Chesil Beach* [1][2].
*   He co-stars alongside **Saoirse Ronan** [1][2].
*   The film was directed by **Dominic Cooke** and adapted from the 2007 novella of the same name by **Ian McEwan** [1].
```
The agent **regressed to free-text Markdown**. The model knew all the entities
(Howle / OCB / Ronan / Cooke / McEwan) — it just abandoned the DSL contract.
sub_queries = 3 ("Search…", "Generate viz…", "Retry…"), `n_retrieved=1`,
duration=171.9 s. Even with retries, it never produced graph syntax.

This is **architecture-cost evidence (a, d)**, not exemplar-style evidence: V4
*had* the entities, ran out of budget producing them in the right format.

### 2.2 `hotpot_08_comparative` — S4 1.00 → V4c 0.38 (Δ = −0.625)

**Q.** Compare casualties in the Pound Ridge massacre versus other Kieft's War incidents using a chart.

`S4_Agentic` (faith 1.00, viz_type=`chartjs_bar`):
```
labels: ["Wappinger Confederacy (Killed)", "New Netherland Forces (Killed)", "New Netherland Forces (Wounded)"]
datasets: [{label: "Casualties in Pound Ridge Massacre (March 1644)", data: [600, 1, 15], backgroundColor: [...]}]
title: "Casualties in the Pound Ridge Massacre (Deadliest Single Incident of Kieft's War)"
```
Title carries the "deadliest single incident" comparative claim and the
"March 1644" date.

`S4_AgenticTMG` (V0, faith 0.375, `chartjs_grouped_bar`):
```
labels: ["Killed","Wounded"]
datasets: [{"label":"Wappinger Confederacy","data":[600,0]},
           {"label":"New Netherland Forces","data":[1,15]}]
```
Loses date + comparative title; pads zeroes.

`S4_AgenticTMGv4_consolidated` (faith 0.375, **also `chartjs_bar`**):
```
labels: ["Wappinger Confederacy Killed","New Netherland Killed","New Netherland Wounded"]
datasets: [{"label":"Casualties in Pound Ridge Massacre", ...}]
title: "Casualties in the Pound Ridge Massacre (Kieft's War)"
```
V4 picked **the same viz_type as S4** (`chartjs_bar`) and the same data shape —
yet **dropped "March 1644" from the title and dropped "Deadliest Single
Incident" qualifier**. Per-item faith items that broke: "March 1644" → NO,
"500-700 range" → PARTIAL, "more casualties than any other single incident" → NO.

This is **not viz_type forcing (c)** — V4 chose correctly. It is **micro-content
omission (a, e)** — the model used 2.0 times the output budget on planning and
shipped a chart that's structurally identical to S4 but missing 3 textual
qualifiers from the source.

### 2.3 `arxiv_00_comparative` — S4 1.00 → V4c 0.50 (Δ = −0.50, V0 catastrophic at 0.00)

**Q.** Compare the parameter update mechanisms of In-Place TTT and Target Policy Optimization.

`S4_Agentic` (faith 1.00, `mermaid_mindmap`) — full math, 2 methods × 5 sub-axes:
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
      Update Mechanism
        Cross-Entropy Minimization
        Loss: L = -sum(q_i * log(p_theta_i))
        Gradient on Logits  dL/dl = p_theta_i - q_i
```

`S4_AgenticTMG` (V0, faith 0.00, **`chartjs_grouped_bar`**) — fabricated 1/2/3 ordinal:
```
labels=["Update Target","Update Granularity","Objective Function","Gradient Signal","Dependency on Rewards"]
datasets:[{"label":"In-Place TTT","data":[1,1,1,1,0]}, {"label":"Target Policy Optimization","data":[2,2,2,2,1]}]
```
Pure structure-imposition.

`S4_AgenticTMGv4_consolidated` (faith 0.50, `mermaid_flowchart`):
```
flowchart TD
    subgraph In-Place TTT
        A1[Input Sequence] --> A2[Partition into Chunks]
        A2 --> A3[Apply Fast Weights W_down]
        A3 --> A4[Compute NTP-Aligned Loss]
        A4 --> A5[Gradient Descent Step]
        A5 --> A6[Update W_down In-Place]
    end
    subgraph TPO
        B1[Sample Candidates from Policy] --> B2[Score Candidates]
        B2 --> B3[Standardize Scores]
        B3 --> B4[Construct Target Distribution q]
        B4 --> B5[Minimize Cross-Entropy Loss]
        B5 --> B6[Update Policy Parameters theta]
    end
```
V4 fixed V0's pathology (no longer 1/2/3 ordinal grid) but **dropped the
mathematical update rules entirely**: no `W_down = W_down + eta * V_hat^T * Z`,
no `dL/dl = p_theta_i - q_i`, no `q_i ∝ p_old_i * exp(u_i / tau)`. The agent
re-architected the whole picture as a control-flow diagram, lost the equations.
Per-item faith losses: "fast weights = final projection matrix of MLP blocks"
→ NO; "TPO gradient vanishes when policy matches target" → NO.

V4_cons output here is *visually richer* than V0 but *content-poorer than S4*.
The exemplar (`mermaid_flowchart` consolidated) shows a flowchart with
subgraphs and styling — the model copied the **architectural motif** (subgraph
+ control flow) but the source had **algebraic facts**, not control flow.
**Schema-template adherence (e), real evidence**.

### 2.4 `multinews_05_comparative` — S4 1.00 → V4c 0.50 (Δ = −0.50)

**Q.** Compare Target CEO Steinhafel's stated intent for the MN Forward donation against the actual political impact described in the articles.

`S4_Agentic` (faith 1.00, `mermaid_flowchart`):
```
graph TD
    A[Target CEO Gregg Steinhafel] -->|Donated $150,000| B(MN Forward)
    B -->|Used funds to support| C[Republican Tom Emmer's Gubernatorial Bid]
    subgraph "Stated Intent"
        D["Support economic growth and job creation"]
        E["Foster a business climate conducive to growth"]
    end
    subgraph "Actual Political Impact"
        F["Support for a right-wing, anti-gay marriage candidate"]
        G["Conflict with Target's progressive image and GLBT support"]
        H["Employee backlash and calls for boycotts"]
        I["Apology criticized as insincere (sorry for offense, not the act)"]
    end
    A --> D
    A --> E
    C --> F
    F --> G
    G --> H
    H --> I
    style D fill:#e1f5fe   ...
```
Edge label `Donated $150,000` carries the donation amount; node `I` carries
the apology nuance.

`S4_AgenticTMG` (V0, faith 0.75) — keeps subgraph structure but uses
"Stated Intent" as an edge label (loses the $150,000 number, loses the apology
nuance node).

`S4_AgenticTMGv4_consolidated` (faith 0.50):
```
graph TD
    A[Target CEO Gregg Steinhafel's MN Forward Donation] --> B[Stated Intent]
    A --> C[Actual Political Impact]
    B --> B1["Support Economic Growth"]
    ...
    C --> C1["Supported Republican Tom Emmer"]
    C1 --> C2["Emmer Described as Anti-Gay Marriage / Right-Wing"]
    C3 --> C5["Alienation of GLBT Community & Progressive Shoppers"]
    style B fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    style C fill:#ffebee,stroke:#b71c1c,stroke-width:2px
```
V4 *kept the styling motif* (fill colors `#e1f5fe / #ffebee`) — a clear
exemplar-imitation signal — and *added* node C5 (Alienation of GLBT) that S4
didn't have. But it **dropped the $150,000 donation amount** (no longer in
any node or edge label) and **dropped the apology-nuance** (`sorry for offense,
not the act`). Per-item faith losses: "$150,000" → NO; "apology for affecting
employees in unanticipated way" → NO.

V4 had budget to add stylistic flourishes from the exemplar but not budget to
double-check that 2 specific source facts made it in. **Architecture-cost (a)
again**.

### 2.5 `multinews_05_temporal` — S4 1.00 → V4c 0.50 (Δ = −0.50)

**Q.** Timeline of Target CEO Steinhafel's apology and actions regarding MN Forward donation.

`S4_Agentic` (faith 1.00, `mermaid_timeline`) — sections "Background / Backlash /
Apology & Actions"; events include `Target donates ~$150,000 to MN Forward
supporting Republican Tom Emmer's gubernatorial bid` and the August 5, 2010
apology with multi-line `<br>` actions.

`S4_AgenticTMG` (V0, faith 1.00) — date-prefixed events with `2010 July /
2010 August 5 / 2010 Fall`; preserves $150,000 and Emmer.

`S4_AgenticTMGv4_consolidated` (faith 0.50):
```
timeline
    title Timeline of Target CEO Gregg Steinhafel's Apology and Actions
    section August 5, 2010
        Apology Letter Issued : Steinhafel apologizes to employees for MN Forward donation
    section Soon After August 2010
        Strategic Review Begins : Review of decision-making process for political contributions
    section Fall 2010
        Diversity Dialogue : Target leads dialogue on diversity and inclusion with partner organizations
```
Per-item faith losses: "MN Forward backed Republican Tom Emmer" → NO ("mentions
MN Forward but does not explicitly state it backed Republican Tom Emmer");
"$150,000 donation amount" → NO. V4 **dropped the donation context section
entirely** even though both S4 and V0 had it.

This is the cleanest evidence that *the consolidated exemplar's "Foundry
Research Institute" timeline pattern* (4 sections, ~1 event per section, no
amounts/named-actors) **shaped how V4 budgeted the section count**. The model
produced 3 sections × 1 event each — same shape as the exemplar — and ran out
of room for the donation-context section that S4 included as section #1.
**Quantity / template adherence (e + b composite)**.

### 2.6 `arxiv_03_hierarchical` — S4 1.00 → V4c 0.75 (Δ = −0.25)

**Q.** Map the agent roles in Paper Circle's multi-agent framework to a hierarchical taxonomy.

S4 (faith 1.00) — preserves the `Discovery Pipeline → Orchestrator/Tracker →
{Intent, Web Search, Paper Search, Sorting, ...}` 3-level structure.

V0 (faith 0.375) — drops the Tracker middle layer entirely (D4 case from
oneshot_failure_analysis.md).

V4_cons (faith 0.75) — **fixes the Tracker omission** (Discovery Pipeline now
contains `Orchestrator Tracker` with 2 sub-bullets) but **drops the Discovery
Orchestrator node** that the source positioned to handle multi-source search.
Per-item: "Discovery Orchestrator handles search from multiple sources" → NO
("visualization omits the 'Discovery Orchestrator' node entirely").

V4_cons trades one structural omission (Tracker, fixed) for another
(Discovery Orchestrator, broken). Net: +0.375 over V0 but still −0.25 vs S4.
The richer exemplar restores depth (V4 mindmap has 3 levels in the exemplar)
but the model still has a hard time enumerating *all* the named coordinator
nodes the source mentions.

### 2.7 `hotpot_00_relational` — S4 1.00 → V4c 0.75 (Δ = −0.25)

S4: `A[Iqbal F. Qadir] -->|Retired Pakistan Navy Admiral| B(Pakistan Navy)` —
edge label carries rank+branch.
V0: `A[Iqbal F. Qadir] -->|was part of| B[Flotilla]` — generic verb;
"Pakistan Navy" + rank disappear.
V4_cons:
```
A[Iqbal F. Qadir] -->|Led/Part of| B(Pakistan Navy Flotilla)
B -->|Attacked| C[Radar Station in Dwarka]
C -->|Located in| D[Dwarka, Gujarat, India]
A -.->|Context| E[1971 War / Second Indo-Pak War]
```
V4 **restores Pakistan Navy and Gujarat** (vs V0) — clear exemplar-quality win.
But still loses "**Vice-Admiral**" / "**Retired Vice-Admiral**" rank from the
edge label. Per-item: "retired Vice-Admiral in Pakistan Navy" → NO ("labels the
node as 'Iqbal F. Qadir' but does not state his rank or service branch").

This is **partial recovery from V0's flattening (good) but still short of S4's
multi-fact predicate edge labels (e)**. The consolidated `mermaid_flowchart`
exemplar has multi-word edge labels like `Postdoc 2014–2017 at`,
`Joined as Senior Research Scientist in 2017`, `Promoted in 2021 to lead the` —
which is structurally good. But these labels also have a **temporal-action
register** (verb + date) that nudges the model away from the **state-attribute
register** S4 used (`Retired Pakistan Navy Admiral` is a state, not a verb +
date).

### 2.8 `multinews_00_comparative` — S4 1.00 → V4c 0.75 (Δ = −0.25)

S4 (faith 1.00, `mermaid_mindmap`) — 3-branch tree with explicit "81%" and
"$3.2 Billion" sub-bullets.

V0 (faith 0.50, `chartjs_grouped_bar`) — only 2 totals: $4B vs $28B.

V4_cons (faith 0.75, **also `chartjs_grouped_bar` — same as V0**):
```
labels:["DEA Total Cash Seized","DEA Cash Seized from Uncharged Individuals","Total DOJ Asset Forfeiture Fund Growth"]
data:[4.0, 3.2, 28.0]
```
V4 *adds* the $3.2B uncharged-individuals bar (huge improvement over V0) but
**still drops the 81% statistic**. Per-item: "81% statistic attributed to
seizures without criminal charges" → NO ("displays absolute dollar amounts but
does not explicitly state or display the 81% statistic"). The 81% is not
encodable in a bar's data array — it's only encodable as text in a label/title.
V4's chart titles do not contain it.

V4 fixed the V0 catastrophe (3 bars vs 2) but still loses the textual
qualifier that the bar-chart format makes hard to encode. **Structure-format
fit issue (c-adjacent)** — but unlike V0, V4 chose a viz_type that was at
least *internally consistent* with the source data.

### 2.9 `multinews_09_comparative` — S4 1.00 → V4c 0.75 (Δ = −0.25)

S4 (faith 1.00, `chartjs_grouped_bar`):
```
2 datasets across 2 y-axes:
  - "Donation Value (Billions USD)" data=[1.5, 2.0, 2.1] (left axis)
  - "Shares Donated (Millions Class B)" data=[18.4, 17.5, 16.6] (right axis)
```
The dual-axis encoding lets the chart show **inverse correlation** (value up,
share count down).

V4_cons (faith 0.75, **`chartjs_line`** — single dataset):
```
data: [1.5, 2.0, 2.1]  // donation value only
```
V4 picked a viz_type (`chartjs_line`) that **structurally cannot represent the
inverse-relationship axis**. Per-item: "share counts decreased while values
increased" → NO ("only displays donation values, omitting share counts entirely,
so it cannot reflect the inverse relationship").

This is **content-fit failure**: V4's agent-inference picked `chartjs_line`
(the secondary for `temporal`) instead of `chartjs_grouped_bar` (the primary
for `comparative`). The model under-specified the chart and lost half the
information.

### 2.10 `hotpot_05_relational` — S4 1.00 → V4c 1.00 (Δ = 0, V4 ties; included as a counter-example)

S4: 3 nodes, edge `A -->|Plays Young Tom Morris, son of| C` — multi-fact label.
V4_cons:
```
graph TD
    A[Jack Lowden] -->|portrays| B[Young Tom Morris]
    B -->|is son of| C[Old Tom Morris]
    A -->|stars in| D[Tommy's Honour]
    C -->|is character in| D
    B -->|is character in| D
```
V4 *split* the multi-fact edge into 2 cleanly separated edges (`portrays` +
`is son of`) and explicitly added `Young Tom Morris` as a node. Result: judge
gives YES on both checklist items that V0 broke (D3 in the prior analysis).
**This is an exemplar-style WIN** — the consolidated flowchart exemplar's
register encouraged decomposition over compression. faith 1.00 ties S4.

This counter-example matters: **the exemplar mechanism does work when the
source content is small** (3 entities, 3 facts). What it doesn't survive is
larger content where the **extra decomposition costs** budget that other facts
needed.

---

## 3. Judge per-item score 패턴 (어떤 checklist 가 V4 에서 NO?)

Aggregating V4_cons LOSS items (S4=YES, V4_cons ∈ {NO, PARTIAL}) across the
records in §2:

| qid | item that V4_cons broke | category |
|---|---|---|
| hotpot_02_relational | director (Cooke) | F1: dropped relation (free-text collapse) |
| hotpot_02_relational | novelist (McEwan) | F1: dropped relation |
| hotpot_02_relational | "Billy Howle stars in" | F1: dropped relation |
| hotpot_08_comparative | "March 1644" | F2: specific date dropped |
| hotpot_08_comparative | "500-700 range" | F2: numeric range collapsed to point |
| hotpot_08_comparative | "more casualties than any other incident" | F3: comparative qualifier dropped |
| arxiv_00_comparative | "fast weights = final projection matrix of MLP blocks" | F4: math/identity claim dropped |
| arxiv_00_comparative | "TPO gradient vanishes when policy matches q" | F4: math claim dropped |
| arxiv_03_hierarchical | "Discovery Orchestrator handles multi-source search" | F5: named coordinator role dropped |
| hotpot_00_relational | "Retired Vice-Admiral in Pakistan Navy" | F6: rank/title qualifier dropped |
| multinews_00_comparative | "81% statistic" | F7: percentage dropped (cannot encode in bar data) |
| multinews_05_comparative | "$150,000 donation amount" | F8: specific amount dropped |
| multinews_05_comparative | "apology for unanticipated effects" | F3: nuance qualifier dropped |
| multinews_05_temporal | "MN Forward backed Tom Emmer" | F1: dropped relation |
| multinews_05_temporal | "$150,000 donation amount" | F8: specific amount dropped |
| multinews_09_comparative | "share counts decreased while values increased" | F9: inverse-relationship axis omitted |

Categorized:

| category | count | what's lost | category cause |
|---|---:|---|---|
| **F2/F8 — specific dates/amounts/numbers** | 4 | March 1644, $150,000 (×2), 500-700 range | **micro-content omission under budget pressure** |
| **F1 — entity-relation pairs** | 4 | director, novelist, lead-actor, candidate-backed | **structure-collapse to free-text or under-decomposition** |
| **F4 — math/algebraic claims** | 2 | TPO gradient identity, fast-weight definition | **template-form mismatch (flowchart vs equation)** |
| **F3 — comparative/qualitative qualifiers** | 2 | "more casualties than any other", "apology nuance" | **non-encodable in chart data field; need title text** |
| **F6 — rank/title/modifiers** | 1 | "Vice-Admiral" rank | **edge-label register trimming** |
| **F7 — percentage statistics** | 1 | "81%" | **chart format limitation + caption omission** |
| **F5 — named coordinator/role** | 1 | "Discovery Orchestrator" | **enumeration omission** |
| **F9 — inverse / dual-axis claims** | 1 | "shares vs value inverse" | **viz_type under-specification** |

**Pattern.** ≥ 60% of V4_cons faith losses are **omissions of specific source
strings** (dates, amounts, ranks, percentages, qualifying clauses) that **the
chart/diagram data structure permits but the model declined to include**. These
are not "the model didn't know" — S4 with the same retrieved chunks puts them
in. They're **"the model ran out of attention budget for the final source-grounded
content pass"**.

V4_cons gains over V0 (where measurable):
- `hotpot_05_relational`: V4 splits multi-fact edge; faith 0.25 → 1.00.
- `arxiv_03_hierarchical`: V4 restores Tracker middle layer; 0.375 → 0.75.
- `hotpot_00_relational`: V4 restores Pakistan Navy + Gujarat; 0.50 → 0.75.
- `arxiv_00_comparative`: V4 escapes V0's numeric-grid trap; 0.00 → 0.50.

V4_cons gains correlate with **single-record content where the better exemplar
register helps the model commit to the right schema**. V4_cons losses correlate
with **multi-fact records where the agent-inference + tool-call layer
consumes the budget that source verification needed**.

---

## 4. 5 가설의 evidence/counter-evidence + 점수

For each hypothesis, the proposed mechanism, then the data signal that
supports or contradicts it. Score = 1 (rejected) to 5 (dominant cause).

### (a) Token-budget override — TMG one-shot reduces source-grounded reasoning

**Mechanism.** TMG injects extra prompt content (router rule + exemplar)
before the source. With a fixed total context, the source-attended portion
shrinks; the model's "did I include source fact X?" scan is shallower.

**Evidence.**
- ✅ V4 `tokens_out` mean = 37,409 vs S4 19,913 (+88%). The agent burns this
  much more on planning/tool calls — the **answer-generation** phase has
  proportionally less compute attention budget.
- ✅ V4 mean `n_sub_queries = 3.15` vs S4 1.63. Sub-queries are
  decomposition / re-search calls before final emission; doubling them means
  the agent spends nearly half its loop on planning, not on source consultation.
- ✅ V4_cons `syntax_valid=85%` vs S4 93%. **Output validity drops** — clear
  signal that the agent runs out of budget before completing well-formed DSL.
  3 of the 19 drop-subset V4 records collapsed to free-text (hotpot_02_rel,
  hotpot_04_comp, multinews_00_comp).
- ✅ `tokens_in` is unmeasured in this batch — can't directly quantify prompt
  pressure. But S4 (no TMG injection) has the **shortest** sub-query loop AND
  the **highest** faith. The negative correlation between agent-loop length
  and faith is consistent with budget displacement.
- ✅ Per-item judge analysis (§3): 8 of the 16 V4 LOSS items are **omissions
  of specific source content that the chart/graph would have permitted**. This
  is the clearest fingerprint of "had the entities, didn't get them in".
- ❌ No counter-evidence in the data; the only way to falsify directly is the
  cap-budget intervention proposed in §6.

**Score: 5/5 — dominant.**

### (d) Tool-call protocol overhead — `generate_viz` loop eats step budget

**Mechanism.** V4 (pool / consolidated) requires the agent to:
(1) inspect chunks, (2) decide viz_type, (3) draft a content_brief,
(4) call `generate_viz(viz_type, content_brief)`, (5) embed the returned JSON
verbatim. Each tool round-trip = a model step. The Smol-Agent step budget
(default ~6) gets consumed mostly by protocol, leaving 1-2 steps for actual
source + draft work.

**Evidence.**
- ✅ V4 `n_sub_queries` ≈ 3.0; V0/V1 ≈ 1.4-1.7; S4 = 1.6. The +1.4
  sub-queries-per-record gap is tool-call protocol, not extra source retrieval
  (`n_retrieved` is constant ≈ 1.0 across all strategies).
- ✅ The free-text-collapse failures (hotpot_02_relational, hotpot_04_comparative)
  show 3-4 sub_queries including a `Retry generating visualization for ...`
  — the agent hit step budget before producing valid DSL, then was forced to
  return *something* and returned its raw thoughts.
- ✅ `duration_seconds` mean 256 (V4_cons) vs 179 (S4) — the agent is taking
  77 s longer per record, mostly inside the tool protocol loop.
- ✅ `mermaid_header:miss` and `chartjs_json:parse_fail` are V4-specific
  failure kinds that **don't appear at meaningful rates in S4** (S4_Agentic
  only has `mermaid_header:miss` on 4 of 60 records, all 10k records where the
  bare model emitted "answer here" placeholder, *not* a tool-protocol issue).
- ❌ V0 and V1 do not have the tool call but are still net-negative — so tool
  call alone can't explain the entire TMG hurt. It is **additive on top of the
  base TMG injection cost**.

**Score: 5/5 — dominant for V4 specifically; explains why V4 ≯ V1 on faith
despite the better exemplar.**

### (e) Schema-template adherence — model copies exemplar's *shape* too literally

**Mechanism.** The consolidated exemplar's `mermaid_flowchart` has subgraphs
+ styles + control-flow arrows; the consolidated `mermaid_timeline` has 4
sections × 1-3 events each. The model imitates the *macro-shape* (subgraph
count, section count, label register) rather than letting the source dictate
shape.

**Evidence.**
- ✅ `arxiv_00_comparative`: V4 produced a control-flow flowchart with 2
  subgraphs (matches exemplar shape) but the source needed equations
  (mismatch), so the equations were dropped.
- ✅ `multinews_05_temporal`: V4 produced 3 sections × 1 event (close to
  exemplar's 4-section template) and dropped the donation-context section
  that didn't fit the exemplar's "Founding / Expansion / Quarterly" register.
- ✅ `multinews_05_comparative`: V4 *kept the styling fill colors verbatim*
  (`#e1f5fe / #ffebee`) from the exemplar — direct visual evidence of
  exemplar-shape mimicry.
- ❌ **No placeholder entity leakage.** Across all 60 V4_cons records, *zero*
  contain exemplar-specific entities (Cape Halverton, Foundry Research,
  Castellan, Pemberton, Halverson, Cinderfall, etc.) — the model successfully
  treats the exemplar as a schema template, not a content template. Same for
  V4_pool. So the leak is at the *shape* layer, not the *string* layer.
- ❌ V4_cons output length (mean 686 chars) ≈ S4 (mean 640) — V4 is not
  systematically truncating, just truncating *the wrong content*. This argues
  against pure template-rigidity; it's selective.

**Score: 3/5 — real but second-tier. Affects shape decisions but doesn't
account for most micro-content omissions.**

### (b) Style mimicry — model copies exemplar's *register* (verb tense, label morphology)

**Mechanism.** V0's exemplar has 1-2 word past-tense verbs (`founded`,
`acquired`, `hired`, `advised`). V4_cons exemplars have richer multi-word
edges. The model regresses to the exemplar's register.

**Evidence.**
- ✅ V0 case `hotpot_05_relational`: edge `Plays Young Tom Morris, son of` →
  `portrays son of` (D3 in oneshot_failure_analysis.md). Clear V0 register
  flattening.
- ✅ V4_cons case `hotpot_00_relational`: V4 uses `Led/Part of` instead of
  `Retired Pakistan Navy Admiral`. Better than V0's `was part of` but still
  short of S4's noun-phrase rank label. Partial mimicry of the consolidated
  exemplar's verb-action register.
- ❌ For V4_cons, the absolute counts are small. Most V4 LOSS items are NOT
  about edge-label morphology — they're about content omission (§3 categories
  F1, F2, F4, F8 dominate; F6 register-trimming is just 1 of 16 items).
- ❌ V4_cons recovers most of V0's style flattening (e.g., `hotpot_05_relational`
  goes 0.25 → 1.00 with multi-word edges restored).

**Score: 2/5 — real for V0, near-resolved by V4. Not the V4-vs-S4 gap.**

### (c) viz_type forcing — router/agent picks a viz_type that mismatches source structure

**Mechanism.** V0/V1 use `TYPE_TO_VIZ` (rule routing) which hard-maps
`comparative → chartjs_grouped_bar`, etc. V4 uses agent inference but the
exposure rule lists per-type "use cases" that bias the choice.

**Evidence.**
- ❌ **V4_cons matches S4's viz_type on 13/19 drop-subset records** (68%).
  When V4 picks the same type as S4, the gap is still large (e.g.,
  hotpot_08_comp same `chartjs_bar` → −0.625; hotpot_05_rel same
  `mermaid_flowchart` → 0.0; multinews_05_comp same `mermaid_flowchart`
  → −0.50). **Same type, still loses.** The bug is downstream of type choice.
- ❌ Only 1 of 19 drop records is a clean viz_type-disagreement case where V4
  matches V0 but not S4: `multinews_00_comparative` (V4 chose
  `chartjs_grouped_bar` like V0, S4 chose `mermaid_mindmap`). And even there,
  V4 outperformed V0 (0.75 vs 0.50) by adding the third bar S4 had as a leaf.
- ❌ The clearest viz_type mismatch case is `multinews_09_comparative` where
  V4 chose `chartjs_line` (a single-dataset format) over S4's `chartjs_grouped_bar`
  (dual-axis). But this is V4 *under*-choosing schema richness, not the rule
  routing forcing the wrong type.
- ✅ For V0/V1 specifically (rule routing), structure imposition is the
  dominant cause (oneshot_failure_analysis.md §2c — 7/19 drops). But that
  is *V0's* problem; V4 inherits the agent's own inference and largely fixes
  it.

**Score: 1/5 for V4_cons; 5/5 for V0/V1. Pillar 2's rule-routing form is
genuinely broken; Pillar 2's agent-inference form is not. The remaining
V4-vs-S4 gap is not viz_type-driven.**

---

### Summary scoreboard

| hypothesis | V0 score | V4_cons score | dominant for which? |
|---|---:|---:|---|
| (a) Token-budget / source-attention budget | 3 | **5** | V4 |
| (d) Tool-call protocol overhead | 0 | **5** | V4 specifically |
| (e) Schema-template (shape) adherence | 4 | 3 | V0 dominant; V4 secondary |
| (b) Style/register mimicry | 4 | 2 | V0 only |
| (c) viz_type forcing | **5** | 1 | V0/V1 only |

V4_cons removes the V0 routing/style problems but **adds new architecture-cost
problems** that net to a *smaller-but-still-negative* gap vs S4. The TMG
*architecture* is the bug, not the TMG *exemplar*.

---

## 5. Root cause + paper framing 함의

### 5.1 Dominant cause

**TMG, in every implemented form, costs the agent more steps/tokens than it
saves, and that cost falls precisely on source-verification.** Specifically:

1. **V0/V1 (rule routing)**: the rule sometimes points at the wrong viz_type
   (`comparative → chartjs_grouped_bar` is wrong for ~50% of comparative
   queries on text-only sources), forcing structure imposition (§4c).
2. **V4 (agent inference + tool call)**: removes (1) but introduces a tool-call
   round-trip protocol that doubles `n_sub_queries` and `tokens_out`. The
   model spends its step budget on `(infer type → write brief → call tool →
   parse return → embed)` instead of `(read source → enumerate facts → emit
   schema-fit DSL → verify each fact appears)`. Source-grounded fidelity
   regresses on **specific dates / amounts / ranks / percentages / inverse-
   relationship axes** — exactly the items that need a final source-checking
   pass.

The exemplar (placeholder vs curated pool vs consolidated) only modulates *how*
the budget-displaced output looks. It cannot recover the missing source-
verification budget.

### 5.2 Paper-level implication for Pillar 2 (TMG)

Current §3.2 framing — "Type-aware Multi-Viz Generation: a query-type → viz-type
router with type-specific one-shot examples improves visual generation
faithfulness" — is **falsified by the data** as currently implemented. The
honest framings:

**Option F1 — narrowed TMG.** "TMG provides a *viz-type rescue* in 2 of 8
prototype cells (10k temporal, 10k quantitative) where the bare agent
sometimes emits empty / wrong-type DSL. Outside those cells, TMG-mediated type
guidance is not measurably beneficial." This is the smallest defensible claim
and is *true* in our data.

**Option F2 — TMG-as-router only, no exemplar.** "TMG = a query-type →
viz-type *recommendation* injected as text into the prompt; *no exemplar*.
This avoids the V4 tool-call overhead and the V0 placeholder leakage." This
matches V1, which is closer to S4 than V0 or V4 are. Re-cast §3.2 as
"router-only TMG, with the exemplar as the −TMG ablation".

**Option F3 — drop TMG entirely.** "The 5-axis judge protocol on these 60
queries does not show evidence that any tested form of type-routed exemplar
injection improves visualization faithfulness over a strong agent baseline.
We retain Pillar 1 (CIS) and Pillar 3 (SAO) as the substantive contributions."
This is the most defensible scientifically; politically the hardest to write.

**Recommendation.** Option F1 + an explicit *negative-result* subsection in
§3.2. Specifically: "We tested 5 variants of type-aware exemplar injection;
none beat the no-TMG baseline at the per-record faithfulness level. We retain
TMG only for its weakest claim (viz-type rescue on degenerate-output cells)
and document the failure modes (this analysis) as a methodological
contribution." This preserves narrative continuity from Week-0 without
overclaiming.

### 5.3 Why this matters for the 3-pillar framing

If TMG is downgraded (F1 or F2), the three-pillar paper becomes a **two-pillar
paper with a methodology contribution** — Pillar 1 (CIS) and Pillar 3 (SAO)
remain net-positive contributions; Pillar 2 (TMG) becomes a
"controlled-failure case study" demonstrating that *structured prompt
injection has measurable negative interactions with agent step budgets*. This
is actually a cleaner contribution than "we have 3 things that work" because
it's a finding the field has not yet quantified.

Risk: the cleanup-and-restate in §3.2 is non-trivial editorial work. But
attempting to publish an "all 3 pillars positive" claim against this evidence
is a reviewer-bait setup.

---

## 6. Week-1 mitigation 우선순위 + V5 design 제안

### 6.1 Priority 1 — Causal isolation: cap V4's sub-query budget

**Why first.** Hypothesis (a)+(d) together predict that **forcing V4 to use the
same step budget as S4** (max ~2 sub_queries) will close most of the gap.
This is a cheap, decisive test.

**Procedure.**
1. Add a `max_steps=2` (or `max_sub_queries=2`) cap to the V4 strategy's
   agent loop (`code/pipelines/s4_agentic_tmg.py`).
2. Re-run on the 19-record drop subset only (cheap; ≈ 19 × 1 strategy ≈ 1 hr).
3. Predicted outcome:
   - If capped-V4 faith ≥ S4 faith on drop subset: hypothesis (a)+(d)
     **confirmed**; the architecture cost was the issue; V4-with-cap is the
     publishable variant.
   - If capped-V4 faith stays at ≈ V4_cons (0.79): hypothesis (e) is larger
     than estimated; need exemplar-shape interventions instead.
   - If capped-V4 faith collapses (model can't finish in 2 steps): the
     tool-call protocol is **structurally** too expensive at this step
     count; V5 redesign needed (see 6.4).

### 6.2 Priority 2 — Closed-API cross-judge

**Why.** Current judge is a single instance of the local model on the
checklist scoring task. The +0.165 V4-vs-S4 gap could be a judge artifact in
either direction (e.g., the judge over-rewards verbose flowcharts that
"look" structured). One closed-API judge run on the same 60 records would
tell us whether the S4 dominance survives a different evaluator.

**Cost.** ≈ 60 records × 4 strategies × 1 judge call ≈ 240 calls × ~3K input
tokens. With Claude/GPT batch, ≈ $5-10. (See `batch-api-cost` skill.)

**Decision rule.** If closed-API also ranks S4 > V4_cons on ≥ 14/19 drop-
subset records, the local-judge result is robust and (a)+(d) is the real
story. If closed-API flips, the analysis above needs revisiting.

### 6.3 Priority 3 — Domain-conditional exemplar rotation (Option A from prior analysis)

**Why deprioritized.** This is exemplar-design work; if (a)+(d) is the
dominant cause, no exemplar redesign will close the gap.

**When to do it.** *After* 6.1 confirms the budget issue is real. Then a
narrow exemplar-conditioned-on-source-domain rotation might recover the small
remaining gap (≤ 0.05). Not worth doing first.

### 6.4 V5 design proposal — "Lazy TMG"

If 6.1 confirms tool-call overhead is the issue, the design that should
beat S4 is:

**V5 = single-shot router-only, *post-hoc* type validation.**

```
1. Run S4_Agentic unchanged. Let the bare agent loop emit (viz_type, viz_dsl)
   with no TMG injection.
2. Inspect emitted (viz_type, viz_dsl) once:
   - If viz_type == "" OR syntax_valid == False: invoke a *single* repair
     call: "The query type is {query_type}. Suggested viz_type for that
     type is {primary}. Re-emit (viz_type, viz_dsl) using the suggested
     type and ONLY the source content already retrieved."
   - Else: keep S4 output verbatim.
3. No exemplar injection at any point.
```

**Why this should beat S4 and V4 simultaneously.**
- **Captures the 2 V0/V4 wins** (10k_01_temporal, 10k_04_temporal) where
  the bare agent emits empty DSL — these are exactly the
  syntax_valid==False / viz_type=="" cases that the repair triggers on.
- **Adds zero overhead in the 56/60 records where the bare agent already
  succeeds.** No extra sub-queries, no exemplar token budget, no tool-call
  protocol.
- **Avoids the (a)+(d)+(e) failure modes** for normal cases because the
  TMG layer never runs.
- **Preserves Pillar 2's identity** as "type-aware" — type information is
  used, just not at the front of the prompt.

Expected mean faith: ≈ S4 + (small fix on the 4 syntax-failure cells), so
≈ 0.84 vs. S4's 0.825. Mostly tied with S4 on a per-record basis but with
fewer catastrophic 0.0 records on degenerate inputs.

**Implementation effort.** ~1 day. Wraps `S4_Agentic` with a post-emission
validator + 1 conditional repair call. Re-uses `tmg.TYPE_TO_VIZ` + a 1-line
repair prompt; no exemplar pool, no tool call.

### 6.5 Optional V6 — "Conditional TMG" (only when source is short)

Hypothesis: the V4 budget cost only matters when the source is long enough
that the agent already needs all its steps. For *short* sources (≤ 3 chunks,
~1500 tokens), V4's exemplar guidance might be net-positive because the
source consultation is cheap.

If V5 is implemented, V6 is a small add-on: gate TMG injection on
`len(retrieved_chunks_chars) < 1500`. Untested in our data; a Week-2 idea.

---

## 7. Limitations

1. **`tokens_in` is unmeasured.** The per-record input-token count was not
   logged in the Week-0 batch run. Hypothesis (a) is therefore inferred from
   output-side proxies (sub_queries, tokens_out, syntax_valid) rather than
   directly measured. The V5 / Priority-1 isolation experiment will surface
   this; until then, the (a)-vs-(d) split is partially conjectural.
2. **n = 19 drop subset is small.** All Cohen's d values above are
   estimated on 19 paired records; the underlying noise is large. The
   directional claims are robust (CI excludes 0 for V4_cons vs S4 faith) but
   the magnitudes are noisy.
3. **Single judge model.** All faith scores are from one judge instance.
   Priority 2 (closed-API cross-judge) directly addresses this; until that's
   done, the V4-vs-S4 ranking has not been triangulated.
4. **Exemplar pool is fixed in this analysis.** A different consolidated
   exemplar (e.g., one without subgraph styling on the flowchart, or with
   per-type-tip emphasis on "preserve named entities") might shift the (e)
   score. The current consolidated exemplar (`code/agent_tools/oneshot_pool.json`)
   has rich Foundry/Castellan content that is hard for the model not to
   pattern-match against.
5. **Step budget is implicit, not configured.** The smol-agent `max_steps`
   default in our s4 strategies is the reason `n_sub_queries` is a useful
   proxy for budget. If the framework's underlying step limit changes
   (e.g., HF library upgrade), this analysis would need re-running.
6. **No retrieval-quality controls.** All strategies use the same retriever
   (`n_retrieved` is constant ≈ 1.0). If V4's tool-call layer happened to
   degrade retrieval quality silently, that would be a confound; we have no
   evidence it does, but no direct measurement either.
7. **No human comparison.** The 30-record human spot-validation kit
   (`code/judge/human_spot_validation.py`) was created but per-record human
   labels for the V4 variants weren't run as part of Week-0. Confirming the
   V4 < S4 ranking against human labels on 5-10 V4 records would be the
   strongest possible check.

---

## Appendix A — Source artefacts referenced

- Data: `outputs/prototype/viz/all.json`, `outputs/prototype/judge_scores/all.json`
- Code:
  - `code/pipelines/tmg.py` — `ONE_SHOT_BY_VIZ_TYPE`, `TYPE_TO_VIZ`,
    `V4_POOL_EXPOSURE_RULE`
  - `code/pipelines/s4_agentic.py`, `code/pipelines/s4_agentic_tmg.py`
  - `code/agent_tools/generate_viz.py`, `code/agent_tools/oneshot_pool.json`
- Prior analysis:
  - `docs/analysis/oneshot_failure_analysis.md` (commit b90eda1) — V0's 5
    failure modes (a/b/c/d/e) and Variant 0-4 predictions. The current
    analysis is the **measured** counterpart; V4 results are consistent
    with that prior's V3/V4 *direction* (V4 > V0 on faith) but **not**
    with the prior's *magnitude* (V4 ≯ S4, contrary to the +0.05 prediction).
  - `docs/analysis/v4_paired_results.md` — paired bootstrap CIs / Cohen's d
    that establish the V4_cons − S4 = −0.16 (drop subset) finding.
- Spec: `PAPER_MASTER_SPEC.md` §3.2 (TMG pillar definition) — needs
  amendment per §5.2 above.
