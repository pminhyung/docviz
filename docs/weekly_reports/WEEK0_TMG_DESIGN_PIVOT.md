# Week-0 TMG Design Pivot — §3.2 spec amendment + V4 supersedes V0-V3

**Date**: 2026-05-10
**Authority**: User-directed (this session)
**Trigger**: paired one-shot failure analysis (`docs/analysis/oneshot_failure_analysis.md`, commit `b90eda1`)
**Scope**: §3.2 spec amendment, §3.4 pillar interaction line, `WEEK0_FOLLOWUP_ACTIONS.md` 액션 3 reorganization, Q2 subagent dispatch

---

## 1. 배경 — 사용자가 지시한 분석

PRE/POST_TMG mentor reports 상정 후, 사용자는 **"우리 one-shot 붙었을 때 오히려 점수가 이전대비 떨어진것들 output과 예시 간에 분석 좀 해볼래요? 왜 떨어졌는지, type별 one-shot 을 우리 task에 맞게 좀 수정해서 최적화하거나 점수가 높았던 output style로 변환하거나 한다면 다른 성능 경향을 뽑을 수 있을것인지 등에 대해서. subagent 호출해서 context 효율적으로 진행하세요."** 라고 지시.

이에 따라 일반 subagent 가 paired drop 분석 + redesign 제안을 `docs/analysis/oneshot_failure_analysis.md` (958 lines, commit `b90eda1`) 로 작성.

---

## 2. 분석 결과의 핵심 발견

### 2.1 C5 가설 (placeholder one-shot → style flattening) 은 **gap 의 절반만 설명**

| 패턴 | n primary | 원인 |
|---|---|---|
| **(c) Structure imposition** | **7** ← 가장 큰 버킷 | `TYPE_TO_VIZ[comparative] = chartjs_grouped_bar` 라우팅이 *비-금융 source* 의 *질적* 비교를 수치 grid 로 강제. 예: 23 명 named artist → 1/2/3 ordinal axis chart; multinews 비교 → 빈 출력. |
| (a) Style flattening | 4 | placeholder 의 짧은 generic verb ("founded", "acquired") 가 model 출력을 평탄화. |
| (b) Quantity mismatch | 4 | 2-level mindmap 예시가 3-level source 의 middle layer ("Tracker" 같은 중간 분류) 를 잘라냄. |
| (d) Content suppression | — | (a) 와 결합 |
| (e) Entity loss | — | (a) 와 결합 |

즉 원래 mentor 보고서의 C5 finding ("naive type-aware one-shot 이 entity-grounded labeling 을 suppress") 은 **(a)(d)(e) 의 4 records 정도** 만 설명. 더 큰 (c) 의 7 records 는 **rule-based router 자체의 결함** 이라는 별도 문제.

### 2.2 Self-bootstrap 분석이 라우터 오류를 자동 노출

faith=1.00 으로 채점된 S4 (TMG 없는) 출력의 viz_type 을 셀별로 보면, **3 개 셀에서 우리 `TYPE_TO_VIZ` 의 primary 와 *불일치***:

| (source, query_type) | spec mapping | model 자기 inference 가 실제로 고른 type |
|---|---|---|
| (arxiv, comparative) | chartjs_grouped_bar | **mermaid_mindmap** |
| (hotpotqa, comparative) | chartjs_grouped_bar | **mermaid_timeline** |
| (multinews, comparative) | chartjs_grouped_bar | **mermaid_flowchart** |

→ Model 은 이미 옳은 viz_type 을 **알고 있다**. 우리 매핑 테이블이 *source* 를 안 봐서 over-generalized 된 것.

### 2.3 Counterfactual prediction (Part 5)

5 개 변형의 hotpot relational faith 회복 예측 (현재 0.71 baseline):

| 변형 | 예측 faith | mechanism |
|---|---|---|
| V0 (관측, placeholder rule routing) | 0.71 | — |
| V1 (one-shot 제거, rule routing) | 0.81–0.85 | (a)(d)(e) 차단 |
| V2 (length-matched generic) | ~0.81 | quantity 효과만 |
| V3 (per-cell domain-rich rule routing) | ~0.87 | (a)(b)(d)(e) 차단, (c) 잔존 |
| **V4 (agent inference + curated pool via tool-call)** | **0.88–0.90** | (a)(b)(c)(d)(e) 모두 차단 |

→ **V4 가 가장 큰 회복 예상**. 이유는 V3 가 가진 모든 효과 + 라우터 오류 자동 해소.

---

## 3. 발견한 문제점 — 두 디자인 결함

### 3.1 Rule-based viz_type 라우터가 연구 framing 과 충돌

논문 §0 의 strategic stance 는 **"generalist agent"**, C1 contribution 은 **"agentic pipeline"**. 그런데 viz_type 결정 같은 핵심 의사결정 한 단계가 if-else 테이블이면 그 단계는 *agent 가 아닌 rule* 이 한 것. Reviewer 가 *"이건 agent 가 아니라 dispatcher 다"* 라고 칠 수 있는 약점.

### 3.2 Rule routing 이 *empirically* 도 일부 셀에서 틀림

§2.2 의 self-bootstrap 분석이 보여준 3 셀의 mismatch. 즉 spec §3.2 의 `Comparative → Chart.js grouped bar / Mermaid flowchart` 매핑이 *재무 데이터에서만* 맞고 일반화 안 됨. spec 자체가 source-conditioning 을 안 본 채로 over-generalize 됨.

---

## 4. 사용자가 지시한 수정 방향

### 4.1 Q1 — Tool-call architecture (agent infers type, tool injects exemplar internally)

> *"이거 agent 가 viz 관련 tool call 할때 type을 생성하도록 해야해. 그러려면 prompt에 (아마 custom rules을 통해 주면될지도) viz_type의 deterministic한 name pool list를 명시해줘야겠고, 이를 tool 안에서 받은거에 따라 그 viz type에 맵핑된 예시를, tool 안에서의 viz text 생성 인퍼런스때 input에 type별 one-shot으로 넣어주면 우리 연구 맥락에도 맞고 성능도 오르지 않아?"*

새 architecture:

```
[현재 구현 (S4_AgenticTMG = V1)]
  custom_rules: TYPE_TO_VIZ[query_type] 로 viz_type 미리 결정 + 그 type 의 one-shot 주입
  agent reasoner: 강제된 viz_type 안에서 reasoning → final_answer

[V4 — 새 설계]
  custom_rules: 6 viz_type pool + 각 use-case 짧게만 노출
  agent reasoner: source / query 보고 viz_type 본인이 결정
                  → tool call: generate_viz(viz_type=<chosen>, content_brief=...)
  generate_viz tool 내부:
      one_shots = ONE_SHOT_POOL_BY_VIZ_TYPE[viz_type]   ← 1~2 selected
      LLM(prompt=[one_shots] + content_brief + DSL 생성)
      → return (viz_type, viz_dsl)
  agent: tool 응답 받아 final_answer 로 wrap
```

세 가지 정합성을 모두 충족:

1. **연구 framing 정합** — viz_type 결정이 agent inference. C1 contribution 이 *실제로* agent 가 결정하는 단계로 입증됨.
2. **데이터 정합** — §2.2 의 3 셀 mismatch 가 자동 해소.
3. **One-shot 효과 보존 + 강화** — type-matched exemplar 가 *DSL 생성 호출의 입력* 에 정확히 들어가 token budget 효율 증가, scaffolding 효과 더 직접적.

### 4.2 Q2 — Per-type one-shot pool curated for high-faith + syntactic diversity

> *"type별 one-shot 을 높은 점수가 해당 type의 다양한 구현을 아우르는 컨텐츠 문법을 모두 커버하면서도 고득점이 나올만한 예시들로 최적화하는 부분에 대한 필요성"*

분석이 두 criterion 모두 직접 지지:

| 패턴 | 해결되는 criterion |
|---|---|
| (b) Quantity mismatch (4) | "다양한 구현 커버" — 단일 4-node placeholder 가 8-node 케이스 커버 못함 → 복잡도 spectrum 가 좁아서 발생. multiple examples 필요. |
| (a)(d)(e) Style flattening 계열 (4+) | "고득점 content style" — placeholder 의 generic verb 가 평탄화. faith=1.00 출력의 풍부한 phrase 가 example 이면 차단. |

→ **각 viz_type 에 2-3 개 high-faith + syntactic-diverse exemplar pool**. dual constraint (faith ≥ 0.75 + 다양한 syntactic feature: depth, node count, edge label length).

### 4.3 V4 가 followup 액션 3 의 새 최우선

> *"v4를 최우선 followup action3로 바꾸고 v0부터 v3는 잠정 보류합니다."*

V4 = Q1 (tool-call inference) + Q2 (curated pool) 통합. V0-V3 는 V4 측정 결과에 따라 일부만 재개될 수 있음 (예: V4 가 회복 못하면 V1 의 "exemplar 자체가 무용" 가설로 fallback).

### 4.4 Q2 subagent dispatch + 검수 fence

> *"Q2의 경우 당신이 subagent에게 시켜서 만점목표의 예시를 type별로 만들게하세요. 그리고 당신이 검수 후 이를 쓰게합니다."*

draft → user-direction → review → 코드 반영. draft 위치: `docs/analysis/tmg_oneshot_pool_draft.md`. 검수 후 `code/pipelines/tmg.py` 의 `ONE_SHOT_POOL_BY_VIZ_TYPE` 으로 들어감.

---

## 5. 이번 commit 으로 적용된 변경

### 5.1 Spec amendments

- **§3.2 Pillar 2 (TMG)** — Mechanism / Mapping table / Why-differentiates / Ablation 4 블록 모두 재작성. 핵심:
  - "Query-type classifier routes" → "agent reasons over query and source content to select viz_type from a deterministic 6-type pool"
  - Mapping table → "soft-prior mapping (informational; agent may override based on source content)"
  - Comparative entry → numeric multi-series → grouped_bar; qualitative cross-entity → Mermaid (3-way) 로 source-conditional 분기 표기.
  - Ablation → "remove per-type exemplar pool and 6-type pool exposure"; Week-0 measurement 의 placeholder-exemplar 결과 인용.
- **§3.4 Pillar interaction** — "TMG decides viz type from query" → "TMG exposes the 6-type viz pool with per-type exemplars, and the agent infers viz_type from query and source".
- **§3.5** — 변경 없음 (§3.5 의 "query-type classifier 5-class" 노트는 그대로 유효; query_type label 은 여전히 분석 stratification 용 + soft prior).

### 5.2 Followup 액션 3 재구성

- 액션 3 상단에 design-pivot 배너 추가.
- **V4 (agent inference + curated pool via tool-call)** 가 새 최우선 변형. spec + 구현 outline 명시.
- V0-V3 는 **잠정 보류** 표기, 기존 텍스트 보존 (V4 결과 미흡 시 fallback 으로 재개).

### 5.3 Q2 subagent dispatch

- 일반 subagent 가 `docs/analysis/tmg_oneshot_pool_draft.md` 작성 중. 6 viz_type × 2-3 examples (high-faith + syntactic diversity dual constraint).

---

## 6. 다음 단계 (V4 측정까지)

1. **Q2 subagent draft 도착** → user 검수 → revisions → 확정.
2. **구현**:
   - `code/agent_tools/generate_viz.py` (custom tool) — viz_type, content_brief 받아서 type-matched exemplar 로 LLM 호출.
   - `code/pipelines/tmg.py` 의 `ONE_SHOT_BY_VIZ_TYPE` → `ONE_SHOT_POOL_BY_VIZ_TYPE` 으로 확장. `TYPE_TO_VIZ` + `build_tmg_rule` 의 강제 라우팅 부분은 deprecate (custom_rules 는 6-type pool + use-case 노출만).
   - `code/pipelines/s4_agentic_tmg.py` 의 `run_paper_default` 에 `custom_tools_path=<generate_viz.py 경로>` 추가, `custom_rules` 단순화.
   - 새 strategy name 후보: `S4_AgenticTMG_v4` (기존 `S4_AgenticTMG` 보존). 현재 명에 v1 suffix 를 추가하는 마이그레이션도 옵션.
3. **V4 측정** — 같은 60 records, 4-way (S1, S4, S4_TMG_v1, S4_TMG_v4). paired Δ(v4 − v1) 가 §11.4 ablation 의 핵심 row.
4. **분석 + 보고** — V4 가 분석 prediction (faith ~0.88-0.90) 를 만족하는지. C6 finding 후보 ("rule-based viz_type routing fails source-conditional cases; agent inference closes gap") 검토.

---

## 7. 향후 paper-side 함의

- **§11.4 ablation row 의 정밀 measurement**: TMG-v1 (placeholder) / TMG-v4 (curated + tool-call) paired Δ 가 method-design claim 의 backbone.
- **C6 finding 후보**: rule-based routing 의 한계 + agent inference 의 자동 자가-치유 효과가 paper §8 의 추가 finding 으로 격상 가능. 단순 +%p claim 보다 *언제 어떤 design choice 가 작동하는지* 에 대한 mechanism understanding.
- **Agentic framing 이 코드와 일치**: §3.2 의 "agent reasons over query and source content to select viz_type" 가 코드의 *실제 동작* 과 정합. reviewer 의 "이건 agent 가 아니라 dispatcher" 비판 차단.

---

## 8. 사용자가 후속으로 결정해야 할 항목

1. Q2 subagent draft 검수 (도착 후).
2. V4 strategy 이름 (`S4_AgenticTMG_v4` vs `S4_AgenticTMGv2` 등) 의 명명.
3. Spec amendment 의 멘토 escalation 시점 (이번 변경은 user authority 로 진행됐고, 멘토 승인은 V4 측정 결과와 함께 보고 권장).
