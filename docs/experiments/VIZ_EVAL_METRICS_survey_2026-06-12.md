# 시각화(차트·도식) 생성 평가 지표 서베이 — 차용 후보 (2026-06-12)

> 목적: DocViz/QG-MDV가 **DiagramEval처럼 차용**할 수 있는, 시각화 분야에서 *이미 확립된*
> 평가 지표를 충실히 정리. 직전 논쟁(수치 정규화 함정, 차트 전용 부분성)에 대한 분야의
> 표준 해법을 포함. 각 지표: 차원 / 차트·도식 적용 / 결정론 vs judge / 공개코드 / 차용 적합성.

---

## 0. 핵심 발견 (직전 입장 정정)

직전에 "value-level 수치 충실도는 정규화 불가로 측정 불가"라 했으나, **서베이 결과 분야는
이 문제를 표준 관행으로 해결**해 놓았다:

- **Relaxed accuracy (5% tolerance)** — 수치는 gold 대비 5% 이내면 정답, 비수치는 exact.
  ChartQA(ACL Findings 2022) 이래 **사실상 분야 표준**. → "완벽한 정규화 불가"는 문제가 아님.
  아무도 완벽을 기대 안 하고, **5% 허용 + 집합매칭**을 모두가 받아들인다.
- **RNSS / RMS-F1** (DePlot, ACL Findings 2023) — permutation-invariant 표 유사도, 수치+텍스트,
  같은 5% tolerance. 결정론·공개. **순서·전치에 강건** → "어떤 숫자가 어디" 정렬 문제 해소.
- **CHARTEVAL** (Doc2Chart, EMNLP 2025) — 차트를 (x, y, value) 튜플로 보고 **source 표에
  역추적 검증**. visual decoding 회피. 우리의 *다문서 grounding*과 가장 정합.

**결론**: value-level 데이터 정확도는 *발명*하면 fragile하지만, **CHARTEVAL/RMS-F1 + 5%
tolerance를 차용**하면 분야 표준이라 방어된다. 단 차트 전용이므로 도식은 별도 지표로 덮는다(§3).

---

## 1. 차용 후보 매트릭스

| 지표 | 차원 | 차트 | 도식 | 방식 | 공개코드 | 출처(venue) |
|---|---|---|---|---|---|---|
| **CHARTEVAL** | 데이터 정확도·**출처귀속** (튜플→source표) | ✅ | ❌ | 결정론(구조 JSON) | △ 미확인 | Doc2Chart, EMNLP 2025 |
| **RMS-F1 / RNSS** | 데이터 정확도 (표 유사, 5% tol, perm-invariant) | ✅ | ❌ | 결정론 | ✅ | DePlot, ACL Findings 2023 |
| **Relaxed Accuracy 5%** | 수치 정확도(셀 단위) | ✅ | ❌ | 결정론 | ✅ | ChartQA, ACL Findings 2022 |
| **ChartMimic low-level** | text·layout·**type·color** F1 | ✅ | △ | 결정론(코드파싱) | ✅ | ChartMimic, ICLR 2025 |
| **ChartMimic high-level** | 시각 유사도 | ✅ | △ | GPT-4V judge | ✅ | ChartMimic, ICLR 2025 |
| **DiagramEval** | node/path 정렬(구조) | ✅* | ✅ | render→VLM→graph | ✅ (현재 사용) | DiagramEval, EMNLP 2025 |
| **TED + field-F1** | **트리 구조 충실도** (계층) | ❌ | ✅(mindmap/flowchart) | 결정론(트리파싱) | ✅ | MindBench, 2024 |
| **VisJudge (7B)** | **Fidelity–Expressiveness–Aesthetics** | ✅ | ✅ | fine-tuned VLM judge (corr 0.687) | ✅ +HF모델 | VisJudge-Bench, 2025 |

*DiagramEval은 차트도 그래프로 렌더-추출해 적용(현 파이프라인).
△ = 부분 적용/적응 필요. △(코드) = 공개 여부 미확인.

---

## 2. 차원별 정리 (무엇을 어떻게 재는가)

**(A) 데이터 충실도 / 수치 grounding — 차트.**
- CHARTEVAL: 차트 (x,y,value) 튜플을 source 표 값에 개별 검증 → completeness + correctness.
  *우리 setting에 최적* (다문서 source 표/claim_units에 역추적). visual decoding 불필요.
- RMS-F1 / RNSS: gold 표 vs 예측 표를 permutation-invariant로 매칭, 5% tol. CHARTEVAL 코드
  미공개 시 **즉시 차용 가능한 결정론 대체재**.
- Relaxed accuracy: 셀 단위 5% — 가장 단순, 보조.

**(B) 구조 충실도.**
- 차트: ChartMimic low-level의 type/color/text/layout F1(코드 파싱). 단 chart-to-code(참조코드
  존재) 가정 → 우리는 참조 DSL이 gold 표/그래프 → type/색 일부만 적응 차용.
- 도식(그래프): DiagramEval node/path (현행).
- 도식(트리: mindmap/flowchart/timeline): **TED(Tree Edit Distance) + field-F1** — 계층 구조의
  정밀 측정. node/path보다 트리에 적합. MindBench 공개구현.

**(C) 시각 품질 / 미학 — 차트+도식 공통.**
- **VisJudge**: Fidelity–Expressiveness–Aesthetics 3차원. fine-tuned 7B judge(Qwen2.5-VL,
  human corr 0.687, GPT-5 능가). **DiagramEval처럼 그대로 차용 가능한 judge 모델**. 단일·다중·
  대시보드, 32 차트유형 커버 → **우리의 다중산출물(k≤3)·차트+도식 혼합에 정합**.
- 이 3분할은 Mackinlay/Bertin InfoVis 고전을 잇는 framework → 전략이슈 §8.5가 원했던
  "viz-고유 차원"의 *확립된* 조작화. 우리가 발명할 필요 없음.

---

## 3. 권고 — 우리 파이프라인에 어떻게 박을까

### 3.1 차용 세트 (모달리티 전부 커버 — 부분성 공격 차단)

| 모달리티 | 데이터/출처 grounding | 구조 | 시각품질 |
|---|---|---|---|
| 차트(~106 gold table) | **CHARTEVAL식 튜플→source 검증** (코드 미공개면 **RMS-F1 + 5% tol**) + Evidence F1 | ChartMimic type/color 적응 | **VisJudge** F-E-A |
| 도식(~226 graph) | **Evidence F1** (ID 기반, 정규화0) | **DiagramEval node/path** + **TED**(트리형) | **VisJudge** F-E-A |

→ 모든 표본이 (grounding + 구조 + 시각품질) 3차원에서 *확립된 차용 지표*로 평가됨.
"차트만/도식만" 부분성 공격 불가. 정규화는 5% tol 표준 관행으로 방어.

### 3.2 우선순위

1. **RMS-F1(+5% tol) 차트 데이터 정확도** — 즉시 차용(공개), 결정론. CHARTEVAL은 코드 공개
   확인되면 교체/병기(다문서 출처귀속까지 봄).
2. **VisJudge judge** — DiagramEval과 동일하게 "차용한 공개 judge"로 시각품질 3차원. 자체
   judge 정당화 부담 없음(직전 폐기한 scope-v3/FSOS 문제 회피).
3. **TED** — mermaid mindmap/flowchart/timeline 트리 구조 보조.
4. **Evidence F1** — 출처귀속 헤드라인 유지(양 모달리티, 정규화0).

### 3.3 framing 효과 (value lift)

차용 지표들이 **decoupling 진단을 다차원으로 강화**한다:
- 구조(DiagramEval/TED/ChartMimic) + 시각품질(VisJudge) = **포화·동률** (생성은 유창)
- 데이터 정확도(RMS-F1/CHARTEVAL) + 출처귀속(Evidence F1) = **백본 무관 붕괴**
→ "시각화는 *구조적으로도 미학적으로도* 완벽해 보이는데 데이터·출처가 접지 안 됨, 표준 지표는
못 봄" — VisJudge의 Fidelity 축이 낮고 Aesthetics 축이 높은 **분리**를 그들의 framework로 직접
보일 수 있음. 발명이 아니라 차용으로 viz-고유 진단 완성.

---

## 4. 측정감사 메모 (Protocol 6-Pre-b)

- **RMS-F1 정규화**: 5% relaxed + permutation-invariant = 분야 표준. 단위/스케일은 gold 표
  단위에 맞춰 정규화(천 단위 등) — ChartQA/DePlot이 쓰는 그 절차 그대로. >2% 측정오차 우려는
  tolerance가 흡수.
- **적용범위 (no implicit universality)**: 데이터 정확도는 차트 표본(gold table 보유)만. 도식은
  Evidence F1+구조. 표에 ✅/❌ 명시(§3.1이 곧 그 cross-validation 표).
- **VisJudge 순환 회피**: VisJudge(Qwen2.5-VL 기반)와 우리 채점/백본이 겹치면 순환 — judge는
  **백본 풀과 분리**해 고정. human corr 0.687은 DiagramEval(0.43)보다 높아 정당화 강함.
- **CHARTEVAL 코드 가용성**: 미확인 → 1순위는 RMS-F1(확실 공개). CHARTEVAL은 공개 확인 시 추가.

---

## 5. 출처

- ChartQA (relaxed accuracy 5%) — Masry et al., ACL Findings 2022. arXiv:2203.10244
- DePlot (RNSS, RMS-F1) — Liu et al., ACL Findings 2023. arXiv:2212.10505
- ChartMimic (high/low-level) — ICLR 2025. arXiv:2406.09961, github.com/ChartMimic/ChartMimic
- Text2Chart31 (data table+code+plot, 자동피드백) — EMNLP 2024 Oral. arXiv:2410.04064
- Doc2Chart / CHARTEVAL (튜플→source 귀속) — EMNLP 2025. arXiv:2507.14819
- DiagramEval (node/path) — EMNLP 2025. github.com/ulab-uiuc/diagram-eval (현행)
- MindBench (TED + field-F1) — 2024. arXiv:2407.02842, github.com/MiaSanLei/MindBench
- VisJudge-Bench (Fidelity-Expressiveness-Aesthetics, VisJudge-7B) — 2025. arXiv:2510.22373,
  github.com/HKUSTDial/VisJudgeBench
- From Pixels to Insights (지표 taxonomy survey) — TKDE 2024. arXiv:2403.12027
