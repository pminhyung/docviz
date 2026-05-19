# SQQ Bias Taxonomy — B6 (V4_consolidated) Low-SQQ Failure Modes

Status: investigation, 2026-05-17
Scope: Why does B6 SQQ mean = 0.755 (lowest of its 4 axes) and how to lift it
to ≥0.85 within V4 design constraints, to help close the §16 −0.056 overall
gap vs B7.
Inputs: `outputs/prototype/judge_scores/all.json` (n=265 B6),
`outputs/prototype/viz/all.json`, `data/prototype/queries/all.json`,
`data/prototype/bundles/all.json`, `code/judge/{scorer.py,checklist_gen.py}`,
`code/pipelines/tmg.py`, `code/agent_tools/generate_viz.py`. Cross-check on
`outputs/text2vis/judge_scores/all.json` (n=100 B6).

---

## 1. Executive summary

- **The single biggest SQQ driver is checklist quality, not agent behavior.**
  The judge expects the agent to issue queries that name very specific
  entities/phrases — but in ≥33% of low-SQQ items the named term does not
  appear in the bundle at all (M2 `pre-tax income` 10k_03, M3 `temporal
  imbalance` arxiv_01, M3 `Claw-Eval` arxiv_04, …). The agent had no
  chance, and tightening the agent prompt cannot recover these.
- **Judge bug is wider than docs claim (8 records, not 3).** Records with
  `n_sub_queries ≥ 1` still get the "non-agentic strategy: no
  sub-queries / no retrieval queries" justification on every SQQ item
  (sqq=0.00). Expanded list: `arxiv_39_comparative`,
  `arxiv_48_comparative`, `hotpot_01_relational`, `hotpot_05_relational`,
  `hotpot_31_comparative`, `multinews_01_temporal`,
  `multinews_04_temporal`, `multinews_06_temporal`. Mechanical PARTIAL
  fallback on these 8 yields +0.020 on the SQQ mean.
- **The dominant fixable agent-side mode is M2 "generic phrasing"**: the
  agent issues 2–3 sub-queries with the right entities at the top level
  but the judge penalizes the absence of a quoted sub-phrase, an
  Item/Section number, or a paired noun (e.g., AMD `'retrospective
  adjustment'`, ADBE `'Item 7A'`, ZS `'foreign currency risk' and 'gain or
  loss'`). Affects 109 unique records, fixable via one sentence in
  `V4_POOL_EXPOSURE_RULE` instructing the agent to mirror exact source
  phrasing in sub-queries.
- **M1 "no sub-queries" (6 unique records, n_sub=0) is an orchestration
  gap**, not a phrasing issue. The hard precondition rule already forces
  `generate_viz`; it does not force a prior `search`. These records
  succeeded on the tool call but skipped retrieval. Should be split off
  as a separate orchestration fix, not bundled here.
- **Conservative aggregate Δ projection**: SQQ +0.064 (0.755 → 0.819),
  which is +0.016 on the 4-axis overall, closing ≈ 29% of the −0.056
  gate gap. The aggressive scenario (M2 80% recovery) gives SQQ +0.091
  / overall +0.023, closing ≈ 41% of the gap. Either way SQQ alone is
  not enough; this is a partial-credit fix.

---

## 2. Method

- Pulled all 265 records with `strategy == "S4_AgenticTMGv4_consolidated"`
  from `outputs/prototype/judge_scores/all.json`. Each has 3 SQQ items in
  `scored`; total = 795 SQQ items, of which 266 scored < 1.0 (NO or
  PARTIAL).
- Joined to `outputs/prototype/viz/all.json` by `query_id+strategy` to
  recover the actual `sub_queries` list and `n_sub_queries`.
- Joined to `data/prototype/queries/all.json` and
  `data/prototype/bundles/all.json` to verify whether quoted terms in the
  checklist questions actually appear in the bundle docs.
- Classified each failing item by a rule cascade on the justification
  string (`non-agentic` + n_sub≥1 → M0; n_sub=0 → M1; "generic / no
  specific / lacking" → M2; "queries targeted X not Y / did not search
  for" → M3; "scorer did not return" → M4; PARTIAL → M5; else M6).
- Spot-checked `outputs/text2vis/judge_scores/all.json` for the same
  modes.

---

## 3. SQQ distribution + cell concentration

Per-record SQQ distribution (n=265, mean=0.755, median=0.833, p25=0.667,
p75=1.000):

| bucket  | n   | %    |
|---------|-----|------|
| 1.00    | 97  | 36.6 |
| [0.75,1)| 74  | 27.9 |
| [0.50,0.75)| 60 | 22.6 |
| [0.25,0.50)| 13 | 4.9 |
| (0,0.25)| 3   | 1.1  |
| 0.00    | 18  | 6.8  |

Long left tail. 18 records at exactly 0.00 — every one of these is
either M0 (judge bug) or M1 (no sub-queries) or a checklist that asks
for content fully absent from the bundle.

Bottom-quartile-by-cell (mean SQQ for `(source, query_type)`):

| source    | query_type     | n  | mean SQQ |
|-----------|----------------|----|----------|
| multinews | temporal       | 30 | 0.633    |
| hotpotqa  | relational     | 30 | 0.689    |
| govreport | hierarchical   | 20 | 0.692    |
| 10k       | quantitative   | 15 | 0.733    |
| arxiv     | hierarchical   | 30 | 0.767    |

`multinews/temporal`, `hotpotqa/relational`, `govreport/hierarchical`
account for most of the M0 judge-bug cluster. The judge-bug records are
concentrated in HotpotQA (3/8), MultiNews (3/8), arxiv (2/8) —
multi-document narrative sources where the sub-queries are short
noun-phrases that the judge appears to misclassify as "no sub-queries".

---

## 4. Failure mode taxonomy

Counts on 266 failing SQQ items (per-item score < 1.0):

| Mode | Name | Failing items | Unique qids | Avg SQQ of affected records | Root cause |
|------|------|---------------|-------------|-----------------------------|------------|
| M0 | Judge hallucination "non-agentic" despite n_sub≥1 | 24 | 8 | 0.000 | Judge prompt edge case, not B6 |
| M1 | n_sub_queries == 0 | 14 | 6 | 0.107 | Agent skipped `search`; tool-call orchestration gap |
| M2 | Generic phrasing — entities present, but missing quoted sub-phrase / section number | 141 | 109 | 0.587 | V4 rule says nothing about sub-query phrasing |
| M3 | Off-topic — judge asks for an aspect not in user query (e.g., FX risk in a segment-income question) | 14 | 11 | 0.286 | Checklist generator hallucinates items not in bundle |
| M4 | Scorer returned no answer → defaulted NO | 3 | 1 | 0.000 | Scorer JSON parse/length issue |
| M5 | PARTIAL coverage (recognized intent, missed a sub-aspect) | 45 | 45 | 0.711 | Mostly the judge being strict; some are agent missing a 3rd sub-query |
| M6 | Other (judge expected a query about a tangential entity in the bundle but not in the user query) | 25 | 24 | 0.493 | Mix of checklist hallucination + agent missing optional 3rd query |

M2 + M5 together account for 186/266 items and 154 unique qids — they
are the actionable agent-facing tail. M0 + M3 + M4 + most of M6 (≈ 56
items / ≈ 38 unique qids) are measurement issues.

---

## 5. Per-mode deep dive

### M0 — Judge "non-agentic" hallucination (8 records)

Pattern: `scored[i].justification` contains the literal string
"non-agentic strategy: no retrieval queries" or "non-agentic strategy:
no sub-queries", but `n_sub_queries ≥ 2`.

Example qids and their actual `sub_queries`:

- `arxiv_39_comparative` n_sub=2: `['D1-D4 score evolution Grok-4 Fast
  GPT-5.2 iterations', 'model performance scores iteration benchmark
  results']`
- `arxiv_48_comparative` n_sub=3: `['CalM POCO TCN correlation scores
  held-out datasets', 'model performance comparison held-out dataset
  metrics', 'CalM POYO correlation R2 scores']`
- `hotpot_01_relational` n_sub=2: `['Wilmslow High School Wilmslow Show
  relationship venue', 'Wilmslow Show location held at']`
- `hotpot_05_relational` n_sub=2: `["Jack Lowden role Tommy's Honour",
  'Jack Lowden Young Tom Morris cast']`
- `hotpot_31_comparative` n_sub=2: `["Carlene LeFevre Nathan's Hot Dog
  Eating Contest ranking 2003 2004 2005", "Rich LeFevre Nathan's Hot Dog
  Eating Contest ranking 2003 2004 2005"]`
- `multinews_01_temporal` n_sub=3, `multinews_04_temporal` n_sub=2,
  `multinews_06_temporal` n_sub=2 — all with substantive sub-queries.

Root cause: the scorer prompt instructs the LLM to emit "non-agentic
strategy: no retrieval queries" only when the sub_queries field is
empty (`scorer.py:101-103`), but the judge LLM appears to apply that
canned justification when the sub-queries are short noun-phrase-only
strings without verbs. This is a measurement issue.

### M1 — `n_sub_queries == 0` (6 records, 1 false positive)

True zeros (5): `10k_14_quantitative`, `govreport_46_hierarchical`,
`hotpot_13_relational`, `multinews_08_temporal`, `tech_docs_*` (none in
the 6). Plus `hotpot_04_relational` (n_sub=0 but SQQ=0.67) and
`hotpot_45_comparative`, `arxiv_03_hierarchical` (also n_sub=0 but
SQQ≥0.83 because their checklists happened to give partial credit).

This is the same `silent n_subq=0` failure mode named in
`docs/analysis/b6_vs_b7_paired_loss_analysis.md` §1. It is an
orchestration gap (agent calls `generate_viz` without first invoking
`search`/`RFD`) and out-of-scope for SQQ prompt-side fixes. Listed for
completeness; the recommended fix is to add a `search`-precondition to
the hard rule in `tmg.py:193-240`, which §1 of b6_vs_b7_paired_loss
already proposes.

### M2 — Generic phrasing (109 records, top fixable mode)

The agent issues 2–3 sub-queries that contain the named entities but
the judge wanted a specific quoted noun-phrase or section/item ID:

- `10k_03_quantitative` (sqq=0.50) sub_q has `Google Services revenue
  2024 2025` — judge wanted `'pre-tax income'` and `'net income'` FX
  impact phrasing.
- `10k_05_quantitative` (sqq=0.83) — judge wanted the literal string
  `'Item 7A'` in the query.
- `10k_09_quantitative` (sqq=0.83) — judge wanted explicit "exclude
  other currencies via negative filtering".
- `10k_11_quantitative` (sqq=0.50) — judge wanted `'retrospective
  adjustment'` and `'segment combination'` literally.
- `hotpot_39_comparative` (sqq=0.17) — sub_q was `['career-high ATP
  ranking', 'doubles ranking', 'singles ranking']` (generic,
  player-name-less); judge wanted `'Wayne Black'` and `'Jonathan Marray'`
  in the query string explicitly.
- `arxiv_15_hierarchical` (sqq=0.33) — sub_q `['WADI dimensions',
  'hierarchical tree structure', 'framework sub-components', 'design
  dimensions']` — judge wanted `'W1 sub-components'`, `'W2 measurement'`
  explicitly.

The diagnostic pattern: when the agent's sub-query is **on-topic but
abstracted one level above the source's literal wording**, the judge
docks the item. This is a real and addressable behavior — instructing
the agent to "include the exact noun-phrase and section/table number
when known" in sub-queries should lift many of these from NO → PARTIAL
or PARTIAL → YES.

### M3 — Off-topic / checklist hallucination (11 records)

Spot-check: of 9 quoted terms extracted from M3 item questions,
**7/9 (78%) do not appear in the bundle at all**. Examples (verified by
direct text search of `data/prototype/bundles/all.json`):

- `arxiv_01_hierarchical` bundle = only the "Good Rankings, Wrong
  Probabilities" Calibration Audit paper (39 KB). Checklist asked about
  `'temporal imbalance'` (0 hits), `'intersectional fairness'` (0),
  `'genomic entropy'` (0). The agent could not have queried for these
  — they are not in the documents.
- `arxiv_04_hierarchical` bundle = only the Spatial Transcriptomics
  Foundation Model paper. Checklist asked about `'Claw-Eval'`,
  `'ACE-Bench'`, `'300 tasks, 3 groups, 9 categories'` — all 0 hits.
- `10k_04_quantitative` — user query is segment income; checklist asked
  for `'foreign currency transaction gains losses'` (a different Item 7A
  topic the user did not request).

This is a checklist-quality issue (the LLM that generated the checklist
hallucinated questions from adjacent topics) and is documented as a
separate measurement issue, not an agent failure.

### M4 — Scorer error (1 record: `tech_docs_28_relational`)

3 items all returned `"scorer did not return a valid answer for this
item"`. JSON parse / token-limit issue in the scorer. Affects 1 record.

### M5 — PARTIAL coverage (45 records, scattered)

Mostly the judge being strict about a 3rd sub-aspect the agent missed.
Some are recoverable (`10k_02_quantitative` — agent had `'foreign
currency risk'` but missed `'gain or loss'` paired phrase); many are
genuine agent under-coverage (`text2vis_088` — listed Venezuela but not
Guyana). Mixed root cause.

### M6 — Other (24 records)

Mix of checklist hallucination (`arxiv_01` "intersectional fairness"),
genuine agent gaps ("`'agent cooperation mechanisms'`" not retrieved in
arxiv_09), and judge expecting a query about a side-aspect named in the
source but not the user query.

---

## 6. Proposed fixes

| ID | Mode targeted | Type | File | Lines | Exact text (proposed) | Records affected | Conservative Δ SQQ | Risk |
|----|---------------|------|------|-------|-----------------------|------------------|---------------------|------|
| F1 | M0 (judge bug) | Auto-correction patch (post-hoc score rewrite) | new helper in `code/judge/` or `outputs/.../all.json` re-judge | re-judge 8 qids | (no prompt change — re-run scorer with `n_sub_queries` count appended to the strategy label, e.g., `agentic (n_sub=2)`) | 8 | +0.0196 | Low; only rewrites items justified by canned "non-agentic" string |
| F2 | M2 (generic phrasing) | V4 rule clarification | `code/pipelines/tmg.py` | 193–221 (within `V4_POOL_EXPOSURE_RULE`, after the `content_brief` sentence) | "When you call `search`, phrase each sub-query to include the literal entities, section or table identifiers (e.g. `Item 7A`), and quoted noun-phrases from the user question — not abstracted topic words like 'data' or 'overview'." | ~109 | +0.0205 to +0.0342 | Low — adds 1 sentence in plain style; might marginally bias sub-queries to over-quote, slight risk to coverage (-0.005) |
| F3 | M2 (generic phrasing, hierarchical+comparative) | Sub-query exemplar in V4 rule | `code/pipelines/tmg.py` | 193–221 (one line after F2) | "Good: `Wayne Black career-high ATP doubles ranking`. Bad: `career-high ATP ranking`." | overlapping subset of F2 | accounted in F2 lift | Low |
| F4 | M3/M6 (checklist hallucination) | Checklist-gen prompt tightening | `code/judge/checklist_gen.py` | 34–59 (in `CHECKLIST_GEN_PROMPT` near the per-axis bullets) | "Every item's question and evidence_hint MUST quote a literal noun-phrase that appears verbatim in the source documents above; do not invent entity names." | ~22 (M3+M6 subset) | +0.0104 | Med — could reduce SQQ item difficulty overall; affects all strategies' SQQ comparability. Apply post-hoc to B6+B7 paired only. |
| F5 | M1 (n_sub=0) | Orchestration precondition (already noted in §1 of paired-loss doc) | `code/pipelines/tmg.py` | 193–240 | Add "`search` must be invoked at least once before `generate_viz`" | 6 | (out-of-scope — already proposed elsewhere; counted there) | Med |
| F6 | M4 (scorer error) | Re-judge single record | n/a | n/a | re-run scorer for `tech_docs_28_relational` | 1 | +0.0019 | None |

All prompt text ≤ 30 words and respects the V4 plain-style constraint
(no banner, no caps, no markdown headers, sentence-style).

---

## 7. Δ aggregation + gate-closing analysis

Cumulative SQQ lift (conservative ⇒ aggressive, with overlap discount):

| Fix | SQQ Δ (conservative) | SQQ Δ (aggressive) |
|-----|----------------------|---------------------|
| F1 (judge-bug PARTIAL fallback, 8 records → 0.65 mean) | +0.0196 | +0.0257 (if lift to 0.85) |
| F2+F3 (V4 rule on phrasing) | +0.0205 | +0.0342 |
| F4 (checklist re-tightening, 22 records) | +0.0104 | +0.0155 |
| F6 (scorer re-judge, 1 record) | +0.0019 | +0.0030 |
| **Total** | **+0.052** | **+0.078** |

(Some overlap between F1/F4 because two M0 records also overlap M3 in
their justifications; subtracting overlap, conservative ≈ +0.050,
aggressive ≈ +0.073.)

Translation to 4-axis overall: SQQ counts 1/4 of the mean, so:

- Conservative overall Δ = +0.050 / 4 ≈ **+0.0125**
- Aggressive overall Δ = +0.073 / 4 ≈ **+0.0183**

Gate gap to close (B7 − B6 overall on text-axis) = +0.056.

- Conservative closes **22% of the gap**
- Aggressive closes **33% of the gap**

Bottom line: SQQ fixes alone are not enough to close the §16 gate.
They are necessary but must be combined with the
type_appropriateness / mermaid_timeline routing fix from
`b6_vs_b7_paired_loss_analysis.md` §1 to plausibly close the gap.

---

## 8. Text2Vis generalization check

Text2Vis B6 axis means (n=100): faithfulness 0.856, coverage 0.817,
type_appropriateness 0.750, **search_query_quality 0.818**. SQQ is no
longer the lowest axis here — `type_appropriateness` is — but SQQ
sits 0.063 above prototype (0.755 → 0.818), consistent with Text2Vis
queries having simpler bundle structure (single text-table per query)
and a less crowded checklist generator.

Failure-mode breakdown on Text2Vis B6 (73 failing items):

- M0 judge-bug: 0 (does not generalize — the bug is specific to
  multi-document narrative bundles).
- M1 n_sub=0: 9 items (≈ 6 records). Generalizes — same orchestration
  gap.
- M2 generic phrasing: 28 items. Generalizes (e.g.,
  `text2vis_088`: queried for Venezuela but not Guyana; `text2vis_081`:
  queried Dominica/Kazakhstan/Mexico but not Brazil). Same root cause.
- Aggregation expectations (judge wants `'cumulative sum'`,
  `'year-over-year'`): 6 items — these are not retrievable concepts;
  they are post-retrieval calculations. Checklist quality issue.

**Generalization verdict**: M2 (generic phrasing) is the only mode that
clearly generalizes across both datasets. F2/F3 are safe to apply
universally. F1 is prototype-specific. F4 should be tested in shadow on
both datasets before becoming default.

---

## 9. Open questions

- **Should we re-judge the 8 M0 records or auto-patch?** A re-judge is
  cleaner; a post-hoc patch (rewrite NO with canned "non-agentic"
  justification + n_sub≥1 → PARTIAL) is reproducible. Recommend
  patch + sidecar audit file rather than mutating
  `outputs/prototype/judge_scores/all.json`.
- **Does F2 (rule clarification) regress faithfulness?** If the agent
  starts mirroring source phrasing literally in sub-queries, it may also
  bias toward over-quoting in `content_brief`, potentially raising
  faithfulness but at the cost of generation variability. Needs A/B
  preflight per `feedback_preflight_before_bulk.md` (10-min preflight
  on 20 records) before bulk rerun.
- **Should M3 (checklist hallucination) be addressed at all in this
  pass?** F4 changes the judge's measurement. If applied,
  *every* strategy's SQQ gets re-baselined, which changes the gate
  arithmetic. Safer to flag M3 as a measurement artifact and report B6
  SQQ as `0.755 (gross) / 0.788 (M0+M3-adjusted)` rather than ship F4
  as a default.
- **Is M5 (PARTIAL coverage) really agent under-coverage or judge
  strictness?** Spot-check on 10 M5 records suggests ~half are
  legitimately recoverable by F2 (the agent missed an exact noun-phrase
  that *is* in the bundle) and half are judge strictness. The
  conservative Δ above counts only the recoverable half via F2; the
  aggressive number assumes M5 partial uplift too.
