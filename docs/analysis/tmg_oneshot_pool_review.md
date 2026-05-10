# Q2 draft 검수 — `tmg_oneshot_pool_draft.md` v0 evaluator review

**Date**: 2026-05-10
**Reviewed artifact**: `docs/analysis/tmg_oneshot_pool_draft.md` (575 lines, 18 exemplars, commit baseline TBD)
**Reviewer**: evaluator agent (read-only, 6-axis structured review)
**Verdict**: **ACCEPT_WITH_REVISIONS** — must-fix 3, minor 4
**Ground truth checked**:
- `outputs/prototype/judge_scores/all.json` (anchor faith score verification)
- `outputs/prototype/viz/all.json` (anchor viz_dsl content verification)
- `code/pipelines/tmg.py` (caller migration impact)
- mentor risk safeguards (`WEEK0_FOLLOWUP_ACTIONS.md` 액션 3 — 4 risks)

---

## 1. 강한 부분 (그대로 OK)

| 검증 항목 | 결과 | 메모 |
|---|---|---|
| Schema validity | **18/18 pass** | `json.loads` round-trip 모두 통과. chartjs nested JSON + mermaid header pattern 정확. mapper strategy 1a fast-path 보장. |
| Anchor 진정성 | **8/8 sample pass** | subagent 가 anchor 로 표시한 records 의 faith 점수가 `judge_scores/all.json` 의 실측과 정확 일치. hand-written 으로 표시한 것도 정직 disclose (특히 chartjs_line 의 2/3). |
| Edge label content style | **clean** | placeholder 단조 verb 패턴 (`founded`/`acquired`/`hired`/`advised`) 발견되지 않음. FLOW-A 의 `"Retired Indian Navy Flag Officer"`, `"Authorized Operation Trident-II in"` 같은 풍부한 phrase 가 지배적 — C5 pattern (a)(d)(e) 차단 기대. |
| Syntactic spread | **mostly strong** | chartjs_bar / chartjs_grouped_bar / mermaid_timeline 강함. chartjs_line borderline pass. mermaid_flowchart / mermaid_mindmap 는 must-fix 의 #2·#3 참조. |
| Archetype mix | **acceptable** | Wikipedia 4 + news 4 + paper-methods 5 + financial 6. 약간 financial-heavy 지만 spread 자체는 4 archetype 모두 존재. must-fix #1 에서 financial 쪽 reuse 가 일부 inflate 되어있음. |
| Paste-readiness | **PASS** | §3 의 Python literal 그대로 dict literal 로 파싱 가능. 단 typing migration 은 minor #4 참조. |

## 2. Must-fix (commit-block)

### Must-fix #1 — `Acme Industries` 가 5/18 exemplar 에 재사용

영향: **brief 의 exclusion list 에 `Acme Corp` 가 명시** 되어있는데, "Acme Industries" 는 그 rebrand 에 불과. 같은 placeholder 패턴이 5 exemplar (28% of pool) 에 침투. 이는 mentor risk #2 (self-bootstrap 의 quirk amplification) 와 직접 연관.

해당 exemplar 와 swap 후보 (evaluator 제안):

| exemplar | 현재 entity | 권고 swap |
|---|---|---|
| BAR-A | Acme Industries | **Northbridge Energy** |
| BAR-B | Acme Industries | **Carrillon Software Group** |
| GBAR-A | Acme Industries | **Halverson Bancorp** |
| LINE-C | Acme Industries | **Verdant Aerospace** |
| TIME-A | Acme Industries | **Atlas Robotics** |

추가: `Lakeshore Foundation` 도 LINE-A + GBAR-B 에 reuse — 한 번 더 분산 권장 (예: GBAR-B 를 다른 fictional org 으로).

### Must-fix #2 — mermaid_flowchart 의 *hub-and-spoke* shape 누락

영향: brief 가 명시한 3 가지 spread (chain / hub-and-spoke / subgraph-cluster) 중 hub-and-spoke 가 빠짐. 현재:
- FLOW-A: chain (5 nodes, sequential edges)
- FLOW-B: subgraph-with-cluster
- FLOW-C: parallel-subgraphs

→ pure hub-and-spoke (1 center + 5-7 peripherals, no subgraph) exemplar 가 없음. mentor action 5 의 syntactic spread 검증 항목 미충족.

해결: hub-and-spoke exemplar 1 개를 hand-write (FLOW-B 교체 또는 4 번째 slot 추가). 도메인 archetype 은 paper-methods 또는 Wikipedia 권장 (financial 은 이미 over-represented).

### Must-fix #3 — MIND-A 의 hotpot prototype entity 누출

영향: MIND-A 가 `Daler Mehndi & Tunak Tunak Tun` 사용 — 이건 **실제 prototype query 에 등장하는 entity** 와 거의 일치 (subagent 본인 §4.1#2 가 "medium-low risk" 로 self-flag). V4 측정 시 이 exemplar 가 prompt 에 들어가면 model 이 query 답을 example 에서 직접 보게 됨 → self-leak.

해결 옵션:
- (a) entity swap (다른 fictional biographical-compare archetype)
- (b) exclude (V4 측정 시 query_id 단위로 가드)
- 권장: (a). subagent revision 단계에서 entity replace.

## 3. Minor improvements (no-blocker)

### #4 — Caller migration plan 필수
`code/pipelines/tmg.py:72` 의 `ONE_SHOT_BY_VIZ_TYPE: Dict[str, str]` 가 `Dict[str, List[str]]` 로 변경되면 line 155 의 `one_shot = ONE_SHOT_BY_VIZ_TYPE[primary]` call site 가 break. 같은 commit 에:
- `select_oneshots(viz_type, query_id, k=1)` helper 추가
- `build_tmg_rule` 에서 helper 사용으로 caller 수정

### #5 — Sampler 결정성 강화
draft §3.1 의 sampler 가 `hash(query_id)` 사용 → `PYTHONHASHSEED` 영향으로 cross-process 재현 안 됨. `hashlib.sha1(query_id.encode()).hexdigest()` 로 교체.

### #6 — 2-level shallow mermaid_mindmap exemplar 추가
현재 mermaid_mindmap exemplar 모두 3-level 이상. 짧은 hierarchy source (예: 단일 paper 의 method-comparison 같은) 에서는 2-level 가 적합. shallow 1 개 추가 권장.

### #7 — `test_oneshot_pool_parses` smoke test
evaluator 가 manually 통과시킨 schema 검증 (json.loads round-trip + viz_type enum match + chartjs `type` field present + mermaid header sniff) 을 pytest 으로 pin. 향후 pool 수정 시 regression 방지.

## 4. 남는 결정 항목 (검수자 → 수정자)

- (a) **5 swap 후보 (Northbridge / Carrillon / Halverson / Verdant / Atlas)** 를 그대로 채택할지, 아니면 더 의미있는 도메인 명을 자체 선정할지.
- (b) FLOW hub-and-spoke 의 archetype: paper-methods (e.g., research framework with central concept + sub-techniques) vs Wikipedia (e.g., individual + their works) vs news (e.g., event + its consequences). **권장: paper-methods** (current pool 에서 Mermaid 쪽 paper-methods 비중 적음).
- (c) MIND-A swap 의 archetype: 다른 biographical comparison 유지 vs 완전 다른 archetype (e.g., paper-methods comparison)?

## 5. Verdict

**ACCEPT_WITH_REVISIONS**. must-fix 3 가 적용되면 V4 측정 코드 paste 가능. minor 4 는 같은 commit 에 묶거나 별도 PR.

다음 단계: 원래 Q2 subagent (Option B per user direction) 에 SendMessage 로 revision 요청 + 추가 directive (consolidated single one-shot variant + per-type file split).
