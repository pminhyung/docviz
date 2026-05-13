# §10 Cross-Task Summary (v0.3 SKELETON)

> Populates after Phases 6, 7, 8 produce per-layer scores.

## 10.1 Three Evaluation Settings + 1 Pillar Ablation

| Setting | Method | n | Eval | Phase produces |
|---|---|---|---|---|
| Layer A in-domain | QG-MDV (ours) | 268 | 4-axis text + M5 CLIPScore | Phase 7 |
| Layer B-1 held-out | Text2Vis | 100 | Text2Vis 4-dim reimpl (Qwen judge) | Phase 5 |
| Layer B-2 held-out | ViviBench | 101 | ViviBench 4-dim reimpl (Qwen judge) | Phase 5 |
| Layer B-3 held-out | Plot2Code | 50 | exec-rate + CLIPScore vs target | Phase 5 ✓ |
| Layer D pillar ablation | QG-MDV variants | 268 × 3 | same 4-axis text | Phase 8 |

## 10.2 Cross-Task Average (best cross-task average claim)

The "best cross-task average across 4 evaluation settings" headline
metric averages B6's per-layer overall score across the 4 settings,
then compares to the same average for each baseline. Δ_avg(B6 - X) >
0 establishes the cross-task lead claim.

| Layer | B1 | B2 | B3 | B4 | B5 | B7 | **B6** |
|---|---|---|---|---|---|---|---|
| Layer A in-domain (n=268) | `<P7>` | `<P7>` | `<P7>` | `<P7>` | `<P7>` | `<P7>` | `<P7>` |
| Layer B-1 Text2Vis (n=100) | `<P5>` | `<P5>` | `<P5>` | `<P5>` | `<P5>` | `<P5>` | `<P5>` |
| Layer B-2 ViviBench (n=101) | `<P5>` | `<P5>` | `<P5>` | `<P5>` | `<P5>` | `<P5>` | `<P5>` |
| Layer B-3 Plot2Code (n=50) | (matplotlib) | 0.61 | 0.58 | 0.63 | 0.60 | 0.57 | 0.61 |
| **Cross-task mean** | `<P9>` | `<P9>` | `<P9>` | `<P9>` | `<P9>` | `<P9>` | `<P9>` |

Plot2Code row pre-filled from v0.3 prototype 5-record preflight
(CLIPScore Hessel-rescaled). exec_rate for B6 on Plot2Code is 0.20 (vs
B5/B7 1.00/0.80) — **Tier-1 framing direction** (held-out single-doc
weakness, multi-doc strength).

## 10.3 Tier-1 Home-Turf Framing

Per amendment §10 line 437 / §16 R7:
- **Tier 1** (specialist on home turf): B8 Text2Vis-original on
  Text2Vis, B9 ViviDoc-original on ViviBench, B10 MatPlotAgent on
  Plot2Code. Run only on their home turf to provide the "within 5-7%p"
  reference.
- **Tier 2** (B1-B7 + B6 cross-method): same model (Qwen3.5-397B)
  on all 4 evaluation settings.
- **Tier 3** (specialists off-home-turf): not run — out of scope.

The headline "within 5-7%p" claim is established by comparing B6's
Layer B-1/B-2 score to B8/B9 (specialists on their home turf):

| Home turf | Specialist | B6 (ours) | Δ (specialist - B6) |
|---|---|---|---|
| Text2Vis | B8 `<P5>` | `<P5>` | `<P5>` |
| ViviBench | B9 `<P5>` | `<P5>` | `<P5>` |
| Plot2Code | B10 `<P5>` | `<P5>` | `<P5>` |

Pass criterion: |Δ| ≤ 0.07 on all 3 home turfs.

## 10.4 Multi-Doc Setting Superiority (+8%p claim)

The "+8%p in multi-doc setting" claim is established on Layer A:

- Δ(B6 - best(B1, B2, B3, B4, B5, B7)) on Layer A overall ≥ +0.08
- Direction (best baseline = X): paired bootstrap p < 0.05 (1-sided)
- Effect size (Cohen's d_z) ≥ +0.3

Populate from Phase 7 result + Phase 9 paired bootstrap.

## 10.5 Pillar-Wise Contribution (Layer D)

Per Phase 8 ablation result (Layer D):

| Pillar | Removed → Δ overall vs Full | Direction |
|---|---|---|
| TMG | `<P8>` | expected significant |
| SAO | `<P8>` | expected small (cosmetic) |
| CIS | deferred to Week-1 | — |

If TMG ablation shows ≥ +0.05 contribution, the headline 3-pillar
claim ("each pillar contributes measurable gain") holds for TMG and
SAO; CIS's contribution awaits Week-1 server-side flag implementation.
