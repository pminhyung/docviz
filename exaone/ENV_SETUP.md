# Exaone `.env` Setup Guide

이 문서는 Exaone harness에서 `.env`를 **어디에 두고**, **어떤 값을 넣어야 하는지**를 빠르게 확인하기 위한 가이드입니다.

## 1) `.env` 파일 위치

- 파일 위치: **레포 루트**
- 경로 예시: `chatexaone-agent-harness/.env`

즉, 아래와 같이 `exaone/` 폴더 안이 아니라 프로젝트 최상위에 있어야 합니다.

```text
chatexaone-agent-harness/
├─ .env  <- 여기
├─ exaone/
├─ gateway/
└─ ...
```

## 2) 언제 로드되는가

- `exaone/serve.py` 또는 `hermes gateway run` 실행 시
- Exaone bootstrap 과정에서 레포 루트 `.env`를 로드합니다.

## 3) 실행 위치

- 반드시 **레포 루트 디렉토리에서 실행**하세요.
- 잘못된 위치에서 실행하면 `.env`가 기대대로 로드되지 않을 수 있습니다.

```bash
cd /path/to/chatexaone-agent-harness
HERMES_EXAONE_AGENT=1 API_SERVER_ENABLED=1 hermes gateway run
```

## 4) 필수/권장 환경변수

```env
# --- Project-local paths (HERMES_EXAONE_AGENT=1일 때 기본 적용) ---
HERMES_HOME=.hermes
EXAONE_TRACE_DIR=logs/exaone_traces

# --- LLM (vLLM / EXAONE) ---
EXAONE_BASE_URL=http://10.1.211.148:8000/v1
EXAONE_MODEL=Qwen3.5-397B-A17B-FP8
EXAONE_API_KEY=EMPTY
# Optional: main model call hyper-params defaults (JSON object).
# Applies as ExaoneAgent defaults; request body values still take precedence.
# VLLM_PARAMS_K_EXAONE={"max_tokens":15000,"temperature":1.0,"top_p":0.95,"seed":100000,"extra_body":{"return_tokens_as_token_ids":true,"top_k":1,"chat_template_kwargs":{"remove_last_turn":false,"enable_thinking":true}},"inputs_format":"string"}

# --- Exaone gateway ---
HERMES_EXAONE_AGENT=1
API_SERVER_ENABLED=1

# --- Tools (Brave API / Jina API) ---
BRAVE_API_KEY=...
JINA_API_KEY=...
```

### 변수 의미

- `HERMES_HOME`
  - Hermes 상태/설정/세션 DB 경로
  - Exaone 모드에서는 보통 레포 내부 `.hermes` 사용
- `EXAONE_TRACE_DIR`
  - `trajectory.json`, `raw_run_result.json` 저장 경로
- `EXAONE_BASE_URL`
  - vLLM(OpenAI-compatible) API 엔드포인트
- `EXAONE_MODEL`
  - 기본 추론 모델명
- `EXAONE_API_KEY`
  - vLLM 인증 키 (내부 무인증 환경은 `EMPTY` 관례 사용 가능)
- `VLLM_PARAMS_K_EXAONE` (또는 `EXAONE_VLLM_PARAMS`)
  - 메인 모델 콜 기본 하이퍼파라미터(JSON 문자열)
  - `max_tokens`는 agent `max_tokens` 기본값으로, 나머지 키는 `request_overrides`로 주입
  - API 요청 바디에서 같은 항목을 보내면 요청값이 우선
- `HERMES_EXAONE_AGENT`
  - Exaone 전용 코드 경로 활성화
- `API_SERVER_ENABLED`
  - `/v1/chat/completions` 등 API 서버 기능 활성화
- `BRAVE_API_KEY`
  - `web_search`에서 Brave API 호출 시 사용
- `JINA_API_KEY`
  - `web_extract`에서 Jina API 호출 시 사용

## 5) 적용 확인 방법

1. `.env` 수정
2. gateway 프로세스 재시작
3. trace/log에서 반영 확인

프로세스 재시작 전에는 기존 환경변수로 계속 동작할 수 있습니다.

## 6) 자주 하는 실수

- `.env`를 `exaone/.env`에 두는 경우
- 레포 루트가 아닌 다른 디렉토리에서 실행하는 경우
- `.env` 수정 후 gateway 재시작을 안 한 경우
- `BRAVE_API_KEY`, `JINA_API_KEY` 누락

