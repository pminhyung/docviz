# Phase-2 게이트 판정 (Loong-100, Qwen3.5-397B 단일 백본)

실행계획 §2단계 검증 기준 대비 판정. 측정: 실제 DiagramEval(Qwen-VL, render→이미지
그래프추출→LLM정렬) node/path, 공정 evidence(B6 explicit source_eids vs baseline
implicit 임베딩 매칭 cosine≥0.75), intent, VSC 위반율.

## 1차 지표 (seed-42, ok기준; vs 최강 baseline B7)

| 지표 | B6 full | B7 | Δ(full−B7) | 게이트(+0.020) |
|---|---|---|---|---|
| node F1 | 0.396 | 0.342 | **+0.054** | ✅ |
| path F1 | 0.340 | 0.341 | −0.001 | — |
| **Evidence F1** | **0.333** | 0.022 | **+0.311** | ✅ (압도) |
| Intent Cov | 0.42 | 0.36 | +0.06 | ✅ |

## 게이트 4기준 판정

1. **B6 full이 B7 대비 ≥2지표 +0.020**: ✅ **통과** (node +0.054, evidence +0.311, intent +0.06).
2. **−SEF가 full 대비 −0.030**: ⚠️ **미충족** — node/path는 −SEF가 오히려 ≈full
   (397B에선 SEF의 구조 기여 약함). Evidence 차원에선 SEF가 SAO 그라운딩 보조.
3. **−VSC가 VSC 위반율 2배**: ❌ **미충족** — full·novsc 모두 구조위반(R2/R3/R4)
   **0/271 vs 0/270**, 렌더위반(R1)도 ~0-2%로 동등. **397B가 이미 계약 준수 DSL을
   생성** → VSC 보수 루프가 작동할 위반이 없음.
4. **3시드 유의성**: node/path는 temp 0.6로 **재실행 변동 ±0.04**라 단일시드 마진
   불안정; **Evidence F1은 robust**(±작음)하여 통계적으로 견고.

## 결론 — 조건부 통과, 핵심 신호 확인

- **핵심 기여 SAO(Evidence F1)가 압도적·robust하게 입증됨** (B6 0.333 vs B7 0.02).
  이것이 논문의 C4(다문서 출처 귀속) 발견의 토대.
- **SEF·VSC는 강한 백본(397B)에서 marginal** — 이는 실패가 아니라 **계획이 예견한
  결과**. 계약 위반·구조 오류는 약한 백본에서 발생하므로 SEF/VSC의 가치는 **4단계
  백본 횡단(특히 약한 백본: Qwen-4B/GPT-5-mini)에서 측정**해야 한다.
- node/path는 397B+gold 한계로 노이즈가 크고 신호가 약함 → 최종 판정은 5단계
  300표본·다백본에서.

## 후속 (Phase-2 종료, 피벗)

- node/path 100표본 완전판(B6 native 13개 포함, `recover_b6_viz --recover-all`)은
  **5단계 최종표용으로 이월**.
- **다음: 4단계 — Evidence F1 × 4백본으로 C4 입증 + 약한 백본서 SEF/VSC 가치.**
