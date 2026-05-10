# Week 0 후속 액션 가이드 — 연구 agent용

**작성일**: 2026-05-10
**대상**: 서버에서 실험을 실행하는 연구 agent
**참조**: `WEEK0_MENTOR_REPORT_PRE_TMG.md`, `WEEK0_MENTOR_REPORT_POST_TMG.md`
**목표**: Week 0 결과를 paper-grade evidence로 closing하고, 다음 단계(Week 1) 진입 결정의 근거를 만든다.

---

## 0. 지금 우리가 어디 있는가

### 우리 연구의 핵심 주장
> DocViz-Agent (3개 핵심 기능: 반복 검색 / 타입별 라우팅 / 출처 부착)가 단순 LLM concat baseline 보다 multi-document query-grounded multi-viz 생성에서 의미있게 낫다.

### 두 보고서가 말한 것
- 60 query × 3 strategy (S1, S4, S4_TMG) prototype 완료
- Method gate "통과" 주장 (S4 vs S1 에서 3 cell 에서 +5~15%p)
- C5 mechanism finding 후보 ("타입별 one-shot 의 generic placeholder 가 entity-rich query 의 source-grounded labeling 을 망친다")

### 진짜 evidence 강도

| 보고된 결론 | 실제 강도 | 부족한 것 |
|---|---|---|
| Method gate 통과 | **방향성만 확인됨, 통계적 유의성 미검증** | 신뢰구간, 유의성 검정, 효과 크기 |
| C5 mechanism finding | **단일 사례 + 5/10 paired drop. 가설 수준** | 4가지 confound (예시 존재 / 길이 / 스타일 / 도메인) 격리 안 됨 |
| Judge 점수 신뢰성 | **자기 모델이 자기를 채점** | 다른 모델(closed API)로 cross-check 0건 |
| Spec §11.4 ablation 예측 | **예측 -2~6%p 인데 실측 -10%p faithfulness** | Spec 업데이트 안 됨 |

이 4가지가 closing 안 되면 paper accept 어렵다. **다행히 1-2일 작업으로 다 closing 가능**.

---

## 1. 이번 주 안에 반드시 끝내야 할 3개 액션

순서대로 실행. 각 액션의 결과가 다음 액션의 입력이 되거나, 의사결정에 영향을 준다.

### 액션 1 — 통계적 유의성 재분석

**왜 필요한가**: 보고서가 "+8.2%p (n=5)", "+6.7%p (n=10)" 을 method gate 통과 근거로 썼는데, 이런 작은 표본에서는 +5~10%p 가 noise 안인지 밖인지 알 수 없다. 신뢰구간을 계산해야 한다. 이게 안 되면 reviewer 첫 줄에 reject 사유.

**수행할 것**:

새 스크립트 작성: `code/analysis/paired_bootstrap.py`

```
입력: outputs/prototype/judge_scores/all.json (180 records, 60 paired triplets)
처리:
  1. (query_id) 단위로 S1 / S4 / S4_TMG 의 overall, faithfulness, coverage, type_app 점수 묶기
  2. (query_type, source) 별로 paired Δ 계산:
     - Δ(S4 - S1)
     - Δ(S4_TMG - S4)
     - Δ(S4_TMG - S1)
  3. 각 cell 에 대해 10,000 회 BCa bootstrap → 95% 신뢰구간
  4. Sign test p-value
  5. Cohen's d (paired)
출력: docs/analysis/week0_paired_bootstrap.md
  - cell 별 Δ, 95% CI, p-value, d
  - 어느 cell 이 "CI 가 0 을 포함하지 않는가" 명시
```

**성공 기준**:
- 최소 1 cell 에서 신뢰구간이 0 을 제외 (p < 0.05)
- Cohen's d ≥ 0.5 (medium effect)

**결과 분기**:
- 1개 이상 cell 통과 → method gate 가 "directional" 이 아니라 "statistically supported" 가 됨. 다음 단계 진입.
- 0개 cell 통과 → "60-query prototype 으로는 effect 검출 불가, 350-bundle scale-up 후 재검증" 으로 narrative 변경. Week 1 의 350 scale-up 이 critical path 가 됨.

**소요**: 2 시간, 비용 $0, GPU 0.

---

### 액션 2 — Cross-judge 검증 (10건만)

**왜 필요한가**: 지금 모든 LLM 호출이 Qwen3.6-27B 다. 생성도 Qwen, 채점도 Qwen. 자기가 만든 출력을 자기가 채점한 셈이라, 모델 self-style preference 가 점수에 들어갔을 가능성을 0 으로 못 만든다. 다른 모델로 10건만 cross-score 해서 ranking 이 보존되는지 본다.

**수행할 것**:

새 스크립트 작성: `code/judge/cross_judge_spotcheck.py`

```
입력:
  - outputs/prototype/judge_scores/all.json
  - 10 records 무작위 샘플:
    - 5 records 는 C5 hot zone (hotpot relational + comparative 에서 S4 vs S4_TMG drop 큰 케이스)
    - 5 records 는 control (다른 source/type 에서 spread 균등)
  - 같은 checklist 사용 (재생성 X)
처리:
  1. 각 record 의 (query, viz_dsl, viz_type, checklist) 를 closed API 에 전달
  2. Claude Sonnet 4.6 로 채점 (또는 GPT-5)
  3. Qwen 점수 vs 새 점수 의 Spearman ρ + per-axis 일치도
  4. 5 hot zone records 에서 C5 effect 가 cross-judge 에서도 reproduce 되는지 확인
출력: docs/analysis/week0_cross_judge_spotcheck.md
```

**모델 선택**: Sonnet 4.6 권장. 다중 modality 처리 가능 + 가격 안정. GPT-5 여도 OK.

**비용**: 10 records × 4 axis × ~$0.5 = ~$30. 1 시간 작업.

**성공 기준**:
- Spearman ρ (Qwen ↔ closed) ≥ 0.7 → Qwen judge ranking 신뢰 가능
- C5 hot zone 5 records 에서 Δ(S4_TMG - S4) 부호가 cross-judge 에서도 같은 방향 → C5 finding 강화

**결과 분기**:
- ρ ≥ 0.7 + 부호 일치 → judge bias 우려 해소. 모든 점수 그대로 사용.
- ρ < 0.5 → self-judge bias 가 결과를 흔든다. PR7 human rating 결과 + closed API 활성 (Week 1) 까지 모든 결론 보류.
- 부호 불일치 → C5 finding 은 self-judge artifact 가능성. 액션 3 결과로 보강 필요.

---

### 액션 3 — V4: agent inference + curated exemplar pool via tool-call

> **[2026-05-10 design pivot]** — `docs/analysis/oneshot_failure_analysis.md` (commit `b90eda1`) + `docs/weekly_reports/WEEK0_TMG_DESIGN_PIVOT.md` (commit `aff7baf`) 의 두 발견 (C5 가설은 gap 의 절반만 설명; rule-based 라우터가 3 셀에서 empirically 틀림) 에 따라 사용자가 V4 를 새 최우선으로 지시. 아래 V4 spec 이 우선. **V0-V3 (원래 isolation experiment plan) 는 잠정 보류** — V4 측정 결과 미흡 시 fallback 으로 선택적 재개.

> **[2026-05-10 mentor review safeguards]** — V4 측정 직전에 박을 4 가지 risk 안전장치 (mentor 피드백 반영, 액션 1·3·4·5):
> 1. **V1 baseline 동시 측정** — 같은 60 records 위에서 V1 (rule routing + no one-shot) 도 별도 strategy 로 추가. 19-record drop subset 의 paired **Δ(V4 − V1)** 가 paper §11.4 의 핵심 ablation row 이자 tool-call 아키텍처 복잡도의 정당화 evidence. Δ(V4 − V1) ≤ +0.03 이면 V4 의 추가 복잡도 justification 어려움.
> 2. **§3.2 amendment 는 Provisional 상태** (commit `903aa42`). V4 측정 결과로 final / narrow / rollback 결정 (PAPER_MASTER_SPEC §3.2 Status 블록 참고).
> 3. **V4 결과 보고는 점추정 단독 금지** — paired bootstrap CI (BCa, 10K resamples, 95%) + Cohen's d 동반. 19-record drop subset + 60-record 전체에 대해 cell 별 Δ·CI·d 모두.
> 4. **Q2 subagent draft 검수 체크리스트** — high-faith 만 보지 말 것. 각 viz_type 의 exemplar pool 안에서 syntactic spread (depth / node count / edge label length / series count) 가 실측 데이터 spectrum 을 cover 하는지 명시 검증. (Q2 subagent prompt 자체에 syntactic-diverse 요구가 들어가 있음, 검수 단계에서 빠짐 없이 확인.)

#### V4 (최우선)

**새 architecture**:
- custom_rules 에 6 viz_type pool + 각 use-case 짧게 노출 (`chartjs_bar = quantitative comparison`, `mermaid_mindmap = hierarchical taxonomy`, ...). 강제 라우팅 없음.
- agent reasoner: query + source 보고 viz_type 본인이 결정 → tool call: `generate_viz(viz_type=<chosen>, content_brief=...)`
- `generate_viz` tool 내부:
  - `ONE_SHOT_POOL_BY_VIZ_TYPE[viz_type]` 에서 1-2 examples 선정 (Q2 subagent draft 결과)
  - LLM 호출: `[examples] + content_brief + DSL 생성 instructions` → `(viz_type, viz_dsl)` 반환
- agent: tool 응답 받아 final_answer 로 wrap

**새 코드**:
- `code/agent_tools/generate_viz.py` — custom tool (vendored agent 의 tools 인터페이스)
- `code/pipelines/tmg.py` — `ONE_SHOT_BY_VIZ_TYPE` → `ONE_SHOT_POOL_BY_VIZ_TYPE` 로 확장. `TYPE_TO_VIZ` + `build_tmg_rule` 의 강제 라우팅 부분은 deprecate (custom_rules 는 6-type pool + use-case 노출만 담당)
- `code/pipelines/s4_agentic_tmg.py` — `run_paper_default(custom_tools_path=<...>, custom_rules=<6-pool 노출만>)` 로 변경. 새 strategy name 후보: `S4_AgenticTMGv4` (기존 `S4_AgenticTMG` = v1 보존)
- `code/run_prototype.py` — strategy registry 갱신

**V4 측정 (paired)**:
- 같은 60 records 로 4-way (S1, S4, S4_TMG=v1, S4_TMG_v4)
- paired Δ(v4 − v1) 가 §11.4 ablation row 의 핵심 measurement
- hypothesis prior (oneshot_failure_analysis.md Part 5): hotpot relational faith 0.71 → ~0.88-0.90 회복

**성공 기준**:
- Δ(v4 − v1) faith mean ≥ +0.10 (V4 가 placeholder-rule 변형보다 의미있게 회복)
- 3 mismatch 셀 (arxiv/comp, hotpot/comp, multinews/comp) 에서 agent 가 mindmap/timeline/flowchart 자기 inference 로 picking 하는지 trace 검증
- 10k chartjs JSON +15%p 효과 보존 (curated pool 의 고품질 chartjs example 로)

**결과 분기**:
- 위 기준 통과 → §11.4 ablation row 에 v4 paired Δ 로 채움. C6 finding 후보 ("rule-based viz_type routing fails source-conditional cases; agent inference closes gap"). PR7 + closed-API 활성과 결합해 paper-grade closing.
- v4 ≈ v1 → V1 (one-shot 자체 제거, 잠정 보류 영역) 재개. one-shot 자체가 무용인지 검증.
- v4 < v1 (예상 밖) → mentor escalate. agent inference 가 vendored agent 환경에서 routing 결정을 안정적으로 못하는지, tool-call interface 가 vLLM Qwen3.6 에서 깨지는지 등 infra-level 진단.

**소요**: 코드 ~반나절 + Qwen3.6 vLLM batch ~62 분 + 채점 ~25 분 + 분석 30 분 = ~1.5 일.

---

#### V0-V3 (잠정 보류 — 원래 plan)

> 아래는 design pivot 이전의 C5 격리 실험 plan. V4 측정 후 필요 시 fallback variant 로 선택적 재개.

**왜 필요한가**: 현재 C5 결론 ("generic placeholder one-shot 이 entity-rich labeling 을 suppress") 은 단일 텍스트 비교 + 5/10 paired drop 에 기반한다. 망친 원인이 진짜 "예시의 content style" 인지, 아니면 (a) 예시 존재 자체, (b) 예시 길이, (c) 예시 도메인 mismatch 인지 분리 안 됨. Reviewer 가 즉시 묻는다: *"네 가지 변수가 한꺼번에 바뀌었는데 어떻게 content style 이 원인이라 단정하나?"*. 이걸 못 답하면 C5 는 paper finding 이 아니라 anecdote.

**수행할 것**:

기존 `code/pipelines/tmg.py` 에 4개 변형 빌더 추가:

```
변형 0 (기준선, 이미 있음):
  현재 S4_TMG = generic placeholder one-shot
  예: "A[Founder] -->|founded| B[Acme Corp]"

변형 1 (예시 없음):
  Routing rule 만 줌, one-shot 제거
  → "예시 존재 자체" 의 효과 측정

변형 2 (길이/구체성 일치):
  Generic content 이지만 verb phrase 가 길고 구체적
  예: "A[Person] -->|served as advisor between 1995 and 2002| B[Organization]"
  → "예시의 길이/구체성" 의 효과 측정

변형 3 (도메인 일치):
  현재 record 의 source bundle 에서 entity 2-3개 뽑아 동적으로 one-shot 생성
  예: hotpot bio query 면 "A[Iqbal Qadir] -->|served in| B[Pakistan Navy]" 같은 예시
  → "도메인 일치" 의 효과 측정 (= TMG-v2 prototype)
```

새 runner: `code/scripts/c5_isolation_experiment.py`

```
입력: 기존 60 queries 중 20 records (relational 10 + comparative 10)
처리:
  1. 각 record 에 대해 변형 1, 2, 3 으로 S4 agentic 재실행 (변형 0 은 이미 있음)
  2. 동일 checklist 로 재채점 (cached checklist 재사용)
  3. Paired Δ 계산:
     - 변형1 vs 변형0 → "예시 존재" 효과
     - 변형2 vs 변형0 → "길이" 효과
     - 변형3 vs 변형0 → "도메인 일치" 효과
출력: docs/analysis/week0_c5_isolation.md
```

**성공 기준**:
- 변형 3 (도메인 일치) 가 변형 0 (현재 placeholder) 대비 faithfulness 회복 → C5 의 "도메인-rich content style" 가설 지지
- 변형 1 (예시 없음) 이 변형 0 과 유사 → "예시 존재 자체" 가 원인 아님
- 변형 2 (길이만 일치) 가 변형 0 과 유사 → "길이" 가 원인 아님

이 패턴이 나오면 C5 가 paper finding 으로 격상 가능.

**결과 분기**:
- 변형 3 회복 + 1, 2 미회복 → C5 정확. TMG-v2 설계 방향 확정 (도메인 회전 one-shot).
- 변형 3 도 회복 안 됨 → C5 hypothesis 자체가 틀림. TMG pillar 의 fundamental design 재검토.
- 변형 1 (예시 없음) 이 가장 좋음 → "TMG one-shot 자체가 무용". TMG pillar 폐기 후보.

**소요**: 20 records × 3 variants = 60 records 추가 생성 (~60 분 wall time, 기존과 같은 vLLM 인프라). 채점 30 분. 분석 30 분. **총 2 시간**.

---

## 2. 이번 주 안에 추가로 정리해야 할 2개

### 액션 4 — Spec §11.4 amendment

**문제**: Spec 에 "-TMG: -2~6%p, axis = type_appropriateness" 라고 적혀있는데 실측은 -10%p faithfulness. Spec 의 prediction 이 틀렸다는 증거가 paper 자료로 들어가게 된다.

**수행할 것**: `spec.md` 또는 paper draft 의 §11.4 부분을 수정. 액션 3 결과까지 보고 통합 amendment 작성:

```
구 prediction:
  -TMG: -2~6%p drop, primary axis = type_appropriateness

empirical observation (commit 24bbff3):
  TMG-v1 (generic placeholder): faithfulness drop -10%p on entity-rich queries (relational, comparative)
  type_appropriateness 차이는 사실상 0

revised prediction (액션 3 결과 반영):
  TMG 효과는 one-shot content design 에 conditional.
  도메인 일치 one-shot (TMG-v2) 에서는 +X%p 회복 예상.
```

**소요**: 30 분.

---

### 액션 5 — Paper scope 확정 (mentor 와 discussion)

**문제**: 두 가지 방향이 섞여있다.
- Method paper: DocViz-Agent 의 3 pillar 효과 입증 (현재 진행 중인 work)
- Benchmark paper: 9 model 평가 / image-input / multi-format (V2.0 plan)

이 둘은 같은 paper 가 아니다. 작업 우선순위, 통계 power, 평가 metric 모두 다르다.

**수행할 것**: mentor 미팅에서 명시 결정.

```
결정 항목: paper 가 method 인가 benchmark 인가?

Method paper 면:
  - 핵심 contribution = DocViz-Agent (S4_TMG) > baseline (S1)
  - Evaluation = QG-MDV 자체 benchmark (60 → 350 → 700 query)
  - Model pool 작음 OK (S1 vs S4 paired)
  - Cross-judge 는 ranking 신뢰성 검증용

Benchmark paper 면:
  - 핵심 contribution = QG-MDV benchmark 자체
  - Evaluation = 다양한 모델 (open VLM, closed VLM)
  - DocViz-Agent 는 reference 또는 single contribution
  - V2.0 plan 의 9 model × image input 다시 활성

결정 후:
  - 방향에 맞춰 docs/strategy.md 업데이트
  - V2.0 plan (VisuBench_EMNLP_2026_Action_Plan_v2.0_Final.md) 의 어느 부분이 살고 어느 부분이 deprecated 인지 명시
```

**소요**: 30분 mentor 대화 + 1시간 문서 업데이트.

---

## 3. 액션 1-3 의 결과로 진입할 수 있는 시나리오

세 액션 끝나면 Week 0 의 진짜 결론이 나온다. 다음 셋 중 하나.

### 시나리오 A — 다 통과 (paper-grade evidence 확보)
- 액션 1: ≥1 cell 신뢰구간이 0 제외 + Cohen's d ≥ 0.5
- 액션 2: cross-judge ρ ≥ 0.7
- 액션 3: 변형 3 회복 + 변형 1, 2 미회복

**다음 단계**: PR7 human rating 만 확인 후 Week 1 정상 진입.
- 350 bundle scale-up
- Closed API 활성화
- TMG-v2 (도메인 회전 one-shot) 구현 + 측정
- External benchmark (Text2Vis, MatPlotAgent, Plot2Code) wrap
- §11.4 ablation row 가 v1 vs v2 paired Δ 로 채워짐

### 시나리오 B — 부분 통과 (방향성 OK, 통계 부족)
- 액션 1: 1 cell 만 통과, 다른 cell 은 directional
- 액션 2: ρ 0.5~0.7 (acceptable but caveat)
- 액션 3: C5 가 부분 격리 (예: 길이 + 도메인 결합 효과)

**다음 단계**: "directional GO with scale-up requirement" narrative.
- Week 1 의 350 bundle 이 critical path
- 모든 paper claim 에 "validated at scale (Week 1)" caveat
- TMG-v2 는 escalation strategy (먼저 type 단위, 미회복이면 cell 단위)

### 시나리오 C — 통과 못함 (가설 자체 재검토)
- 액션 1: 0 cell 통과
- 액션 2: ρ < 0.5
- 액션 3: 변형 3 도 미회복 또는 변형 1 이 가장 좋음

**다음 단계**: PIVOT.
- 60-query prototype 으로 가설 검증 불가 → Week 1 작업 전 가설 재설계
- Mentor escalation
- 가능 옵션:
  - (a) 더 큰 prototype 으로 재시도 (350 bundle 직행)
  - (b) Method 가설 reframe (예: TMG pillar 폐기, CIS+SAO 두 pillar 만 claim)
  - (c) Paper scope 를 benchmark 로 전환 (method claim 약화)

---

## 4. 액션 1, 2, 3 의 실행 우선순위 + 의존성

```
액션 1 (통계 재분석)
  ├─ 비용 0, 시간 2h
  ├─ 결과 없이도 액션 2, 3 진행 가능
  └─ 완료 직후 보고: "method gate 의 통계적 강도가 X 다"

액션 2 (cross-judge 10건)
  ├─ 비용 $30, 시간 1h
  ├─ 액션 1 과 병렬 가능
  └─ 완료 직후 보고: "judge bias 우려가 X 다"

액션 3 (C5 격리 실험)
  ├─ 비용 0, 시간 2h
  ├─ 새 코드 (3 variant builder + isolation runner) 필요
  └─ 완료 직후 보고: "C5 가 진짜 mechanism finding 인가 X 다"

액션 4 (Spec amendment)
  ├─ 액션 3 결과에 의존
  └─ 30 분

액션 5 (paper scope)
  ├─ mentor discussion
  └─ 액션 1-3 결과 보고 후 진행 권장
```

**병렬 실행 시 1일 안에 끝.** 순차 실행해도 1.5일.

---

## 5. 각 액션별 산출물 위치

```
docs/analysis/week0_paired_bootstrap.md       ← 액션 1
docs/analysis/week0_cross_judge_spotcheck.md  ← 액션 2
docs/analysis/week0_c5_isolation.md           ← 액션 3
spec.md (또는 paper draft) §11.4              ← 액션 4
docs/strategy.md                              ← 액션 5

새 코드:
code/analysis/paired_bootstrap.py
code/judge/cross_judge_spotcheck.py
code/scripts/c5_isolation_experiment.py
code/pipelines/tmg.py (variant builder 추가)
```

---

## 6. 보고 시점

각 액션 완료 직후 짧은 update 한 줄로 충분:

```
[액션 1 완료] cell 별 paired bootstrap 결과: arxiv 95% CI [+0.058, +0.260] excludes 0 (Cohen's d = 1.04). hierarchical CI [-0.041, +0.221] includes 0. relational CI [+0.005, +0.142] excludes 0. → method gate 통과 cell 2 개.

[액션 2 완료] cross-judge ρ = 0.78 (overall). C5 hot zone 5 records 의 Δ(S4_TMG - S4) 부호 5/5 일치. → judge bias 우려 해소.

[액션 3 완료] 변형 3 (도메인 일치) faithfulness +0.18 회복. 변형 1, 2 는 ±0.03. → C5 의 "content style" 가설 지지. TMG-v2 설계 정당.

→ 시나리오 A. Week 1 진입.
```

세 보고 다 받으면 Week 0 final decision.

---

## 7. 한 번 더 강조할 핵심

지금 work 의 framing 에 한 가지 위험이 있다. 두 보고서 다 *"GO"* 라는 결론을 내렸지만 evidence 는 그만큼 강하지 않다. Reviewer 가 *"60 records 에 신뢰구간 없이 +5%p effect 를 method gate 통과 근거로 쓰는가?"* 라고 물으면 답할 게 없다.

이번 followup 의 목적은 두 가지:
1. **결론을 evidence 강도에 맞게 calibrate 한다.** "통과" 가 진짜 통과인지, "방향성" 인지 정직하게 정한다.
2. **Week 1 진입 결정을 evidence 위에 세운다.** 시나리오 A/B/C 중 어디인지 안 정한 채로 350 bundle scale-up 으로 가면, 같은 통계적 약점을 5배로 키우는 게 된다.

3 액션 끝나면 진짜 GO 인지 PIVOT 인지 정직하게 알 수 있다.

---

## 8. 다음 mentor 보고 시 강조할 한 줄

> *"Week 0 prototype 의 directional signal 을 paired bootstrap CI / cross-judge / C5 isolation 으로 calibrate 했다. 결과는 시나리오 X (A/B/C). Week 1 은 이 결과 위에서 진입한다."*

이게 honest 한 narrative.
