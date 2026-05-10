# V4 measurement — paired bootstrap CI + Cohen's d

**Source**: `outputs/prototype/judge_scores/all.json` (300 records)
**Bootstrap**: BCa, 10000 resamples, seed=42, α=0.05
**Cohen's d**: paired (mean of Δ ÷ SD of Δ)
**Available strategies**: S1_Direct, S4_Agentic, S4_AgenticTMG, S4_AgenticTMGv1noshot, S4_AgenticTMGv4_consolidated

**Faith-drop subset** (records where V0 < S4 on faith axis): 19 records

## V0 − S4 (placeholder TMG vs no-TMG)

### Full-set (all paired records)

| Axis | Δ | 95% CI | Cohen's d | n | CI excludes 0? |
|---|---|---|---|---|---|
| faithfulness | -0.1042 | [-0.1917, -0.0292] | -0.32 | 60 | **YES** |
| coverage | -0.0389 | [-0.1167, +0.0444] | -0.12 | 60 | no |
| type_appropriateness | -0.0042 | [-0.0833, +0.0625] | -0.01 | 60 | no |
| search_query_quality | -0.0417 | [-0.1167, +0.0278] | -0.14 | 60 | no |
| **overall** | -0.0472 | [-0.1111, +0.0090] | -0.20 | 60 | no |

### Faith-drop subset (n=19)

| Axis | Δ | 95% CI | Cohen's d | n | CI excludes 0? |
|---|---|---|---|---|---|
| faithfulness | -0.4737 | [-0.6053, -0.3816] | -1.93 | 19 | **YES** |
| coverage | -0.2281 | [-0.3860, -0.0702] | -0.64 | 19 | **YES** |
| type_appropriateness | -0.1316 | [-0.3421, -0.0263] | -0.40 | 19 | **YES** |
| search_query_quality | -0.1667 | [-0.3333, -0.0175] | -0.46 | 19 | **YES** |
| **overall** | -0.2500 | [-0.3816, -0.1552] | -0.99 | 19 | **YES** |

## V1 − S4 (rule routing, no one-shot)

### Full-set (all paired records)

| Axis | Δ | 95% CI | Cohen's d | n | CI excludes 0? |
|---|---|---|---|---|---|
| faithfulness | -0.0917 | [-0.1708, -0.0250] | -0.32 | 60 | **YES** |
| coverage | -0.0667 | [-0.1472, +0.0111] | -0.21 | 60 | no |
| type_appropriateness | -0.0292 | [-0.1208, +0.0417] | -0.09 | 60 | no |
| search_query_quality | -0.0278 | [-0.1278, +0.0583] | -0.08 | 60 | no |
| **overall** | -0.0538 | [-0.1231, +0.0024] | -0.22 | 60 | no |

### Faith-drop subset (n=19)

| Axis | Δ | 95% CI | Cohen's d | n | CI excludes 0? |
|---|---|---|---|---|---|
| faithfulness | -0.2303 | [-0.3487, -0.1447] | -1.02 | 19 | **YES** |
| coverage | -0.1053 | [-0.1930, -0.0263] | -0.57 | 19 | **YES** |
| type_appropriateness | -0.0263 | [-0.1579, +0.0263] | -0.13 | 19 | no |
| search_query_quality | -0.0351 | [-0.1930, +0.1228] | -0.10 | 19 | no |
| **overall** | -0.0992 | [-0.1667, -0.0120] | -0.58 | 19 | **YES** |

## V1 − V0 (one-shot effect, rule held)

### Full-set (all paired records)

| Axis | Δ | 95% CI | Cohen's d | n | CI excludes 0? |
|---|---|---|---|---|---|
| faithfulness | +0.0125 | [-0.0688, +0.0854] | +0.04 | 60 | no |
| coverage | -0.0278 | [-0.1083, +0.0389] | -0.10 | 60 | no |
| type_appropriateness | -0.0250 | [-0.1083, +0.0417] | -0.08 | 60 | no |
| search_query_quality | +0.0139 | [-0.0528, +0.0889] | +0.05 | 60 | no |
| **overall** | -0.0066 | [-0.0674, +0.0543] | -0.03 | 60 | no |

### Faith-drop subset (n=19)

| Axis | Δ | 95% CI | Cohen's d | n | CI excludes 0? |
|---|---|---|---|---|---|
| faithfulness | +0.2434 | [+0.1250, +0.3684] | +0.90 | 19 | **YES** |
| coverage | +0.1228 | [+0.0000, +0.2544] | +0.42 | 19 | **YES** |
| type_appropriateness | +0.1053 | [+0.0000, +0.2632] | +0.39 | 19 | no |
| search_query_quality | +0.1316 | [+0.0088, +0.3070] | +0.40 | 19 | **YES** |
| **overall** | +0.1508 | [+0.0746, +0.2922] | +0.66 | 19 | **YES** |

## V4_pool − V1 (MENTOR RISK #1)
  *skipped — strategies missing (S4_AgenticTMGv1noshot or S4_AgenticTMGv4_pool not in judge_scores)*

## V4_pool − V0 (V4 vs current placeholder)
  *skipped — strategies missing (S4_AgenticTMG or S4_AgenticTMGv4_pool not in judge_scores)*

## V4_pool − S4 (V4 vs no-TMG baseline)
  *skipped — strategies missing (S4_Agentic or S4_AgenticTMGv4_pool not in judge_scores)*

## V4_consolidated − V4_pool (NEW direction)
  *skipped — strategies missing (S4_AgenticTMGv4_pool or S4_AgenticTMGv4_consolidated not in judge_scores)*

## V4_consolidated − V0

### Full-set (all paired records)

| Axis | Δ | 95% CI | Cohen's d | n | CI excludes 0? |
|---|---|---|---|---|---|
| faithfulness | +0.0688 | [+0.0042, +0.1417] | +0.25 | 60 | **YES** |
| coverage | +0.0167 | [-0.0389, +0.0889] | +0.06 | 60 | no |
| type_appropriateness | -0.0375 | [-0.1375, +0.0417] | -0.11 | 60 | no |
| search_query_quality | +0.1472 | [+0.0750, +0.2361] | +0.47 | 60 | **YES** |
| **overall** | +0.0488 | [+0.0024, +0.1104] | +0.23 | 60 | **YES** |

### Faith-drop subset (n=19)

| Axis | Δ | 95% CI | Cohen's d | n | CI excludes 0? |
|---|---|---|---|---|---|
| faithfulness | +0.3092 | [+0.1711, +0.4408] | +1.01 | 19 | **YES** |
| coverage | +0.1140 | [-0.0263, +0.3158] | +0.30 | 19 | no |
| type_appropriateness | +0.0658 | [-0.1184, +0.2237] | +0.17 | 19 | no |
| search_query_quality | +0.2632 | [+0.1140, +0.4211] | +0.76 | 19 | **YES** |
| **overall** | +0.1881 | [+0.0949, +0.3388] | +0.71 | 19 | **YES** |

## Decision summary (per spec §3.2 Provisional gates)

§3.2 amendment becomes:
- **final** if `Δ(V4_pool − V1)` faith mean ≥ +0.05 with CI excluding 0
- **narrow** (drop per-type pool claim, keep agent-inference framing) if mean ∈ (+0.03, +0.05) with CI inconclusive
- **rollback** if mean ≤ +0.03 (tool-call complexity not justified)
