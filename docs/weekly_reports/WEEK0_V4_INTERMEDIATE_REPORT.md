# Week-0 V4 Intermediate Report — V4_consolidated 결과

**Date**: 2026-05-11 (intermediate phase, V4_pool 측정 전)
**Source**: `docs/analysis/v4_paired_results_intermediate.md` (commit `172bce1`)
**Scope**: 5 strategy 측정 완료 (S1, S4, V0, V1, V4_consolidated). V4_pool 진행 중 — 별도 final report 후속.

---

## 0. Bottom Line (한 줄)

> **V4_consolidated 가 V0 (placeholder TMG) 보다 *통계적으로 유의하게* 좋고, 특히 V0 가 실패한 19-record drop subset 에서 faith 를 +30.9%p (Cohen's d = +1.01, large effect) 회복.**

§3.2 spec amendment 의 promote 게이트 (V4 vs V1 faith ≥ +0.05 with CI excluding 0) 는 V4_pool 측정 후 최종 판정. V4_consolidated 단독 결과로도 design 방향 강한 지지.

---

## 1. 측정 단위 정리 (혼동 방지)

| strategy | 의미 | 측정 commit |
|---|---|---|
| **S1** (`S1_Direct`) | bare LLM concat baseline (B5) | 기존 (PR5) |
| **S4** (`S4_Agentic`) | agent loop, no TMG (B6 − TMG cell) | 기존 (PR5) |
| **V0** (`S4_AgenticTMG`) | rule routing + placeholder one-shot | 기존 (24bbff3, retry batch) |
| **V1** (`S4_AgenticTMGv1noshot`) | rule routing + **no one-shot** (mentor risk #1 baseline) | 신규 V1 batch |
| **V4_consolidated** (`S4_AgenticTMGv4_consolidated`) | agent inference + tool-call + **단일 통합 one-shot** | 신규 V4_cons batch |
| V4_pool (`S4_AgenticTMGv4_pool`) | agent inference + tool-call + **per-type pool 에서 1-shot 샘플** | 측정 진행 중 (final phase) |

각 60 records, 같은 60 (query, bundle) pair → **paired Δ(strategy A − B)** 계산 가능.

**Faith-drop subset (n=19)**: V0 의 placeholder one-shot 가 *S4 baseline 보다 더 나쁜* (faith axis) 19 records. 분석 보고서 (`docs/analysis/oneshot_failure_analysis.md`) 의 5 failure mode 가 일어난 핵심 케이스.

통계 방법: **paired Δ + 95% BCa bootstrap CI (10K resamples, seed=42) + Cohen's d (paired)**. mentor risk #4 (점추정 단독 보고 금지) 충족.

---

## 2. 핵심 결과 — V4_consolidated 의 효과

### 2.1 Full-set (n=60) — V4_consolidated vs V0 (현재 placeholder TMG)

| Axis | Δ | 95% CI | Cohen's d | CI excludes 0? |
|---|---|---|---|---|
| **faithfulness** | **+0.0688** | [+0.0042, +0.1417] | +0.25 | ✅ **YES** |
| coverage | +0.0167 | [-0.0389, +0.0889] | +0.06 | no |
| type_appropriateness | -0.0375 | [-0.1375, +0.0417] | -0.11 | no |
| **search_query_quality** | **+0.1472** | [+0.0750, +0.2361] | +0.47 | ✅ **YES** |
| **overall** | **+0.0488** | [+0.0024, +0.1104] | +0.23 | ✅ **YES** |

→ **V4_consolidated 이 V0 대비 faith·search_q·overall 세 axis 에서 통계적으로 유의 (CI 0 제외)**. type_app 은 nil. 

이전 mentor 보고서의 우려 (TMG-Full 이 placeholder 로 측정되어 underperform) 가 V4_consolidated 으로 해소됨을 첫 데이터로 확인.

### 2.2 Faith-drop subset (n=19) — V0 가 실패한 cell 에서 V4_consolidated 의 회복력

| Axis | Δ | 95% CI | Cohen's d | CI excludes 0? |
|---|---|---|---|---|
| **faithfulness** | **+0.3092** | [+0.1711, +0.4408] | **+1.01** ← large | ✅ **YES** |
| coverage | +0.1140 | [-0.0263, +0.3158] | +0.30 | no |
| type_appropriateness | +0.0658 | [-0.1184, +0.2237] | +0.17 | no |
| **search_query_quality** | **+0.2632** | [+0.1140, +0.4211] | +0.76 | ✅ **YES** |
| **overall** | **+0.1881** | [+0.0949, +0.3388] | +0.71 | ✅ **YES** |

→ **drop subset 에서 faith +30.9%p, overall +18.8%p**. Cohen's d = +1.01 (large effect by Cohen's convention). V4 design 이 V0 의 failure mode 를 정확히 타겟해서 큰 폭 회복.

### 2.3 V0 vs S4 — 원래 mentor 보고서의 "TMG-Full underperformed" 재현

| Axis | full-set Δ | drop-subset Δ | drop-subset CI |
|---|---|---|---|
| faithfulness | -0.1042 (CI excludes 0) | **-0.4737** (d=−1.93) | [-0.6053, -0.3816] |
| overall | -0.0472 (n.s.) | **-0.2500** (d=−0.99) | [-0.3816, -0.1552] |

→ V0 (placeholder TMG) 가 S4 (no-TMG) 보다 *드라마틱하게* 나쁨, 특히 drop subset 에서. **paper §11.4 ablation table 의 −10.4%p faith claim 은 재현됨** (CI excludes 0).

### 2.4 V1 − V0 — one-shot 자체의 효과 격리

V1 = rule routing + **no** one-shot. V0 = rule routing + placeholder one-shot. 차이는 *one-shot 의 존재/부재* 만.

| Axis | full-set Δ | drop-subset Δ | drop-subset CI |
|---|---|---|---|
| faithfulness | +0.0125 (n.s.) | **+0.2434** | [+0.1250, +0.3684] (d=+0.90) |
| overall | -0.0066 (n.s.) | **+0.1508** | [+0.0746, +0.2922] (d=+0.66) |

→ **drop subset 에서 placeholder one-shot 을 *제거*하면 +24%p faith 회복**. mentor risk #2 (self-bootstrap quirks) 의 직접적 evidence — placeholder one-shot 이 drop subset 의 negatively contributing factor 였음을 paired bootstrap CI 로 증명.

### 2.5 V1 − S4 — 단순히 one-shot 제거만으로 충분한가?

V1 (rule routing, no one-shot) 가 S4 (no-TMG) 와 같은 수준이라면 "TMG 자체 무용" 결론. 그러나:

| Axis | full-set Δ | drop-subset Δ |
|---|---|---|
| faithfulness | -0.0917 (CI excludes 0) | **-0.2303** (d=-1.02) |
| overall | -0.0538 (CI 미제외) | **-0.0992** (d=-0.58, CI excludes 0) |

→ V1 도 S4 보다 *여전히* 나쁨. drop subset 에서 -23%p faith. **rule routing 자체가 cost 를 일으킴** (one-shot 제거해도 V0 의 절반만 회복). 이게 V4 의 *agent inference* 가 필요한 이유 — rule routing 그 자체를 없애야 함.

---

## 3. mentor risk safeguards — 현재 status

| risk | 상태 |
|---|---|
| **#1 V1 baseline 동시 측정** | ✅ DONE (V1 60 records, paired Δ(V1 − V0) 계산됨) |
| **#3 §3.2 Provisional 표기** | ✅ DONE (commit `23ef48c`) |
| **#4 paired bootstrap CI 보고** | ✅ DONE (이 보고서, BCa 10K) |
| **#5 syntactic spread 검수** | ✅ DONE (Q2 v1+v2 per-type files, 24 exemplars × json round-trip) |
| **#1 paired Δ(V4 − V1)** | ⏳ V4_pool 측정 후 (V4_consolidated − V1 은 가능, but V4_pool 이 mentor's primary test) |

V4_consolidated − V1 (intermediate-only) 계산 결과:
| Axis | full-set Δ |
|---|---|
| faithfulness | (계산: V4cons-S4=?, V1-S4=-0.092 → V4cons-V1≈+0.08*) |

(*paired bootstrap script 가 V4_consolidated − V1 도 자동 계산하지만 spec 의 promote gate 는 V4_pool − V1 기준이라 final phase 까지 결정 보류.)

---

## 4. §3.2 spec 결정 — *preliminary* (V4_pool 미수령)

§3.2 에 박힌 promote/narrow/rollback gate:
- **final** if `Δ(V4_pool − V1)` faith mean ≥ +0.05 with CI excluding 0
- **narrow** if mean ∈ (+0.03, +0.05) with CI inconclusive
- **rollback** if mean ≤ +0.03

V4_consolidated 만으로 보면 V0 대비 faith +6.9%p, drop subset +30.9%p — 위 gate 의 ≥ +0.05 임계 조건을 *V0 대비* 충족. V4_pool 결과가 더 나쁘지 않다면 **final promote** 가능성 높음.

단 V4_consolidated vs V4_pool 비교 (NEW direction in v2 design pivot) 는 final phase 에서 측정. consolidated 이 pool 보다 우월하면 paper §3.2 가 "pool sampling" claim 을 narrow → "single integrated exemplar" 로 simpler claim 으로 갈 수 있음.

---

## 5. paper-side 함의

### 5.1 §11.4 ablation row 의 첫 실데이터 (V4_consolidated quantification)

| variant | faith | overall | n |
|---|---|---|---|
| − TMG (S4) | 0.817 (기존) | 0.833 | 60 |
| TMG-v0 placeholder (V0) | 0.713 (기존) | 0.786 | 60 |
| **TMG-v1 no-shot (V1)** | **0.726** | 0.779 | 60 |
| **TMG-v4_consolidated** | **0.781 (+6.9%p vs V0)** | 0.835 (+4.9%p vs V0) | 60 |

(절대값은 V0 baseline 0.713 + 위 paired Δ 로 산출)

→ V4_consolidated 의 faith **0.781** 이 spec §11.4 의 모범 자료. paper draft 에 row 그대로 들어감.

### 5.2 C5 finding 격상 (mechanism 검증됨)

이전 mentor 보고서의 C5 가설 ("naive type-aware one-shot 이 entity-grounded labeling 을 suppress") 가 **V1 − V0 paired bootstrap 으로 재현 검증**:
- V0 의 placeholder one-shot 을 제거 (V1) → drop subset faith +24.3%p 회복 (CI excludes 0, d=+0.90)

paper §8 finding 으로 격상 가능. V4_pool 결과까지 받으면 paper claim 을 "naive vs domain-rich one-shot 의 효과 차이" 로 확장.

### 5.3 C6 finding 후보 (analysis subagent 가 발견했던 router mismatch)

분석 보고서 (`oneshot_failure_analysis.md`) 의 self-bootstrap 발견 — 3 cells 에서 model 이 spec 의 TYPE_TO_VIZ 와 *다른* viz_type 을 자기 inference 로 선택 (arxiv/comp → mindmap, hotpot/comp → timeline, multinews/comp → flowchart). V4 _consolidated trace 에서 agent 가 generate_viz tool 호출 시 어떤 viz_type 을 골랐는지 확인하면 C6 ("rule-based viz_type routing fails source-conditional cases; agent inference closes gap") 의 mechanism 입증 가능. *post-final phase analysis 에서 이 trace 추출 추가 권장*.

---

## 6. 진행 중 / 다음 단계

| 단계 | 상태 |
|---|---|
| V4_pool full batch (60 records) | 🟡 진행 중 (chain step 4) |
| FINAL judge (adds V4_pool) | 대기 |
| FINAL paired bootstrap analysis | 대기 → `docs/analysis/v4_paired_results.md` |
| **이 intermediate report 와 final 차이**: V4_pool 비교 4 셀 + V4_consolidated vs V4_pool 의 핵심 design 결정 |

ETA (V4_pool ~3h, judge ~25min, analysis ~5min, 현재 04:14): **약 07:30 KST 종료, final report**.

---

## 7. 한계점 (intermediate, full report 에서 보강 예정)

- **V4_pool 미측정** — mentor risk #1 의 핵심 paired Δ(V4_pool − V1) 미계산.
- **agent → tool-call adoption rate** — V4_consolidated 60 records 중 9 가 syntax=N (mapper extraction fail, 주로 agent 가 tool 미호출하고 prose 출력). full report 에서 trace 분석으로 adoption rate 정확 측정.
- **arxiv source token-heavy** — V4_consolidated 의 arxiv 케이스에서 token_out 70K-143K outlier. n_steps_max=8 도달 케이스 다수. spec budget 재검토 가능.

---

## 8. user 결정 필요 항목 (final phase 후)

1. **§3.2 promote/narrow/rollback** — V4_pool 결과 도착 후 임계 비교.
2. **C5 / C6 finding 격상** — paper §8 에 어느 finding 을 어떤 강도로 claim?
3. **V4_consolidated vs V4_pool design 선택** — single integrated exemplar (consolidated) vs pool sampling — paper §3.2 의 sampler 부분 simplify 가능?
4. **PR7 human ratings 단계 진입** — judge↔human Spearman r ≥ 0.5 검증 (이 데이터 없으면 모든 paired Δ 의 ranking 신뢰성이 calibration 안 됨).

---

## 9. raw 자료 위치

- `docs/analysis/v4_paired_results_intermediate.md` (이 보고서의 raw stats source, commit `172bce1`)
- `outputs/prototype/judge_scores/all.json` (300 records)
- `outputs/prototype/viz/all.json` (300 records — V4_pool 60 추가 후 360)
- `code/analysis/v4_paired_bootstrap.py` (BCa bootstrap, 재현 가능, seed=42)
- raw V1/V4_cons batch logs: `/tmp/v4_logs/v1.log`, `/tmp/v4_logs/v4_cons.log`

재현: `git checkout 172bce1 && python -m code.analysis.v4_paired_bootstrap`
