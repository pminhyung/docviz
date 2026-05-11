# Week-0 V4 Final Report — 6 strategy 측정 종합 (V4_pool 포함)

**Date**: 2026-05-11 09:00 KST (chain ALL STEPS DONE)
**Source**: `docs/analysis/v4_paired_results.md` (commit pending), `outputs/prototype/judge_scores/all.json` (360 records)
**Scope**: 6 strategy 모두 측정 + paired bootstrap CI 완료. 멘토 readable.

---

## 0. Bottom Line — 솔직히 (한 줄)

> **V4 가 V0 를 통계적으로 유의하게 회복했다 (drop subset faith +30.9%p, d=+1.01). 그러나 mentor risk #1 의 핵심 게이트 — Δ(V4_pool − V1) faith CI 0 제외 — 는 *통과하지 못했다*. §3.2 amendment 는 promote 대신 NARROW. 더 근본적으로, S4 (no-TMG) 가 모든 V4/V0/V1 변형보다 faith axis 에서 우수 — TMG pillar 자체의 net-positive 가 의문.**

---

## 1. 절대값 비교 — faith axis 만 (drop-subset, n=19)

| Strategy | faith mean | drop-subset 에서의 위치 |
|---|---|---|
| **S4** (no-TMG, agent loop only) | **0.954** (baseline) | 🟢 best |
| V4_consolidated | 0.789 | drop subset 의 ~83% 회복 |
| V4_pool | 0.789 | 동일 |
| V1 (rule routing, no one-shot) | 0.724 | drop subset 의 ~76% 회복 |
| V0 (rule routing + placeholder one-shot) | 0.480 | 🔴 worst — placeholder TMG 의 catastrophic fail |

(파생값: drop subset = V0 가 S4 보다 worse 한 19 records. S4 평균 faith 0.954 ↔ V0 0.480 = −47.4%p paired Δ — d=−1.93 large.)

**눈에 띄는 사실**: TMG 를 *전혀 적용하지 않은* S4 가 모든 TMG 변형 (V0, V1, V4_pool, V4_consolidated) 보다 drop subset 에서 더 잘 한다. V4 의 architecture 가 V0 의 손해를 *상당히* 회복하지만 S4 baseline 까지는 못 따라잡음.

---

## 2. mentor risk #1 — V4_pool − V1 paired Δ (핵심 gate)

§3.2 spec 의 promote/narrow/rollback gate:
- **final** if `Δ(V4_pool − V1)` faith mean ≥ +0.05 **with CI excluding 0**
- **narrow** if mean ∈ (+0.03, +0.05) **with CI inconclusive**
- **rollback** if mean ≤ +0.03

**측정 결과 (full-set, n=60)**:
- faith Δ = **+0.0458** | 95% CI = **[−0.0500, +0.1417]** | Cohen's d = +0.12
- → mean **NARROW zone** (+0.03 < +0.046 < +0.05) 에 가까움
- → CI 가 **0 을 포함** → "inconclusive"

**결정**: **NARROW** — paper §3.2 의 *per-type curated exemplar pool* claim 은 drop, *agent-inference framing* 만 keep. tool-call architecture 의 추가 복잡도가 V1 대비 통계적으로 정당화되지 못함.

drop subset (n=19) 도 같은 결론: faith Δ = +0.066 [−0.079, +0.191], CI 0 포함.

---

## 3. 6 strategy paired comparison 종합 (full-set, n=60, faith axis)

| pair | Δ faith | 95% CI | Cohen's d | CI excludes 0 | 의의 |
|---|---|---|---|---|---|
| V0 − S4 | **−0.104** | [−0.192, −0.029] | −0.32 | **YES** | placeholder TMG 가 no-TMG 보다 나쁨 (mentor 보고서 재현) |
| V1 − S4 | **−0.092** | [−0.171, −0.025] | −0.32 | **YES** | rule routing 만으로도 net negative |
| V1 − V0 | +0.013 | [−0.069, +0.085] | +0.04 | no | one-shot 제거의 effect (full-set 에서 null) |
| V4_pool − V0 | +0.058 | [−0.029, +0.140] | +0.17 | no | V4 가 V0 회복 (border) |
| V4_pool − V1 | +0.046 | [−0.050, +0.142] | +0.12 | no | **mentor primary gate 미통과** |
| V4_pool − S4 | −0.046 | [−0.131, +0.033] | −0.14 | no | V4_pool 도 S4 보다 약간 나쁨 (n.s.) |
| V4_cons − V0 | **+0.069** | [+0.004, +0.142] | +0.25 | **YES** | V4_cons 가 V0 회복 (significant) |
| V4_cons − V4_pool | +0.010 | [−0.071, +0.094] | +0.03 | no | 둘 design 본질적 동일 (faith axis) |

---

## 4. drop subset (n=19) — V0 가 망가진 records 에서의 회복력

이 19 records 에서 placeholder TMG 의 drop 패턴 (mentor risk #2 의 근거) 발생.

| pair | drop-subset Δ faith | 95% CI | Cohen's d | CI excludes 0 |
|---|---|---|---|---|
| V0 − S4 | **−0.474** | [−0.605, −0.382] | **−1.93** | **YES** ← V0 의 catastrophic |
| V1 − S4 | −0.230 | [−0.349, −0.145] | −1.02 | **YES** |
| V1 − V0 | **+0.243** | [+0.125, +0.368] | +0.90 | **YES** ← one-shot 제거가 절반 회복 |
| V4_pool − V0 | **+0.309** | [+0.145, +0.454] | +0.88 | **YES** |
| V4_pool − V1 | +0.066 | [−0.079, +0.191] | +0.21 | no |
| V4_pool − S4 | **−0.165** | [−0.283, −0.066] | −0.68 | **YES** ← V4_pool 도 여전히 S4 못 따라감 |
| V4_cons − V0 | **+0.309** | [+0.171, +0.441] | **+1.01** | **YES** |
| V4_cons − V4_pool | 0.000 | [−0.171, +0.145] | 0.00 | no |

핵심: **drop subset 에서 V4 strategies 는 V0 대비 +30.9%p (대형 effect) 회복하지만 S4 까지 −16.5%p 부족**. 즉 *agent inference + tool* 으로 V0 의 손해를 매꾸지만, *애초에 TMG 자체* 가 net-positive 가 아니라는 implication.

---

## 5. V4_consolidated vs V4_pool — design 결정

분석 보고서 (`oneshot_failure_analysis.md`) 의 새 directive 였던 *consolidated single one-shot* 변형은 *pool sampling* 변형 대비:

| axis | full-set Δ | drop-subset Δ |
|---|---|---|
| faith | +0.010 (n.s.) | 0.000 (n.s.) |
| coverage | +0.014 (n.s.) | −0.044 (n.s.) |
| type_app | +0.029 (n.s.) | −0.013 (n.s.) |
| **search_query_quality** | **+0.067 [+0.017, +0.136] d=+0.29** ✅ | +0.088 (n.s.) |
| overall | +0.030 (n.s.) | +0.008 (n.s.) |

**결정 권장**: **consolidated 와 pool 본질적 동일** (faith·overall null). consolidated 가 search_q 에서 약간 우위 (CI excludes 0, full-set 만). paper §3.2 의 *pool sampling vs consolidated* 의 design 선택은:

- **paper §11.4 ablation** 에 둘 다 row 로 넣음 — paired Δ null 이 자체 finding ("두 design 모두 작동, 거의 동일")
- **paper §3.2 implementation** 은 *consolidated* 로 단순화 — sampler 코드 / per-query deterministic hash 가 필요 없어짐, 더 간단한 architecture

---

## 6. §3.2 spec amendment 결정 — NARROW

### 6.1 Provisional → NARROW

`PAPER_MASTER_SPEC.md` §3.2 의 "Status: Provisional" 블록을 **NARROW** 로 promote:

원래 amendment 의 두 핵심 claim:
1. ✅ "agent reasons over query and source content to select viz_type from a deterministic 6-type pool" — **유지**
2. ✗ "per-type exemplar pool" + "dual constraint (faith ≥ 0.75 + syntactic spread)" — **drop**

대신 **single integrated exemplar per viz_type** (consolidated variant) 로 spec 단순화. paper §11.4 에 v0/v1/v4_pool/v4_consolidated 4-row ablation table 보유.

### 6.2 더 큰 의문 — TMG pillar 자체

데이터가 보여주는 우려: **모든 TMG 변형 (V0/V1/V4_pool/V4_consolidated) 이 S4 (no-TMG) 보다 faith 에서 약함**:
- V0 −10.4%p (CI excludes 0)
- V1 −9.2%p (CI excludes 0)
- V4_pool −4.6%p (n.s.)
- V4_cons −3.6%p (n.s.)

V4 가 V0 회복은 했지만 *S4 baseline 까지는 못 도달*. paper §3.2 의 "TMG pillar 가 method contribution" 이라는 claim 자체가 데이터로 *지지받지 못함*.

3 가지 honest 옵션:
- **A. NARROW (위)**: TMG-v4 (consolidated) 형태로 spec 유지, S4 vs V4_cons 가 n.s. 라서 "harmless equivalent" 로 frame.
- **B. ROLLBACK**: TMG pillar 자체를 §3 contribution 에서 빼고, §11.4 에 "negative finding" 으로만 보존. Method paper claim 은 CIS + SAO 두 pillar 로 축소.
- **C. PIVOT**: TMG pillar 의 *prompt engineering* 자체가 성능을 저해한다는 mechanism finding 으로 격상. "extra prompt engineering can hurt agentic pipelines when source is rich enough" 라는 negative-finding-as-contribution.

**권장**: **A** (NARROW), 단 **C** 의 negative finding 도 paper §8 candidate 로 강력히 추가. mentor 검토 후 결정.

---

## 7. mentor risk safeguards — 최종 status

| risk | 상태 | 결과 |
|---|---|---|
| **#1 V1 baseline 측정** | ✅ DONE | Δ(V4_pool − V1) faith +0.046, CI [−0.05, +0.14] — primary gate 미통과 |
| **#3 §3.2 Provisional 표기** | ✅ DONE | NARROW 로 promote 권장 |
| **#4 paired bootstrap CI 보고** | ✅ DONE | 8 paired comparison × full-set + drop-subset, BCa 10K |
| **#5 syntactic spread 검수** | ✅ DONE | 24 exemplars (10-type 확장 후 30+10) sidecar JSON, smoke 9/9 pass |

mentor's risk #2 (self-bootstrap quirks) 는 V1 vs V0 데이터로 검증됨 — drop subset 에서 placeholder one-shot 제거가 +24.3%p faith 회복 (CI excludes 0, d=+0.90). placeholder one-shot 이 negative contributor 였음 empirical 입증.

---

## 8. paper-side 함의

### 8.1 §11.4 ablation table — 5-row 채워짐

| variant | faith mean (n=60) | overall (n=60) |
|---|---|---|
| − TMG (S4) | 0.817 | 0.833 |
| TMG-v0 (placeholder rule) | 0.713 | 0.786 |
| TMG-v1 (rule, no one-shot) | 0.726 | 0.779 |
| TMG-v4 pool (agent-inference + tool) | 0.771 | 0.852 |
| TMG-v4 consolidated (single integrated) | 0.781 | 0.835 |

paper §11.4 의 ablation 표가 5-row real-data 로 채워짐. TMG의 negative 효과 + V4 의 회복력 + S4 의 우수성 모두 표현.

### 8.2 C5 finding (paper §8 강력 후보)

mentor 보고서의 C5 hypothesis ("naive type-aware one-shot can suppress entity-grounded labeling") 가 **V1 − V0 paired bootstrap 으로 입증** (drop subset faith +24.3%p, CI excludes 0, d=+0.90). placeholder one-shot 자체가 negative contributor.

### 8.3 C6 finding 후보 — TMG net-negative on drop subset

새 finding: "TMG pillar 의 어떤 design (rule-based 또는 agent-inference) 도 drop subset 에서 *no-TMG* 를 유의하게 능가하지 못함." 이는 *agentic pipeline 에서 추가 prompt engineering 의 한계* 라는 paper-level claim 으로 격상 가능.

### 8.4 C7 finding 후보 — agent inference 가 routing 정확성 회복

V4_pool 과 V4_consolidated 모두 V0 의 catastrophic drop 을 +30%p 회복. 이는 **rule-based viz_type routing 의 실패를 agent inference 가 자동 fix** 한다는 evidence — `oneshot_failure_analysis.md` 의 "model already knows the right viz_type" 발견을 paired bootstrap CI 로 강화.

---

## 9. 한계점 (final report 기준)

- **Δ(V4_pool − V1) primary gate 통과 못함**: tool-call architecture complexity 의 통계적 정당화 부족. paper claim 을 NARROW 로 줄여야 함.
- **S4 vs V4_cons full-set faith Δ = -3.6%p (n.s.)**: V4 design 이 *S4 baseline 을 능가하지 못함*. TMG contribution 자체에 대한 의문.
- **single-judge bias 미해소**: Qwen3.6-27B 가 query gen + viz gen + judge 모두 담당. PR7 human ratings + closed-API cross-judge (GPT-5/Opus 4.6) 가 ranking 신뢰성의 최종 검증.
- **n=60, drop subset n=19**: 통계 power 한계. Week-1 350 bundle scale-up 후 재측정 필요.
- **agent → tool-call adoption rate**: V4_pool 9 syntax-fail, V4_cons 9 syntax-fail (각 60 중 15%) — 다수가 "agent 가 tool 미호출하고 prose emit" 패턴. tool-call interface 가 vLLM Qwen3.6 에서 100% 안정적이지 않음.

---

## 10. 다음 단계 — user 결정 필요 항목

### 즉시 결정
1. **§3.2 amendment 최종 형태** — NARROW (option A) vs ROLLBACK (B) vs PIVOT-as-negative-finding (C)?
2. **Provisional → final 확정 commit** — 어느 형태든 §3.2 의 Status: Provisional 블록을 정리.
3. **C5/C6/C7 paper §8 finding 격상 어디까지?**

### Week-1 진입 결정
4. **PR7 human ratings collection** — 30-viz template (`outputs/prototype/human_ratings/template.csv`) 두 rater fill → judge↔human Spearman r ≥ 0.5 검증.
5. **Closed-API activation** — GPT-5 judge gen + Opus 4.6 score per spec §8.2 cross-judge protocol.
6. **350 bundle scale-up** — 현재 evidence 가 n=60 에서 도출. effect size 최종 입증을 위해 scale-up 후 재측정.

### Method 의 미래 (mentor escalate)
7. **TMG pillar 의 future-work framing** — 본 데이터가 TMG net-positive 를 지지하지 못함을 *honest 하게* paper 에 어떻게 reflect 할 것인가?

---

## 11. raw 자료 위치

| | 경로 | commit |
|---|---|---|
| 데이터 | `outputs/prototype/judge_scores/all.json` (360 records) | TBD |
| 데이터 | `outputs/prototype/viz/all.json` (360 records) | TBD |
| 분석 | `docs/analysis/v4_paired_results.md` (191 lines) | TBD |
| 분석 (intermediate) | `docs/analysis/v4_paired_results_intermediate.md` | `172bce1` |
| 분석 (raw failure) | `docs/analysis/oneshot_failure_analysis.md` | `b90eda1` |
| 분석 (review) | `docs/analysis/tmg_oneshot_pool_review.md` | `be43b1d` |
| 코드 | `code/agent_tools/generate_viz.py`, `code/pipelines/{tmg, s4_agentic_tmg}.py` | various |
| 사이드카 | `code/agent_tools/oneshot_pool.json` (10 viz_type × 3 pool + 1 consolidated) | `b3bebcf` |
| 분석 script | `code/analysis/v4_paired_bootstrap.py` (BCa, 10K, seed=42, no scipy) | `963a370` |
| chain runner | `code/scripts/v4_chain.sh` (6-step intermediate→final) | `1e56b4a` |
| 멘토 보고서 (이 파일) | `docs/weekly_reports/WEEK0_V4_FINAL_REPORT.md` | TBD |
| 멘토 보고서 (intermediate) | `docs/weekly_reports/WEEK0_V4_INTERMEDIATE_REPORT.md` | `4840c4c` |

재현: `git checkout <final commit> && python -m code.analysis.v4_paired_bootstrap`
