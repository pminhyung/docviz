# 커스텀 Tool 확장 & 학습 데이터 생성 가이드

## 1. 개요

커스텀 Tool `.py` 파일 하나를 작성하고 API에 경로를 전달하면:

- 파이프라인에 새로운 Tool Action이 추가됨
- Reasoning 모델이 자동으로 해당 Tool을 사용
- 매 요청마다 **SFT 학습 데이터가 동시 생성**됨
- 세션 누적 후 GCS에 일괄 업로드 가능

내부 코드를 import할 필요 없다. `execute(args, context) -> str`만 구현하면 된다.

---

## 2. 커스텀 Tool 작성법

### 2.1 필수 구조

```python
# my_tools.py
import json

class MyTool:
    name = "my_tool"                    # 고유 이름
    description = "이 도구의 역할 설명"    # LLM이 보는 설명
    parameters = {                       # JSON Schema
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "검색어"}
        },
        "required": ["query"]
    }
    tool_type = "search"                 # "search" 또는 "inference"

    def execute(self, args: dict, context: dict) -> str:
        query = args["query"]
        # ... 로직 ...
        return json.dumps({"result": "..."}, ensure_ascii=False)
```

### 2.2 필수 속성

| 속성 | 타입 | 설명 |
|------|------|------|
| `name` | str | 고유 이름 (LLM이 이 이름으로 호출) |
| `description` | str | 도구 설명 (LLM이 언제 쓸지 판단하는 근거) |
| `parameters` | dict | JSON Schema 형식 파라미터 정의 |
| `tool_type` | str | `"search"` (조회) 또는 `"inference"` (분석/생성) |
| `execute()` | method | `(self, args: dict, context: dict) -> str` |

### 2.3 tool_type

- **`"search"`** — 문서 검색, DB 조회, 외부 API 호출 등 정보를 가져오는 도구
- **`"inference"`** — LLM/VLM을 호출하여 분석·요약·변환하는 도구

---

## 3. context에서 사용 가능한 서비스

`execute(args, context)` 의 `context` dict에 아래 서비스가 주입된다.

### 3.1 기본 정보

| 키 | 타입 | 설명 |
|----|------|------|
| `user_query` | str | 사용자 질문 |
| `filenames` | list[str] | 문서 파일명 |
| `multi_docs` | list[list[dict]] | 문서 페이지 데이터 |
| `image_dir` | str \| None | 이미지 디렉토리 경로 |
| `language` | str | `"ko"` 또는 `"en"` |
| `current_step` | int | 현재 에이전트 스텝 번호 |
| `tool_secrets` | dict \| None | 클라이언트가 전달한 시크릿 (아래 참고) |

#### `tool_secrets` 사용법

클라이언트가 요청 시 `tool_secrets`를 전달하면 커스텀 Tool에서 접근 가능:

```python
# 클라이언트 요청
requests.post("/v2/run", json={
    "tool_secrets": {"serpapi_key": "sk_xxx", "db_host": "10.0.0.1"},
    ...
})

# 커스텀 Tool에서 사용
def execute(self, args, context):
    api_key = (context.get("tool_secrets") or {}).get("serpapi_key", "")
    if not api_key:
        return json.dumps({"error": "serpapi_key not provided in tool_secrets"})
    # ... api_key 사용 ...
```

> **주의**: `tool_secrets`는 서버 로그에 기록되지 않는다. 하드코딩 대신 항상 `tool_secrets`로 전달할 것.

### 3.2 서비스 Callable

#### `context["call_llm"]` — LLM 호출

```python
result: str = context["call_llm"](
    messages=[{"role": "user", "content": "요약해줘"}],
    role="extraction",       # "extraction" | "reasoning" | "summarization" | "query_generation"
    temperature=0.2,         # 기본 0.2
    max_tokens=16384,        # 기본 16384 (Novita/OpenAI 제한)
)
```

#### `context["call_vl"]` — Vision-Language 모델 호출

```python
result: str = context["call_vl"](
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "이 차트를 분석해줘"},
            {"type": "image_url", "image_url": {
                "url": f"data:image/png;base64,{b64_data}"
            }},
        ],
    }],
    temperature=0.2,         # 기본 0.2
    max_tokens=2000,         # 기본 2000
)
```

#### `context["record_training"]` — SFT 학습 데이터 기록

```python
context["record_training"](
    "vl_analysis",  # task_type: 원하는 키 이름
    [
        {"role": "user", "content": prompt, "loss_masking": True},
        {"role": "assistant", "content": result, "loss_masking": False},
    ],
)
```

- `task_type`: 학습 데이터 분류 키 (자유롭게 지정 가능)
- `loss_masking: True` → 학습 시 loss 계산 제외 (입력)
- `loss_masking: False` → 학습 시 loss 계산 포함 (출력)
- 기록된 데이터는 `train_sample[task_type]`에 누적됨

#### `context["search_documents"]` — 문서 검색

```python
pages: list[dict] = context["search_documents"](
    query="매출액 추이",
    doc_ids=[1],             # 1-indexed, None이면 전체 문서
)
# 반환: [{"Index": 1, "filename": "...", "page": 3, "content": "..."}, ...]
```

---

## 4. API 호출

### 4.1 서버 시작

```bash
./run_server.sh  # 기본 포트 9024
```

### 4.2 `POST /v2/run` — 쿼리 실행

```python
import requests

response = requests.post("http://HOST:9024/v2/run", json={
    # === 필수 ===
    "doc_json_path": "/path/to/doc.json",
    "user_query": "2페이지의 차트를 분석해주세요",
    "reasoner_api_key": "your-api-key",

    # === 커스텀 도구 ===
    "custom_tools_path": "/path/to/my_tools.py",
    "custom_rules": "- 차트 분석 시 analyze_page_image 도구를 사용하세요",
    "tool_secrets": {"api_key": "sk_xxx"},

    # === 문서 이미지 ===
    "doc_image_dir": "/path/to/images/",

    # === 옵션 ===
    "lang": "ko",                    # "ko" | "en"
    "n_steps_max": 10,               # 최대 스텝 수 (기본 20)
    "session_id": "my_session_001",  # 세션 누적용
    "return_trace": True,            # 추론 트레이스 반환
    "return_train_sample": True,     # 학습 데이터 반환

    # === Reasoner 설정 ===
    "reasoner_type": "llm",              # "llm" | "vl"
    # "reasoner_model_name": "gpt-5.2",  # 기본값 (OpenAI gpt-5.2)
    # "reasoner_model_max_length": None,  # max output tokens (null → 모델 기본값)
    # "reasoner_base_url": None,          # 로컬 vLLM: "http://localhost:8000/v1"
})

result = response.json()
print(result["final_answer"])
print(f"Steps: {result['num_steps']}, Tokens: {result['total_tokens']}")
```

### 4.3 요청 필드 전체

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `doc_json_path` | str | O | — | 문서 JSON 경로 |
| `user_query` | str | O | — | 사용자 질문 |
| `reasoner_api_key` | str | O | — | Reasoner API 키 (필수, sandbox 포함) |
| `doc_json_path_2` | str | | null | 두 번째 문서 경로 (다중 문서) |
| `doc_image_dir` | str | | null | 문서 이미지 디렉토리 |
| `custom_tools_path` | str | | null | 커스텀 Tool .py 파일 경로 |
| `custom_rules` | str | | null | 추가 규칙 (줄바꿈 구분) |
| `tool_secrets` | dict | | null | Tool 시크릿 (API 키 등) |
| `lang` | str | | "en" | 출력 언어 (`"ko"` \| `"en"`) |
| `n_steps_max` | int | | 20 | 최대 스텝 수 (1~100) |
| `session_id` | str | | null | 세션 ID (학습데이터 누적용) |
| `return_trace` | bool | | false | 트레이스 반환 여부 |
| `return_train_sample` | bool | | false | 학습 데이터 반환 여부 |
| `reasoner_type` | str | | "llm" | Reasoner 타입 (`"llm"` \| `"vl"`) |
| `reasoner_model_name` | str | | "gpt-5.2" | 모델명 (기본: gpt-5.2. `gpt-` 프리픽스면 OpenAI) |
| `reasoner_model_max_length` | int | | null | Reasoner max output tokens (null이면 모델 기본값) |
| `reasoner_base_url` | str | | null | Reasoner 엔드포인트 URL |
| `single_doc` | bool | | true | 단일 문서 모드 |

### 4.4 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `success` | bool | 성공 여부 |
| `final_answer` | str | 최종 답변 |
| `num_steps` | int | 사용된 스텝 수 |
| `total_tokens` | int | 총 토큰 수 |
| `total_duration_seconds` | float | 총 소요 시간(초) |
| `steps_reasoning` | list | 추론 스텝 목록 |
| `train_sample` | dict \| null | 학습 데이터 (`return_train_sample=true` 시) |
| `session_sample_count` | int \| null | 세션 누적 샘플 수 |
| `error` | str \| null | 에러 메시지 |

---

## 5. 학습 데이터 생성

### 5.1 자동 생성

`/v2/run` 호출 시 매 요청마다 학습 데이터가 자동 생성된다:

- `reasoning`: Reasoner 대화 기록
- `doc_step`: 문서 요약
- `readfulldocument`: 전체 문서 읽기 기록
- `readfulltext`: 웹 페이지 읽기 기록

### 5.2 커스텀 학습 데이터

`context["record_training"]`으로 직접 기록하면 커스텀 키로 저장된다:

```python
context["record_training"]("vl_analysis", [...])
# → train_sample["vl_analysis"]에 저장
```

### 5.3 세션 누적 & GCS 업로드

```python
# 1. 여러 쿼리를 같은 session_id로 실행
for query in queries:
    requests.post("/v2/run", json={
        "doc_json_path": doc_path,
        "user_query": query,
        "session_id": "batch_001",
        "reasoner_api_key": api_key,
    })

# 2. 세션 종료 → GCS 업로드
result = requests.post("/v2/finalize_session", json={
    "session_id": "batch_001"
}).json()

print(f"GCS: {result['gcs_path']}")       # gs://bucket/.../train.jsonl
print(f"Samples: {result['sample_count']}")
```

---

## 6. 이미지 경로 규칙

문서 이미지 디렉토리 구조:

```
/path/to/images/
├── page_1_image0.png
├── page_2_image0.png
├── page_3_image0.png
└── ...
```

Tool에서 이미지 접근:

```python
image_dir = context["image_dir"]  # API 요청의 doc_image_dir
image_path = f"{image_dir}/page_{page_num}_image0.png"
```

---

## 7. 문서 JSON 포맷

### 표준 포맷 (docai)

```json
{
    "id": "uuid",
    "outputs": [{
        "file_name": "report.pdf",
        "html_parsed": {
            "1": ["1페이지 텍스트..."],
            "2": ["2페이지 텍스트..."]
        }
    }]
}
```

### 다중 문서

```python
requests.post("/v2/run", json={
    "doc_json_path": "/path/to/doc1.json",
    "doc_json_path_2": "/path/to/doc2.json",
    "single_doc": False,
    ...
})
```

---

## 8. Reasoner 설정

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `reasoner_model_name` | `gpt-5.2` | 기본 Reasoner 모델 (OpenAI) |
| `reasoner_type` | `llm` | `"llm"` (텍스트) 또는 `"vl"` (비전) |
| `reasoner_model_max_length` | null | max output tokens 오버라이드 (null → 모델 기본값) |

### 기본 (gpt-5.2)

```python
{"reasoner_api_key": "sk-proj-your-openai-key"}
```

### VL Reasoner (이미지 입력 지원)

```python
{"reasoner_type": "vl", "reasoner_model_name": "qwen/qwen2.5-vl-72b-instruct", "reasoner_api_key": "your-novita-key"}
```

VL Reasoner를 선택하면 Tool 결과에 이미지가 포함될 때 자동으로 멀티모달 메시지로 전달된다.

### 다른 OpenAI 모델

```python
{
    "reasoner_model_name": "gpt-4o",     # gpt-5.2 대신 gpt-4o
    "reasoner_api_key": "sk-..."
}
```

### Novita LLM 모델

```python
{
    "reasoner_model_name": "qwen/qwen3-235b-a22b-instruct-2507",
    "reasoner_api_key": "your-novita-key"
}
```

### 로컬 vLLM

```python
{
    "reasoner_model_name": "local/qwen3",
    "reasoner_base_url": "http://localhost:8000/v1",
    "reasoner_api_key": "dummy"
}
```

### Max Length 오버라이드

```python
{
    "reasoner_api_key": "sk-...",
    "reasoner_model_max_length": 16384   # 기본 32768 대신 제한
}
```

---

## 9. 빠른 참조

### 파일 구성 예시

```
project/
├── my_tools.py              # 커스텀 Tool 정의
├── run_analysis.py           # API 호출 클라이언트
└── queries.jsonl             # 배치 처리용 쿼리 목록
```

### 최소 코드

**Tool 파일** (`my_tools.py`):

```python
import json

class SummarizeTool:
    name = "summarize_page"
    description = "지정된 페이지를 LLM으로 요약합니다"
    parameters = {
        "type": "object",
        "properties": {
            "page_number": {"type": "integer", "description": "페이지 번호"},
            "focus": {"type": "string", "description": "요약 포커스"}
        },
        "required": ["page_number"]
    }
    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        page_num = args["page_number"]
        focus = args.get("focus", "전체 내용")

        # 문서에서 페이지 내용 가져오기
        pages = context["multi_docs"][0]  # 첫 번째 문서
        page_content = ""
        for p in pages:
            if p.get("page") == page_num:
                page_content = p.get("content", "")
                break

        if not page_content:
            return json.dumps({"error": f"Page {page_num} not found"})

        # LLM으로 요약
        result = context["call_llm"](
            messages=[{"role": "user", "content": f"다음 내용을 '{focus}' 관점에서 요약:\n{page_content}"}],
        )

        # 학습 데이터 기록
        context["record_training"]("page_summary", [
            {"role": "user", "content": f"Summarize page {page_num}: {focus}", "loss_masking": True},
            {"role": "assistant", "content": result, "loss_masking": False},
        ])

        return result
```

**클라이언트** (`run_analysis.py`):

```python
import requests

r = requests.post("http://HOST:9024/v2/run", json={
    "doc_json_path": "/path/to/doc.json",
    "user_query": "3페이지를 재무 관점에서 요약해주세요",
    "custom_tools_path": "/path/to/my_tools.py",
    "custom_rules": "- 페이지 요약이 필요하면 summarize_page 도구를 사용하세요",
    "reasoner_api_key": "your-key",
    "session_id": "experiment_001",
    "lang": "ko",
})
print(r.json()["final_answer"])
```
