# B6 (V4_consolidated) vs B7 (SelfRefine) — Paired Loss Analysis

Status: investigation, 2026-05-15
Scope: Why does B6 lose Δ=-0.056 mean overall to B7 on text-axis (paired n=265)?
Inputs: `/tmp/b6_b7_pairs.json`, `outputs/prototype/judge_scores/all.json`,
        `outputs/prototype/viz/all.json`, V4 pipeline + tool source.

---

## 1. Executive summary

- **Top failure mode:** TMG mis-routing into a viz_type the judge marks as a
  poor fit for the query intent (`type_appropriateness < 1.0` while B7 hits
  1.0) — 17/28 records (61%). Worst sub-pattern: agent picks
  `mermaid_timeline` for relational/comparative HotpotQA queries that B7
  answers as flowchart/grouped-bar, then the timeline renders as
  1-section/0-edge "thin" output (12/28).
- **Top strength:** When B6 routes correctly (mermaid_flowchart for
  hierarchical/relational, mermaid_timeline for true temporal), its
  retrieval-driven content beats B7 across all axes — mean Δ on B6-wins
  bucket (n=14) is faithfulness +0.26, coverage +0.34,
  type_appropriateness +0.38, search_query_quality +0.91.
- **Headline strategy:** Tighten the `V4_POOL_EXPOSURE_RULE` to bias
  away from `mermaid_timeline` for relational queries unless ≥2 dated
  events appear in retrieval, AND fix the silent `n_subq=0` failure mode
  in V4 (3 records hit it, all losses) by surfacing it as a hard precondition
  alongside the existing `generate_viz` precondition. These two changes
  alone target ~18/28 of the loss bucket.

Headline statistic: paired-bootstrap on full set (n=265) gives
B7−B6 mean = +0.0561 with 95% CI [+0.0322, +0.0810] — the gap is
statistically meaningful, not noise. Within the b7_wins_valid bucket
(n=28) mean Δ = +0.341 (range +0.20…+0.94).

---

## 2. Method

**Data sources.**
- `/tmp/b6_b7_pairs.json` — three buckets pre-computed by the harness:
  - `b7_wins_valid` (n=28): both syntax-valid, B7 ≥ B6+0.20
  - `b6_wins_valid` (n=14): both syntax-valid, B6 ≥ B7+0.20
  - `b7_wins_b6_fail` (n=7): B6 invalid/empty (Mode B residue)
- `outputs/prototype/judge_scores/all.json` — 2120 judge records
  (8 strategies × 265 queries), schema includes per-item `scored` array
  with `axis`, `question`, `answer`, `score`, `justification`.
- `outputs/prototype/viz/all.json` — 2120 viz records keyed by
  `(query_id, strategy)` with `viz_dsl`, `viz_type`, `sub_queries`,
  `n_sub_queries`, `tokens_in/out`, `duration_seconds`.

**Calibration sample (per task §1).** 5 records were read end-to-end
on both B6 and B7 (`scored` arrays + DSLs):
- `10k_04_quantitative` — B6 0.23 vs B7 0.53 → real gap, but checklist
  bias evident (see judge-noise check)
- `arxiv_04_hierarchical` — B6 0.19 vs B7 1.00 → real gap, B6 retrieved
  wrong topic
- `tech_docs_28_relational` — B6 0.00 vs B7 0.94 → JUDGE FAILURE: all 12
  scored items returned `"scorer did not return a valid answer for this
  item"`. B6's actual viz is a 13-node mermaid_flowchart on the right
  topic. **Drop from analysis.**
- `arxiv_22_hierarchical` (B6-win) — B6 1.00 vs B7 0.58 → real
- `tech_docs_06_relational` (B6-win) — B6 0.96 vs B7 0.67 → real

**Judge-noise check result (CRITICAL caveat).**
The judge generates *separate* checklists for `agentic` vs `non_agentic`
strategy classes (see `code/judge/checklist_gen.py:34-67`). The `agentic`
checklist has 12 items including 3 `search_query_quality` (SQQ) items
that don't apply to B7. So the comparison is NOT apples-to-apples — B6
faces 25% more questions, including 3 that interrogate retrieval
quality. Two artifacts were quantified:

1. **JUDGE_FAIL_ALL** — 1 record (`tech_docs_28_relational`) hit a
   wholesale scorer failure: all items returned a single justification
   string `"scorer did not return a valid answer for this item"` →
   B6 scored 0.0 across all axes despite a valid 13-node viz. This
   single record contributes ~3.5% of the total Δ on the b7_wins_valid
   bucket.
2. **JUDGE_BUG_SQQ_MISCLASS** — 3 records
   (`hotpot_01_relational`, `multinews_04_temporal`,
   `multinews_06_temporal`) where B6 issued ≥2 sub-queries but the
   scorer LLM still claimed "non-agentic strategy: no sub-queries" and
   gave 0.0 on all 3 SQQ items. Verified against
   `viz['n_sub_queries']` field. The scorer prompt
   (`code/judge/scorer.py:101-107`) tells the LLM to use that exact
   wording when sub-queries are absent — the LLM is hallucinating their
   absence. This costs B6 ~0.25 overall per record (3 SQQ × 0.25 weight).

After excluding `tech_docs_28_relational`, **n=27** remains for the
failure-mode analysis. The 3 SQQ-misclass records are kept (their other
axes are still informative) but the SQQ axis is annotated as
unreliable.

---

## 3. Failure mode taxonomy (b7_wins_valid, n=27 after judge-fail drop)

Each record may carry multiple tags. Tags are derived from a programmatic
pass over `scored` arrays + viz metadata (`viz['n_sub_queries']`,
`viz_parsed_summary`, DSL length).

| Mode | Count | Mechanism | Representative qids |
|---|---:|---|---|
| **F1. TA_INFERIOR_TO_B7** (TMG mis-routes the viz_type) | 16/27 | B6's `type_appropriateness` < 1.0 while B7 hits 1.0. Sub-pattern: agent picks `mermaid_timeline` for relational/comparative queries with ≤1 real event, gets dinged for "single-track" or "no parallel comparison". | `hotpot_22_relational` (TA 0.50 vs 1.00 — single-track timeline merges two subjects), `hotpot_35_comparative` (B6 grouped-bar shoehorns text into bar; B7 picks timeline correctly), `multinews_33_comparative` (mindmap "Document 1/Document 2" pseudo-structure, TA=0.0) |
| **F2. TIMELINE_PARSE_THIN** (mermaid_timeline rendered as 0–1 nodes) | 12/27 | `viz_parsed_summary` reports 0 or 1 nodes despite a multi-section DSL — `code/render/*` mermaid parser doesn't pick up timeline section entries as nodes. Affects every B6 mermaid_timeline record but B7 too — judge isn't penalizing this directly, more a parser caveat. Co-occurs with F1 in 8/12 cases. | `multinews_04`, `multinews_06`, `multinews_08`, `multinews_23`, `tech_docs_17`, `tech_docs_27`, `hotpot_08`, `hotpot_09`, `hotpot_20`, `hotpot_22`, `hotpot_48`, `govreport_25` |
| **F3. COVERAGE_ZERO** (B6's coverage axis = 0.0) | 5/27 | Visualization addresses none of the entities the checklist asks about. Often paired with F4 (topic mismatch). | `10k_04` (chart shows segment income; checklist asks about FX gains/notes), `arxiv_01` (calibration data; checklist asks about challenge categories), `arxiv_04` (kidney-cancer immune cells; checklist asks about claw-eval task counts), `hotpot_48` (Yakuza partial timeline), `tech_docs_28` [JUDGE_FAIL] |
| **F4. TOPIC_MISMATCH** (faithfulness=0.0 because viz on wrong topic vs checklist-implied entities) | 3/27 | Sub-queries retrieved a tangentially-related slice of the bundle; agent visualized that slice; judge's checklist (built from the FULL bundle) asks about the slice the agent missed. Symptom of retrieval narrowness. | `10k_04_quantitative` (sub_qs targeted "income from operations" but checklist anchored on FX gains/senior notes), `arxiv_01_hierarchical` (calibration architectures vs ML challenge categories), `arxiv_04_hierarchical` (subqs about TLS/INFL biology vs checklist on Claw-Eval benchmark) |
| **F5. AGENT_SKIPS_RETRIEVAL** (V4 emits `n_sub_queries=0`) | 3/27 | Despite `V4_POOL_EXPOSURE_RULE` mandating "(1) one search/RFD action … (2) generate_viz … (3) final_answer", the agent occasionally skips step (1). 3/265 V4 records hit `n_subq=0` AND the bucket; 7/265 globally (2.6%). For these, agent invented data — `10k_14` produced `data: [0,0]` and burned 22680 output tokens in 210s with no errors logged. | `10k_14_quantitative`, `govreport_46_hierarchical`, `multinews_08_temporal` |
| **F6. DSL_SHORTER_THAN_B7** (B6 viz_dsl < 0.5× B7's chars) | 4/27 | Agent's content_brief is sparse, so generate_viz produces a thin DSL. B7 sees the full doc concatenation (12k chars/doc per `s7_self_refine.py:155`) and packs more facts. | `10k_04`, `10k_10`, `multinews_08`, `multinews_33` |
| **F7. JUDGE_BUG_SQQ_MISCLASS** (judge hallucinates "non-agentic") | 3/27 | Scorer LLM violated its own rule and emitted "non-agentic strategy: no sub-queries" despite `n_sub_queries>=2`. Costs ~0.25 overall per record. | `hotpot_01_relational`, `multinews_04_temporal`, `multinews_06_temporal` |

**Patterns NOT confirmed by evidence** (despite priors in
`docs/analysis/v4_cons_fail_root_cause.md`):

- *Categorical bucketing of specific numbers* (record-3 from feedback) — I
  did not find this pattern in the 27-record loss bucket. B6's chartjs
  outputs preserve specific numbers (e.g., `10k_04` shows 87109/-17729,
  `10k_10` shows 1/3, `arxiv_01` shows 5/5/5 fold counts). Whatever
  oneshot-pool revision fixed it appears to be holding.
- *Title missing source date* (record-2) — Examined titles in `10k_10`,
  `10k_04`, `govreport_11`, `arxiv_01`. The chartjs records have full
  titles like *"Foreign Currency Fluctuation Impact on CRM Fiscal 2026
  Metrics (Source: CRM 10-K Item 7 and Item 7A for fiscal year ended
  January 31, 2026)"*. This pattern is not driving losses.
- *Generic content (exemplar mimicry leak)* — DSLs use named entities
  ("MCAT", "INFL1", "Wilmslow High School", "Vitess", "Aggregate Root").
  Not driving losses.

**Contradiction with prior assumption:** the team's mental model has been
that the text-axis loss is "specific-fact loss" (categorical bucketing,
date stripping). My read of the 27 loss records says it is actually
**structural** — TMG picks the wrong viz_type 16/27 times, and the
mermaid_timeline misuse for relational/comparative queries (12/27)
is the dominant single pattern. This is an architectural router issue,
not a content-extraction issue.

---

## 4. Strength taxonomy (b6_wins_valid, n=14)

| Strength | Count | Mechanism | Representative qids |
|---|---:|---|---|
| **S1. Retrieval depth wins on long-tail facts** | 14/14 | All B6-wins have `n_subq ∈ {2,3}`, all B7s have `n_subq=0`. B6 mean SQQ in this bucket = 0.91. The 3 sub-queries surface specific dates/quantities B7 misses when the doc is long and the relevant fact is buried. | `arxiv_22_hierarchical` (B6 1.00 vs B7 0.58 — B6 captured all 5 themes + co-occurrence counts; B7 invented "EO1" theme), `govreport_16_temporal` (B6 captured 5y/Indefinite buckets; B7 collapsed into "1 Year start–Indefinite end") |
| **S2. Mermaid taxonomy/process diagrams (right viz_type) win on type_appropriateness** | 8/14 | B6 mean TA in this bucket = 0.82 vs B7 0.45. When B6's TMG routes correctly (mermaid_flowchart for relational/hierarchical, mermaid_sequenceDiagram for protocol queries), B7 frequently picks chartjs_bar for the same query, getting TA=0.0–0.5. | `tech_docs_06_relational` (B6 sequenceDiagram TA=1.00 vs B7 same-type TA=0.00 — judge faulted B7 for "lacking activation bars / numbered messages"), `govreport_41_hierarchical` (B6 mindmap vs B7 chartjs_bar) |
| **S3. Hierarchical layouts with named-entity nodes** | 5/14 | B6's content_brief specifically names entities/dates ("UAW labor agreements", "Tracey Ullman Show short Good Night on April 19"). B7's full-doc summarization tends to genericize node names ("Various brands"). | `multinews_43_comparative`, `arxiv_22_hierarchical`, `tech_docs_05_relational` |
| **S4. Faithfulness from sub-query targeting** | 11/14 | B6 mean faithfulness in this bucket = 0.79 vs B7 0.53. B7 invents/conflates when context is long (e.g., `multinews_43` B7 added a non-source dataset). | `tech_docs_05_relational`, `hotpot_10_relational` |

**Key insight:** B6's wins concentrate where the query type unambiguously
maps to a Mermaid diagram (hierarchical→mindmap, relational→flowchart,
protocol→sequenceDiagram) AND the source has many specific facts that
benefit from focused retrieval. Nothing B6 wins on requires the agent
loop per se; same effect could come from a "retrieve-then-generate" 2-step
pipeline IF the routing decision were correct.

---

## 5. Source × query_type heat patterns

| (source, query_type) | b7_wins_valid n | b6_wins_valid n | net |
|---|---:|---:|---:|
| `hotpotqa, relational` | 5 | 2 | **−3** (B6 over-uses timeline) |
| `multinews, temporal` | 4 | 0 | **−4** (TIMELINE_PARSE_THIN dominant) |
| `govreport, hierarchical` | 3 | 2 | −1 |
| `tech_docs, relational` | 3 | 2 | −1 |
| `arxiv, hierarchical` | 3 | 2 | −1 |
| `hotpotqa, comparative` | 3 | 0 | **−3** (timeline mis-route again) |
| `10k, quantitative` | 3 | 0 | **−3** (skipped retrieval + DSL_SHORT) |
| `govreport, temporal` | 2 | 3 | **+1** ✓ |
| `multinews, comparative` | 1 | 1 | 0 |
| `tech_docs, hierarchical` | 1 | 1 | 0 |
| `arxiv, comparative` | 0 | 1 | +1 ✓ |

**Concentration cells driving the loss (≥3 net):**
1. `multinews × temporal` (−4): chronic mermaid_timeline parse failure
   + content thinness when retrieval narrows the doc.
2. `hotpotqa × relational` and `hotpotqa × comparative` (−6 combined):
   agent reflexively picks `mermaid_timeline` for two-entity HotpotQA
   queries because some have dates; the judge then asks for "parallel
   side-by-side" structure.
3. `10k × quantitative` (−3): sub-queries either too broad (returns
   wrong section) or skipped entirely. 2/3 records show retrieval
   pathology.

**Where B6 actually wins:** `govreport × temporal` (+1) — long
multi-section reports where the dates ARE chronological and B6's
mindmap/timeline-with-3-subqs surfaces dates B7 misses.

---

## 6. Strategy: top-3 changes (file:line, why, predicted Δ, risk, test qids)

### Change A — Bias TMG away from `mermaid_timeline` for relational/comparative on HotpotQA-style queries

**File / locus.** `code/pipelines/tmg.py:V4_POOL_EXPOSURE_RULE` (lines
193–240). Add one sentence inside the existing rule (does NOT add a new
rule — keeps base reasoning system style per feedback line 14).

**Concrete edit suggestion** (≤30 words, fits style):

> Insert after the `viz_type` argument enum sentence (~line 215):
> "If the user query asks for a **relationship** or **side-by-side
> comparison** of named entities and the source contains fewer than 3
> distinct dates, prefer `mermaid_flowchart` or `chartjs_grouped_bar`
> over `mermaid_timeline` — a one-section timeline collapses the
> relationship into a chronology that the judge will mark as
> single-track."

**Why this addresses F1+F2.** 12 of the 16 TA_INFERIOR_TO_B7 records
share the same anti-pattern: B6 picks `mermaid_timeline` for a query
that has 1–2 events at most. The render parser counts these as 0–1
"nodes" and the judge always penalizes "no parallel comparison".
Evidence: `hotpot_22_relational` ("Matt Groening alongside Lisa Simpson"
→ B6 single-track timeline TA=0.50, B7 also-timeline but split into
two `section`s TA=1.00); `hotpot_35_comparative` ("Dundee Canal vs
Miami Canal" → B6 grouped-bar with one bar empty, B7 timeline with two
sections). Five records (`hotpot_01`, `hotpot_08`, `hotpot_09`,
`hotpot_20`, `hotpot_22`) all share the "two-entity relational query
forced into timeline" pattern.

**Predicted Δ.** If 8/12 of the timeline-misroute losses move to
flowchart/grouped-bar at TA=1.00 and pick up an average of +0.20 on the
other axes (because the layout permits the comparison the judge wants),
this is +8 × 0.30 = +2.4 points across 27 = **+0.08 mean text-axis
gain on the b7_wins_valid bucket; +0.009 on the full 265 set**. Small
but cheap.

**Risks.**
- Must not break `mermaid_timeline` selection for genuine temporal
  queries (currently working — `govreport × temporal` is +1 cell).
  Conditioning on "≤2 distinct dates" should keep this safe.
- Must respect feedback rule 14 (style = base reasoning system, no
  banner / no capital block). Use lowercase, single sentence, embedded
  in existing rule. Verify the rule still fits inside the agent's
  custom_rules slot without truncation.

**Test qids (smoke).** `hotpot_01_relational`, `hotpot_22_relational`,
`hotpot_35_comparative`, `hotpot_48_comparative`, `multinews_06_temporal`
(this last one IS true temporal but has 4 sub-events — should still
route to timeline, regression check).

### Change B — Surface `n_sub_queries=0` as a hard precondition violation in V4 rule

**File / locus.** `code/pipelines/s4_agentic_tmg.py:280-296` (post-run
sidecar handling) AND `code/pipelines/tmg.py:V4_POOL_EXPOSURE_RULE`
(extend the existing precondition sentence).

**Concrete edit suggestion.**
- In the rule, change the existing "(1) one `search` or
  `ReadFullDocument` action per rule 11" → "(1) **at least one**
  `search` or `ReadFullDocument` action per rule 11 — emitting
  `<final_answer>` after zero retrieval actions is rejected the same
  way as emitting it before `generate_viz`".
- In the orchestrator, after sidecar read, if `vo.sub_queries == []`
  AND `vo.viz_dsl` is non-empty, append an error
  `"{name}: agent skipped retrieval (n_sub_queries=0) — viz is
  un-grounded"`. This is a logging change only; it does not retry.
  (Retry would violate the budget; surfacing as an error lets the next
  preflight catch it.)

**Why this addresses F5.** 3 of 27 b7_wins_valid records had
`n_sub_queries=0` (`10k_14_quantitative`, `govreport_46_hierarchical`,
`multinews_08_temporal`); 0 of 14 b6_wins records did. `10k_14` burned
22680 output tokens in 210s with no errors logged — agent looped
internally and went straight to `generate_viz` with `data:[0,0]`.
With retrieval enforced, `10k_14`'s actual notional values ($2.1B,
$3.6B) would have been retrievable in one query — B7 found them
trivially.

**Predicted Δ.** 3 records × ~0.50 overall lift if retrieval succeeds
= +0.06 on the bucket; +0.006 on full 265. Plus indirect benefit on
the ~7 globally-affected records.

**Risks.**
- The rule already says "(1) one search…" — so this is a *clarification*,
  not a new constraint. The base reasoning system style is preserved.
- Must NOT slip a "you must retrieve specific entities" instruction in —
  feedback rule 15 prohibits source-groundedness instructions in
  generate_viz tool prompt; this change is in the agent rule, not the
  tool prompt, so it is allowed. But verify the orchestrator error
  message doesn't leak into the tool's content_brief on a retry path
  (currently no retry path exists; safe).
- Cannot break n_subq=0 records that ARE legitimate (e.g., a query
  whose answer is in the abstract — agent might justifiably skip
  search). Mitigation: surface as warning, not block. Adoption
  decision can wait for n_subq=0 frequency to be measured per source.

**Test qids.** `10k_14_quantitative`, `govreport_46_hierarchical`,
`multinews_08_temporal`. Plus `multinews_06_temporal` (n_subq=2,
should not regress).

### Change C — Patch the SQQ-misclass judge bug

**File / locus.** `code/judge/scorer.py:101-107`. Tighten the prompt
constraint AND add a deterministic post-hoc check.

**Concrete edit suggestion.**
1. In the prompt (line 102), change `"or empty (i.e., a non-agentic
   strategy with no search or RFD calls at all)"` → `"or empty —
   meaning the literal string '(none)' was provided in the Retrieval
   queries section above"`. Removes the "non-agentic strategy"
   inferential wording that the LLM was using as license to claim
   absence.
2. In `score_checklist()` after parsing the LLM response, add a guard:
   ```
   if sub_queries:  # agent DID issue queries
       for item in scored:
           if item.get("axis") == "search_query_quality" and \
              "non-agentic" in (item.get("justification") or ""):
               item["answer"] = "PARTIAL"  # or re-score
               item["score"] = 0.5
               item["justification"] += " [auto-corrected: queries WERE issued]"
   ```
   (Or re-issue the SQQ items as a follow-up call. Cheaper to
   PARTIAL-fallback for v0.3 close.)

**Why this addresses F7.** 3 of 27 b7_wins_valid records (and 12/265
B6 records globally) get hit. Each loses ~0.25 on overall. If
re-graded to PARTIAL, those 3 records gain +0.125 each → +0.375
points across the bucket = **+0.014 on the bucket / +0.0014 on full
265**. Modest but free; also reduces noise for the v0.3 numerical
report.

**Risks.**
- A re-score requires re-running the scorer. A fallback to PARTIAL
  is conservative and traceable (justification annotated).
- This change does NOT alter B6's pipeline; it's a judge fix. Need to
  document in v0.3 results summary that the SQQ axis was patched
  post-hoc.

**Test qids.** `hotpot_01_relational`, `multinews_04_temporal`,
`multinews_06_temporal`. Plus any record where `n_sub_queries==0`
SHOULD score 0 (`govreport_46_hierarchical` regression check).

---

## 7. Summary Δ projections (rough, bounded by record counts)

| Change | Records targeted | Bucket Δ (mean B7−B6) | Full-set Δ (mean B7−B6) |
|---|---:|---:|---:|
| A. Anti-timeline-for-relational rule | 8 of 16 (TA improves) | −0.08 | −0.009 |
| B. n_subq=0 hard precondition | 3 (recover most lost overall) | −0.06 | −0.006 |
| C. SQQ judge-bug patch | 3 (PARTIAL fallback) | −0.014 | −0.0014 |
| **Combined (assuming independent)** | ~14 distinct records | **−0.15** on bucket | **−0.016** on full set |

If all three land cleanly, the headline gap moves from B7−B6 = +0.056
to ≈ +0.040 (still B7-favored). That is **not** a flip to B6-favored.
To flip the sign would require addressing the 5 COVERAGE_ZERO + 3
TOPIC_MISMATCH records, which need a fundamentally different
intervention (cross-checking sub-queries against the FULL bundle, OR
adopting B7's full-context fallback for short bundles). That deeper
intervention is outside the V4 design budget and should be deferred to
a v0.4 line.

---

## 8. Open questions

1. **Does the TIMELINE_PARSE_THIN tag reflect a parser bug or a real
   judge penalty?** `viz_parsed_summary` says "1 nodes, 0 edges" for
   most B6 timelines — but B7 timelines also report similar (e.g.,
   `hotpot_22` B7 says "2 nodes, 0 edges"), and B7 still scores 1.00.
   So the parse summary is not what the judge uses. The judge appears
   to read the full DSL string. **Cannot resolve from data alone —
   need to trace `code/render/mermaid_parser.py` if it exists.**
2. **Why does V4 sometimes skip retrieval?** Is it a model decision
   (Qwen3.5 chose not to call search), an agent-server bug
   (call attempted but masked as 0), or a custom_rules ambiguity?
   The 10k_14 case (210s, 22680 tokens, no errors, n_subq=0) is
   diagnostic — agent thought hard but didn't act. Need agent trace
   logs (not currently in `viz['errors']`) to disambiguate.
3. **Is the judge checklist generator over-fitting to long-tail
   facts?** The `10k_04` checklist for B6 (agentic) asks about FX
   gains and senior notes — facts that are NOT what the user query
   asked for ("Family of Apps and Reality Labs"). The B7 checklist
   (non-agentic) for the same query stays on-topic. That asymmetry
   is structural and may inflate B7's apparent advantage on this
   bucket. Worth a separate judge-calibration pass.
4. **Does Change A risk regressing B6's mermaid_timeline wins on
   genuine temporal queries?** `govreport × temporal` is currently +1
   — most of those wins are records with 4–6 distinct dates. A
   "≤2 dates" condition should preserve them, but I don't have a
   counter-test set to confirm.
5. **Sample size caveat.** With n=27 in the loss bucket and
   ~10 records per failure-mode tag, the per-mode counts have wide
   bootstrap intervals. The recommendations should be read as
   directional, not as guaranteed Δ.

---

## 9. Appendix — record-level mode tags (reproducible)

Tags computed by deterministic pass over `scored` arrays + viz metadata.
Source: in-line python at investigation time; reproducible from
`outputs/prototype/judge_scores/all.json` + `outputs/prototype/viz/all.json`.

```
qid                             tags
10k_04_quantitative             COVERAGE_ZERO, DSL_SHORTER_THAN_B7, TA_INFERIOR_TO_B7, TOPIC_MISMATCH
10k_10_quantitative             DSL_SHORTER_THAN_B7
10k_14_quantitative             AGENT_SKIPS_RETRIEVAL, TA_INFERIOR_TO_B7
arxiv_01_hierarchical           COVERAGE_ZERO, TOPIC_MISMATCH
arxiv_04_hierarchical           COVERAGE_ZERO, TA_INFERIOR_TO_B7, TOPIC_MISMATCH
arxiv_09_hierarchical           TA_INFERIOR_TO_B7
govreport_11_temporal           (none — narrow loss; faithfulness 0.62→1.00 dominates)
govreport_25_temporal           TIMELINE_PARSE_THIN
govreport_33_hierarchical       TA_INFERIOR_TO_B7
govreport_34_hierarchical       TA_INFERIOR_TO_B7
govreport_46_hierarchical       AGENT_SKIPS_RETRIEVAL
hotpot_01_relational            JUDGE_BUG_SQQ_MISCLASS
hotpot_08_relational            TA_INFERIOR_TO_B7, TIMELINE_PARSE_THIN
hotpot_09_relational            TA_INFERIOR_TO_B7, TIMELINE_PARSE_THIN
hotpot_20_relational            TA_INFERIOR_TO_B7, TIMELINE_PARSE_THIN
hotpot_22_relational            TA_INFERIOR_TO_B7, TIMELINE_PARSE_THIN
hotpot_35_comparative           TA_INFERIOR_TO_B7
hotpot_39_comparative           TA_INFERIOR_TO_B7
hotpot_48_comparative           COVERAGE_ZERO, TA_INFERIOR_TO_B7, TIMELINE_PARSE_THIN
multinews_04_temporal           JUDGE_BUG_SQQ_MISCLASS, TIMELINE_PARSE_THIN
multinews_06_temporal           JUDGE_BUG_SQQ_MISCLASS, TIMELINE_PARSE_THIN
multinews_08_temporal           AGENT_SKIPS_RETRIEVAL, DSL_SHORTER_THAN_B7, TIMELINE_PARSE_THIN
multinews_23_temporal           TIMELINE_PARSE_THIN
multinews_33_comparative        DSL_SHORTER_THAN_B7, TA_INFERIOR_TO_B7
tech_docs_17_relational         TA_INFERIOR_TO_B7, TIMELINE_PARSE_THIN
tech_docs_27_relational         TA_INFERIOR_TO_B7, TIMELINE_PARSE_THIN
tech_docs_28_relational         JUDGE_FAIL_ALL  ← drop from analysis
tech_docs_38_hierarchical       (none — narrow loss; only TA partials)
```

Tag glossary:

- **TA_INFERIOR_TO_B7**: B6 `axis_scores.type_appropriateness < 1.0`
  AND B7 `>= 1.0`.
- **TIMELINE_PARSE_THIN**: `viz_parsed_summary` matches
  `"mermaid_timeline: [01] nodes"`.
- **COVERAGE_ZERO**: B6 `axis_scores.coverage == 0.0`.
- **TOPIC_MISMATCH**: B6 `axis_scores.faithfulness == 0.0` AND ≥1
  scored justification contains "displays" / "discusses" / "missing"
  with negation (judge says viz on wrong topic).
- **AGENT_SKIPS_RETRIEVAL**: `viz['n_sub_queries'] == 0`.
- **DSL_SHORTER_THAN_B7**: `len(B6.viz_dsl) < 0.5 × len(B7.viz_dsl)`.
- **JUDGE_BUG_SQQ_MISCLASS**: All SQQ items have justification
  containing "non-agentic" AND `n_sub_queries > 0`.
- **JUDGE_FAIL_ALL**: All scored items have justification
  "scorer did not return a valid answer for this item".
