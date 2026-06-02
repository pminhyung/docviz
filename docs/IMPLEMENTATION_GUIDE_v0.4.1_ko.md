# DocViz v0.4.1 구현 가이드 — 연구자용 한국어판

> **목적**: 영문 구현 가이드 (`IMPLEMENTATION_GUIDE_v0.4.1.md`)와 짝을 이루는 한국어판. 연구 책임자가 *연구 방향과 핵심 결정 사항*을 빠르게 파악할 수 있도록 구성. 구현 세부 사항이 아닌 *왜 이렇게 하는가*와 *논문 어디에 들어가는가*를 중심으로 기술. 원본 영문판과 1:1 대응되며 내용 누락 없음.
>
> **개정 노트**: 이전 초안에 4가지 잘못된 결정이 있었다 — (a) 즉석에서 만든 가중치 합산 점수 "FSOS", (b) 미공개 벤치마크 ViviBench를 주요 held-out으로 포함, (c) 우리 세팅과 정렬되지 않은 Plot2Code를 mandatory로 격상, (d) rate limit으로 막힌 `claude -p` CLI를 A5 judge 경로로 지정. 네 항목 모두 이번 개정에서 제거. 골드 구성 §6은 추출 프롬프트, 중복 제거 알고리즘, Prolific 과제 설계를 자세히 보강.

---

## 0. 이 가이드를 읽기 전에

### 0.1 두 가지 문서의 역할 분담

- **영문판**: 연구 에이전트가 파일 단위로 그대로 구현할 수 있는 코드 명세. 함수 시그니처, 파일 경로, 도커러 명령 포함.
- **한국어판 (이 문서)**: 연구 책임자가 *전체 그림*을 파악하는 용도. 각 구현 결정이 *어떤 논문 기여*를 뒷받침하는지, *어떤 표를 채우려고 하는지*, *왜 이 설계를 선택했는지*를 설명. 코드 블록 최소화.

두 문서 모두 v0.4.1 기준이며, 같은 결정 사항을 다른 시점에서 기술한다.

### 0.2 v0.4.1이 v0.3에서 바뀐 핵심 결정

| 항목 | v0.3 (이전) | v0.4.1 (현재) | 이유 |
|---|---|---|---|
| 기여 개수 | 5개 (방법 / 과제 / 평가 / 비교 / 발견) | 4개 (과제 / 방법 / 평가 / 발견) | "비교"는 기여가 아니라 평가 방법론 |
| 주된 포지셔닝 | "최초의 일반화 파이프라인" | "최초의 질의 기반 다문서 시각화 과제 정형화" | 일반화는 instruction-tuned 모델에 어울리는 framing — 프롬프팅 파이프라인에는 약함 |
| 헤드라인 보고 방식 | 4축 RocketEval 점수 평균 단일 숫자 | **결정론적 구조화 지표 4개를 가중치 없이 병렬 보고** + Evidence F1을 발견 기여의 주 지표로 designate | 이전 초안의 "FSOS = 0.35×chart + 0.35×graph + 0.20×evidence + 0.10×intent" 가중치는 이론적/경험적 근거 없는 즉석 작성 — 폐기 |
| 엄격 게이트 정의 | 단일 점수에 대한 차이 ≥ +0.020 | **4개 지표 중 3개 이상에서 B6 우위, Evidence F1에서 차이 ≥ +0.020 필수** | reviewer "왜 이 가중치?" 공격에 방어 없음 — 다중 기준 게이트가 정직 |
| 백본 풀 | 5개 (closed 3 + open 2) | 4개 (open 2 + closed 2, 등급 spread) | mini + frontier 양극 spread가 mid 세 개보다 강함 |
| 질의 분류 | 출력 구조 5개 한 축 | 추론 난이도 5개 + 출력 구조 5개 두 축 | 난이도 필터링과 능력 검증 둘 다 필요 |
| 평가 패러다임 | judge 단일 | 3-tier (결정론적 주 + 이미지 보조 + judge 검증) | 주관성 약점 제거 + 이미지 평가 누락 보완 |
| Held-out 외부 벤치 | Text2Vis + ViviBench + Plot2Code 셋 다 mandatory | **Text2Vis + Doc2Chart (EMNLP 2025 Main) + SciDoc2DiagramBench (EMNLP 2024 Findings) 3개 mandatory** (chart 측 2 + diagram 측 1), Plot2Code 선택, ViviBench/VisDoM 제거 | 단일 벤치 = universality 공격 취약. 3-bench 구성으로 diagram side 외부 검증 gap 메우고 chart side 2개로 sharp specialist 비교 확보 |
| A5 이미지 judge 호출 경로 | `claude -p` CLI | **Anthropic API (Claude Sonnet 4.6 SDK)** | CLI 구독은 rate limit으로 2,800회 배치 막힘. API + batch mode로 ~$11 비용. |
| 4축 RocketEval judge 위치 | 헤드라인 | Tier 3 검증 보조 | prototype 코드 + scope-v3 결과는 보존, 단 헤드라인 자리에서 내림 |

이 결정들은 직전 mentor 세션의 audit 결과로 도출. 영문판 §15.3에 PAPER_MASTER_SPEC 어느 절을 어떻게 고쳐야 하는지 목록 정리.

---

## 1. 연구 기여 4개 — 모든 구현은 이 중 하나를 위해 존재한다

### 1.1 기여 1 — 과제 정형화 및 벤치마크 (QG-MDV)

**한 줄 주장**: 질의 기반 × 다문서 × 10종 시각화 기본형 동시 충족을 요구하는 과제를 처음으로 정형화하고, 300개 질의 + 6개 출처 도메인 + 90개 사람 검증 골드를 공개한다.

**왜 새로운가**: MMLongBench-Doc은 다문서 질의응답이지만 시각화 출력이 없다. Text2Vis는 시각화 출력이지만 단문서 + 단일 시각화 유형이다. ChartMuseum은 차트 전용 질의응답이다. *세 요건 교집합은 비어 있다.*

**구현 위치**: 영문판 §4 질의 생성 + §8 골드 구축. 논문 Table 2, Table 3 출력.

### 1.2 기여 2 — 첫 번째 일반화 방법 (DocViz-Agent)

**한 줄 주장**: 3축 (다문서 반복 검색 / 유형 인식 다중 시각화 생성 / 출처 귀속 출력) 파이프라인이 QG-MDV에서 다중 기준 엄격 게이트를 4개 백본에서 통과한다.

**가장 중요한 사실**: scope-v3 prototype 결과 *유형 인식 다중 시각화 생성* 축의 ablation 단독 기여가 -0.254로 가장 크다. 다른 두 축 합보다 크다. 즉 *유형 인식 다중 시각화 생성이 진짜 method core*, 나머지 두 축은 보조. 논문 §4 페이지 배분도 1.5 페이지를 유형 인식 0.7 / 다문서 반복 검색 0.4 / 출처 귀속 0.4로 재배분해야 한다.

**구현 위치**: 영문판 §5 B6 생성 파이프라인. Table 4, Table 7 출력.

### 1.3 기여 3 — 결정론적 구조화 평가 + Hungarian intent matching

**한 줄 주장**: Chart.js 출력을 테이블 F1, Mermaid 출력을 그래프 노드/엣지 F1로 평가하고, multiple-valid-output 문제를 Hungarian intent matching으로 해결하는 평가 프레임워크. **단일 가중치 합산 점수 없이 각 지표를 병렬 보고**.

**왜 새로운가**:
- Doc2Chart (EMNLP 2025 Main), DiagramEval (arXiv 2025), ChartEval (IJCNLP 2025 Demo) 모두 결정론적 구조화 출력 평가를 사용한다 — venue 선례 정렬.
- 셋 다 단일 가중치 합산 점수는 사용하지 않는다 — *지표 suite로 병렬 보고*. v0.4.1은 이 관행 따른다. 이전 초안의 "FSOS = 0.35×chart + 0.35×graph + 0.20×evidence + 0.10×intent" 가중치는 근거 없는 즉석 작성이라 폐기.
- *Hungarian intent matching으로 multiple-valid-output 공정성 문제를 직접 해결*한 사례는 prior work에 없다. 이 부분이 진짜 새로움.
- 기존 prototype의 scope-v3 4-axis judge는 *Tier 3 sanity*로 격하하되 보존.

**구현 위치**: 영문판 §3 평가 패러다임 + §7 DSL parser + §9 metric 모듈. 논문 §6 평가 프레임워크 절 + Table 5 출력.

### 1.4 기여 4 — 다문서 grounding 격차의 발견

**한 줄 주장**: 4개 백본 × 7개 파이프라인 행렬에서 Evidence F1 지표가 다문서 질의에서 일관되게 낮다. **백본 종류와 무관, 파이프라인 종류와 무관**.

**Evidence F1을 발견 기여의 주 지표로 designate**: 이 지표가 다문서 grounding을 직접 측정하므로, 발견의 강도는 Evidence F1 격차의 일관성으로 측정. 다른 3개 지표는 보고만 함.

**중요 단서 (정직성)**: 현재 prototype에서 관찰된 패턴 ("Cross-Document Integration 축 점수가 다른 3축보다 0.30 낮음")이 *진짜 발견인지 평가 rubric artifact인지* 미확정. v0.4.1에서는:
1. Evidence F1을 결정론적 지표로 *직접 측정* — judge rubric 강도 의존성 제거.
2. 백본 종류 4개로 확장하여 frontier (Opus 4.8) 포함 — "frontier에서는 해결된다" 방어 차단.
3. 사람 상한 비교 30개 시각화 — 사람도 같은 수준이면 평가 아티팩트, 사람이 훨씬 높으면 진짜 격차.

세 가지가 모두 격차 방향이어야 *task-inherent bottleneck* 주장 가능. 그 전까지는 *cross-axis difficulty asymmetry consistent across pipelines* 정도로 약하게 표현.

**구현 위치**: 영문판 §11 외부 벤치 + §13 종합 집계. Table 4 + 헤드라인 그림 출력.

---

## 2. 최종 목표 — 어떤 표를 채우는가

논문 본문 + 부록에 들어가는 표 11개.

| 표 | 보여주는 것 | 백본 | 크기 |
|---|---|---|---|
| Table 1 | **4 setting** × 7 baseline, **지표 4개 병렬**: QG-MDV + Text2Vis + Doc2Chart + SciDoc2DiagramBench | 4개 평균 | 7행 × 16열 (4 setting × 4 지표) |
| Table 2 | QG-MDV 출처별 번들/질의 통계 | — | 6행 |
| Table 3 | 추론 난이도 A/B/C/D/E × 7 baseline × 지표 4개. **기여 2의 헤드라인급 표** | 4개 평균 | 5행 × (7×4)열 |
| Table 4 | 4 백본 × 7 baseline × **Evidence F1 주 지표**. *기여 4 발견의 핵심 근거* | 4개 모두 | 4행 × 7열 |
| Table 5 | 4-axis RocketEval Tier 3 검증 | 4개 평균 | 7행 × 5열 |
| Table 6 | 출처별 점수 (4개 지표) | 4개 평균 | 6행 × 7열 |
| Table 7 | 3축 ablation × 4개 지표 | 4개 평균 | 4행 × 4열 |
| Table 8 | 이미지 품질 (M1 + M5 + A5 readability/layout/overall) | 100개 부집합 | 7행 × 5열 |
| Appendix A1 | 문서 수 1/2/3/5에 따른 Evidence F1 | 4개 평균 | 7행 × 4열 |
| Appendix A2 | 컨텍스트 길이 8K/32K/128K 역설 | window 가능한 2 백본 | 7행 × 3열 |
| Appendix A3 | 검증 anchor (Layer 2/3/4) | — | 8행 |

**논문 main-track 채택 기준** (이 중 하나라도 실패하면 Findings로 reframing):

1. **기여 4 발견 게이트 (최우선)**: B6가 Evidence F1에서 가장 강한 baseline 대비 차이 ≥ +0.020을 *4개 백본 중 3개 이상*에서 달성.
2. **기여 2 방법 게이트**: B6가 Chart Data F1과 Graph Edge F1에서도 차이 ≥ +0.020을 *4개 백본 중 2개 이상*에서 달성.
3. **다중 기준 엄격 게이트**: QG-MDV 백본 평균에서 B6가 **4개 주 지표 중 3개 이상에서 우위**, Evidence F1에서 차이 ≥ +0.020 필수.
4. **추론 난이도 폭**: T3에서 5개 추론 난이도 유형 중 *4개 이상*에서 B6가 Evidence F1 기준 우위.
5. **Held-out chart 측**: Text2Vis에서 B7 Text2Vis-orig 대비 -7%p 이내; Doc2Chart에서 B8 Doc2Chart-orig 대비 -7%p 이내.
6. **Held-out diagram 측**: SciDoc2DiagramBench에서 B9 SciDoc2Diagrammer-MAF 대비 CLIPScore + completeness Likert 평균 -7%p 이내. **이 기준이 단일-벤치 Text2Vis-only로는 못 메우던 diagram 측 외부 검증 gap을 채운다.**

---

## 3. 백본 풀 (v0.3.1 amend로 확정)

| 슬롯 | 모델 | 등급 | 역할 |
|---|---|---|---|
| O1 | Qwen3.5-397B-A17B-FP8 | 오픈 frontier | 주요 측정 백본 (scope-v3 게이트 통과 완료) |
| O2 | DeepSeek-V4-Flash | 오픈 MoE | 두 번째 아키텍처 보조 |
| C1 | GPT-5-mini | 클로즈드 budget | 비용 효율 클로즈드 |
| C2 | Claude Opus 4.8 | 클로즈드 frontier | 최상위 클로즈드 |

**난이도 필터링용 모델**: GPT-5 full + Claude Opus 4.7. 둘 다 평가 풀에 *없다* — 순환 평가 차단.

왜 2+2 (open 2 + closed 2), 왜 클로즈드 3개가 아닌가:
- mini + frontier 양극 spread (4 사분면: 오픈/클로즈드 × budget/frontier)가 reviewer "왜 mid tier만?" 공격을 원천 차단.
- 비용도 더 싸다.
- 기여 4의 "across all LLMs" 주장이 4사분면 cover로 강해진다.

---

## 4. 시각 이미지 평가 — 절대 빼면 안 되는 이유와 어떻게 다루는가

### 4.1 왜 필수인가

모든 주요 시각화 생성 벤치마크 (Plot2Code, MatPlotAgent, SciDoc2-MAF, ChartLlama, VisJudge-Bench)가 이미지 단계 평가를 보고. 빼면 즉시 reviewer attack.

단 *헤드라인은 아님*. 헤드라인은 결정론적 구조화 출력 4개 지표. 이미지 평가는 *부수 차원* — 구조화 점수만으로는 못 잡는 차원 (축 레이블 가독성, 레이아웃 겹침, 색 대비)을 보완.

### 4.2 기존 코드 활용 가능 항목

영문판 §6 갱신본 (legacy code map)에 따라:

| 항목 | 기존 파일 | 상태 |
|---|---|---|
| M1 렌더링 성공률 | `_legacy/code/render/renderer.py` 381 LOC | 재사용 (포팅만) |
| M5 CLIPScore | `_legacy/code/metrics/clipscore.py` 205 LOC | 재사용 |
| M5 일괄 실행 | `_legacy/code/scripts/clipscore_batch.py` 140 LOC | 재사용 |
| A5 이미지 품질 judge | `_legacy/code/judge/image_judge.py` 304 LOC | **확장 필요** — CLI 경로를 Anthropic API SDK로 교체 |
| Sonnet subset baseline 실행 | `_legacy/code/scripts/run_sonnet_subset.py` 148 LOC | 재사용 (단 API 모드) |

### 4.3 A5 judge — CLI에서 API로 전환하는 이유

`claude -p` CLI는 Claude Pro 구독 quota를 사용하는데 *분당 호출 수 rate limit*이 있어 2,800회 배치가 막힘. 따라서:

- Anthropic Python SDK (`anthropic.Anthropic().messages.create(...)`)로 호출 경로 변경.
- Sonnet 4.6 vision 모델 사용 — 이미지 base64 + 텍스트 프롬프트.
- Batch API (50% off + 비동기 24시간 처리) 활용.
- 비용 추정: 호출당 약 $0.00375 → 2,800회 약 $11.
- Cross-judge spot (50 viz × GPT-5-mini vision): 약 $0.5.

영문판 §2.3에 prompt template + 코드 샘플 포함.

### 4.4 표본 추출 방침

- M1: 모든 시각화 8,400개 (300 × 7 baseline × 4 백본). 비용 0.
- M5: 모든 시각화 8,400개. 비용 0 (로컬 CLIP).
- A5: 추론 난이도 유형별 20개 × 5유형 = 100개 부집합 × 7 baseline × 4 백본 = 2,800 judgment. 비용 약 $11.
- A5 cross-judge κ: 2,800개 중 50개 × GPT-5-mini API. G11 게이트 κ ≥ 0.6. 비용 약 $0.5.

---

## 5. 외부 벤치 — Held-out cross-task generalization (Tier 1 face, 3개 벤치)

**개정된 범위** (held-out audit 후 2026-06-02 확정):

Tier 1 face는 **3개 외부 벤치 + 1개 선택 + 2개 deferral**:
- **Text2Vis** (mandatory, chart-side general)
- **Doc2Chart** (mandatory, chart-side intent-driven — EMNLP 2025 Main precedent, 가장 sharp specialist 비교)
- **SciDoc2DiagramBench** (mandatory, diagram-side — 현재 다이어그램 외부 검증 0 gap 메움, EMNLP 2024 Findings precedent)
- Plot2Code (선택 부록 sensitivity)
- ViviBench (코드 미공개 deferral)
- VisDoM (multi-doc reverse-QA augmentation deferral)

**핵심 가치**: 3-bench 구성으로 chart 측 2 + diagram 측 1, universality 공격 정직하게 차단. 단일 벤치 의존성 제거. EMNLP 2024/2025 venue precedent 둘 다 활용.

### 5.1 Text2Vis — chart 측 general held-out (mandatory)

- 로더: `_legacy/code/utils/load_text2vis.py` 155 LOC 재사용.
- 평가 adapter: **새로 작성** — ~150 LOC. Text2Vis 공식 4축 평가 사용.
- 표본: 100개 부집합 (seed=42 random from Text2Vis dev), 6 baseline × 4 백본 = 2,400 cell.
- Specialist: **B7 Text2Vis-orig**. 목표: B6가 B7 대비 -7%p 이내.

### 5.2 Doc2Chart — chart 측 intent-driven held-out (mandatory, EMNLP 2025 Main precedent)

참조: Jain, Ramu, Garimella, Saxena — "Doc2Chart: Intent-Driven Zero-Shot Chart Generation from Documents", EMNLP 2025 Main 1770. arXiv 2507.14819.

- 로더: `code/utils/load_doc2chart.py` **새로 작성** ~120 LOC.
- 평가 adapter: `code/eval/doc2chart_eval.py` **새로 작성** ~150 LOC. Doc2Chart 공식 차트 정확도 + intent adherence + hallucination metric 사용.
- 표본: 100개 부집합, 6 baseline × 4 백본 = 2,400 cell.
- Specialist: **B8 Doc2Chart-orig** (그들의 multi-stage framework: intent decomp → iterative data extraction → 차트 type heuristic 선택). 목표: B6가 B8 대비 -7%p 이내 (차트 정확도 + intent adherence 평균).

**왜 가장 sharp한 specialist 비교**: Doc2Chart의 setting (intent + 문서 → 차트)이 우리 QG-MDV의 단일-doc sub-case에 가장 가깝다. 그들의 *one-shot heuristic* type 선택이 우리 *agent-inferred TMG*의 직접 비교 대상 — head-to-head 동일 차원.

**위험**: Doc2Chart-orig가 단일-doc intent-driven 차트에서 B6를 진짜로 이길 가능성 실재. 완화: Doc2Chart를 *우리 QG-MDV의 단일-doc 차트 sub-case*로 framing; B6의 우위가 multi-doc + multi-viz에 있음을 강조 (Doc2Chart는 multi-doc 확장 불가능).

### 5.3 SciDoc2DiagramBench — diagram 측 held-out (mandatory, gap 메움)

참조: Mondal et al. — "SciDoc2Diagrammer-MAF: Towards Generation of Scientific Diagrams from Documents guided by Multi-Aspect Feedback Refinement", Findings of EMNLP 2024. arXiv 2409.19242.

- 로더: `code/utils/load_scidoc2diagram.py` **새로 작성** ~160 LOC. 89 ACL paper × 1,080 diagram.
- 평가 adapter: `code/eval/scidoc2diagram_eval.py` **새로 작성** ~200 LOC. CLIPScore (우리 M5 재사용) + completeness / faithfulness / layout Likert 1-5 (A5와 동일 Anthropic API Sonnet vision 경로).
- 표본: 200개 부집합 (그들 bench가 larger sample 지원), 6 baseline × 4 백본 = 4,800 cell.
- Specialist: **B9 SciDoc2Diagrammer-MAF**. 목표: B6가 B9 대비 -7%p 이내 (CLIPScore + completeness Likert 평균).

**format mismatch 정직하게 명시**: SciDoc2DiagramBench의 원래 평가는 TikZ 코드에 ROUGE / BERTScore. **우리는 Mermaid markdown 출력** — TikZ/Mermaid 문자열 단위 비교 불가능. 따라서:
- 그들의 ROUGE/BERTScore 지표는 **skip** (paper 노트: "format mismatch; not applicable").
- 그들의 CLIPScore + Likert 사람 평가는 **적용** (image-level, format-agnostic).
- 논문 §11 limitation: "SciDoc2DiagramBench 비교는 DSL format mismatch (Mermaid ≠ TikZ)로 image-level 지표에 한정."

이 trade-off 수용 가능: image-level 지표가 *그들의 사람 검증 2축*이므로 코드 비교 축만 잃는다.

**왜 gap을 메우는가**: SciDoc2DiagramBench는 우리 diagram 측이 *정확히 외부 검증 0 capability* — 긴 문서로부터 다이어그램 생성을 직접 테스트. TMG의 diagram-type 선택 (5 mermaid 유형)이 그들 MAF의 specialized diagram 합성과 head-to-head. 이 벤치 없으면 paper의 diagram 주장이 *내부 전용*; 추가 시 외부 anchor 확보.

### 5.4 Plot2Code — 선택 부록 sensitivity

- 우리 세팅과 정렬 약함. Phase 7 gating: Phase 6 클로즈드 백본 실행 예산 미달일 때만. 기본 skip.
- Specialist: **B10 MatPlotAgent-orig** (Plot2Code 경로 갈 시).

### 5.5 ViviBench / VisDoM — v0.4.1 deferral

- ViviBench: 평가 코드 미공개. 자체 재구현 = unaudited methodology. v0.5로 deferral.
- VisDoM (multi-doc reverse-QA augmentation): v0.5 선택 sensitivity로 deferral.

### 5.6 Specialist 라인업 (B7-B10) — 갱신

| ID | Specialist | 대응 벤치 | 상태 |
|---|---|---|---|
| B7 | Text2Vis-orig | Text2Vis | mandatory |
| **B8** | **Doc2Chart-orig** | **Doc2Chart** | **mandatory (v0.4.1 신규)** |
| **B9** | **SciDoc2Diagrammer-MAF** | **SciDoc2DiagramBench** | **mandatory (v0.4.1 신규)** |
| B10 | MatPlotAgent-orig | Plot2Code | 선택 |

(v0.3 spec에서 B8 = ViviDoc-orig, B9 = MatPlotAgent였음 — 재번호.)

### 5.7 비용 요약 (held-out 추가분)

| 벤치 | Cell 수 | 클로즈드-API 비용 (Opus + GPT-5-mini batch) |
|---|---|---|
| Text2Vis 100 × 6 × 4 백본 | 2,400 | ~$80 |
| Doc2Chart 100 × 6 × 4 | 2,400 | ~$80 |
| SciDoc2DiagramBench 200 × 6 × 4 | 4,800 | ~$160 |
| (Plot2Code 50 × 6 × 4, 선택) | 1,200 | ~$40 |
| **합계 (mandatory)** | **9,600** | **~$320** |

추가로 SciDoc2DiagramBench image-judge (Sonnet vision): 200 × 7 × 4 = 5,600 judgment × $0.00375 = **~$21** (diagram 측 Likert 자동화).

### 5.8 In-domain 벤치 환경 변수

| 환경 변수 값 | 데이터셋 |
|---|---|
| `DOCVIZ_BENCH=full` | `data/bundles/qg_mdv_full_300.jsonl` |
| `DOCVIZ_BENCH=heldout` | `data/bundles/qg_mdv_heldout.jsonl` (별도 split 있을 시) |
| `DOCVIZ_BENCH=text2vis` | §5.1 |
| `DOCVIZ_BENCH=doc2chart` | §5.2 |
| `DOCVIZ_BENCH=scidoc2diagram` | §5.3 |
| `DOCVIZ_BENCH=plot2code` | §5.4 (선택) |

---

## 6. 골드 구성 — 상세 프로토콜 (이전 가이드에서 미흡한 부분 보강)

골드는 파이프라인에서 가장 실패 가능성 높은 단계. 골드가 잘못되면 모든 metric이 무의미. 추출 프롬프트, 중복 제거 알고리즘, Prolific 과제 설계까지 자세히.

### 6.1 골드 스키마

`exaone/sft_gen/docviz/gold_schema.py`에 다음 데이터 클래스:
- `EvidenceSpan`: 증거 span의 verbatim 텍스트 + 위치 정보
- `GoldFact`: 질의에 답하는 declarative 문장 + 지지 증거 ID들 + distractor 여부 + 사람 검증 후 confidence 점수
- `GoldTable`: 차트 아티팩트의 이상적 테이블 표현
- `GoldGraph`: 다이어그램 아티팩트의 이상적 그래프 표현
- `GoldContradiction`: Type E 질의 전용 — 양 claim + 지지받는 쪽 + 각 측 증거
- `Gold`: 위 모두를 묶는 컨테이너 + intent 분해

### 6.2 다중 LLM 합집합 추출

`exaone/sft_gen/docviz/gold_builder.py`:
- Extractor A = GPT-5-mini, Extractor B = Claude Opus 4.8.
- 두 모델이 *같은 프롬프트로 독립 추출*.
- 합집합 (multi-LLM union, *not* majority) 후 중복 제거.
- 사람 검증 90개 부집합에서 *양방향* 검증:
  - 출처 정확성 (지지받지 못한 fact 제거)
  - 완전성 (누락된 fact 추가)

핵심: *단일 추출 LLM에 편향되지 않게 합집합 → 사람이 양방향으로 다듬는다*. 이전 초안의 "LLM이 만든 gold만 사람이 검증" 약점 보완.

### 6.3 추출 프롬프트 템플릿 (challenge-type 인식)

`exaone/sft_gen/docviz/prompts/gold_extraction/base.txt`에 base 프롬프트.

추출 요청 항목:
1. **evidence_spans**: doc_id, chunk_id, verbatim 텍스트, span 위치
2. **facts**: 질의 답변 declarative 문장 + 지지 증거 ID 1개 이상
3. **tables**: 질의 intent가 차트 요구 시 이상적 테이블 표현
4. **graphs**: 질의 intent가 다이어그램 요구 시 이상적 그래프 표현
5. **distractor_facts** (Type D 전용): 번들에 있지만 질의 phrasing이 *제외*하는 fact (예: "preliminary numbers"). 나중에 오염 측정용.
6. **contradictions** (Type E 전용): 충돌 claim 쌍 + 어느 쪽이 audited evidence로 지지받는지

제약:
- 모든 fact가 evidence_span_id 1개 이상 인용 필수
- evidence_span 텍스트는 verbatim (의역 금지)
- 같은 fact가 여러 doc에 있으면 모든 지지 span 나열
- 출력은 strict JSON, Gold schema 준수

### 6.4 합집합 / 중복 제거 알고리즘

```
1. Extractor A 결과로 key 기반 dict 구축.
2. Extractor B 각 item에 대해:
   - key 충돌 시: supporting_evidence_ids 병합, statement 텍스트는 B 우선 (Opus 4.8 prior 일반적 유창성 높음)
   - B-only item: append
3. 각 Gold item에 provenance 기록: {extractors: ["A" | "B" | "both"]}
```

- Tables/graphs: (intent_id, chart_type/diagram_type)로 dedup
- Evidence: (doc_id, span_start)로 dedup
- Facts: 정규화 statement (소문자, 구두점 제거, sentence-transformer 임베딩 ≥ 0.90) = 중복

### 6.5 사람 검증 — 90 부집합 Prolific 프로토콜

**부집합 선정**: 90 query, 추론 난이도 5유형 × 출처 6도메인 stratified (유형당 15, 출처당 목표 18 — 소폭 불균형 허용). seed=42.

**질의당 3 rater × 3 task**:

| Task | 질문 | 집계 규칙 |
|---|---|---|
| T1 출처 정확성 | "각 fact를 인용된 출처 span에서 찾을 수 있나? yes/no" | 2/3 이상 yes → fact 유지 |
| T2 완전성 | "질의 + 번들 읽고, 골드가 놓친 중요한 fact 있나? 자유 텍스트로 추가" | 추가된 fact는 추가 4번째 rater 검증 후 수락 |
| T3 과추출 | "지지받지 않은 fact 있나? 표시" | 2/3 이상 표시 → fact 제거 |

각 task는 별도 Prolific HIT (인지 부담 분리):
- T1: HIT당 $0.40 × 270 HIT (90 × 3) = $108
- T2: HIT당 $0.60 × 270 HIT = $162
- T3: HIT당 $0.40 × 270 HIT = $108
- 완전성 재검증 (4번째 rater): $50 buffer

**총 약 $430**.

**Inter-rater 합의 게이트**: T1과 T3 (binary task)에 Cohen's κ ≥ 0.6. 0.6 미만이면 rubric 명확화 후 task 재실행. *추론 난이도 유형별로 별도 계산* — 유형별 rubric 실패 감지.

**Rubric 명확성**: 각 task 프롬프트에 3가지 worked example (easy yes / easy no / borderline + 추론 설명) 포함 — 차트 평가 Prolific 연구에서 κ를 0.1-0.2 향상시킨다고 알려짐.

### 6.6 Intent 분해

- 90 gold 부집합: 사람이 정의 (질의당 intent 1-3개), T2와 같이 batch.
- 210 silver: `generate_queries.py`에서 LLM 추출. 30개 랜덤 spot-verify; 정확도 < 80% 시 사람 라벨링 300개 전체로 확장.

### 6.7 기존 인프라 재사용

`_legacy/code/judge/sample_for_human.py` 172 LOC 재사용 — stratified 부집합 추출. 위 3-task 구조에 맞춰 출력 확장.

### 6.8 최종 골드 산출물

`data/gold/qg_mdv_v0.4.1.jsonl`. 한 줄당 한 Gold 인스턴스 JSON 직렬화. 빌드 hash + extractor 모델 버전 헤더에 기록.

---

## 7. 평가 검증 파이프라인 (Table A3 Layer 2 / Layer 3 / Layer 4)

### 7.1 Layer 2 — 사람 정합성

- `_legacy/code/judge/sample_for_human.py` 172 LOC 재사용. 90개 골드 부집합 추출.
- 평가 task는 §6.5의 T1/T2/T3 + viz preference 50 viz (개별 지표 합리성 검사용 — 가중치 fit이 없으므로 단순 spot check).
- 게이트: rater 간 κ ≥ 0.6.

### 7.2 Layer 3 — judge 간 일치도

- `_legacy/code/judge/analyze_correlation.py` 272 LOC 재사용. Cohen's κ + Spearman ρ.
- 확장: Tier 1 (지표별) ↔ Tier 3 (4-axis judge 평균) 상관도 계산 → "결정론적 평가가 기존 judge 기반 선행 연구와 일관됨" 논거.
- 게이트: Tier 3 cross-judge κ ≥ 0.70; Tier 1 ↔ Tier 3 Spearman ρ ≥ 0.65.

### 7.3 Layer 4 — 역방향 질의응답

**신규**. GPT-5-mini가 생성된 시각화 이미지만 보고 원래 질의에 답한 정확도. 100개 추론 난이도 균형 부집합 × 7 baseline = 700 cell. 비용 약 $3.

게이트: B6 − 가장 강한 baseline 정확도 차이 양의 방향.

---

## 8. 종합 집계 및 표 생성

### 8.1 기존 인프라

- `_legacy/code/scripts/aggregate_v04_results.py` 187 LOC **확장**:
  - 4-axis judge 평균 헤드라인 → **4개 주 지표 병렬 보고 (가중치 없음)**.
  - 추론 난이도별 breakdown (Table 3) 추가.
  - 출력 구조별 breakdown (Table 4 유형 인식 evidence) 추가.
  - 이미지 품질 열 (Table 8 — M1/M5/A5) 추가.
  - **다중 기준 엄격 게이트 로직** (§1.3): per-cell PASS/FAIL flag, ≥ 3 of 4 주 지표 + Evidence F1 차이 ≥ +0.020.
- `_legacy/code/scripts/run_v04_pipeline.sh` **확장**:
  - Phase 0 parser 사전 검증 추가.
  - `clipscore_batch.py` 호출 추가 (M5 전체).
  - `image_judge.py` Anthropic API 모드 호출 추가 (100 부집합).
  - `reverse_qa.py` 호출 추가.
  - **Held-out 호출**: Text2Vis (§5.1, mandatory) + **Doc2Chart (§5.2, mandatory)** + **SciDoc2DiagramBench (§5.3, mandatory)** + Plot2Code (§5.4, 선택). ViviBench 제거.
  - Specialist 호출: **B7 Text2Vis-orig + B8 Doc2Chart-orig + B9 SciDoc2Diagrammer-MAF** 각 대응 벤치에서.

### 8.2 신규 paper table builder

`code/eval/build_paper_tables.py` — Table 1부터 Table 8 + Appendix A1부터 A3을 LaTeX로 출력. `outputs/paper/blank_tables_reference.md` 빈 칸 양식과 정확히 일치.

### 8.3 헤드라인 Table 3 — 추론 난이도별 (지표 4개 병렬, 합산 없음)

각 추론 난이도별 4개 지표 + 1개 type-specific 시그널을 row로 분리 보고:

```
| 난이도 | n  | 지표              | B6              | 가장 강한 baseline | 차이 |
| A multi_hop      |80 | Evidence F1      | _ ± _ | _ ± _ | +_  |
|                  |   | Chart Data F1    | _ ± _ | _ ± _ | +_  |
|                  |   | Graph Edge F1    | _ ± _ | _ ± _ | +_  |
|                  |   | Intent Coverage  | _ ± _ | _ ± _ | +_  |
|                  |   | cross_doc_evidence_recall (Type A 시그널) | _ | _ | +_ |
| B planning       |50 | (같은 4+1 row)
| C mixed          |70 | ...
| D distractor     |50 | ...
| E contradiction  |50 | ...
| Overall          |300| ...
```

채택 기준: B6가 5개 추론 난이도 중 4개 이상에서 Evidence F1 기준 차이 ≥ +0.020 → 기여 2와 기여 4 공동 검증.

---

## 9. 단계별 진행 계획 (Phase 0부터 Phase 10까지)

각 phase는 합격선이 있고, 통과해야 다음 phase 진입.

| Phase | 범위 | 합격선 |
|---|---|---|
| **P0** parser 사전 검증 | Qwen3.5-397B prototype 출력 30개에 parser 적용 | chartjs와 mermaid 둘 다 성공률 ≥ 85% |
| **P1** 도구 + 프롬프트 포팅 | `generate_viz`를 multi-artifact로 확장, ablation용 identity 파일 4개 작성, `EXAONE_V19_ADAPTER=1` 전체 적용 | 5개 샘플 도구 호출 → 렌더링 → sidecar 사슬 오류 없이 통과 |
| **P2** 질의 재생성 (300개) | 영문판 §4 생성 + §10 난이도 필터 + §4.5 phrasing 감사 | 출처 × 난이도 분포 계획 ±10% 이내, phrasing regex 통과 |
| **P3** 골드 구축 | §6.2 다중 LLM 합집합 → §6.5 Prolific 90개 부집합 검증 | 추론 난이도 유형별 rater 간 κ ≥ 0.6 |
| **P4** metric 구현 | 영문판 §9 모듈 (FSOS 없음 — 4개 지표 병렬 보고) | 모든 metric test가 `scripts/run_tests.sh`로 통과, 불변량 assertion |
| **P5** prototype 적용 | scope-v3 기존 출력 (Qwen + DeepSeek-V4)에 새 metric 적용 | 지표별 scope-v3 judge ranking과 Spearman ≥ 0.7 |
| **P6** 백본 전체 실행 | GPT-5-mini, Opus 4.8 각각 30 record E0 pilot; 통과 시 Layer A 본격 실행 (7 baseline × 3 seed × 4 백본) | E0 PASS: 두 pilot 중 적어도 하나가 30 record 부집합에서 §1.3 다중 기준 게이트 통과 |
| **P7** held-out | Text2Vis 100 + **Doc2Chart 100 + SciDoc2DiagramBench 200** (모두 mandatory), Plot2Code 50 (선택). B7/B8/B9 specialist 동시 실행 | 각 mandatory 벤치 렌더링 > 90%, B6가 대응 specialist 대비 -7%p 이내 |
| **P8** 이미지 평가 | M5 CLIPScore 전체 + A5 Anthropic API 100 부집합 + cross-judge κ | G11 게이트 κ ≥ 0.6 |
| **P9** 검증 | L2 Prolific 50 viz × 3 rater, L3 cross-judge, L4 reverse-QA | L2 Spearman ≥ 0.65, L3 κ ≥ 0.70, L4 방향 양 |
| **P10** 보고 | `build_paper_tables.py` 실행 | Table 1부터 Table 8 + Appendix A1-A3 채워짐, 지표별 차이 표 |

---

## 10. 위험 요소 및 미결 결정

### 10.1 구현 위험

| ID | 위험 | 완화 |
|---|---|---|
| R1 | Mermaid parser 실패율 > 15% | P0 pilot 먼저, DiagramEval upstream vendor 활용, mermaid-cli 10.x 고정 |
| R2 | GPT-5-mini가 V4 nested precondition 못 따라감 | E0 30 record pilot, 실패 시 GPT-5-mini 폐기 후 재선정 |
| R3 | 골드 과추출 → baseline 부당하게 낮음 | 사람 검증을 양방향 (추가 + 제거), 다중 LLM 합집합 (§6.5) |
| R4 | Hungarian matching 너무 관대 | cost 임계값 0.5 강제, 30개 prototype 검증 |
| R5 | Sonnet API rate limit으로 2,800 A5 배치 막힘 | batch API (50% off + 24시간 비동기), per-host quota 모니터링 |
| R6 | 난이도 필터 LLM이 평가 풀 LLM과 학습 데이터 중첩으로 leak | 필터를 GPT-5 full + Opus 4.7로 — 둘 다 평가 풀에 없음 |
| R7 | 추론 난이도 유형 C (mixed) "B6 유리하게 설계" 공격 | 데모 phrasing 규칙 (§4.5) regex 강제, baseline도 mixed 출력 가능 |
| R8 | 단일 벤치 Tier 1 face 부족 (해소됨: Doc2Chart + SciDoc2DiagramBench 추가) | 3-bench Tier 1 (chart × 2 + diagram × 1), 추론 난이도 폭 (T3) 보조 |
| R9 | 다중 기준 엄격 게이트가 1개 지표 약하면 fail | 지표별 차이 모두 표로 공개, 3-of-4 임계값은 충분히 관대 |
| R10 | **Doc2Chart-orig가 단일-doc intent-driven 차트에서 B6를 진짜로 이김** (setting overlap 실재) | Doc2Chart를 QG-MDV의 단일-doc sub-case로 framing; B6의 우위가 multi-doc + multi-viz임을 강조 (Doc2Chart 확장 불가); 음의 Δ도 정직하게 보고 |
| R11 | **SciDoc2DiagramBench format mismatch (TikZ vs Mermaid)** 코드-단위 비교 불가능 | image-level 지표 (CLIPScore + Sonnet vision Likert)에 한정; §5.3 + 논문 §11 limitation 명시 |
| R12 | **Held-out 작업 +8-10일 timeline 확장** (Doc2Chart 1-2일 + SciDoc2DiagramBench 2-3일 adapter + specialist 실행) | Phase 1-2와 병렬, P7 1주 → 2주로 확장. v0.3 timeline buffer 안에 fit |

### 10.2 연구 책임자 결정 필요

- **F1** 골드 추출자 B 모델: Opus 4.8 (평가 풀에 들어 있음, 미세 편향) vs Opus 4.7 (풀에 없음, 최신 능력 누락). 권고는 **4.8 + 편향을 paper에 명시** (90 부집합 양방향 사람 검증으로 편향 완화).
- **F2** P5 통과 후 4-axis RocketEval judge를 완전히 폐기할지 (Tier 1 ↔ Tier 3 Spearman ρ ≥ 0.85일 때). 권고는 **Tier 3 sanity로 유지** — scope-v3 독자 backward 호환성.
- **F3** Plot2Code 포함 여부: Phase 6 예산 미달 시만 추가. 기본은 skip.
- **F4** 엄격 게이트 임계값 관대함: 3-of-4 vs 4-of-4 지표 통과. 권고는 **3-of-4 + Evidence F1 mandatory** — 4-of-4는 Hungarian noise 때문에 너무 엄격.

### 10.3 PAPER_MASTER_SPEC v0.3 → v0.4.1 개정 대상 절

CHANGELOG에 들어갈 amendment 목록:
- §0.2 포지셔닝 문단 → task-first framing
- §2.1 기여 5개 → 4개
- §3.6 VizOutput dataclass → ArtifactSpec 리스트 + Hungarian intent matching
- §4 과제 분류 → 추론 난이도 5개 primary + 출력 구조 5개 secondary
- §5.4 외부 벤치마크: ViviBench 제거, **Doc2Chart (EMNLP 2025 Main) 추가 — chart 측 intent-driven primary held-out**, **SciDoc2DiagramBench (EMNLP 2024 Findings) 추가 — diagram 측 primary held-out, diagram 외부 검증 gap 메움**, Plot2Code 선택, Text2Vis chart 측 general primary
- §7 baseline matrix: B7-B10 specialist 재정의 — B7 Text2Vis-orig, **B8 Doc2Chart-orig (신규)**, **B9 SciDoc2Diagrammer-MAF (신규, v0.3의 ViviDoc-orig 대체)**, B10 MatPlotAgent-orig (선택, v0.3에서 B9였음)
- §6 모델 풀 5 → 4 (2 open + 2 closed, tier spread)
- §8 평가 프레임워크 → 3-tier (결정론적 주 지표 *4개 병렬, 가중치 없음* + 이미지 보조 + Tier 3 judge sanity)
- §16 엄격 게이트 지표 → 다중 기준 per-metric gate (Evidence F1 mandatory)
- §19 inviolable rule → 항목 4개 추가 (parser-first 평가, 난이도 필터 순환 차단, 다중 LLM 골드 합집합, A5 judge Anthropic API)

---

## 11. 무엇부터 시작해야 하는가

권고 순서:

1. **Phase 0 — parser 사전 검증** (1주, 비용 0). 통과 못하면 전체 결정론적 평가 전제가 무너진다. 다른 모든 phase의 게이트.
2. PAPER_MASTER_SPEC v0.4.1 amendment 작성 (위 10.3 목록). 이걸 먼저 commit해야 연구 에이전트가 혼동 없음.
3. Phase 1 — 도구 + 프롬프트 포팅. 4개 ablation identity 파일 작성이 가장 노동집약적이지만 critical path.
4. Phase 2 — 질의 재생성. Phase 1과 병렬 가능.

세 단계 모두 통과한 뒤에야 Phase 3 (골드 구축, Prolific $430 비용) → Phase 6 (백본 본격 실행, 약 $200 closed API 비용) → Phase 8 (이미지 평가 A5 batch 약 $11) 진입.

영문판 §14 표가 phase별 합격선의 단일 진실 소스. 연구 에이전트는 영문판의 phase 표를 기준으로 작업 자체 추적.

---

## 마무리

이 한국어판은 연구 책임자가 *어디로 가는지* 파악하는 용도. 실제 코드 구현은 영문판 (`IMPLEMENTATION_GUIDE_v0.4.1.md`)을 따른다. 두 문서가 충돌하면 영문판이 우선 — 한국어판은 영문판에서 누락된 사항을 추가하지 않으며, 영문판의 결정을 *해석*만 한다.

이의 또는 결정 변경이 필요하면 10.2의 결정 필요 4개와 10.3의 PAPER_MASTER_SPEC 개정 9개 항목 위에서 논의를 시작한다.
