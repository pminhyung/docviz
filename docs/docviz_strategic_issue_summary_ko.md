# DocViz-Agent 연구 — 전략적 이슈 정리 (외부 자문용)

> **목적**: 본 문서는 DocViz-Agent (QG-MDV) 연구의 현재 진행 상황과, 최근 발견된 핵심 전략적 이슈를 외부 자문용으로 정리한 것임. 자문자가 본 연구의 맥락을 이해하고 객관적 조언을 제공할 수 있도록 *중립적*으로 기술함. 작성자의 권고는 포함하지 않음.
>
> **작성 기준일**: 2026-06-05

---

## 1. 연구 목표 및 위치 (Research Target)

- **타겟 venue**: EMNLP 2026 main 시도 → Findings auto-fallback
- **메인 트랙 acceptance 목표 확률**: 30-45%
- **현재 단계**: v0.4.2 실험 설계 완료, Phase 0 (사전 검증) 진입 직전
- **시제품 (v0.4.1) 검증 상태**: n=265, single seed, 자체 4-axis judge로 B6 = 0.839 vs B7 = 0.808 strict gate +0.020 통과 확인. 단 자체 평가의 cell-level floor issue로 v0.4.2에서 평가 framework 전면 교체

---

## 2. 과제 정형화 (QG-MDV Task)

### 2.1 정의

**다문서 질의 기반 시각화 (Query-Grounded Multi-Document Visualization, QG-MDV)**:
- 입력: 자연어 질의 $Q$ + 다문서 묶음 $\mathcal{D} = \{D_1, \ldots, D_n\}$, $n \geq 2$
- 출력: 시각화 산출물 $V$ (Chart.js JSON 또는 Mermaid 마크다운)
- 조건: $V$의 모든 시각적 주장이 $\mathcal{D}$의 어느 문서 청크에 근거되어야 함 (source attribution 가능)

### 2.2 두 가지 직교 분류 축

**1차 축 — 추론 난이도 (challenge type, 5종)**:
- A multi_hop (다단계 추론, 가교 개체)
- B artifact_planning (산출물 수와 종류 결정)
- C mixed_artifact (chart와 diagram 동시 출력)
- D distractor_heavy (방해 문서 다수)
- E contradiction (모순 해소)

**2차 축 — 출력 구조 (output type, 5종)**:
- Quantitative, Relational, Temporal, Hierarchical, Comparative

### 2.3 10개 시각화 기본형

- Chart 계열: chartjs_bar, chartjs_line, chartjs_grouped_bar, chartjs_pie, chartjs_scatter
- Diagram 계열: mermaid_flowchart, mermaid_timeline, mermaid_mindmap, mermaid_sequenceDiagram, mermaid_classDiagram

---

## 3. 현재 제안 방법 (DocViz-Agent)

3축 에이전트 파이프라인:

| 축 | 명칭 | 메커니즘 |
|---|---|---|
| **CIS** | Cross-doc Iterative Search | 다문서를 반복 검색하며 sub-query 생성, sufficiency 도달 시까지 |
| **TMG** | Type-aware Multi-Viz Generation | 10개 viz 기본형 pool 인지, query + content로 viz_type 자율 추론, 유형별 exemplar pool 활용 |
| **SAO** | Source-Attributed Output | 각 시각적 요소가 `{doc_id}#{chunk_id}#{span}` 메타데이터 보유 |

**시제품 측정에서의 축별 단독 절제 영향** (n=265):
- B6 Full: 0.839
- B6 −CIS: $\Delta = -0.106$
- B6 −SAO: $\Delta = -0.075$
- B6 −TMG: $\Delta = -0.254$ (가장 큰 격차)

---

## 4. 말뭉치 구성 (Corpus)

7개의 학계 검증 다문서 벤치마크에서 300개 표본 추출. 각 challenge type 60 표본을 3개 출처에 분산.

| Challenge | 60 표본 출처 |
|---|---|
| A multi_hop | Loong CoR (20) + DocHop-QA multi-hop (20) + MultiHop-RAG Inference (20) |
| B planning | Loong Clustering (20) + DocHop-QA synthesis (20) + FinMMDocR multi-step (20) |
| C mixed | VisDoMBench SciGraphQA (20) + VisDoMBench PaperTab (20) + FinMMDocR Portfolio (20) |
| D distractor | MultiHop-RAG Null (20) + FinMMDocR cross-page (20) + Loong long-context (20) |
| E contradiction | FinAuditing FinSM (20) + TEMPO cross-period (20) + DocHop-QA conflict (20) |

도메인: 금융 100, 과학 100, 뉴스 40, 법률 10, 시계열 20, 장문맥 20. **모두 실제 PDF/구조화 문서, Wikipedia 0%**.

---

## 5. 평가 프레임워크 (Evaluation Framework, v0.4.2)

- **차트 + 도식 통합 (단일 method)**: DiagramEval (EMNLP 2025 Main)의 렌더링 → VLM 추출 → 노드 정렬 F1 + 경로 정렬 F1
- **출처 귀속 점수**: Evidence F1 (B6 explicit set / baseline implicit embedding)
- **의도 충족률**: Hungarian matching, ROUGE-L
- **이미지 단계**: M1 렌더 성공률, M5 CLIPScore, A5 Sonnet vision Likert (100 부집합)
- **시각 언어 모델 선택**: Phase 0에서 Qwen3.5-397B-VL 로컬 vs GPT-5-mini vision 비교 후 단일 선택
- **폐기 항목**: Doc2Chart CHARTEVAL (공식 코드 미공개), scope-v3 4-axis RocketEval (정당화 부담), 자체 정상화 계층, FSOS 가중치 합산

### 5.1 §16 엄격 게이트

B6가 (DiagramEval 노드 F1, DiagramEval 경로 F1, Evidence F1, Intent Coverage) **4 지표 모두**에서 가장 강한 비교 대상 대비 +0.020 이상.

---

## 6. 백본 풀 (4 backbones, tier-spread)

| 슬롯 | 모델 | 등급 | 역할 |
|---|---|---|---|
| O1 | Qwen3.5-397B-A17B-FP8 (text-only) | 오픈 frontier | 주요 측정 |
| O2 | DeepSeek-V4-Flash | 오픈 MoE | 보조 evidence |
| C1 | GPT-5-mini | 클로즈드 budget | 비용 효율 |
| C2 | Claude Opus 4.8 | 클로즈드 frontier | 최상위 |

난이도 필터: GPT-5 full + Opus 4.7 (평가 풀 외, 순환 평가 차단)

---

## 7. 단계적 실험 계획 (Phased Execution Plan)

| Phase | 범위 | 비용 | 기간 |
|---|---|---|---|
| P0 사전 검증 + VLM 선택 | Loong 30 표본 × Qwen 백본, dual-VLM 비교 | $33 | 1.5주 |
| P1 최소 실효 | Loong 100 표본 × Qwen × 3 비교 대상 | $20 | 1.5주 |
| P2 다중 출처 | + DocHop-QA + FinMMDocR (3 출처) | $30 | 2주 |
| P3 백본 횡단 (C4 발견) | × 4 백본 | $60 | 2주 |
| P4 완전 말뭉치 + 보류 평가 | 7 출처 300 표본 × 4 백본 × 7 비교, Text2Vis + Doc2Chart + SciDoc2DiagramBench held-out | $100 | 2주 |
| P5 이미지 평가 + 검증 + 작성 | M5/A5/Prolific/reverse-QA | $50+ | 2주 |
| **합계** | | **~$315 + Prolific** | **10.5주** |

---

## 8. 발견된 핵심 전략적 이슈 (Critical Strategic Issue)

### 8.1 issue 발제 (사용자가 제기한 우려)

> "Multi document based 관련해서 실제로 Understanding (Question Answering) 측면에서 어려운점들을 기반으로 우리가 visualization 테스트셋도 만들고 방법론을 제시하잖아. 그런데 일부 리뷰어들이 '그럼 이건 MD-QA 에서도 잘 working 하는것이냐? 딱히 viz를 위한것과 구분은 되지 않는것이냐? 그러면 MD-QA에서도 SOTA가 나올수있고 나와야하지 않느냐?'라는 관점을 가질수 있을까 고민돼요."
>
> "TMG, SAO, CIS만 자꾸 언급하냐. 이게 MD-QA와 구별시키는 시각화를 위한 배타적인 독립 기여 방법은 아니지 않아? 별도 시각화를 위한 효과적인 추가 방식이 필요할것인지"

### 8.2 핵심 logical structure of the attack

```
Reviewer 추론:
1. 우리 방법은 hard MD reasoning type 5종을 잘 cover하여 viz 생성
2. 같은 reasoning capability는 MD-QA에도 직접 적용 가능
3. 현재 multimodal MD-QA 벤치마크 다수 존재 (MMLongBench-Doc, M-LongDoc, 
   VisDoMBench, DocHop-QA, LongDocURL, FinMMDocR, BRIDGE 등)
4. 우리 method가 hard MD reasoning을 진짜 잘 한다면, 위 multimodal MD-QA 
   벤치마크들에서도 SOTA가 나와야 함
5. 만약 SOTA가 안 나오면: "방법이 진짜 좋은 게 아니라 viz에만 우연히 좋은 것 아닌가?"
6. SOTA가 나오면: "그럼 이건 MD-QA 논문이지 viz 논문이 아닌데"
   → 어느 쪽이든 paper claim 약화
```

### 8.3 작성자의 직전 defense 시도들의 한계

| 시도 | 내용 | 한계 |
|---|---|---|
| 첫 번째 | "CIS는 generic, TMG/SAO는 viz-specific" | 정확히 *왜* viz-specific인지 설명 부재 |
| 두 번째 | "MD-QA는 text-only modality라 우리 multimodal advantage 측정 불가" | **factually 틀림** — multimodal MD-QA가 dominant trend (MMLongBench-Doc, M-LongDoc 등) |
| 세 번째 | "output modality 차별화 + cross-task ablation" | TMG/SAO가 *진짜* viz-exclusive인지 객관적 audit 부재 |

### 8.4 객관적 audit — CIS/TMG/SAO의 viz-exclusivity

| 축 | 본질 | MD-QA에 동일 mechanism 존재? |
|---|---|---|
| CIS (다문서 반복 검색) | retrieval-augmented generation의 iterative 변형 | ✓ IRCoT, ReAct retrieval, FLARE 등 |
| TMG (viz 유형 선택) | 출력 형식 자동 선택 | ✓ ChartQA, TableQA의 answer format selection |
| SAO (시각 요소 출처 귀속) | fine-grained citation | ✓ Verifiable QA, CiteRAG, ReClaim 등 |

→ **3축 모두 generic mechanism의 viz output에의 적용**. *진짜* viz-exclusive method novelty는 약함.

### 8.5 진짜 viz-exclusive challenge (현재 B6 어느 것도 다루지 않음)

QA에는 없고 viz에만 존재하는 challenge:

1. **시각 인코딩 선택**: 데이터를 bar 높이 vs color vs 위치로 인코딩 (Mackinlay 1986, Bertin 1983)
2. **2차원 공간 배치**: 노드 위치, 엣지 라우팅, 겹침 회피
3. **인지적 가독성 제약**: chunking 한계, color contrast, label 가독성
4. **다중 산출물 내 일관성**: chart + diagram 동시 출력 시 같은 entity = 같은 label/색/위치
5. **수치 충실도**: 차트 값이 source data를 *정확히* 보존 (paraphrase 금지)
6. **다중 산출물 narrative 조정**: chart는 metrics, diagram은 causal flow 등 *상호 보완 분담*

현재 B6의 어느 축도 위 6개 중 어느 것도 mechanism으로 다루지 않음.

---

## 9. 가능한 전략적 path (작성자 권고 없음 — 객관 정리)

### Path A: 현재 그대로 + 정직히 reframing

- Method novelty 약함을 paper에 명시 인정
- Contribution을 "첫 QG-MDV 통합 시스템 + benchmark + 진단적 발견 (C4 cross-LLM gap)"로 재framing
- Method axis는 "integration of standard techniques"로 framing
- 비용 추가: 0
- Main track 가능성: 낮음

### Path B: 진짜 viz-exclusive method axis 추가

기존 3축에 viz-exclusive 신규 axis 1-2개 추가:

- **(α) IVC (Inter-artifact Visual Consistency)**: 다중 산출물에서 같은 entity → 같은 label/색/위치 강제. DSL post-processing
- **(β) VDFV (Visual Data Fidelity Verifier)**: 차트 DSL의 수치 → source span 추출 → 일치 검증, 불일치 시 재생성
- **(γ) EMH (Encoding-Meaning Heuristic)**: Mackinlay/Bertin 표준 인코딩 우선순위 (위치 > 길이 > 각도 > 색 > 면적) 기반 자동 선택

각 axis 구현 비용 약 1-2주 + 절제 분석 cell 추가.

- 비용 추가: $30-50 + 1-3주
- Main track 가능성: 중간 (실제 viz-exclusive contribution 입증)

### Path C: Path B의 axis 중 *가장 cheap한 1개*만 추가

(α) IVC 또는 (γ) EMH 단독 추가. 절충안.

- 비용 추가: $10-20 + 1주
- Main track 가능성: 약간 향상

---

## 10. 자문이 필요한 핵심 결정 사항

1. **TMG/SAO/CIS의 viz-exclusivity가 약하다는 사실에 대해**:
   - 본 method의 novelty를 약하게 인정하고 paper position을 reframe할지 (Path A)
   - 진짜 viz-exclusive axis를 method에 추가할지 (Path B/C)

2. **MD-QA 비교 부재의 정당화**:
   - "method가 generic이라 MD-QA에 적용 가능하지만 우리는 viz output에 집중"이라는 framing이 reviewer에게 충분한가
   - 아니면 *진짜* viz-exclusive axis가 method에 있어야 정당화 가능한가

3. **EMNLP main vs Findings**:
   - Main track 도전이라면 Path B가 필수인가
   - Findings 수용이라면 Path A가 충분한가
   - 현재 시제품 measurement (n=265, B6 +0.0314 vs B7) 강도는 어느 트랙에 적합한가

4. **시각 인코딩 / 다중 산출물 일관성 등 viz-exclusive 영역의 method 추가가 진짜 effective할지**:
   - Mackinlay 1986, Bertin 1983 등 InfoVis 고전 차용으로 정당화 가능한가
   - 우리 setting (다문서 + viz output)에서 정량적 ablation 효과 기대 가능한가

---

## 11. 부가 제약 (Constraints)

- **Timeline**: 10.5주 (Phase 0-5) — Path B 추가 시 12-13주로 확장 가능
- **예산**: 총 $315 + Prolific. Path B 추가 시 $355-365
- **인프라**: Qwen3.5-397B (text-only) 백본 풀, Anthropic + OpenAI API 키 보유, Gemini 키 없음
- **출력 DSL**: Chart.js JSON + Mermaid 마크다운에 한정. TikZ 등 미지원
- **평가 코드**: DiagramEval 공식 코드 활용. Doc2Chart는 공식 코드 미공개로 미사용
- **사람 검증 한도**: Prolific 약 $200 (gold subset) + $50 (정합성 점검) 정도로 한정

---

## 12. 자문 시 고려해주실 점

본 연구는 *벤치마크 + 시스템 통합 + 진단적 발견*의 세 contribution이 강하나, *method 그 자체의 novelty가 약하다*는 점이 발견되었음.

- 본 method가 *MD-QA의 multimodal 변형들*과 mechanism 측면에서 어떻게 구별되는가
- 진짜 viz-exclusive contribution이 필요한가, 아니면 reframing으로 충분한가
- 만약 필요하다면 어떤 axis가 가장 정당화 가능하고 효과적일까

위 세 질문에 대한 외부 자문자의 객관적 의견을 부탁드림.

---

## 부록 A: 관련 prior work 매핑

- **Doc2Chart** (EMNLP 2025 Main): intent-driven 차트 생성, 단일 문서, 차트 전용. 공식 코드 미공개
- **DiagramEval** (EMNLP 2025 Main): 도식 평가, 다문서 입력 아님. 공식 코드 공개 (github.com/ulab-uiuc/diagram-eval)
- **MMLongBench-Doc** (NeurIPS 2024 D&B): 다문서 PDF 질의응답, 단일 문서/질의, multimodal
- **M-LongDoc** (EMNLP 2025 Main): multimodal long doc QA
- **VisDoMBench** (NAACL 2025): 다문서 + 시각 풍부 요소 (chart, table, slide) QA
- **DocHop-QA** (arXiv 2025-08): multimodal multi-hop QA, PubMed
- **MultiHop-RAG** (arXiv 2024): 4-type 질의 (Inference / Comparison / Temporal / Null)
- **MEBench** (EMNLP 2025 Main): 다문서 다개체 질의응답, 3 reasoning category × 8 sub-type
- **HopWeaver** (OpenReview 2025): 다문서 multi-hop 질의 자동 합성
- **MDBench** (Findings ACL 2025): 5 reasoning category (knowledge aggregation / multi-hop / numeric / soft / temporal)
- **Text2Chart31** (EMNLP 2024 Main Oral): 차트 instruction tuning 데이터 생성
- **Mackinlay 1986** (InfoVis 고전): 시각 인코딩 우선순위 — 위치 > 길이 > 각도 > 색 > 면적
- **Bertin 1983** (Semiology of Graphics): 시각 표현의 7개 차원

---

## 부록 B: v0.4.2 폐기 결정 항목

이미 본 연구에서 폐기 결정된 항목들 (자문 시 재고려 X):

- ViviBench held-out (공식 평가 코드 미공개)
- Plot2Code 필수 보류 평가 (선택 부록 sensitivity로 강등)
- 시제품 단계 scope-v3 4-axis RocketEval (자체 정당화 부담)
- FSOS 가중치 합산 점수 (가중치 정당화 부담)
- 자체 규칙 기반 정상화 계층 (구현 결함 위험)
- `claude -p` CLI A5 judge 경로 (rate limit)
- Wikipedia 기반 다단계 QA 데이터 (실세계 원문 자료 정의 부적합)
- Doc2Chart CHARTEVAL (공식 코드 미공개)

---

**문서 끝**
