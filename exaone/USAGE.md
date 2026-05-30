# ExaoneAgent Usage

`ExaoneAgent`는 LGAI EXAONE / Qwen 계열 모델을 vLLM OpenAI-compatible 엔드포인트에 연결하는 `AIAgent` 서브클래스다. prompt-facing tool(`web_search`, `web_extract`) + custom template tool(`doc_tool`, `code_tool`) + canvas tool(`get_canvas_status`, `create_canvasdoc`, `update_canvasdoc`) 조합, 5-block 시스템 프롬프트, 학습 데이터용 Trace 저장, Per-query toolset/reasoning 제어를 제공한다.

현재 EXAONE 커스터마이징 경로는 **stateless per-request** 운용을 목표로 한다. 요청마다 새 `ExaoneAgent` 인스턴스를 생성하고, `qa_mode`/`toolset`에 따라 tool 가용 범위와 pre-query 프롬프트를 `__init__()`에서 확정한다.

---

## 실행

```bash
HERMES_EXAONE_AGENT=1 API_SERVER_ENABLED=1 hermes gateway run
```

일부 환경에서는 gateway 초기화 시 runtime provider 검증이 먼저 수행되므로, **최초 1회 `hermes model` 설정이 사실상 필요**하다.  
설정하지 않으면 아래 에러가 날 수 있다.

```text
No inference provider configured. Run 'hermes model' ...
```

```bash
hermes model
```

권장 절차(예: vLLM OpenAI-compatible 엔드포인트):

1. `hermes model` 실행
2. provider에서 `custom (direct API)` 선택
3. URL 입력 프롬프트에 `http://<vllm-host>:<port>/v1` 입력
4. API key 프롬프트에는 vLLM 설정에 맞게 입력 (`EMPTY` 또는 실제 키)
5. 모델명 입력(예: `Qwen`)

예시 입력:

```text
$ hermes model
Select provider: custom (direct API)
Base URL: http://10.1.211.148:8000/v1
API key: EMPTY
Model name: Qwen
```

위 과정을 1회 완료하면 API 서버 기동 후 ExaoneAgent 경로(`HERMES_EXAONE_AGENT=1`)를 정상 사용할 수 있다.

환경변수 없이 실행하면 기존 AIAgent 그대로 동작한다.

---

## API 파라미터

`POST /v1/chat/completions` 요청 body에 아래 필드를 추가할 수 있다.

### 기본 요청

```bash
curl http://127.0.0.1:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer EMPTY" \
  -d '{
    "messages": [{"role": "user", "content": "LG AI Research에 대해 검색해줘"}],
    "stream": false
  }'
```

### `toolset` — 사용할 tool 범위 지정

```bash
# 단일 tool 이름
"toolset": "web_search"

# 여러 tool 이름 union (합집합)
"toolset": ["web_search", "code_tool"]

# 미지정 시 기본 웹 toolset 사용 (web_search, web_extract)
```

> `toolset`과 `qa_mode`는 동시에 사용할 수 없다. 함께 보내면 400 에러가 반환된다.

```bash
curl http://127.0.0.1:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer EMPTY" \
  -d '{
    "messages": [{"role": "user", "content": "search lg ai research"}],
    "stream": false,
    "toolset": ["web_search", "code_tool"]
  }'
```

### `reasoning` — Thinking 토큰 on/off

```bash
# thinking 비활성화 (응답 빠름, reasoning_content 없음)
"reasoning": false

# thinking 활성화 (기본값)
"reasoning": true
```

```bash
curl http://127.0.0.1:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer EMPTY" \
  -d '{
    "messages": [{"role": "user", "content": "2+2는?"}],
    "stream": false,
    "reasoning": false
  }'
```

> vLLM에 `chat_template_kwargs: {"enable_thinking": false}` 로 전달된다. Qwen3.5 계열 모델 기준.

### `enabled_toolsets` — 최우선 toolset 지정 (hermes built-in 포함 가능)

```bash
# EXAONE_TOOLSET 그룹 이름
"enabled_toolsets": "doc_tools"

# 개별 tool 이름 (hermes built-in tool도 가능)
"enabled_toolsets": ["web_search", "doc_tool"]
```

- `qa_mode`와 `toolset`보다 **우선순위가 높다.** 셋 중 `enabled_toolsets`가 있으면 나머지 두 필드는 무시된다.
- `qa_mode` / `toolset`과 달리 **hermes built-in tool(memory 등)도 포함할 수 있다.** `enabled_toolsets`를 지정하면 AIAgent pool이 exaone-tools로 제한되지 않고 전체 tool에서 필터링한다.
- 값은 `EXAONE_TOOLSET` 그룹 이름(`"web_tools"`, `"doc_tools"`, ...), hermes toolset 이름, 또는 개별 tool 이름을 문자열이나 리스트로 전달한다.

| 파라미터 | AIAgent pool | 설명 |
|---|---|---|
| `qa_mode` / `toolset` | exaone-tools만 | EXAONE 전용 tool만 사용 가능 |
| `enabled_toolsets` | 전체 (hermes + exaone) | hermes built-in tool도 사용 가능 |

```bash
curl http://127.0.0.1:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer EMPTY" \
  -d '{
    "messages": [{"role": "user", "content": "문서에서 찾아줘"}],
    "stream": false,
    "enabled_toolsets": "doc_tools"
  }'
```

### `qa_mode` — mode 기반 system block + toolset 선택

```bash
"qa_mode": "general"
```

- `qa_mode`는 ExaoneAgent가 mode 정의(`QA_MODES`)를 보고 `EXAONE_TOOLSET` 그룹 리스트, `identities/<name>.txt`, `style/<name>.txt`를 함께 결정한다.
- 각 mode의 `toolset`은 `EXAONE_TOOLSET` 키(그룹 이름) 리스트다. 리스트에 있는 그룹을 union해서 실제 tool 목록을 구성한다.
- `qa_mode`가 가리키는 필수 prompt 파일이 없으면 `RuntimeError`로 처리되며 API에서는 400 에러를 반환한다.
- `qa_mode`와 `toolset`은 mutual exclusive다.
- `tool_list` 블록은 고정 파일이 아니라 **이번 요청에서 실제로 활성화된 tool 목록** 기준으로 `prompts/tools/<tool_name>.txt`를 조합해 생성된다.

현재 정의된 mode:

| mode | toolset 그룹 | 실제 tools | identity | style |
|---|---|---|---|---|
| `general` | `["web_tools"]` | `web_search`, `web_extract` | `default` | `default` |
| `research` | `["web_tools"]` | `web_search`, `web_extract` | `research` | `research` |
| `canvas` | `["web_tools"]` | `web_search`, `web_extract` | `think` | `think` |

```bash
curl http://127.0.0.1:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer EMPTY" \
  -d '{
    "messages": [{"role": "user", "content": "LG AI Research에 대해 검색해줘"}],
    "stream": false,
    "qa_mode": "general"
  }'
```

---

## Built-in / Custom tool 구성

`exaone/tools.py`에서 Exaone 전용 toolset을 구성한다.

`EXAONE_TOOLSET`은 fine-grained 그룹 단위로 tool을 정의한다. `qa_mode` 또는 `toolset` 파라미터에서 이 그룹 이름을 리스트로 지정하면 union되어 실제 tool 목록을 구성한다.

```python
EXAONE_TOOLSET: dict = {
    "web_tools":    ["web_search", "web_extract"],
    "doc_tools":    ["doc_tool"],
    "code_tools":   ["code_tool"],
    "canvas_tools": ["canvas_tool"],
}
```

예를 들어 `toolset=["web_tools", "code_tools"]`를 전달하면 `web_search`, `web_extract`, `code_tool` 세 가지가 활성화된다.

---

## Tool 이름 규칙

`toolset` 인자에는 short tool name을 전달한다: `{tool_name}`

### Tool prompt 설명 파일

요청에서 실제로 사용되는 tool들의 설명 프롬프트는 아래 경로에서 조합된다.

```text
exaone/prompts/tools/<tool_name>.txt
```

예:

- `exaone/prompts/tools/web_search.txt`
- `exaone/prompts/tools/web_extract.txt`
- `exaone/prompts/tools/code_tool.txt`
- `exaone/prompts/tools/doc_tool.txt`
- `exaone/prompts/tools/echo.txt`

---

## Trace 출력

`run_conversation()` 완료 시 아래 구조로 저장된다.

```
<project-root>/.hermes/exaone_traces/
└── 20260515T123456Z/          ← UTC timestamp
    └── <query-id>/            ← UUID
        ├── raw_run_result.json                          ← RunResult-compatible 전체 trace
        ├── trajectory.json                              ← inference 메시지 형식(role/content, completed run만)
        ├── 01_step1-N_pre_compaction.json               ← compaction 직전 messages
        ├── 01_step1-N_compaction_round_trip.json        ← summarizer 결과 텍스트
        └── 01_step1-N_post_compaction.json              ← compaction 직후 messages
                                                           (_force_finish suffix: max_iterations 도달 시)
```

compaction triplet은 compaction 발생 횟수만큼 생성된다 (`01_`, `02_`, ...).

환경변수 `EXAONE_TRACE_DIR`로 저장 경로를 변경할 수 있다.

### 최신 trace 보기

```bash
LATEST=$(ls -td ./.hermes/exaone_traces/*/*/ | head -1)

# 전체 trace
cat "${LATEST}raw_run_result.json" | python3 -m json.tool

# trajectory (대화 흐름)
cat "${LATEST}trajectory.json" | python3 -m json.tool

# 대화 내용만 출력
cat "${LATEST}trajectory.json" | python3 -c "
import sys, json
for t in json.load(sys.stdin)['messages']:
    print(f'[{t[\"role\"]}]')
    print((t.get('content') or '')[:500])
    print()
"

# compaction 요약 텍스트 확인
cat "${LATEST}01_step1-"*"_compaction_round_trip.json" | python3 -m json.tool
```

---

## Finalization 프롬프트

max_iterations(기본값 10) 도달 시 모델에게 최종 답변을 요청하는 프롬프트를 커스터마이즈할 수 있다.

```
exaone/prompts/finalization/
├── system.txt           ← 기존 system 프롬프트를 교체 (tool-using 모드 탈출)
└── termination_user.txt ← 대화 끝에 추가되는 유저 메시지
```

두 파일 모두 없으면 영어 fallback 프롬프트가 사용된다. 파일이 있으면 그 내용이 그대로 사용되므로 자유롭게 편집 가능하다.

> Thinking은 finalization 호출 시 무조건 off로 강제된다 (`enable_thinking: false`).

---

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `HERMES_EXAONE_AGENT` | — | `1`로 설정 시 ExaoneAgent 활성화 |
| `EXAONE_BASE_URL` | `http://10.1.211.148:8000/v1` | vLLM 엔드포인트 |
| `EXAONE_MODEL` | `Qwen` | 모델명 |
| `EXAONE_API_KEY` | `EMPTY` | API 키 |
| `EXAONE_TRACE_DIR` | `<project-root>/.hermes/exaone_traces` | Trace 저장 경로 |
| `EXAONE_SAVE_RAW_TRACE` | `1` | `0`으로 설정 시 `raw_run_result.json` 저장 안 함 |
| `EXAONE_SAVE_TRAJECTORY` | `1` | `0`으로 설정 시 `trajectory.json` 저장 안 함 |

> 환경변수는 gateway 시작 시 1회 읽힌다(`lru_cache`). `.env` 수정 후에는 gateway 재시작이 필요하다.

> `max_iterations` 기본값은 10. 생성자에서 `max_iterations=N`으로 오버라이드 가능하다.

---

## CLI 실행 (`exaone/cli.py`)

gateway 없이 ExaoneAgent를 직접 CLI로 실행할 수 있다.  
API payload 파라미터(`qa_mode`, `toolset`, `reasoning`)가 CLI 인자로 그대로 매핑된다.

```bash
# 기본 실행
python exaone/cli.py "LG AI Research 검색해줘"

# qa_mode 지정
python exaone/cli.py "LG AI Research 검색해줘" --qa_mode=general

# toolset 직접 지정 (단일)
python exaone/cli.py "search lg ai" --toolset=web_search

# toolset 리스트 (JSON 형식)
python exaone/cli.py "query" --toolset='["web_search","code_tool"]'

# enabled_toolsets 지정 (qa_mode/toolset보다 우선, hermes built-in tool도 가능)
python exaone/cli.py "문서 찾아줘" --enabled_toolsets=doc_tools
python exaone/cli.py "메모리 조회" --enabled_toolsets=memory

# reasoning 끄기
python exaone/cli.py "2+2는?" --reasoning=false

# trace 저장 없이 실행
EXAONE_SAVE_RAW_TRACE=0 EXAONE_SAVE_TRAJECTORY=0 python exaone/cli.py "query"
```

`HERMES_EXAONE_AGENT=1`은 불필요하다. `bootstrap_gateway_env()`가 내부에서 자동으로 세팅한다.

### API payload ↔ CLI 인자 대응

| API payload 필드 | CLI 인자 | 기본값 |
|---|---|---|
| `messages[0].content` | `query` (positional) | 필수 |
| `enabled_toolsets` | `--enabled_toolsets` | `None` |
| `qa_mode` | `--qa_mode` | `None` |
| `toolset` | `--toolset` | `None` |
| `reasoning` | `--reasoning` | `True` |
| — | `--verbose` | `False` |
| — | `--max_iterations` | `10` |

---

## AIAgent 기본 기능 비활성화

ExaoneAgent는 stateless per-request 운용에 불필요한 AIAgent 내장 기능들을 초기화 시점에 끈다.

| 기능 | 설정 | 이유 |
|---|---|---|
| `session_db` | `None` 강제 | 자체 tracer(raw_run_result.json, trajectory.json)로 대화 기록. gateway가 넘겨도 SQLite 중복 저장 불필요 |
| `tool_delay` | `0` | tool call 간 기본 1s sleep 제거. vLLM 로컬 엔드포인트에서 rate limit 없음 |
| `_cleanup_dead_connections()` | no-op override | per-turn httpx connection pool zombie socket 검사 제거. stateless라 이전 turn 좀비 소켓 개념 없음 |
| `_persist_session()` | no-op override | per-turn session JSON 파일 쓰기 + SQLite 쓰기 제거. tracer 파일로 이미 기록 |
| `skip_memory` | `True` | 메모리 DB 로드/저장 불필요 |
| `skip_context_files` | `True` | SOUL.md, AGENTS.md, .cursorrules 시스템 프롬프트 주입 불필요 |
| `enabled_toolsets` | `[EXAONE_TOOLSET_NAME]` (qa_mode/toolset 사용 시) | `qa_mode`/`toolset` 사용 시 hermes 내장 toolset 차단. `enabled_toolsets` 인자 전달 시 pool 전체 개방 |

---

## Batch Runner

`exaone/batch_runner.py`는 JSONL 데이터셋으로 대량 학습 데이터를 생성하는 배치 처리기다. gateway 없이 `ExaoneAgent`를 직접 호출하며, 병렬 처리·체크포인트·resume를 지원한다.

### 실행

```bash
HERMES_EXAONE_AGENT=1 uv run python exaone/batch_runner.py \
  --dataset_file=data.jsonl \
  --batch_size=10 \
  --run_name=my_run \
  --num_workers=4
```

### JSONL 입력 형식

각 행에 `prompt` 필드가 필수이며, `enabled_toolsets` / `qa_mode` / `toolset` / `reasoning`을 선택적으로 지정한다.

```jsonl
{"prompt": "LG AI Research 검색해줘", "qa_mode": "general"}
{"prompt": "리서치 해줘", "qa_mode": "research"}
{"prompt": "코드 실행해줘", "toolset": ["code_tool"]}
{"prompt": "피보나치 짜줘", "qa_mode": "general", "reasoning": false}
{"prompt": "문서에서 찾아줘", "enabled_toolsets": "doc_tools"}
{"prompt": "문서+웹 병행", "enabled_toolsets": ["doc_tool", "web_search"]}
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `prompt` | ✅ | 유저 쿼리 |
| `enabled_toolsets` | — | 최우선 toolset 지정. 있으면 `qa_mode`·`toolset` 무시. hermes built-in tool도 포함 가능 |
| `qa_mode` | — | mode 기반 toolset + 시스템 프롬프트 선택. `toolset`과 상호 배타 |
| `toolset` | — | tool 이름(또는 그룹 이름). `qa_mode`와 상호 배타 |
| `reasoning` | — | 행별 thinking 토큰 on/off. 미지정 시 CLI `--reasoning` 기본값 사용 |

- `enabled_toolsets`가 없고 `qa_mode`와 `toolset` 모두 미지정이면 `qa_mode="general"` 기본값 적용
- `reasoning`은 행별로 CLI 전역값을 덮어쓸 수 있다

### CLI 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--dataset_file` | (필수) | JSONL 파일 경로 |
| `--batch_size` | (필수) | 배치당 prompt 수 |
| `--run_name` | (필수) | 실행 이름 (출력 디렉토리명) |
| `--num_workers` | `4` | 병렬 worker 프로세스 수 |
| `--max_turns` | `10` | prompt당 최대 tool 호출 횟수 |
| `--reasoning` | `true` | 전역 thinking 토큰 on/off (행별 `reasoning` 필드로 덮어쓰기 가능) |
| `--resume` | `false` | 체크포인트 기반 이어하기 |
| `--max_samples` | — | 데이터셋 앞 N개만 처리 |
| `--verbose` | `false` | 상세 로그 출력 |

### 출력 구조

```
data/<run_name>/
├── batch_0.jsonl          ← 배치별 결과 (디버깅용)
├── batch_1.jsonl
├── ...
├── trajectories.jsonl     ← 전체 합본 (학습 데이터)
├── statistics.json        ← tool 사용 통계
└── checkpoint.json        ← resume용 체크포인트
```

Exaone trace는 `run_conversation()` 완료마다 별도 기록된다.

```
<project-root>/logs/exaone_traces/
└── <UTC-timestamp>/<query-id>/
    ├── raw_run_result.json
    └── trajectory.json
```

### Resume

중단된 실행을 이어하려면 동일한 `--run_name`에 `--resume`을 추가한다.

```bash
HERMES_EXAONE_AGENT=1 uv run python exaone/batch_runner.py \
  --dataset_file=data.jsonl \
  --batch_size=10 \
  --run_name=my_run \
  --num_workers=4 \
  --resume
```

`--resume` 없이 동일 `--run_name`으로 재실행하면 체크포인트를 무시하고 처음부터 전부 처리한다.
