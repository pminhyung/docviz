# Phase-2 Report — 3-seed (seeds 42/43/44)

## Primary metrics (mean±std)

| arm | node_f1 | path_f1 | **evidence_f1** | intent_cov | render |
|---|---|---|---|---|---|
| B5 | 0.076±0.009 | 0.021±0.005 | **0.000±0.000** | 0.393±0.033 | 1.00 |
| B7 | 0.089±0.005 | 0.010±0.001 | **0.000±0.000** | 0.337±0.017 | 1.00 |
| B6 full | 0.090±0.004 | 0.000±0.000 | **0.337±0.004** | 0.433±0.019 | 1.00 |
| B6 -SEF | 0.080±0.005 | 0.000±0.000 | **0.034±0.007** | 0.427±0.005 | 1.00 |
| B6 -VSC | 0.094±0.011 | 0.001±0.001 | **0.159±0.160** | 0.427±0.009 | 1.00 |

## Ablation + gate

- **SEF effect** (Evidence F1 drop when −SEF): mean Δ=-0.302 over 3 seeds; proven in 3/3.
- **VSC effect** (violation reduction vs −VSC): proven in 0/3 — marginal on Qwen-397B (direct DSL already clean).
- **Strict 4-metric gate**: 1.3/4 metrics pass +0.020 (mean). Evidence F1 (SAO) is the discriminating metric; node/path/intent are gold-floored across all arms.

## Verdict (user framing)

Lead with **Evidence F1 (SAO) + SEF ablation** as the QG-MDV contribution that distinguishes it from MD-QA. node/path/intent at floor = single-pass gold limitation (consistent with Phase-1). VSC reframed as a deterministic validity *guarantee* whose violation-reduction value is backbone-dependent.