# 실험 발견·결정 로그 (작성 agent용 맥락)

paper(`docviz_paper_draft_v0.4.2_ko.tex`) / plan(`docviz_execution_plan_v0.4.2_ko.tex`)
작성/수정 시 반영할 실험 발견과 결정. 각 항목: **이슈 → 조사 → 결정 → 논문 영향**.
숫자 결과는 `RESULTS_multisource_B1B7.md` 참조. (2026-06-10~12, branch feat/source-loaders)

---

## A. 측정(metric) 관련

**A1. DiagramEval은 render→VLM추출→LLM정렬 (자체 파서 폐기).** [확정]
- 이슈: 초기 자체 DSL-파서 node/path가 viz_type별로 다르게 깨져 측정 아티팩트(B5>B6 오인).
- 결정: 실제 DiagramEval 사용 — 생성 viz를 PNG 렌더 → **Qwen3.5-397B(VLM)이 이미지에서 그래프 추출** → Qwen LLM 노드 의미정렬 → node/path F1.
- 논문 영향: §5 평가. **Qwen3.5-397B은 VLM(멀티모달)** — "text-only"라는 서술 금지.

**A2. gold 참조 그래프도 Qwen 생성 (human_verified=False).** [확정·한계]
- 채점기(VLM/정렬)와 gold가 같은 Qwen군 → **순환 우려**. 단 모든 arm 동일 gold → arm 간 상대비교는 공정.
- 논문 영향: §5/타당성 위협에 명시. 절대값보다 상대비교. 사람검증은 6단계.

**A3. node/path는 노이즈 큼 (temp 0.6, 재실행 ±0.04).** [확정]
- 단일시드 +0.01~0.03 마진은 노이즈 내. **3시드 mean±std 필수**, 단일시드 단정 금지.
- 논문 영향: 결과표 3시드 보고. node/path는 보조 신호로 취급.

**A4. Evidence F1 = 논문의 핵심 기여(C4), 가장 robust.** [확정]
- B6 explicit source_eids vs baseline **implicit 임베딩매칭(cosine≥0.75)** — 둘 다 측정(코드 `score_phase1._implicit_pred_docs` 구현). Loong: **B6 0.333 vs baseline 0.05**(압도, 노이즈 무관).
- 논문 영향: **C4(다문서 출처귀속 격차)의 토대.** node/path보다 Evidence F1을 결과의 중심에 둘 것.

---

## B. 축(axis) 관련

**B1. VSC 제거 후보 (5축 → 4축: CIS/SEF/TMG/SAO).** [강한 권고]
- 이슈: VSC 위반-감소 가치가 백본 무관 marginal. Phase-2 full vs −VSC 구조위반 **0/271 vs 0/270**; Qwen-4B 직접생성도 5/5 렌더. 원인: 결정론적 to_dsl이 유효성 보장 + mermaid 관대 + render auto-repair.
- 결정: VSC 축·`tab:vsc`·−VSC ablation·게이트 criterion③ 삭제 검토. 근거 `docs/experiments/VSC_marginal_findings.md`.
- 논문 영향: §4.5 VSC, tab:vsc, −VSC ablation, Phase-2 게이트③ 제거 또는 "결정론적 보장" 메커니즘으로 재서술.

**B2. SEF는 유지 (이전 "marginal" 주장 철회).** [확정]
- 이슈: 한때 −SEF≈full(node/path)로 SEF marginal 의심.
- 조사: **−SEF ablation이 교란됨** — `recover_b6_viz`가 모든 arm에 SEF eids 주입(−SEF도 source_eids 보유, 83/84). 즉 절제가 SEF를 안 뺌. node/path는 SEF의 역할(그라운딩)을 측정하는 지표도 아님.
- 결정: **SEF 유지.** 제대로 검증하려면 에이전트를 SEF-입력 vs 마크다운-입력으로 돌려 **Evidence F1** 직접 비교 필요.
- 논문 영향: §4.2 SEF 유지. −SEF ablation은 evidence 기반으로 재측정해야 유효.

**B3. ablation은 복구과정에서 교란됨.** [방법론 주의]
- recover_b6_viz가 SEF eids 주입 + to_dsl 균일 적용 → 복구 아티팩트의 −SEF/−VSC 절제가 무력화. native emission(13%)은 사이드카에 qid 연결이 없어 별도 측정 불가(`--recover-all`로 전체 균일복구).
- 논문 영향: 5축 ablation(§T7)은 복구 아닌 native/agent 산출 기반이어야 유효.

---

## C. 비교대상(baseline)·실험 구성

**C1. B1-B4 = 발표 SOTA 적응판 (legacy 코드 부활).** [확정]
- `_legacy_v0.4_pre_harness/code/pipelines/{b1_matplotagent,b2_nvagent,b3_coda,b4_vividoc}.py`를 현재 Loong+H100백본으로 포팅. B5=Direct, B7=SelfRefine.
- 논문 영향: 비교대상 라인업표(현재 B1-B7 전부 실측됨). 단일문서 차트용 B1-B4가 다문서서 단순 Direct(B5)보다 약함 — 논의거리.

**C2. 멀티소스 B6는 viz-synth 근사 (CIS 검색 생략).** [한계]
- Loong B6는 full-agent(faithful). DocHop/MultiHop B6는 brief→SEF-spec→VSC→to_dsl 합성(에이전트 retrieval 없이 docs 직접). node/path엔 적합하나 evidence 측정 불가(source_eids 빈 채 생성). **evidence 측정하려면 source_eids 넣어 재생성 필요.**
- 논문 영향: 멀티소스 B6 결과는 viz-생성 품질 근사로 명시.

---

## D. 인프라·데이터 현실

**D1. 백본**: Qwen3.5-397B(H100 클러스터 10.1.211.163-170, **api_key=vs_task_only**). Qwen-4B는 약한백본 probe(논문 백본 아님 — 계획 백본은 397B/DeepSeek/GPT-5-mini/Opus). 클로즈드 백본은 API비용 홀딩으로 보류 → C4 4백본 일부 차단.
- vision 채점은 **격리 실행 필수**(경쟁 다운로드/잡이 자원포화→hang).

**D2. 데이터 가용성**: Loong/DocHop/MultiHop(번들+쿼리+gold 완료) + Text2Vis(docs만). 나머지 source(FinMMDocR/VisDoM/FinAuditing/TEMPO)·held-out(Doc2Chart/SciDoc) 다운로드/로더 미완.
- 논문 영향: 현재 결과는 3 source(7 중). 300샘플·7출처는 5단계.

---

## E. 현재까지 결과 (요약 — 상세는 RESULTS_multisource_B1B7.md)

**3소스(Loong/DocHop/MultiHop) × B1-B7, seed-42 완료.**

- **Evidence F1 (C4·핵심): B6가 3소스 전부 압도** — 0.408 / 0.766 / 0.880 vs 최강 baseline ~0.00 / 0.141 / 0.041 (B6 explicit source_eids vs baseline implicit 임베딩매칭). **C4(출처귀속 격차 파이프라인 무관 일관)의 멀티소스 입증.** node/path와 달리 robust·일관·압도.
- **path (DiagramEval): B6가 3소스 전부 최고** (구조 엣지 정렬, VSC 이점).
- **node (DiagramEval): 경쟁적** — Loong 최고, DocHop 동률(B3와), MultiHop 2위(B3가 1위). 노이즈 큼(단일시드).
- intent: Loong만(B6 0.42 ≈ baseline) — 멀티소스 미측정.
- 발표 SOTA 적응판(B1-B4)이 다문서서 단순 Direct(B5)보다도 약함.

**남은 것**: 3시드(42/43/44) mean±std, intent 멀티소스, source 4-7(FinMMDocR/VisDoM/FinAuditing/TEMPO)+held-out, 논문 VSC제거·SEF정식측정.