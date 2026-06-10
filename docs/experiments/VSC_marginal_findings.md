# VSC (Visual Specification Contract) — 한계 실험 기록

**상태**: VSC 축의 측정 가능한 기여가 marginal. **VSC 제거(5축→4축) 또는 "결정론적
유효성 보장" 메커니즘으로 재프레이밍 검토 필요.**

날짜: 2026-06-10. 백본: Qwen3.5-397B(강), Qwen3-4B-Instruct-2507(약, 로컬 서빙).

## VSC가 노린 실패 모드
형식 오류 DSL(R1 렌더 실패), 차원 불일치(R2/R3), 끊긴 엣지(R4), 무효 출처 참조(R5).
파이프라인: brief → LLM이 canonical spec 합성 → **결정론적 to_dsl** → validate(R1-R5)
→ 1회 repair.

## 수렴하는 증거 (3종) — 위반이 백본 무관하게 거의 없음

| 측정 | 결과 |
|---|---|
| Phase-2 실데이터, full vs −VSC 구조 위반(R2/R3/R4) | **0/271 vs 0/270** (둘 다 0%) |
| Phase-2 렌더 실패(R1), full vs −VSC | ~0-2%, 양쪽 동등 |
| Qwen-4B(약)로 spec→to_dsl 합성, VSC 위반 | **0** (vsc_ok=True, repaired=None) |
| Qwen-4B **직접** DSL 생성(5 viz타입), 렌더 성공 | **5/5** (직접 생성도 안 깨짐) |

## 원인 (왜 VSC가 고칠 게 없나)
1. **결정론적 to_dsl**이 백본 품질과 무관하게 항상 구조적으로 유효한 DSL을 생성 →
   B6 내부에서 위반이 발생하지 않음. 그래서 −VSC ablation(spec-only도 to_dsl 사용)이
   full과 거의 동일 → VSC 기여 분리 불가.
2. **mermaid가 관대한 포맷** + **render.py auto-repair** → 약한 4B의 직접 생성마저
   렌더 성공.
3. 계획의 가설 "VSC는 약한 백본서 빛난다"가 **실증적으로 성립하지 않음** — 약한 4B에서도
   위반이 발생하지 않기 때문.

## 게이트 영향
- Phase-2 게이트 criterion ③ ("−VSC가 VSC 위반율 2배"): **구조적으로 충족 불가** —
  to_dsl이 결정론적이라 −VSC도 위반 0.

## 권고
- **(A) VSC 제거**: 5축 → 4축 (CIS, SEF, TMG, SAO). 논문에서 VSC 축·tab:vsc·−VSC
  ablation 삭제. SAO/Evidence가 robust한 핵심 기여이므로 주장 약화 없음.
- **(B) 재프레이밍**: VSC를 "위반을 고친다"가 아니라 "spec→결정론적 to_dsl로 유효성을
  *보장*한다"는 **안전장치**로 서술. 단 이 경우 정량적 우위 표(tab:vsc, −VSC)는 의미
  없으므로 정성적 서술로 한정.

robust한 진짜 기여는 **SAO / Evidence F1**(B6 0.333 vs B7 0.02, 백본 무관) — C4 발견의
토대. VSC 제거해도 이 핵심은 그대로.
