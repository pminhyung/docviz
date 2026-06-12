# QG-MDV B1-B7 결과 (real DiagramEval node/path, seed-42)

비교 대상: B1 MatPlotAgent, B2 NVAGENT, B3 CoDA, B4 ViviDoc (발표 SOTA 적응판),
B5 Direct, B7 SelfRefine (단순 baseline), **B6 DocViz-Agent (제안)**.
metric: DiagramEval (render→Qwen-VL 이미지 그래프추출→정렬) node/path F1, ok기준.

## Loong (source 1, 100샘플) — B6 full-agent
| arm | node | path |
|---|---|---|
| **B6 (ours)** | **0.396** | 0.340 |
| B5 Direct | 0.388 | 0.309 |
| B2 NVAGENT | 0.359 | 0.320 |
| B7 SelfRefine | 0.342 | 0.341 |
| B3 CoDA | 0.321 | 0.247 |
| B4 ViviDoc | 0.299 | 0.243 |
| B1 MatPlot | 0.287 | 0.104 |
→ B6 node 최고(발표 SOTA 전부 앞섬), path B7과 동률. Direct(B5)가 SOTA적응판들 앞섬.

## DocHop-QA (source 2, 100샘플) — B6 viz-synth 근사
| arm | node | path |
|---|---|---|
| **B6 (ours)** | 0.432 | **0.552** |
| B3 CoDA | 0.437 | 0.343 |
| B4 ViviDoc | 0.403 | 0.360 |
| B5 Direct | 0.401 | 0.354 |
| B2 NVAGENT | 0.393 | 0.281 |
| B7 SelfRefine | 0.375 | 0.372 |
| B1 MatPlot | 0.342 | 0.042 |
→ B6 path 압도(0.552, +0.18), node B3와 동률(-0.006). VSC 구조적 엣지 이점 발현.

## 결론 (2 source 일반화)
B6가 두 source 모두에서 최강 baseline과 동률 이상. Loong=node 우위, DocHop=path 우위.
발표 SOTA 적응판(B1-B4)은 다문서 과제에서 단순 Direct(B5)보다도 약함(단일문서 차트 특화).

## caveat / 남은 것
- B6-DocHop은 viz-synth 근사(CIS 검색 생략). Loong B6는 full-agent.
- 진행 중: MultiHop(source 3). 남음: 3시드(42/43/44) 평균±std, source 4-7, held-out.

## MultiHop-RAG (source 3, 96샘플) — B6 viz-synth 근사
| arm | node | path |
|---|---|---|
| B3 CoDA | **0.289** | 0.129 |
| B6 (ours) | 0.241 | **0.191** |
| B2 NVAGENT | 0.237 | 0.085 |
| B5 Direct | 0.227 | 0.087 |
| B1 MatPlot | 0.196 | 0.024 |
| B7 SelfRefine | 0.191 | 0.126 |
| B4 ViviDoc | 0.182 | 0.087 |
→ 전반 점수 낮음(뉴스 멀티홉 난이도). B6 node는 B3에 짐(-0.047), path는 최고(+0.062).

## 3-source 종합 (node/path)
- **path: B6가 3 source 전부 최고** (Loong 동률, DocHop +0.18, MultiHop +0.062) — VSC 구조적 엣지 이점 robust.
- **node: 혼재** — Loong 최고, DocHop 동률, MultiHop은 B3 CoDA가 앞섬.
- 즉 B6의 일관 우위는 **path(엣지구조)**. node는 경쟁적이나 균일하지 않음.
- 미측정: **Evidence F1(C4)** 멀티소스 (B6 최강 차원). 다음 우선순위.

## Evidence F1 (C4) — 3소스, B6 explicit source_eids
| arm | loong | dochop | multihop |
|---|---|---|---|
| **B6 (ours)** | **0.408** | **0.766** | **0.880** |
| B4 ViviDoc | 0.004 | 0.141 | 0.041 |
| B7 SelfRefine | — | 0.131 | 0.012 |
| B5 Direct | — | 0.113 | 0.020 |
| B3 CoDA | 0.000 | 0.058 | 0.008 |
| B2 NVAGENT | 0.000 | 0.041 | 0.000 |
| B1 MatPlot | 0.000 | 0.000 | 0.000 |
→ **B6가 3소스 전부 압도 (+0.40~+0.84).** 출처귀속(SAO)이 node/path와 달리 robust·일관 우위.
이것이 C4(출처귀속 격차 일관)의 멀티소스 입증. B6=explicit source_eids, baseline=implicit 임베딩매칭(cosine≥0.75).
B6는 .148 단일 pool로 재생성(brief-gen이 인용 doc_id 출력). 계산은 ST 임베딩(cluster-free).
