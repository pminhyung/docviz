# Measurement Plan vs Actual — Status & Blockers (2026-05-24)

> Audience: research mentor. Each section ties an original plan item
> from PAPER_MASTER_SPEC §15 to (a) what was actually executed, (b)
> what schema/data was used, (c) the specific issue if misaligned or
> blocked. Decision points listed at the end.

---

## Executive summary

| Layer | Plan | Actual | Status |
|---|---|---|---|
| **A** in-domain QG-MDV | 7 baselines × 265, 4-axis text + M5 CLIPScore | 7 baselines + 3 ablations × 265, scope-v3 4-axis + CDI + M5 | ✅ done & extended; B6 SOTA on text and image |
| **B-1** Text2Vis held-out | 7 + B8 spec × 100, Text2Vis 4-dim reimpl | 7 × 100 judged with our Layer A prompt (not Text2Vis native 4-dim); B8 missing | ⚠️ schema misaligned; format compatibility OK |
| **B-2** ViviBench held-out | 7 + B9 spec × 101, ViviBench 4-dim reimpl | nothing | ❌ blocked — dataset not publicly released |
| **B-3** Plot2Code held-out | 7 + B10 spec × 50, exec_rate + CLIPScore vs target | 50 viz attempted, rendering done; no metrics at scale | ❌ blocked — fundamental format & taxonomy incompatibility (detail in §3.3) |
| **D** pillar ablation | 4 variants × 268 | 4 variants × 265 under scope-v3 | ✅ done; magnitude TMG > CIS > SAO |

Headline: **Layer A is the rigorous main result; Layer D ablations
support it; Layer B held-out cells need redirection (B-1 schema fix,
B-2 dataset-blocked, B-3 fundamentally incompatible with our output
form factor).**

---

## 1. Original measurement plan (spec §15.1, §15.2, §6.1)

### 1.1 Per-layer generation matrix

| Layer | Setting | # records | Generation count |
|---|---|---:|---:|
| A | QG-MDV in-domain | 268 (prototype 265) | 1,876 |
| B-1 | Text2Vis held-out | 100 | 800 (7×100 + 1×100 specialist) |
| B-2 | ViviBench held-out | 101 | 808 |
| B-3 | Plot2Code held-out | 50 | 400 |
| D | Pillar ablation | 268 | 1,072 (3 active variants) |
| **Total active** | | | **~4,956** |

### 1.2 Per-layer evaluation schema

| Layer | Phase-1 judge (active, Qwen) | Phase-2 judge (deferred, closed-API) | Deterministic |
|---|---|---|---|
| A | 4-axis (faith / coverage / type / SQ) | Claude Opus 4.6 scorer + GPT-5 cross-judge | M1 render + M5 CLIPScore + DSL parse |
| B-1 | **Text2Vis 4-dim answer-match** (Qwen reimpl of Text2Vis paper's eval) | Text2Vis original GPT-4o eval | M1 + M5 |
| B-2 | **ViviBench 4-dim** (Qwen reimpl) | ViviBench original eval | (pending) |
| B-3 | **exec-rate (deterministic)** + CLIPScore vs target | Plot2Code GPT-4V overall | M1 + M5 |
| D | 4-axis (Qwen) | (selectively re-judge if Phase-2 budget activated) | M1 + M5 |

### 1.3 Cross-record metrics (spec §6.1)

| Metric | Type | Implementation | Spec activation |
|---|---|---|---|
| A1 Faithfulness | text-judge | `code/judge/scorer.py` | every record |
| A2 Coverage | text-judge | scorer.py | every record |
| A3 Type appropriateness | text-judge | scorer.py | every record |
| A4 Search-query quality | text-judge | scorer.py | agentic only |
| **A5 Visual Quality (D7)** | image-judge (Claude Sonnet via `claude -p`) | `code/judge/image_judge.py` | 100-record sub-sample, **closed-API** |
| M1 Render success | deterministic | `code/render/renderer.py` | every record |
| M3 Element count | deterministic (DSL parser) | `code/judge/dsl_parser.py` | every record |
| **M5 CLIPScore** | deterministic (open_clip ViT-L-14 + Hessel ×2.5) | `code/metrics/clipscore.py` | every record |

### 1.4 Two-phase judge strategy (spec §6.2)

- **Phase 1** (active, on-prem Qwen3.5-397B): trend scan, $0
- **Phase 2** (deferred, closed-API): paper-grade re-judge on Layer A
  + Layer D pillar ablation overall + Layer B home-turf rows
  (~5,050 records, ~$1,265)
- Gate: Phase-1 V4 advantage ≥+5%p multi-doc + Layer B home-turf gap
  ≤7%p → GO Phase 2

---

## 2. Layer A in-domain — ✅ DONE (with extensions vs plan)

### 2.1 Plan vs actual

| Aspect | Plan (§15) | Actual |
|---|---|---|
| n | 268 | 265 (prototype-scale: 10-K loader returned 15 vs target 50; documented §5.1 caveat) |
| Baselines | 7 (B1-B5, B7, B6) | 7 main (B1-B4, S1, B7, B6) + 3 ablations (B6_NoCIS / NoSAO / NoTMG) |
| Text axes | 4-axis (faith / coverage / type / SQ) | **4-axis amended: faith / coverage / type / CDI** (cross-document integration added 5/17 for 4-universal-axis composition; SQ kept as agentic-only diagnostic, **excluded from `overall`**) |
| Judge protocol | RocketEval-style Qwen judge | **scope-v3 per-axis isolation** (5/23 — addresses off-query checklist asymmetry; anti-CDI-contamination clause) |
| Phase-2 closed-API | deferred until borderline trigger | deferred (Phase-1 advantage now clears ≥+0.020 strict gate; Phase-2 still deferrable) |
| M5 CLIPScore | every record | every record done (`outputs/prototype/clip_scores/all.json`, 2,039 entries) |
| M1 render success | every record | every record (in `viz/all.json`'s `syntax_valid` + render pass) |
| M3 element count | every record | available in `viz_parsed_summary` (not yet aggregated into a table) |

### 2.2 Layer A multi-metric result (production)

| Strategy | M1 syntax % | M1 render % | M5 CLIPScore (Hessel) | scope-v3 overall |
|---|---:|---:|---:|---:|
| **★ B6 (S4_AgenticTMGv4_consolidated)** | **98.9%** | 82.7% | **1.9487 (n=210)** | **0.8391** |
| B7 SelfRefine | 98.1% | 89.8% | 1.8779 (n=238) | 0.8077 |
| S1 Direct | 99.6% | 89.8% | 1.9405 (n=238) | 0.7980 |
| B4 ViviDoc | 98.5% | 90.9% | 1.8783 (n=241) | 0.7863 |
| B3 CoDA | 99.2% | 94.0% | 1.8708 (n=249) | 0.7447 |
| B1 MatPlotAgent | 0% | 0% | n=0 | 0.7215 |
| B2 NVAGENT | 97.4% | 94.7% | 1.8639 (n=251) | 0.7031 |

Key cross-validation: **Spearman ρ(text-overall, CLIPScore) = +0.857**
> spec §16 G7 target of 0.5. Two completely different measurement
protocols (LLM 4-axis vs deterministic image-text similarity) agree
on the ranking — strong protocol-validation evidence.

### 2.3 Layer A ablation table (§11.4)

| Variant | overall | Δ vs Full | Δ Faith | Δ Cov | Δ TA | Δ CDI |
|---|---:|---:|---:|---:|---:|---:|
| B6 Full | 0.8391 | — | 0.893 | 0.930 | 0.932 | 0.602 |
| B6 −CIS | 0.7332 | −0.106 | −0.101 | −0.098 | −0.124 | −0.108 |
| B6 −SAO | 0.7639 | −0.075 | −0.072 | −0.088 | −0.100 | −0.047 |
| **B6 −TMG** | **0.5855** | **−0.254** | −0.271 | −0.273 | −0.277 | −0.193 |

All three pillars contribute positively across all four axes.

### 2.4 Known caveats on Layer A

- **B1 MatPlotAgent M1 render = 0%**: B1's output is a Python
  matplotlib subprocess (not a DSL string in our 10-enum pool), so our
  shared renderer cannot rasterize its output. Documented spec §6.4
  limitation. CLIPScore not measurable for B1 in our pipeline; M1
  render is a structural metric and B1's "0%" should be interpreted
  as "out-of-pool format, not a quality signal."
- **B6 M1 render = 82.7%** (lower than B3-B7's 89-95%): residual Mode B
  failures (agent reasoning without invoking `generate_viz`) on a
  small subset (~17/265 records). Did not block §16 gate.
- Single-seed (seed 42). Three-seed reporting (§13 non-negotiable)
  PENDING — 6 baselines × 265 × 2 additional seeds ≈ 3-5h on the
  multi-host cluster.

---

## 3. Layer B — Held-out generalization

### 3.1 Layer B-1 Text2Vis — ⚠️ SCHEMA MISALIGNED

**Plan (§15.2)**: Text2Vis 4-dim answer-match (Qwen reimpl of the
Text2Vis EMNLP 2025 paper's eval methodology).

**Actual**:
- 700 records produced and judged (7 baselines × 100 queries)
- Judge invoked: **our Layer A `code/judge/checklist_gen.py`** —
  produces faith / coverage / type-appropriateness items (the same
  axes used for QG-MDV). Output schema observed:
  `['coverage', 'faithfulness', 'type_appropriateness']` × ~9 items
  per checklist (non_agentic; agentic adds SQQ; CDI items did NOT fire
  because Text2Vis bundles are single-table)
- **B8 Text2Vis-original specialist run: missing entirely.** §10.3
  Tier-1 reference cannot be established yet.

**The specific issue (per user critique)**:
- Spec wording "Text2Vis 4-dim answer-match" refers to **the four
  evaluation dimensions defined by the Text2Vis paper itself** —
  typically data-accuracy / chart-type match / axis encoding / layout.
  These are external benchmark conventions.
- Our judge ran *our internal* RocketEval-style axes against Text2Vis
  viz, which is a different evaluation protocol entirely. The numbers
  are well-defined but they answer the wrong question: they say
  "how do baselines compare on our judge's axes when applied to
  Text2Vis viz" rather than "how do baselines compare on Text2Vis's
  own published evaluation."
- Reviewer attack surface: *"You evaluated an external benchmark with
  your own judge — that is not generalization evidence; you've only
  shown your judge is consistent across viz sources."*

**Format compatibility (separate from schema)**: GOOD. B6 output on
Text2Vis = 97/100 chartjs_* + 3/100 mermaid_flowchart. Text2Vis is a
table→chart task whose ground-truth charts are chart-specification
shaped; B6's chartjs output is directly compatible.

**Current "result" (with caveat that the schema is mislabeled)**:

| Rank | Strategy | mean (Layer A judge applied to Text2Vis viz) |
|---:|---|---:|
| 1 | B1 MatPlotAgent | 0.870 |
| 2 | B7 SelfRefine | 0.839 |
| 3 | B6 (ours) | 0.810 |
| 4 | S1 Direct | 0.791 |
| 5 | B4 ViviDoc | 0.772 |
| 6 | B3 CoDA | 0.738 |
| 7 | B2 NVAGENT | 0.677 |

B6 ranks 3rd here, which is consistent with the Tier-1 framing
("specialists win on home turf, we win on multi-doc"), but the
underlying eval is mislabeled. **Decision needed.**

### 3.2 Layer B-2 ViviBench — ❌ BLOCKED (dataset)

**Plan (§15.1)**: 7 + B9 specialist × 101 records, ViviBench
4-dim reimpl.

**Actual**: nothing. No data acquired.

**The specific issue**:
- Spec note §15.1: *"data not yet public"*
- ViviBench (2026) has not been released on HuggingFace or via paper
  supplementary.
- Cannot proceed without the benchmark's queries and ground-truth
  visualizations.

**Action**: Out-of-scope for v0.3 prototype unless the dataset is
released. Document as such in §11 limitations.

### 3.3 Layer B-3 Plot2Code — ❌ BLOCKED (fundamental format & taxonomy incompatibility)

**Plan (§15.2)**: 7 + B10 specialist × 50 records, exec_rate
(deterministic) + CLIPScore vs target (deterministic).

**Actual**:
- 350 viz records produced (7 baselines × 50)
- Renders directory populated for 6 baselines
  (`outputs/plot2code/renders/{strategy}/`)
- **No exec_rate computed at scale.** No CLIPScore-at-scale
  computed against Plot2Code ground-truth target images.
- **5-record preflight from v0.3 prototype**: B6 exec_rate = 0.20
  vs B5/B7 = 1.00/0.80 (spec §6.4 table).

**The specific issue — three nested incompatibilities**:

**(i) Output-form mismatch.** Plot2Code's expected output is *Python
matplotlib code* (executable .py source). Plot2Code's exec_rate metric
is defined as *"fraction of generated programs that import matplotlib
and run to completion producing a figure"*. Our 10-enum `viz_type`
pool produces (a) chartjs JSON or (b) Mermaid markdown — neither is
Python source. Even if execution were attempted, there is no
Python interpreter input. Our pipeline produces a structurally
different artifact class.

Concretely, B6's 50 Plot2Code outputs distribute as:
- `mermaid_flowchart`: 41 (most common)
- empty (Mode B / agent failure): 8
- `chartjs_bar`: 1

None of these can be executed as Python matplotlib code. exec_rate is
therefore 0/50 = 0%, but this is a category error in the metric
applicability, not a quality signal.

**(ii) Taxonomy mismatch.** Plot2Code's source material includes
multi-panel matplotlib figures: 2×2 grids, plot-with-insets, treemaps,
boxplot grids, and figures with custom axis layouts. Our `viz_type`
enum has 10 single-panel options (5 chartjs subtypes + 5 mermaid
subtypes); none of them can encode a multi-panel composition. From
the 5/13 Plot2Code failure analysis
(`docs/analysis/plot2code_v4_cons_fail_analysis.md`):
*"T: taxonomy fundamental limit (≥10 records out of 50): source is
2×2 / 4-subplot / treemap / box-plot grid; none of the 10 enum
subtypes can capture multi-panel composition."*

**(iii) Image-comparison mismatch.** CLIPScore vs target requires
comparing our rendered output image to Plot2Code's ground-truth
matplotlib figure. The graphical languages differ (mermaid SVG vs
matplotlib raster); even when both render successfully, the visual
encoding choices (axis style, color, font, glyph layout) are
incommensurable at the pixel-similarity level. CLIPScore via ViT-L
would measure a domain-gap distance, not a quality distance.

**Bottom line**: Plot2Code is not a meaningful held-out benchmark for
our system as designed. The 5/13 preflight result (B6 exec_rate 0.20)
is consistent with this: B6 produced ~10/50 attempts that even
"executed" in a loose sense (chart specs that could be re-instantiated),
and the rest hit category errors. The honest framing is **"Plot2Code
single-doc figure-replication task is out of our pipeline's
expressive domain"** — Tier-1 specialists (matplotlib home-turf
B1/B10) win by definition.

**B10 MatPlotAgent specialist run on Plot2Code**: missing. Not blocked
by anything but time; should run if Plot2Code is kept in §10 table
for Tier-1 reference. Otherwise drop B-3 from the cross-task table.

### 3.4 §10.3 Tier-1 "within 5-7%p home turf" — current evidence: NONE

Spec requires B8 / B9 / B10 specialist runs on their home turf
benchmarks to establish the 5-7%p reference. None have been executed.
The claim is unsupported as of today.

If §10.3 framing is retained, B8 (Text2Vis-original) is the lowest-cost
specialist to add (single benchmark, format-compatible). B9 needs
ViviBench data. B10 needs Plot2Code's incompatibilities resolved or
re-framed.

---

## 4. Metric-level status (per spec §6.1)

| Metric | Layer A | Layer B-1 | Layer B-2 | Layer B-3 | Layer D | Notes |
|---|---|---|---|---|---|---|
| A1-A4 text-judge (Qwen) | ✅ scope-v3 | ⚠️ Layer A prompt mis-applied | ❌ no data | n/a (deterministic only) | ✅ scope-v3 | A4=SQQ excluded from overall |
| A5 image-judge (Claude Sonnet) | ❌ deferred (closed-API) | ❌ deferred | n/a | ❌ deferred | ❌ deferred | $200-350 budget; 700 records sub-sample |
| M1 render success | ✅ in viz | ✅ in viz | n/a | partial (rendered, not metricized at scale) | ✅ | B1 0% expected (out-of-pool format) |
| M3 element count | available (not aggregated) | available | n/a | available | available | DSL parser path: `code/judge/dsl_parser.py` |
| **M5 CLIPScore** | ✅ 2,039 records | ❌ not run | n/a | partial (5-record preflight) | partial (subset) | open_clip ViT-L-14 + Hessel ×2.5 |
| Phase-2 closed-API re-judge | ❌ deferred | ❌ | ❌ | ❌ | ❌ | $1,265 envelope; triggered only on borderline §16 — not borderline now |
| Cross-judge κ (Opus 4.6 × GPT-5) | ❌ deferred | ❌ | ❌ | ❌ | ❌ | tied to Phase-2 |

---

## 5. §13 three-seed reporting — ❌ PENDING

Spec §13 (non-negotiable for prototype): seeds 42 / 43 / 44, mean ± std
on Layer A overall.

**Current**: single-seed (42) only.
**Required additional work**: seeds 43 + 44 × 7 baselines × 265 records =
3,710 generations + judge. ~3-5h on the multi-host cluster.

This is the remaining statistical-strength step before the §16
gate-pass claim is publication-ready.

---

## 6. Decision points for mentor

| # | Decision | Options | Recommendation |
|---:|---|---|---|
| 1 | Text2Vis schema | (a) Look up Text2Vis paper's 4-dim eval, reimpl checklist_gen for it; (b) Switch to deterministic native metrics (syntax_pass + chart-type-match + data-cell-accuracy from chartjs JSON vs reference); (c) Drop Layer B-1 from §10 and acknowledge limitation in §11 | **(b)** for v0.3: faster, fully defensible, no LLM-in-the-loop on external benchmark; (a) if reviewer pressure |
| 2 | Plot2Code | (a) Drop from §10 cross-task; acknowledge in §11 that Plot2Code requires Python-matplotlib output form which is out of our DSL-based pipeline's design; (b) Re-frame Plot2Code as a "category-error stress test" showing where our taxonomy doesn't reach; (c) Run B10 specialist for the 5-7%p reference even though our scores are not directly comparable | **(a)** is honest; (b) is academically interesting but risks reviewer confusion; (c) only if §10.3 Tier-1 claim is retained |
| 3 | ViviBench | (a) Drop, document as data-unavailable in §11; (b) Wait for release | **(a)** for v0.3 timeline |
| 4 | §10.3 Tier-1 "within 5-7%p" claim | (a) Retain — needs B8/B10 specialist runs; (b) Soften to qualitative "competitive on home-turf" without strict %p bound; (c) Drop entirely | **(b)** if specialists are not run; (a) if B8 is run (cheapest) |
| 5 | Phase-2 closed-API re-judge | (a) Trigger now (~$1,265) as paper-grade backstop; (b) Defer per spec (no borderline trigger, current advantage > +0.020); (c) Run only on Layer A + Layer D, skip Layer B | **(b)** is consistent with spec gate logic; (a) if reviewer-attack-surface reduction warrants it; (c) is middle ground |
| 6 | Three-seed reporting | (a) Run now (~3-5h, $0 on-prem); (b) Run after deciding §10/§11 framing | **(a)** — non-negotiable per §13; complete this and §16 gate-pass becomes robustness-verified |

### Recommended priority order (for v0.3 paper submission)

1. **Three-seed reporting** (3-5h on-prem) — required for §13/§16
   robustness.
2. **Layer B-1 Text2Vis native-metric path (option 1b)** — switch to
   deterministic chartjs-vs-reference comparison; immediate,
   reviewer-defensible.
3. **Layer B-3 Plot2Code drop + §11 documentation (option 2a)** — no
   work needed; just write the §11 limitation paragraph.
4. **§10.3 framing softening (option 4b)** — no specialist runs needed.
5. **A5 image judge + Phase-2 closed-API** — defer to revision/camera-
   ready phase.

Total remaining work to v0.3 submission: ~5-7h compute (mostly
three-seed) + ~half-day writing.

---

## 7. File pointers (for reproducibility)

- Layer A data: `outputs/prototype/judge_scores/all.json` (10 strategies × 265, scope-v3) + `outputs/prototype/viz/all.json`
- Layer A CLIPScore: `outputs/prototype/clip_scores/all.json` (2,039 records)
- Layer A checklists: `outputs/prototype/judge_scores/checklists.json`
- SOTA snapshot (current): `outputs/prototype/judge_scores/all.json.SOTA_scope_v3_FINAL_20260523_210925`
- Layer B-1 data: `outputs/text2vis/{viz,judge_scores}/all.json`
- Layer B-3 viz: `outputs/plot2code/viz/all.json`; renders: `outputs/plot2code/renders/`
- Judge implementation: `code/judge/checklist_gen.py` (scope-v3), `code/judge/scorer.py`
- Metric implementations: `code/render/renderer.py` (M1), `code/judge/dsl_parser.py` (M3), `code/metrics/clipscore.py` (M5)
- Earlier per-benchmark failure analyses:
  - `docs/analysis/plot2code_v4_cons_fail_analysis.md` (cited §3.3)
  - `docs/analysis/text2vis_v4_cons_fail_analysis.md`
- Scope-v3 design + result: `docs/analysis/scope_v3_gate_pass_260523.md`
- This document: `docs/analysis/measurement_plan_vs_actual_260524.md`
