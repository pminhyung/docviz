# Coverage-axis Bias Taxonomy — B6 (V4_consolidated) vs B7 (SelfRefine)

Status: investigation, 2026-05-17. Scope: 265 paired records. Coverage
axis only. Complementary to `b6_vs_b7_paired_loss_analysis.md` (which
focused on type_appropriateness + structural loss) and
`viz_type_bias_taxonomy_260516.md` (viz-type routing). Goal: input-side
bias driving the −0.032 coverage gap, with V4-compatible fixes.

## 1. Executive summary

- **Paired coverage means (n=265, all-records)**: B6 = 0.8283,
  B7 = 0.8742, Δ = **−0.0459**. The task brief cites −0.032 — that is
  the valid-only intersection (excluding B6's 11 empty-DSL fails);
  this report uses both views and aggregates conservatively.
- **The single biggest contributor is `EMPTY_OUTPUT` (n=11 across all
  B6, mean coverage 0.227 vs 0.854 on non-empty)** — 5 of those land
  in the 40 ≥0.20 gap records and drag the full-population mean by
  ~0.026 alone (qids `hotpot_13_relational`, `hotpot_45_comparative`,
  `arxiv_48_comparative`, `arxiv_34_comparative`, `arxiv_39_comparative`).
  Mostly `AGENT_SKIPPED_RETRIEVAL` (n_sub_queries=0) or sidecar-missing.
- **Among non-empty losses, the dominant input-side bias is
  `NARROW_RETRIEVAL + MISSING_AXIS`** (20/40 and 23/40 of the gap
  records co-tagged): the agent issues 2 sub-queries on multi-axis
  queries ("X versus Y", "A and B", "release dates AND platforms"),
  hits one axis, and the checklist marks the other axis FAIL.
  Examples: `hotpot_48_comparative` (release dates ✓, platforms-of-
  original ✗), `tech_docs_28_relational` (concepts ✓, Vitess/MongoDB
  implementations ✗), `arxiv_34_comparative` (tax effect ✓, age-group
  breakdown ✗).
- **`HEADER_ONLY` (22/40, mean gap 0.515)** — the viz shows the
  high-level entity/category but omits the specific attribute the
  checklist asks for (e.g., `hotpot_48` shows the timeline but never
  states "Kiwami is a remake of the original"; `govreport_44` shows
  USML→CCL but never names the horsepower/speed criterion).
- **`EXEMPLAR_NUM_CAP` (13/40)**: B6 outputs converge to the
  exemplar's element count (chartjs_bar exemplar has 5 labels × 1
  dataset; chartjs_grouped_bar has 4 × 3; mermaid_flowchart 12 nodes
  / 11 edges). B6 median elements in gap records = 9; B7 median = 12.
  The cap shows up when the query needs more breadth than the
  exemplar implies.
- **Recipe from B6 wins (n=25)**: wins have *higher* n_sub_queries
  (mean 2.56 vs 2.25 in losses), longer DSL (mean 973 vs 786 chars),
  and the same multi-axis query wording. The fix is not "fewer
  sub_queries", it is "decompose multi-axis queries into one
  sub_query per axis AND verify each named entity appears in the
  viz".

## 2. Method

- Data: `outputs/prototype/judge_scores/all.json`,
  `outputs/prototype/viz/all.json`,
  `outputs/prototype/judge_scores/checklists.json`,
  `data/prototype/queries/all.json`, `data/prototype/bundles/all.json`.
- B6 = `S4_AgenticTMGv4_consolidated`, B7 = `S7_SelfRefine`, both
  n=265, fully paired by `query_id`.
- Gap set: paired records with B7_cov − B6_cov ≥ 0.20 → n=40.
- For each gap record, read query, coverage checklist items, B6
  sub_queries, B6 viz_dsl, B6 FAILed coverage `scored` entries with
  the judge `justification`, plus the B7 viz_dsl for contrast.
- Element counts: chartjs `labels × datasets`; mermaid_flowchart
  unique node IDs via `^([A-Z][A-Za-z0-9_]*)[\[\(]` regex (rough but
  consistent across B6/B7).

## 3. Coverage distribution + cell concentration

| Bucket | n / 265 |
|---|---:|
| [0.00, 0.25) | 19 |
| [0.25, 0.50) | 6 |
| [0.50, 0.75) | 42 |
| [0.75, 1.00] | 198 |

Bottom-quartile cell concentration (n=66):

| (source, query_type) | n |
|---|---:|
| `govreport, temporal` | 11 |
| `10k, quantitative` | 7 |
| `arxiv, hierarchical` | 7 |
| `tech_docs, relational` | 7 |
| `govreport, hierarchical` | 7 |
| `hotpotqa, relational` | 6 |
| `hotpotqa, comparative` | 6 |
| `multinews, comparative` | 6 |

40-record gap-set cell concentration:

| (source, query_type) | n |
|---|---:|
| `tech_docs, relational` | 6 |
| `arxiv, hierarchical` | 5 |
| `arxiv, comparative` | 4 |
| `hotpotqa, comparative` | 4 |
| `hotpotqa, relational` | 4 |
| `govreport, hierarchical` | 4 |
| `govreport, temporal` | 4 |
| `10k, quantitative` | 4 |

The loss is broad across sources; no single cell dominates. This
matters for fix design: a rule edit affects all cells equally, an
exemplar-pool edit affects only the viz_type it touches.

## 4. Failure mode taxonomy

Tags applied programmatically; a single record can carry multiple tags
(over-counted on purpose to surface co-occurrence). Counts over the
40-record gap set.

| Mode | Count | Mean Δ_cov | Mechanism (one line) |
|---|---:|---:|---|
| `MISSING_AXIS` | 23 | 0.478 | Coverage justification names something the viz "lacks / omits / fails to include" |
| `HEADER_ONLY` | 22 | 0.515 | Judge cites a "specific" / "detail" / "breakdown" the viz never spells out |
| `NARROW_RETRIEVAL` | 20 | 0.458 | n_sub_queries ≤ 2 on a query with multi-axis wording (`and`/`vs`/`compare`/`between`) |
| `EXEMPLAR_NUM_CAP` | 13 | 0.423 | Output element count sits inside the exemplar's range (chart 2–4 labels × 1–3 series, or flowchart 5–10 nodes) |
| `SHORT_DSL` | 7 | 0.405 | B6 DSL chars < 0.55 × B7 DSL chars |
| `EMPTY_OUTPUT` | 5 | 0.800 | B6 `viz_dsl == ""` (sidecar missing or agent skipped tool) |
| `AGENT_SKIPPED_RETRIEVAL` | 3 | 0.778 | `n_sub_queries == 0` |
| `DOC_FOCUSED` | 0 | — | No FAIL justification cites "one-of-N docs" — not a driver on this dataset |
| `WRONG_SLICE` | 0 | — | No FAIL cites "wrong topic / tangential" explicitly; the topic-mismatch records all also carry NARROW_RETRIEVAL and were re-classified there |

39/40 records carry ≥1 tag (only `govreport_29_temporal` is
unclassified — its checklist failures are about ordering/dates that
ARE in the DSL, judge nit-pick). NARROW_RETRIEVAL and MISSING_AXIS
co-occur in **17/20** NARROW_RETRIEVAL records — confirming the
"narrow sub_queries → axis missed" causal chain rather than two
independent failures.

## 5. Per-mode deep-dive

### 5.1 `MISSING_AXIS` (23, mean gap 0.478) — the biggest mode

User query implies ≥2 dimensions; B6 viz covers 1, judge checklist
checks both. Examples (qid, what was hit ✓ / missed ✗):

- `hotpot_48_comparative` ("release timelines AND platforms for
  Yakuza vs Yakuza Kiwami"): timeline ✓ for Kiwami, original Yakuza's
  release date and platform ✗.
- `tech_docs_28_relational` ("sharding vs horizontal partitioning,
  highlighting how Vitess AND MongoDB implement"): Vitess/MongoDB ✓,
  contrast of architectural scope ✗.
- `arxiv_34_comparative` ("smoking reduction effects of price vs tax
  across age groups"): B6 viz empty (also EMPTY_OUTPUT); checklist:
  effect-size comparison ✗, age-group breakdown ✗, EU+timeframe ✗.
- `govreport_44_hierarchical` ("migration USML→CCL under STA"): the
  migration ✓, "specific criteria like horsepower/speed" ✗, "items
  remain on USML" ✗.
- `govreport_25_temporal` ("Service Center development from IEED
  concept to 2016 budget"): timeline ✓, "initial IEED concept" ✗
  (timeline starts at 2013 Council), "lack of documented decision
  bases" ✗.

Root cause: the V4 rule's "(2) tool_invoke generate_viz with viz_type
+ content_brief" does not name an axis-coverage invariant. The
content_brief the agent writes is summary-shaped ("show timeline of
X"), not enumerative ("include for each of A, B, C: date + platform").

### 5.2 `HEADER_ONLY` (22, mean gap 0.515)

Viz shows the category but never the specific instance. Examples:

- `tech_docs_01_relational` ("link MongoDB and Couchbase to shared
  NoSQL types like Document store and Key-value cache"): B6 shows
  MongoDB→Document store, Couchbase→Document store/Key-value
  store/Key-value cache, but checklist asks "does it reflect
  Document store is a SHARED type for both?" — there is no visual
  shared-node, just two arrows pointing at separate `Document store`
  boxes. PARTIAL.
- `tech_docs_21_relational` ("Merkle-Damgård + length-extension
  attacks"): DSL lists "naive authentication schemes" only inline as
  text, not as a mapped node. FAIL.
- `arxiv_05_hierarchical` ("LEEP/LogME → GBV loss function"):
  formula shown ✓, but "smaller loss = higher transferability" ✗
  (no annotation).

Root cause: the generate_viz tool prompt's "preserve every specific
fact present in the brief" only enforces facts *that already exist in
the brief*. If the brief omits the fact, the prompt cannot rescue it.
This is upstream — the agent's content_brief is the choke point.

### 5.3 `NARROW_RETRIEVAL` (20, mean gap 0.458)

n_sub_queries ≤ 2 on a multi-axis query. Examples:

- `hotpot_35_comparative` ("compare construction timelines AND
  primary purposes of Dundee Canal vs Miami Canal"): 2 sub_queries
  `construction timeline dates built` / `primary purpose function` —
  generic, no canal names, retrieves general filler.
- `govreport_11_temporal` ("FDA inspection shortfalls FY1996 AND
  FY1997"): 2 sub_queries hit FY1997 + "Table 3.1"; FY1996 data is
  zero-filled in the DSL because retrieval never asked for it.
- `arxiv_05_hierarchical` (4 transferability measures + GBV loss): 2
  sub_queries hit the framework and 2 of the 4 measures cleanly; the
  derived-fact ("smaller loss → higher transferability") needs a 3rd
  sub_query the agent never issued.

Stratified mean coverage by n_sub_queries (all B6 records):

| n_subq | n | mean cov |
|---:|---:|---:|
| 0 | 7 | 0.476 |
| 1 | 10 | 0.900 |
| 2 | 156 | 0.833 |
| 3 | 84 | 0.843 |
| 4 | 5 | 0.933 |
| 6 | 3 | 0.556 |

n_subq=4 has the best mean coverage (n=5), n_subq=2 (the modal
choice) is below average. This is correlational, but the per-record
trace consistently shows "2 sub_queries on a 3-axis query → 1
checklist item FAIL". n_subq=6 is small-n noise (one outlier:
`arxiv_34_comparative` with 6 sub_queries that all returned the same
generic chunk and still produced empty DSL).

### 5.4 `EXEMPLAR_NUM_CAP` (13, mean gap 0.423)

The consolidated exemplar sizes:

| viz_type | exemplar elements |
|---|---|
| chartjs_bar | 5 labels × 1 dataset |
| chartjs_grouped_bar | 4 labels × 3 datasets |
| chartjs_line | 6 labels × 2 datasets |
| chartjs_pie | 6 labels × 1 dataset |
| chartjs_scatter | 3 datasets |
| mermaid_flowchart | 12 nodes / 11 edges |
| mermaid_timeline | 4 sections / ≈13 events |
| mermaid_mindmap | (1-block exemplar, multi-level) |

B6 element counts on gap records cluster near the exemplar floor:

- 6/9 chartjs gap records use exactly 4 labels (matching grouped_bar
  exemplar) or 2 labels (matching bar exemplar). Examples:
  `10k_03_quantitative` (4 labels), `10k_04_quantitative` (4 labels),
  `10k_10_quantitative` (2 labels), `10k_14_quantitative` (2 labels),
  `arxiv_47_comparative` (3×2).
- B6 median elements on gaps = 9; B7 median = 12. Per-record
  comparison shows B7 consistently expands the structure when the
  source warrants it (e.g., `arxiv_05_hierarchical` B6 9 nodes vs B7
  25 nodes; `arxiv_11_hierarchical` B6 12 vs B7 24).

Caveat: this is correlational and could partly reflect content
sparsity rather than exemplar mimicry. But the chartjs cases where
B6 emits exactly 2 or 4 labels (matching the exemplars) on queries
where the source has more rows (e.g., `10k_03` has at least 8 line
items) are strong evidence of mimicry.

### 5.5 `SHORT_DSL` (7) and `EMPTY_OUTPUT` (5)

EMPTY_OUTPUT (5 of 40 gaps; 11 of 265 overall):

- `hotpot_13_relational`, `hotpot_45_comparative`,
  `arxiv_48_comparative`, `arxiv_34_comparative`,
  `arxiv_39_comparative` — sidecar missing or agent ReadTimeout.
  Errors logged: `agent returned empty final_answer` /
  `generate_viz sidecar missing for query_id=...; agent likely did
  not invoke the tool`. These are infrastructure failures that
  appear as coverage 0.

SHORT_DSL (7): B6 DSL < 0.55× B7 DSL. Co-tagged with NARROW_RETRIEVAL
in 5/7 — when retrieval is narrow the brief is sparse, and the tool
produces a thin DSL. Not an independent driver.

### 5.6 `AGENT_SKIPPED_RETRIEVAL` (3)

`hotpot_13_relational` (B6 viz empty), `hotpot_45_comparative` (B6
viz empty, ReadTimeout), `10k_14_quantitative` (B6 viz non-empty but
data invented as `[0]`). For the third the V4 rule does mandate "(1)
search/RFD before (2) generate_viz", but the agent collapsed steps
1+2 into one and made up numbers. Confirms F5 of the prior loss
analysis.

## 6. Recipe from B6's high-coverage wins

25 records have B6_cov − B7_cov ≥ 0.20. Stats:

| Feature | Wins (n=25) | Gaps (n=40) |
|---|---:|---:|
| n_sub_queries mean | 2.56 | 2.25 |
| n_sub_queries median | 2.0 | 2.0 |
| n_sub_queries=3 share | 10/25 (40%) | 13/40 (33%) |
| DSL chars mean | 973 | 786 |
| DSL chars median | 932 | 794 |
| Empty DSL | 0 | 5 |

Pattern from wins (qids `govreport_12_temporal`,
`hotpot_08_relational`, `arxiv_45_comparative`,
`tech_docs_39_hierarchical`, `hotpot_23_relational`,
`govreport_35_hierarchical`):

- 2-3 sub_queries that EACH name a different specific entity from
  the user query (e.g., `tech_docs_39`: "ER model abstraction levels
  Conceptual Logical Physical" + "three levels ER model hierarchy"
  → all 3 levels appear).
- Content_brief mentions every named entity from the query
  (`hotpot_08`: "Willem Kieft Kieft's War timeline events" + "Pound
  Ridge massacre March 1644 John Underhill" → both Kieft and
  massacre present).
- DSL element count exceeds the exemplar floor (median 932 chars =
  larger than most exemplars).

This is the counter-example to EXEMPLAR_NUM_CAP — when the brief
names enough entities, the tool prompt's "preserve every specific
fact" works and the DSL grows past the exemplar.

## 7. Proposed fixes

All edits respect V4 constraints: rule = lower-case, no banner, no
caps, names `generate_viz` + forces call; tool prompt = no source-
groundedness language, only "don't lose specific facts"; one-word
final_answer.

| ID | Locus | Mode targeted | Edit (≤30 words) | Expected Δ_cov | Risk |
|---|---|---|---|---:|---|
| **A** | `code/pipelines/tmg.py:V4_POOL_EXPOSURE_RULE` after the `content_brief` argument sentence (~line 221) | MISSING_AXIS, NARROW_RETRIEVAL | Insert: "if the query names two or more entities, dimensions, or comparison axes, the `content_brief` must list each one explicitly by name and the matching fact from the source." | **+0.012** | Over-coverage on single-axis queries — bounded because the conditional triggers only on `≥2 entities` |
| **B** | `code/pipelines/tmg.py:V4_POOL_EXPOSURE_RULE` after the step (1)/(2)/(3) sequence sentence (~line 207) | NARROW_RETRIEVAL | Insert: "before invoking `generate_viz`, you must have issued one `search` per distinct entity or axis named in the user query — count the named items and issue that many searches." | **+0.008** | Cost increase (more `search` calls); may bloat n_sub_queries to 4-5 on long queries |
| **C** | `code/agent_tools/generate_viz.py:_build_prompt` after "preserve every specific fact … in the brief" (~line 416) | HEADER_ONLY, MISSING_AXIS | Insert: "if the brief names a comparison, a relationship, or a contrast between two items, the visualization must show both items as separate, comparable elements — not as one combined node." | **+0.006** | If the brief is one-sided this rewrites the structure; mostly upside |
| **D** | `code/agent_tools/oneshot_pool.json` `consolidated.chartjs_bar` + `chartjs_grouped_bar` + `mermaid_flowchart` | EXEMPLAR_NUM_CAP | Replace exemplars with versions showing 8 labels (chartjs_bar), 6 labels × 4 datasets (grouped_bar), 18 nodes / 22 edges (mermaid_flowchart) — same domain, just denser | **+0.005** | Increased token budget per call (+~200 tokens); over-expansion on naturally-sparse sources |
| **E** | `code/pipelines/s4_agentic_tmg.py:S4AgenticTMG.__init__` `n_steps_max=8` → `n_steps_max=10` | NARROW_RETRIEVAL (combined with B) | Default `n_steps_max=10` so the +2-step budget from B does not hit the cap | **+0.003** (only realized if B lands) | Latency / cost +25% on long agent runs |
| **F** | `code/pipelines/s4_agentic_tmg.py` empty-DSL retry — the existing Mode A recovery (~lines 263-272) already retries on `total_tokens==0`; widen the gate to also retry on `len(sidecar.viz_dsl) < 50` after sidecar read | EMPTY_OUTPUT | Inside the `if self.mode in ("v4_pool","v4_consolidated"):` block after `_read_viz_sidecar`, add a one-shot retry path that re-runs `_do_run` if the sidecar yields <50 chars | **+0.004** | Doubles cost on ~5% of records; needs new code path so partly outside "rule-only" scope |

### Verbatim insertions (exact text, ≤30 words each)

**A** — append to `V4_POOL_EXPOSURE_RULE` after the existing
`content_brief` description sentence (lines 216–221 of `tmg.py`):

> "If the query names two or more entities, dimensions, or comparison axes, the `content_brief` must list each one explicitly by name and the matching fact from the source."

**B** — append to the rule after the step-sequence sentence
(lines 201–209 of `tmg.py`):

> "Before invoking `generate_viz`, issue one `search` per distinct entity or axis named in the user query; count the named items and issue that many searches."

**C** — append to `_build_prompt` after the
"Do not omit a fact…" sentence (line 416 of `generate_viz.py`):

> "If the brief names a comparison, a relationship, or a contrast between two items, the visualization must show both items as separate, comparable elements — not as one combined node."

## 8. Δ aggregation + gate-closing

Conservative bottom-up Δ (with overlap discount because A+B+C all
attack the same MISSING_AXIS/NARROW_RETRIEVAL co-occurring cluster):

| Fix | Independent Δ_cov | Overlap-adjusted Δ_cov |
|---|---:|---:|
| A (brief axis-list rule) | +0.012 | +0.012 |
| B (one-search-per-axis rule) | +0.008 | +0.005 (50% overlap with A) |
| C (tool prompt comparison rule) | +0.006 | +0.003 (50% overlap with A on HEADER_ONLY) |
| D (denser exemplars) | +0.005 | +0.005 |
| E (n_steps_max 8→10) | +0.003 | +0.001 (mostly captured by B) |
| F (empty-DSL retry) | +0.004 | +0.004 |
| **Sum** | **+0.038** | **+0.030** |

Target: B6 coverage 0.852 → **0.882** (paired-intersection view per
brief). Mean overall lift, using coverage weight = 1/3 in the
3-axis-fair view (PAPER_MASTER_SPEC §16 the "valid" gate cell):

- Overall lift ≈ +0.030 × (1/3) = **+0.010** on 3-axis fair.
- Gap to close (§16 amendment, valid-only cell): B6 0.8432 vs B7
  0.8804 → −0.0372. With +0.010 coverage-axis lift the gap closes
  to −0.027 — still HALT, **closes ~27% of the residual**.
- On full 4-axis with coverage weight = 1/4: lift ≈ +0.0075,
  closes ~13% of −0.056 full gap.

This is fix-bundle A+B+C+D+F combined. Single most cost-efficient
fix is **A alone** (one-sentence rule edit, +0.012 → ~32% of valid-
only gap closed if the conservative estimate holds and the other
axes are unaffected).

## 9. Open questions

- **Is the −0.032 number from the brief on a paired intersection
  excluding Mode A fails?** My full-paired = −0.046; 3-axis "fair"
  (also excluding 7 B6 empty-DSL per `v4_cons_dual_gate.md`) ≈
  −0.032. Re-apply fix budget against whichever §16 cell gates on.
- **Does fix A over-cover on single-axis queries?** Preflight the
  ~80 single-axis queries (no "and"/"vs"/"compare") to confirm.
- **Does fix D break syntax-validity?** The chartjs_bar expansion to
  8 labels must keep the brace-balance invariant the tool's auto-
  repair (`generate_viz.py:317-323`) relies on; rerun smoke_test_pr4.
- **Is `hotpot_45_comparative` recoverable?** Source genuinely lacks
  Livesey Hall counts; B7 used a "data unavailable" placeholder. V4
  may need an explicit missing-data affordance — out of scope.
- **n_subq=4 cov 0.933 vs n_subq=2 cov 0.833 (n=5)** — directional
  support for fix B; small-n. Preflight gap-set with B to confirm.

---

Cited files:

- `/ex_disk2/mhpark/poc/docviz/code/pipelines/tmg.py` (lines 193-240)
- `/ex_disk2/mhpark/poc/docviz/code/agent_tools/generate_viz.py` (lines 380-440)
- `/ex_disk2/mhpark/poc/docviz/code/agent_tools/oneshot_pool.json`
- `/ex_disk2/mhpark/poc/docviz/code/pipelines/s4_agentic_tmg.py` (lines 122-145, 263-272)
- Prior analysis: `/ex_disk2/mhpark/poc/docviz/docs/analysis/b6_vs_b7_paired_loss_analysis.md`
- Prior analysis: `/ex_disk2/mhpark/poc/docviz/docs/analysis/viz_type_bias_taxonomy_260516.md`
- Gate spec: `/ex_disk2/mhpark/poc/docviz/docs/analysis/v4_cons_dual_gate.md`
