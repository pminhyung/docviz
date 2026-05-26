# Experiment Status — 2026-05-23

Spec §15 Experiment Matrix vs actual completion state. Honest assessment
of what's done correctly vs misaligned vs missing.

## 1. Per-layer status

| Layer | Setting | Spec target (§15) | Actual |
|---|---|---|---|
| **A** | QG-MDV in-domain | 7 baselines × 265, 4-axis (faith/cov/type/SQ) Qwen | ✅ **DONE + extended** — 7 baselines + 3 ablations × 265 records, scope-v3 judge (4-axis faith/cov/TA/CDI; SQQ kept as agentic-only diagnostic, excluded from overall). B6 mean=0.839 SOTA. **CDI is spec amendment** (added during 5/17 redesign for 4-universal-axis composition fairness). |
| **B-1** | Text2Vis held-out | 7 + B8 specialist × 100, **Text2Vis 4-dim answer-match (Qwen reimpl)** | ⚠️ **MISALIGNED** — 700 records (7 × 100) judged, but the judge ran our **Layer A prompt** (axes: faith/cov/type) on Text2Vis viz, NOT a Text2Vis-native 4-dim answer-match reimpl. Spec wording ("4-dim answer-match") implies Text2Vis original paper's evaluation dimensions, not ours. **B8 specialist run also missing.** |
| **B-2** | ViviBench held-out | 7 + B9 specialist × 101, ViviBench 4-dim | ❌ **DEFERRED** — no data, no outputs. Spec note: "data not yet public". No work done. |
| **B-3** | Plot2Code held-out | 7 + B10 specialist × 50, exec-rate (deterministic) + CLIPScore vs target | 🟡 **PARTIAL** — viz: 350 records (7 × 50) generated; renders: 6 baselines' images present. **judge_scores empty** — no exec_rate / CLIPScore at scale measurement. Prior 5-record preflight: B6 exec_rate 0.20 vs B5/B7 1.00/0.80. Earlier note: 47/50 of B6 V4_cons polluted by cluster 401, needs retry verification. **B10 specialist (MatPlotAgent) missing.** |
| **D** | Pillar ablation | 4 (B6 Full / −TMG / −SAO / −CIS deferred) × 268 | ✅ **DONE** — 3 ablations × 265 under scope-v3 judge. Pillar magnitude (mean drop vs Full): TMG −0.254 > CIS −0.106 > SAO −0.075. All pillars positive across all 4 axes. CIS WAS deferred per spec but now COMPLETED. |

## 2. Layer A detail (production state)

n = 265, scope-v3 judge protocol (per-axis isolation in `code/judge/checklist_gen.py`).

| Rank | Strategy | mean overall | Δ vs B6 |
|---:|---|---:|---:|
| 1 | **★ B6 (S4_AgenticTMGv4_consolidated)** | **0.8391** | — |
| 2 | B7 SelfRefine | 0.8077 | −0.0314 |
| 3 | S1 Direct | 0.7980 | −0.0411 |
| 4 | B4 ViviDoc | 0.7863 | −0.0528 |
| 5 | B6 −SAO (ablation) | 0.7639 | −0.0752 |
| 6 | B3 CoDA | 0.7447 | −0.0945 |
| 7 | B6 −CIS (ablation) | 0.7332 | −0.1059 |
| 8 | B1 MatPlotAgent | 0.7215 | −0.1176 |
| 9 | B2 NVAGENT | 0.7031 | −0.1360 |
| 10 | B6 −TMG (ablation) | 0.5855 | −0.2537 |

B6 wins all 4 axes (Faith / Cov / TA / CDI), 5/6 sources (lone loss: 10-K
quantitative n=15 to B3 CoDA), 5/5 query types. **Strict +0.020 gate
PASSED vs strongest baseline (B7)**.

Production data: `outputs/prototype/judge_scores/all.json`.

## 3. Layer B-1 Text2Vis — what's needed

Current state is misaligned with spec. Two paths to align:

### Path A1 — Implement Text2Vis 4-dim answer-match
Need:
1. Locate Text2Vis original paper's 4 dimensions (likely: data accuracy /
   visual encoding match / layout / semantic). Get exact wording.
2. Add Text2Vis-specific checklist generator
   (`code/judge/text2vis_checklist_gen.py`) using those dimensions —
   single-doc table-to-chart task, no CDI, no SQQ.
3. Re-judge 700 records under new schema.
4. Run B8 specialist (Text2Vis-original) on Text2Vis 100 records for
   Tier-1 "within 5-7%p" reference.

Estimated time: depends on paper-side spec lookup; once schema fixed,
~30min for re-judge.

### Path A2 — Native automated metric only
Text2Vis viz often has chart-spec-level ground truth. Compute:
- Syntax-pass rate (already in viz.json's `syntax_valid` flag)
- Chart-type match accuracy vs reference (need to extract reference
  chart_type from Text2Vis ground truth)
- Data-cell match (parse generated chartjs JSON, compare data arrays
  with reference)

This bypasses LLM judge entirely. Faster, more defensible, fewer
moving parts. Spec wording "4-dim answer-match" is open to this
interpretation.

**Recommendation: A2 first (deterministic, paper-defensible), A1 if A2
result is insufficient for §10 framing.**

## 4. Layer B-3 Plot2Code — what's needed

Spec native = exec_rate + CLIPScore vs target. Both are deterministic
(no LLM judge), code already exists (`code/metrics/clipscore.py`,
exec_rate from render success).

Steps:
1. Verify viz quality on 50 records per strategy (47/50 polluted note —
   need fresh viz for B6 V4_cons after cluster recovery).
2. Render all 350 viz to images (already partial — `outputs/plot2code/renders/`
   has 6 baselines).
3. Compute exec_rate per strategy (deterministic from render success).
4. Compute CLIPScore vs Plot2Code ground-truth images (open_clip ViT-L-14
   per spec, Hessel ×2.5 rescale).
5. Run B10 specialist (MatPlotAgent on Plot2Code) for Tier-1 reference.

Estimated time: ~1-2h depending on retry need.

## 5. Layer B-2 ViviBench — Out of scope for v0.3

Spec note: "data not yet public". No further action this session unless
data status changed.

## 6. M5 CLIPScore at scale (Layer A image-axis)

`outputs/prototype/clip_scores/all.json` exists per state.md note:
"CLIPScore at scale: B6 1.949 top, Δ vs S1 +0.008". Image-axis evidence
for Layer A is already collected. Not affected by scope-v3 (CLIPScore is
deterministic image metric, no LLM judge).

## 7. §10 Cross-Task Table (spec §10.2 + §15.1) — actual fillable state

| Layer | Eval | B1 | B2 | B3 | B4 | S1 | B7 | **B6** |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | scope-v3 overall | 0.722 | 0.703 | 0.745 | 0.786 | 0.798 | 0.808 | **0.839** |
| B-1 Text2Vis | Layer A judge on Text2Vis viz (MISALIGNED) | 0.870 | 0.677 | 0.738 | 0.772 | 0.791 | 0.839 | 0.810 |
| B-1 Text2Vis | Native 4-dim reimpl (PENDING) | — | — | — | — | — | — | — |
| B-2 ViviBench | Native 4-dim (DEFERRED) | — | — | — | — | — | — | — |
| B-3 Plot2Code | exec_rate (PENDING at scale) | — | — | — | — | — | — | — |
| B-3 Plot2Code | CLIPScore (PENDING at scale) | — | — | — | — | — | — | — |

Layer A row is publication-ready under current scope-v3 protocol.
B-1 row exists but spec-misaligned. B-2 deferred. B-3 needs computation.

## 8. Tier-1 "within 5-7%p home turf" claim (spec §10.3) — current state

Spec requires:
| Home turf | Specialist | B6 (ours) | Δ |
|---|---|---|---|
| Text2Vis | B8 Text2Vis-original | B6 | within ±0.07 |
| ViviBench | B9 ViviDoc-original | B6 | within ±0.07 |
| Plot2Code | B10 MatPlotAgent | B6 | within ±0.07 |

None of B8/B9/B10 specialists have been run. The claim cannot yet be
established. Currently, **B1 MatPlotAgent on Text2Vis (0.870)** sits as
a proxy for chart-specialist Tier-1 reference, with B6 at 0.810 (Δ =
−0.060, within 5-7%p threshold) — but B1 is not the specialist on
Text2Vis; B8 (Text2Vis-original) would be the proper Tier-1 reference.

## 9. Honest §16 framing options (post-scope-v3)

| Option | Headline | Honest about what's done |
|---|---|---|
| **a** — Layer A only | "B6 SOTA on QG-MDV in-domain (+0.031 over next-best, n=265)" | Layer A is rigorous; held-out layers acknowledged as future work |
| **b** — Layer A + Plot2Code exec_rate + CLIPScore | "B6 SOTA in-domain; Plot2Code generalization within 5-7%p of specialist" | Defensible if B-3 native metrics computed |
| **c** — Layer A + Layer B-1 Text2Vis 4-dim reimpl + Plot2Code | "B6 dominates multi-doc; competitive on held-out single-doc tasks" | Most complete; requires B-1 reimpl + B-3 metrics + B8/B10 specialists |

**Current state supports option (a) directly. Option (b) is ~1-2h
work. Option (c) requires Text2Vis schema lookup + B8/B10 specialist
runs.**

## 10. Recommended next steps (priority order)

1. **Plot2Code native metric measurement** — exec_rate + CLIPScore at
   scale. Deterministic, defensible, no schema-lookup needed. Unblocks
   option (b). ~1h.
2. **Text2Vis 4-dim native reimpl** — requires Text2Vis paper lookup
   to get exact dimensions, then reimpl checklist gen. Unblocks
   option (c). Half-day.
3. **B8 / B10 specialist runs** — Tier-1 reference for §10.3 claim.
   ~1-2h each per benchmark.
4. **Three-seed reporting** (§13 non-negotiable) — seeds 42/43/44
   mean±std on Layer A. ~3-5h.
5. **ViviBench** — deferred; data availability check.

Items 1-2 directly affect paper §10 cross-task table integrity.
Item 4 affects paper §16 robustness claim.
