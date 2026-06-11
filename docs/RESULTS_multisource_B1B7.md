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
