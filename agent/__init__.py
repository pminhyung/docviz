"""
Document Agent V2 — Custom Tool Extension API for Pipeline Experimentation

═══════════════════════════════════════════════════════════════════════
ARCHITECTURE INTENT (설계 의도 — 이 원칙을 위반하는 변경은 금지)
═══════════════════════════════════════════════════════════════════════

이 API의 핵심 목적:
  Client가 core 코드를 전혀 모르는 상태에서, 커스텀 tool action 파일(.py)
  하나만 작성/오버라이딩하는 것만으로 파이프라인 실험 및 SFT 학습 데이터
  생성이 가능하도록 하는 것.

핵심 원칙:
  1. 커스텀 툴 확장만으로 실험 가능 — client는 .py 파일에 tool class를
     정의하고 custom_tools_path로 전달하면 끝
  2. Duck typing 기반 계약 — tool은 execute(args, context) -> str만 구현
  3. 서비스 callable 노출 — context["call_llm"], context["record_training"] 등
  4. Inference + 학습 데이터 동시 생성
  5. 세션 누적 → GCS 업로드

이 원칙에 위배되는 리팩토링/변경은 하지 않는다.
═══════════════════════════════════════════════════════════════════════

This package provides:
1. Sealed runtime prompt vs public training system prompt
2. YAML-based override patch mechanism
3. Role-based model routing
4. Rich step-by-step trace export
5. Backward-compatible training JSONL export
6. Clean language enforcement (ENGLISH/KOREAN)
7. Document input via JSON file paths
8. CLI entrypoint
"""

__version__ = "2.1.0"
__all__ = ["config", "core", "export"]

# Training sample format versions:
#   v1 (default): 7 base keys + train_system_prompt + custom tool keys
#                 CHATEXAONE prefix applied. Compatible with doc_deep_*.py pipelines.
#   v2 (admin):   v1 + version, runtime_prompt_hash, override_hash,
#                 session_id, language, trace_summary, timestamp, metadata
#                 Activate via train_sample_version="v2" in RunRequestV2.
