# 다문서 시각화 — 난제 문헌조사 → Agent Tool 기여 → SOTA 타게팅 설계 (2026-06-12)

> 요청: (1) CHARTEVAL/RMS-F1이 우리 output에 matching 되는지(lexical?), VisJudge/TED는 어떤지,
> (2) **다문서 시각화(차트·도식)의 중요·어려운 점을 선행연구로 충실히** 찾고,
> (3) 그 난제에 우리 **agentic tool 기여**를 매핑, (4) 실제 **SOTA 타게팅** 가능하게.
> 데이터 가용성은 코드/데이터 직접 검증(§6).

---

## 1. Matching 문제 — 지표별 판정 (당신 의심이 맞음)

| 지표 | matching 방식 | 우리 open-gen에 적용성 | 판정 |
|---|---|---|---|
| **RMS-F1 / CHARTEVAL** | 셀 = 수치(5% tol) + **행/열 라벨 = lexical** | 라벨 표현 변주("Revenue" vs "Total Revenue")에 false-neg | **부분 차용**: 라벨 매칭은 버리고 **수치 집합만** |
| **RNSS (Relative Number Set Similarity)** | **수치 집합만**, perm-invariant, 5% tol, **라벨 무관** | lexical 회피 → robust | **차용** (차트 데이터 충실도) |
| **DiagramEval node/path** | render→VLM→**semantic(cosine) 정렬** | lexical 아님 → robust (현행) | **유지** (도식 구조) |
| **TED (MindBench)** | 트리 편집거리 + **node는 semantic 정렬** 가능 | 트리형 도식에 적합, 라벨은 cosine로 | **차용** (mindmap/flowchart/timeline 구조) |
| **VisJudge (F-E-A)** | **이미지 기반 VLM judge** — matching 자체 없음 | 단 "Fidelity"=*자기 데이터*에 충실, **source 문서 grounding 아님** | **차용하되 용도 한정**(시각품질·decoupling의 "포화" 축) |

**결론**: lexical 매칭(RMS-F1 라벨, CHARTEVAL 라벨)은 우리 setting에서 깨진다. **수치 집합(RNSS)
+ semantic 정렬(DiagramEval/TED) + 이미지 judge(VisJudge)** 로 가면 matching 문제가 사라진다.
그리고 가장 강한 카드는 §6에서 확인한 사실 — **B6 datapoint가 이미 `(value, unit, source_eid)`를
보유** → gold-table 정렬 없이 **모델 자신의 citation을 anchor로 한 value 검증**이 가능(§4 AVC).

---

## 2. 다문서 시각화의 난제 (선행연구 grounded)

### 2.1 다문서 추론·요약 일반 난제

| 난제 | 내용 | 출처 |
|---|---|---|
| **교차문서 집계(aggregation)** | 흩어진 값을 통합 (DB식 aggregation 포함) | MEBench(2025), MDBench(2025), HoloBench |
| **모순·상충 값(conflict)** | 문서 간 같은 사실에 다른 값/주장 | MDS survey(CSUR), MEBench |
| **중복(redundancy)** | 같은 정보 반복 → 중복 제거 필요 | MDS survey |
| **정보 분산(dispersion)** | 핵심 데이터가 여러 문서에 흩어짐 | MDS survey, Doc2Chart |
| **시간 정합(temporal)** | 다른 시점 발행 문서의 시변 값 | MDS survey, TEMPO |
| **다개체 entity 정합** | 고밀도 개체의 교차문서 해소 | MEBench |
| **교차문서 수치추론** | 값 연산·비교·집계 | MDBench, NumericBench, DocMath-Eval |

### 2.2 문서→차트 생성 고유 난제

| 난제 | 내용 | 출처 |
|---|---|---|
| **모호 수치 → plottable 값** | "27,000 이상", "약 50%", "8% 초과" 를 값으로 추론 | ChartifyText(2024), Doc2Chart(EMNLP25) |
| **단위/스케일 변환** | millions→실값, 스키마 단위 불일치 변환 | Doc2Chart(Doc2Table), ChartifyText, DTBench(2026) |
| **다segment 분산·대형표 subsetting** | 데이터가 여러 구획에 → 누락 위험 | Doc2Chart |
| **환각·무관 데이터·intent 위반** | 없는 값 생성, 의도 이탈 | Doc2Chart |
| **출처귀속(faithfulness)** | 차트 내용을 source 표로 역추적 | Doc2Chart CHARTEVAL |
| **표면매칭 불가 값** | 직접추출 불가, 변환 필요 | DTBench, Doc2Chart |

### 2.3 viz × multidoc **교집합**의 진짜 난제 (우리 sweet spot)

단일문서 차트생성에도, MD-QA에도 *없는*, 다문서 시각화에만 있는 난제 — **여기가 method 기여의
자리이자 MD-QA 공격 무력화 지점**:

- **(A) 공유 축(axis)을 위한 교차문서 값 정합**: 한 막대그래프에 올리려면 문서별 단위·스케일·
  회계연도·정의가 통일돼야 함($M vs $B, FY 상이). 단일패스 LLM은 조용히 섞음 → 잘못된 차트.
  [난제 2.1-집계/시간 + 2.2-단위변환]
- **(B) 시각 mark에 대한 충돌 해소 + provenance**: 문서가 값에 불일치할 때 어느 값을 막대에
  인코딩하고 어디에 귀속할지. 단일패스는 평균/임의 선택, 출처 없음. [2.1-conflict + 2.2-귀속]
- **(C) 분산·distractor 하 완전성**: 흩어진 series 멤버를 모두 모으고 방해문서를 거부해야 차트
  범주 누락 없음. [2.1-dispersion/redundancy + 2.2-subsetting]
- **(D) spec→DSL 변환을 관통하는 datapoint-level 귀속**: 각 mark가 source 문서/claim에 추적.
  [2.2-faithfulness]
- **(E) 모호값 → 인코딩값 추론**: "약 50%"→0.5, 모호성 기록. [2.2-모호수치]

---

## 3. Agent Tool 기여 설계 (난제 A–E 매핑)

**핵심 주장**: 다문서 시각화는 "텍스트 많은 단일문서 차트생성"이 아니다. **교차문서 값 정합·충돌
해소·datapoint 귀속**을 요구하며, 이는 **단일패스 생성이 구조적으로 못 하는** 능력이다. 우리는
이를 **agent tool**로 제공한다(=agentic 기여). 이 tool들은 generic RAG가 아니라 *시각 인코딩을
위한 다문서 데이터 준비*에 특화된다 → "CIS/TMG/SAO는 generic" 비판 해소.

| Tool | 난제 | 메커니즘 | 왜 viz×multidoc 고유 |
|---|---|---|---|
| **CVR** (Cross-doc Value Reconciliation) | A,E | 한 series 후보값들을 공통 단위/스케일/시점 frame으로 정규화 후 반환 + 변환로그 + per-value provenance | 공유 *축*을 위한 정합 — QA답엔 축이 없음 |
| **CA** (Conflict Adjudication) | B | (entity,metric,time) 셀의 문서간 충돌 탐지 → 정책(최신/권위/다수)으로 해소 → mark에 provenance+conflict flag | 시각 mark는 단일값을 강제 — QA는 "양측 서술"로 회피 가능 |
| **CIS** (Cross-doc Iterative Search) | C | 반복 검색으로 series 멤버 완전 수집 + distractor 거부 (기존) | 차트 범주 완전성 — dispersion/distractor 문헌이 정당화 |
| **SAO** (Source-Attributed Output) | D | datapoint/node/edge → source_eid (기존, 헤드라인) | mark-level 귀속 — 텍스트 citation과 granularity 다름 |

> TMG/VSC는 헤드라인에서 내림(앞선 분석). **새 기여 핵심 = CVR + CA** (문헌 직접 근거). 이 둘이
> "왜 agent가 필요한가 + 왜 단일패스가 지는가"를 설명 → **SOTA 논리의 토대**.

---

## 4. 평가 설계 — matchable + SOTA-demonstrable

직전 matching 문제를 모두 회피하도록, **lexical 매칭 없는** 지표만 사용:

| 지표 | 무엇 | 매칭방식(정규화·lexical 회피) | 모달리티 | gold 출처 |
|---|---|---|---|---|
| **AVC** (Attributed Value Consistency) *신규·핵심* | datapoint value가 *자신이 cite한 source_eid 청크*에 실제 존재하는가 | **id anchor(source_eid)** + 수치 존재검사(5% tol) — gold표/라벨 정렬 불필요 | 차트 | 불필요(모델 citation이 anchor) |
| **RNSS** | 그린 수치집합 ↔ gold표 수치집합 | **수치 집합만**, perm-invariant, 5% tol, **라벨 무관** | 차트 | gold tables(106, 67 numeric) |
| **Evidence F1** | 출처 doc/claim 귀속 정확도 | **id 집합 연산** (정규화0) | 차트+도식 | gold evidence(300) |
| **CRC** (Conflict Resolution Correctness) *신규* | 모순 질의서 supported_side 값 인코딩 + 올바른 evidence 귀속 | supported_side/evidence_ids 대조(id) | 차트+도식 | **gold contradictions(44 확인)** |
| **node/path + TED** | 구조 충실도 | render→VLM **semantic** / 트리편집+semantic node | 도식 | gold graphs(226) |
| **VisJudge F-E-A** | 시각품질(자기데이터 충실·표현·미학) | 이미지 judge(off-pool) | 차트+도식 | 불필요 |

**AVC가 matching 논쟁의 최종 해법**: gold 표에 우리 차트를 정렬할 필요 없이, **모델이 스스로 단
source_eid를 정답 anchor로** 삼아 "그 청크에 이 값이 있나"만 본다. lexical 라벨매칭·단위정렬 문제
원천 소거. baseline은 source_eid가 없으므로 *implicit*(검색청크 내 수치 존재)로 측정 → 자연스러운
explicit/implicit 격차(Evidence F1과 동일 설계, 코드 `evidence_metrics.py` 패턴 재사용).

---

## 5. SOTA 타게팅 논리

**무엇의 SOTA인가**(정직·방어가능): "더 나은 생성기"가 아니라 **grounding-aware 지표의 SOTA**.

- 구조(node/path/TED)·미학(VisJudge): **전 모델 포화/동률** — 여기선 SOTA 주장 안 함.
- **grounding 축(AVC·RNSS·Evidence F1·CRC)**: baseline(B1–B5,B7)은 교차문서 정합·충돌해소·
  mark귀속을 **구조적으로 못 함** → tool 장착 B6가 **명확히 우위**. = "SOTA on grounded
  multi-doc visualization".
- **필요성 입증**: −CVR / −CA / −CIS / −SAO ablation이 각 grounding 지표를 떨어뜨림(native 산출
  기반, 복구경로 금지 — B3 교란 주의).
- **전이**: held-out(Doc2Chart, Text2Vis)에서 grounding 우위 유지 → 일반화.

이 프레임이면 node/path 동률이 약점이 아니라 **"생성은 다 잘하는데 grounding은 tool 있는 우리만"**
이라는 SOTA 서사가 된다. MD-QA 공격도 무력: CVR(축 단위정합)·CA(mark 충돌해소)는 QA에 없는 연산.

---

## 6. 데이터 가용성 — 직접 검증 결과 (가정 금지)

| 자원 | 상태 | 설계 영향 |
|---|---|---|
| B6 datapoint `(value,unit,source_eid)` | **존재** (`handle_generate_viz.py` 프롬프트 L277/282) | **AVC 가능** |
| gold contradictions | **44/300 populated** (claim_a/b, supported_side, evidence_ids) | **CRC 가능**(44표본). Type E 60 중 44 |
| gold tables(cells,value,evidence_ids) | **106 tables, 67 ≥2 numeric** | **RNSS 가능**(차트 subset) |
| gold evidence(doc-level) | 300 | **Evidence F1 가동중** |
| **SEF claim_units.normalized_value** | **데이터에 미materialize** (`code/sef`는 코드만, data/엔 없음) | cuid→정규화값 anchor 설계 **보류**; AVC는 source_eid 청크 텍스트로 대체 anchor |
| CVR/CA tool | **미구현** (신규 개발 필요) | §3 구현 + 절제 = 핵심 작업량 |

**리스크**: CRC 44표본은 작음 → Type E gold contradiction 추가 추출로 보강 권장. SEF normalized_value
미materialize → AVC는 "cited 청크 내 수치 존재"로 구현(정규화값 의존 안 함).

---

## 7. 즉시 할 일 (우선순위)

1. **AVC 10-샘플 프로토타입**: 기존 B6 산출의 datapoint `(value,source_eid)` → cited 청크에 값
   존재(5% tol) 비율. baseline은 implicit. 격차 나오는지 확인. (gold 불필요, 즉시 가능)
2. **CRC 측정**: 44 contradiction 표본에서 각 arm이 supported_side 값/귀속을 맞히는지.
3. **CVR/CA tool 설계 스펙** 1쪽: 입력(후보값+provenance)/출력(정합값+변환로그+conflict flag)/
   절제 스위치. → 구현 착수.
4. **VisJudge·TED 차용 셋업**: off-pool judge 고정, 트리형 도식에 TED.

이 4개로 "grounded multi-doc viz SOTA" 서사의 실현성을 2주 내 검증한다.

---

## 8. 출처

- MDS challenges(redundancy/conflict/temporal/dispersion) — CSUR survey, arXiv:2011.04843; LlamaIndex glossary
- MEBench(cross-doc multi-entity aggregation) — arXiv:2502.18993
- MDBench(numeric + knowledge aggregation) — arXiv:2506.14927
- NumericBench / DocMath-Eval(수치추론) — arXiv:2502.11075 / 2311.09805
- Doc2Chart / CHARTEVAL(문서→차트 난제·귀속) — EMNLP 2025, arXiv:2507.14819
- ChartifyText(모호수치·단위정규화) — arXiv:2410.14331
- DTBench(문서→표 변환 난제) — arXiv:2602.13812
- DePlot(RNSS/RMS-F1, 5% tol) — ACL Findings 2023, arXiv:2212.10505
- ChartQA(relaxed accuracy 5%) — ACL Findings 2022, arXiv:2203.10244
- DiagramEval(node/path) — EMNLP 2025, github.com/ulab-uiuc/diagram-eval
- MindBench(TED) — arXiv:2407.02842
- VisJudge-Bench(F-E-A judge) — arXiv:2510.22373
