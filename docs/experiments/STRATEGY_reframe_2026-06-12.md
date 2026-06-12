# DocViz-Agent / QG-MDV — 전략 재정렬 (2026-06-12)

> 입력: v0.4.3 논문초안(5축) + EXPERIMENT_DECISIONS_LOG + VSC_marginal_findings +
> RESULTS_multisource_B1B7 + 전략이슈정리(MD-QA 구별성).
> 작성: research-strategy-advisor (senior mentor mode). 권고는 단정형으로 기술.

> **정정 (2026-06-12, post-review)**: 초판의 **C5 = CNF(반사실 수치충실도)** 및 그 대체안
> **Data Accuracy(gold-table 수치 매칭)** 는 **둘 다 폐기**한다. 사유: (1) 차트 수치 vs gold
> 수치는 단위·스케일·% ·반올림 정규화가 불가피 → v0.4.2에서 이미 폐기한 "자체 정상화 계층"의
> 재발(측정오차 >2%, gate 탈락). (2) 차트 표본(~67/300)에만 적용 → 도식 다수(~226)를 못 덮어
> 헤드라인 부분성 공격. **value-level 수치 충실도는 이 setting에서 본질적으로 noisy+partial.**
> 코어 기여에서 제거하고, 아래 §C5'·§6.1'의 **구조-출처 decoupling 진단**으로 대체한다.

---

## 0. 한 줄 진단

**원래 계획은 "5축 에이전트가 더 잘 생성한다"는 *method-superiority* 논문이었지만,
실측 데이터는 그 주장을 지지하지 않는다.** node/path는 baseline과 동률(노이즈 내),
VSC는 측정 불가(구조적 0), 유일하게 robust한 신호는 **출처귀속(Evidence F1) 6배 격차**다.
동시에 전략이슈(CIS/TMG/SAO의 viz-비배타성)도 *독립적으로* 같은 결론을 가리킨다 —
**살아남는 기여는 "생성 우월"이 아니라 "출처귀속·수치충실도라는 viz-고유 병목의 진단"이다.**
데이터가 말해주는 방향으로 논문을 재정렬하라. 이건 손실이 아니라 더 깨끗하고 더
방어 가능한 논문으로의 업그레이드다.

---

## 1. 증거 분류 (Protocol 2 — finding vs artifact)

원래 계획의 4개 측정축을 실측 강도로 재분류한다.

| 측정축 | 실측 상태 | 판정 | 논문에서의 위치 |
|---|---|---|---|
| **Evidence F1 (출처귀속)** | Loong B6 **0.333 vs baseline 0.05** (6×, 백본·노이즈 무관) | **ROBUST — 핵심** | **헤드라인** |
| node/path F1 (생성구조) | Loong node +0.008(동률), DocHop node 동률·path +0.18(혼재). temp0.6 재실행 ±0.04 | **NOISY — 보조** | 보조(3시드 mean±std), "동급 유지" 서술 |
| VSC 위반율 | full vs −VSC **0/271 vs 0/270**, 약한 4B 직접생성도 5/5 렌더 | **DEAD — 측정불가** | **삭제** (tab:vsc·−VSC·게이트③ 제거) |
| Intent Coverage | 미측정(헝가리안+ROUGE-L) | 미검증 | 보조, 우선순위 낮음 |

**결론**: 헤드라인을 node/path(생성품질)에 두면 reviewer는 Loong node +0.008·path 동률을
보고 reject한다. 이건 **지는 헤드라인**이다. Evidence F1(0.333 vs 0.05)에 두면 6배 격차의
clean signal이다 — **이기는 헤드라인**. 논문 무게중심을 옮겨라.

### 1.1 두 개의 측정 신뢰성 경고 (즉시 처리)

- **A2 순환성 (gold = Qwen 생성)**: node/path gold가 채점기(Qwen-VLM)와 동일 군 → 상대비교만
  공정. 단 **Evidence F1의 gold(source_eids)가 어떻게 구성되는지 반드시 확인하라.** gold가
  *질의생성 provenance*(질의를 만든 chunk)에서 결정론적으로 나오면 순환 아님(깨끗). gold가
  같은 생성 파이프라인에서 나오면 순환. → §7 측정감사의 1순위 검증 항목.
- **B2/B3 ablation 교란**: `recover_b6_viz`가 모든 arm에 SEF eids 주입(−SEF도 83/84 보유) +
  to_dsl 균일적용 → −SEF/−VSC 절제가 **무력화됨**. 현재 ablation 표는 **유효하지 않다.**
  복구산출이 아닌 **native/agent 산출**로 재측정해야 함.

---

## 2. 권고 방향 (목표결과·framing·실험 통합)

### 2.1 새 중심 주장 (one-sentence claim)

> 다문서 시각화 생성에서 **출처귀속과 수치충실도는 백본 무관하게 붕괴하며,
> 이는 텍스트 MD-QA에는 존재할 수 없는 viz-고유 실패 양상이다.** 우리는 이를 측정하는
> 벤치마크와, 명시적 구조 귀속(SAO)이 이 격차를 닫는 유일한 메커니즘임을 보인다.

이 주장이 강한 이유: (a) 측정이 깨끗하다(Evidence F1 + 결정론적 counterfactual),
(b) **MD-QA 공격을 구조적으로 무력화**한다(§3), (c) 2026 frontier(ChartFI, IGenBench,
RFEval 등 faithfulness/reliability)와 정렬되면서 *multi-doc → viz* 조합은 미점유.

### 2.2 기여 재구성 (C1–C4 → 재정렬)

| | 원래 | 재정렬 |
|---|---|---|
| C1 | 7출처 300묶음 벤치마크 | **유지** (단 §5 데이터설계 정당화 보강) |
| C2 | 5축 에이전트(method superiority) | **격하** → "강한 reference system / 출처귀속 메커니즘(SAO)". 5축→**3축(CIS+TMG+SAO)**, SEF는 입력표현, VSC는 부록 안전장치 |
| C3 | DiagramEval 통합평가 | **유지·보조화** (node/path는 secondary) |
| C4 | 백본횡단 출처귀속 격차(진단) | **승격 → 헤드라인 기여** |
| **C5'(신규)** | — | **구조-출처 decoupling 진단** — 구조(node/path)는 포화되나 grounding(Evidence F1)은 백본 무관 붕괴; 표준 구조지표가 못 봄. ID기반·정규화0·양 modality |

### 2.3 method 범위 결정 (단정 — 정정판)

**새 value-level 지표를 추가하지 마라. CNF·Data Accuracy 모두 폐기.** value-level 수치 충실도는
정규화 불가피(측정오차) + 차트 전용(부분성)으로 이 setting에서 본질적으로 측정 불가에 가깝다.
IVC/EMH도 같은 운명(VSC의 null 교훈). **코어는 깨끗하고 보편적인 두 지표뿐:**

- **node/path (구조)** — 차트+도식 300 전부(render→VLM→graph). 정규화 없음.
- **Evidence F1 (출처)** — ID 집합 연산, 차트+도식 300 전부. 정규화 없음, robust(0.333 vs 0.05).

framing value = 세 번째 지표가 아니라 **이 둘이 만드는 decoupling 발견**(§6.1'). 출처 축을 더
viz-스럽게 deepen하려면 **mark-level grounding coverage**(차트 datapoint·도식 node/edge의
source_eid 유효성; gold `supporting_evidence_ids` 활용) — 여전히 ID기반·정규화0·양 modality.
Data Accuracy는 살리면 **부록 67개 numeric-subset sanity check로만**, 헤드라인 금지.

---

## 3. MD-QA 공격의 구조적 무력화 (전략이슈 §8 해결)

원래 defense들은 전부 실패했다("multimodal MD-QA가 dominant라 modality 차별화 틀림" 등).
재정렬은 **공격을 증거로 전환**한다.

**공격**: "method가 hard MD reasoning을 잘하면 MD-QA에서도 SOTA 나와야. 안 나오면 우연,
나오면 MD-QA 논문."

**무력화 (3중)**:

1. **반사실 수치충실도(CNF)는 MD-QA에 존재 불가능한 실패다.** 텍스트 답은 숫자를 막대높이·
   노드좌표로 인코딩하지 않는다. "source의 45를 78로 바꿨을 때 차트가 따라가는가"라는 질문
   자체가 QA에는 없다. → reviewer는 "MD-QA SOTA 보여라"를 요구할 수 없다. 그 양상이 QA에
   *없기* 때문이다.
2. **Reverse-QA 프로브(L4 재활용)로 공격을 역이용.** B6가 검색한 evidence로 원 MD-QA 질문에
   답 → MD-QA 동급 정확도임을 보인다. 즉 **"retrieval은 MD-QA 수준으로 멀쩡한데, *그럼에도*
   차트 수치가 깨진다"** → 병목이 reasoning이 아니라 viz-인코딩임을 입증. 공격이 우리 주장의
   증거가 된다.
3. **method를 "더 나은 MD reasoner"로 주장하지 않는다.** 우리는 진단(C4)+측정도구(C5)+벤치마크
   (C1)를 판다. method(SAO)는 "격차를 닫는 메커니즘"이지 "MD 추론 SOTA"가 아니다.

---

## 4. 목표결과 (확보해야 할 숫자 — 우선순위순)

| # | 결과 | 기대치 | 강도 | 비고 |
|---|---|---|---|---|
| **R1** | **Evidence F1: B6 explicit vs baseline implicit, ≥3 출처** | B6 ~0.30–0.40 vs base ~0.05–0.10 | 헤드라인 | 현재 Loong만. **멀티소스 evidence가 최우선** (로그 E와 동일 결론) |
| **R2** | **구조-출처 decoupling**: 지표별 변별력 CV(Protocol 1) + 표본별 구조-출처 상관 | node/path CV 낮음(포화)·Evidence F1 CV 높음(변별); 상관 낮음(decoupled) | 헤드라인·신규 | 정규화0, 기존 점수로 계산. 양 modality 300 전부 |
| **R3** | **백본횡단 일관성** (R1·R2가 ≥2–3 백본서 유지) | 격차 부호 일관 | C4 핵심 | Qwen 확정 + API예산 풀리면 1–2개 |
| **R4** | node/path **3시드 mean±std** | B6 ≥ 최강baseline (노이즈 내 동급) | 보조 | "생성품질 희생 없이 귀속 우위" 서술 |
| **R5** | Reverse-QA: B6 evidence로 MD-QA 정확도 | MD-QA 동급 | 공격무력화 | §3-(2) |
| **R6** | SAO ablation (clean): SEF-입력 vs markdown-입력 agent의 Evidence F1 직접비교 | −SAO서 Evidence F1 급락 | C2/C5 뒷받침 | **복구산출 금지, native만** (B3) |

**게이트 재정의**: 기존 "4지표 모두 +0.020"은 폐기(node/path가 동률이라 충족 불가, 게이트③은
구조적 불가). 새 게이트 = **R1(Evidence F1) + R2(CNF) 두 핵심에서 유의 우위 + R4 동급유지.**

---

## 5. Framing 변경 (논문 구조 — 절별)

- **제목/Abstract**: "5축 + VSC 결정론 평가" → **"다문서 시각화의 출처귀속·수치충실도 병목:
  벤치마크와 진단"**. VSC를 제목에서 제거.
- **§1 기여**: C4 승격, C5(CNF) 추가, C2 격하(§2.2). "method가 더 낫다" 문장 삭제.
- **§4.5 VSC**: 정량 축에서 **삭제** → 부록 한 줄("spec→결정론 to_dsl이 구조유효성을 *보장*,
  따라서 위반은 설계상 0; 측정대상 아님"). tab:vsc·−VSC ablation row·게이트③ 제거.
- **§4.2 SEF**: "명명된 기여"에서 → "B6 입력표현". 검증은 R6(Evidence F1 직접비교)로만.
- **§5 평가**: node/path를 secondary로 명시. **CNF 프로토콜 신설**(§7).
- **§9 논의**: MD-QA 구별을 §3 3중논리로 전면 재서술. "viz-exclusive challenge"를
  CNF·SAO로 *구체적으로* 못박음(전략이슈 §8.5의 추상 6개 나열 금지 — 측정 가능한 것만).
- **한계**: 순환성(A2)·auto-gen gold·ablation 복구교란을 정직히 명시 + 그것이 결론을
  바꾸지 않는 이유(상대비교·counterfactual은 gold 불필요) 병기.

---

## 6. 실험 계획 (decoupling 진단 + 측정감사)

### 6.1' 구조-출처 decoupling — 신규 핵심 분석 (정정판, 새 데이터 수집 0)

**설계**: 새 생성 없이 *기존 표본별 점수*만으로 계산.
1. **변별력 (Protocol 1)**: 지표별 모델 간 CV=std/mean. 가설 — node/path CV<0.1(포화·변별불가),
   Evidence F1 CV 높음(sharp 변별). "표준 구조지표는 다문서 viz를 변별하지 못한다"의 정량 근거.
2. **decoupling 상관**: 표본 단위 node/path vs Evidence F1 산점도 + Pearson/Spearman. 가설 —
   상관 낮음. "구조적으로 완벽한 viz도 접지 안 됨"의 직접 증거.
3. **백본 무관성**: 1·2가 ≥2 백본서 유지 → C4.

**왜 깨끗한가**: ID기반 기존 점수만 사용 → **수치 정규화 0, 새 생성 0, 차트+도식 300 전부**.
당신이 지적한 두 함정(정규화·차트전용)이 구조적으로 발생 불가.

**(선택) mark-level grounding coverage** — 출처 축 deepen 시: 차트 datapoint·도식 node/edge
각각의 source_eid ∈ 유효 SEF id 비율. gold `supporting_evidence_ids`로 claim-level Evidence F1.
여전히 ID 집합 연산(정규화0)·양 modality. 새 fragile 축 아님 — 기존 Evidence F1 granularity 강화.

**(부록 한정) Data Accuracy** — 67개 numeric-table(≥2 numeric cell) 표본에서만, 단위 정규화
규칙 명시. sanity check·secondary. **헤드라인 금지.**

**측정감사 (Protocol 6-Pre-b)**: decoupling 분석은 파싱·매칭 단계가 없어(기존 점수 재사용)
측정오차 면이 거의 없음. 유일 검증 — 표본별 점수가 qid 단위로 올바로 join되는지(키 정합) 확인.

### 6.2 즉시 재측정 (교란된 것 바로잡기)

1. **R1 멀티소스 Evidence F1** — DocHop/MultiHop B6를 source_eids 넣어 재생성(C2 한계 해소).
   현재 viz-synth 근사는 evidence 측정 불가.
2. **R6 SAO ablation을 native 산출로** — `--recover-all` 균일복구 경로 폐기, agent native
   emission 기반. SEF-입력 vs markdown-입력 두 조건 직접비교.
3. **R4 3시드(42/43/44)** — node/path 단일시드 표 전부 mean±std로 교체.

### 6.3 모델 풀 (currency)

계획 백본 유지(Qwen3.5-397B / DeepSeek-V4 / GPT-5-mini / Opus 4.8) 중 **Qwen 확정 + 예산
풀리면 1개 클로즈드**로 R3 최소충족. ICLR 2027 시점 최신버전 web 재확인 후 고정(반사실·귀속은
백본 1–2개로도 진단 성립; 4백본은 nice-to-have). 채점 VLM은 격리실행 필수(D1).

---

## 7. 측정감사 1순위 (착수 전 반드시 확인)

1. **Evidence F1 gold 출처 확인** — query-provenance 기반인가(깨끗) vs 생성파이프라인 기반인가
   (순환). 코드 `score_phase1` + gold 생성경로 추적. **이게 헤드라인의 생사를 가른다.**
2. **CNF 10-샘플 프로토타입** (§6.1).
3. **데이터필드 검증** — claim_units.values.normalized_value가 *모든* 차트표본에 존재하는지
   출처별 확인. 없는 출처는 CNF 제외 표에 명시.

---

## 8. 리뷰어 시뮬레이션 (재정렬 후)

| | R1 진단회의론 | R2 method빈약 | R3 데이터품질 | R4 재현감사 |
|---|---|---|---|---|
| 주공격 | "출처귀속 낮은 게 흥미로운가, 그냥 어려운 거 아닌가" | "SAO=일반 citation, viz novelty 약함" | "auto-gen 질의·gold, 순환 아닌가" | "CNF 파싱·교란이 실제 되나, 백본 최신인가" |
| Fatal? | No | No(과거엔 Yes) | No | No |
| 무력화 증거 | R2 CNF counterfactual + R3 백본횡단 일관 = "진단적 보편 병목" | §3 3중논리 + CNF가 viz-배타 측정 신설 | counterfactual은 gold 불필요 + 90 human 골드검증 + Evidence gold provenance 확인(§7-1) | 10-샘플 프로토타입 + DiagramEval 공식코드 + 버전 web확인 |
| 예상점수 | 보더→약수용 | 약수용 | 보더 | 수용 |

**과거 fatal(R2 method 빈약)이 non-fatal로 강등된 것이 이 재정렬의 핵심 성과.**

---

## 9. Venue·타임라인

- **EMNLP 2026 main = 불가** (ARR 5/25 마감 경과, Phase 0는 6월 시작).
- **1순위: ICLR 2027 (~2026-09 마감)** — 벤치마크+진단+counterfactual 분석에 최적, ~3개월 runway로
  R1–R6 + CNF 프로토타입까지 충분. D&B성 작업도 main서 수용.
- **2순위(빠른 fallback): ARR 7월 → AACL 2026** — runway 짧으면 R1·R2·R4 핵심만으로 제출,
  R3·R5는 부록/후속.
- 권고: **ICLR 2027 타겟, R1+R2를 8월 내 확정**, R3–R6는 9월 초까지. 버퍼 ≥2주.

---

## 10. 단정형 결론 + 다음 3가지

데이터가 이미 답을 줬다: **method-superiority 논문을 포기하고, 출처귀속·수치충실도라는
viz-고유 병목의 진단 논문으로 재정렬하라.** node/path 헤드라인은 진다. VSC는 버려라. CNF
하나만 추가하라 — 그게 MD-QA 공격을 죽이고, 이미 이기고 있는 귀속 스토리를 viz-배타로 못박는다.

**지금 당장 (이번 주):**
1. **Evidence F1 gold provenance 추적** (§7-1) — 코드 확인 결과 gold는 gold-추출(다LLM union)
   에서 오고 DOC-level 비교 → 채점 Qwen과 분리되어 순환은 제한적. 단 **doc-level이 "RAG citation"
   공격에 약함** → mark/claim-level granularity 강화(§6.1' 선택) + human validation이 실제 취약점.
2. **decoupling 분석 (§6.1')** — 기존 Loong/DocHop 점수로 CV + 상관 즉시 계산(새 생성 0). 가설
   (구조 포화·출처 변별) 성립하는지 확인.
3. **R1 멀티소스 Evidence F1 재생성 착수** (DocHop/MultiHop, source_eids 주입).

이 셋의 결과로 ICLR 2027 vs AACL fallback을 9월 1주차에 확정한다. **value-level 수치 지표
(CNF·Data Accuracy)는 코어에서 제외 — §정정 참조.**
