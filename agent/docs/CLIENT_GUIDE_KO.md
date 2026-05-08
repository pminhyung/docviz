# agent API 클라이언트 가이드

## 개요

agent API를 사용하면 문서 분석 에이전트를 호출하고, 커스텀 도구를 추가하여 시각적 요소(차트, 표, 다이어그램)를 분석할 수 있습니다.

### 주요 기능

- 문서 내용 검색 및 요약
- **Reasoner 선택** (LLM/VL 모드, 모델 지정 가능)
- **VL 모드 이미지 입력** (Tool 출력 이미지를 Reasoner에 전달)
- 커스텀 Tool Action 추가 (VL 모델 연동 등)
- 세션 기반 대량 처리 및 GCS 업로드
- 훈련용 JSONL 데이터 자동 생성

---

## 아키텍처 다이어그램

### 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              클라이언트 요청                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  doc_json_path, user_query, reasoner_type, reasoner_model_name, ... │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            agent API                                  │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────────────────┐   │
│  │ ModelRouter   │───▶│ ProxyClient   │───▶│ LLM/VL API               │   │
│  │               │    │ (OpenAI/Novita)│    │ (gpt-5.2/qwen-vl/etc.)  │   │
│  └───────────────┘    └───────────────┘    └───────────────────────────┘   │
│          │                                                                   │
│          ▼                                                                   │
│  ┌───────────────────────────────────────────────────────────────────┐     │
│  │                         AgentV2Runner                              │     │
│  │   ┌─────────┐     ┌──────────────┐     ┌──────────────────────┐  │     │
│  │   │ 문서    │────▶│ Tool Action  │────▶│ Reasoning Loop       │  │     │
│  │   │ 로딩    │     │ (Search/VL)  │     │ (이미지 입력 지원)    │  │     │
│  │   └─────────┘     └──────────────┘     └──────────────────────┘  │     │
│  └───────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                               응답                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  final_answer, steps_reasoning, total_tokens, success, ...          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### VL 모드 이미지 입력 흐름

```
┌─────────────────┐
│  User Query     │
│  "차트 분석해줘"  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────────────────────────────────┐
│  Agent Step 1   │────▶│  Tool: analyze_chart                        │
│  (Reasoning)    │     │  Arguments: {page: 3}                       │
└─────────────────┘     └────────────────┬────────────────────────────┘
                                         │
                                         ▼
                        ┌─────────────────────────────────────────────┐
                        │  Tool Output (JSON):                        │
                        │  {                                          │
                        │    "analysis": "...",                       │
                        │    "image_paths": ["/tmp/chart.png"]  ◀──── │ 이미지 경로 키
                        │  }                                          │
                        └────────────────┬────────────────────────────┘
                                         │
         ┌───────────────────────────────┴───────────────────────────┐
         │                                                           │
         ▼                                                           ▼
┌─────────────────┐                                   ┌─────────────────┐
│ reasoner_type:  │                                   │ reasoner_type:  │
│     "llm"       │                                   │     "vl"        │
└────────┬────────┘                                   └────────┬────────┘
         │                                                     │
         ▼                                                     ▼
┌─────────────────┐                         ┌─────────────────────────────┐
│ 다음 Step에     │                         │ 다음 Step에 이미지 포함:     │
│ 텍스트만 전달   │                         │ ┌─────────────────────────┐ │
└─────────────────┘                         │ │ {"role": "user",        │ │
                                            │ │  "content": [           │ │
                                            │ │    {"type": "text", ...}│ │
                                            │ │    {"type": "image_url",│ │
                                            │ │     "image_url": {...}} │ │
                                            │ │  ]}                     │ │
                                            │ └─────────────────────────┘ │
                                            └─────────────────────────────┘
```

---

## 단건 요청

### Python 코드로 직접 요청

```python
import requests

# 가장 간단한 단건 요청
response = requests.post("http://10.4.43.13:9024/v2/run", json={
    "doc_json_path": "/path/to/document.json",
    "user_query": "이 문서를 요약해주세요",
    "lang": "ko",
    "reasoner_api_key": "your-openai-api-key-here"  # 필수 (기본 모델 gpt-5.2)
})
print(response.json()["final_answer"])
```

### CLI 스크립트 사용 (simple_client_example.py)

```bash
# 기본 실행 (VL 도구 사용)
python simple_client_example.py

# API 키를 직접 전달 (-s key=value 형식)
python simple_client_example.py -s api_key=sk_xxx

# 커스텀 쿼리와 언어 지정
python simple_client_example.py \
  --query "목표주가를 알려주세요" \
  --lang ko \
  -s api_key=sk_xxx

# 커스텀 도구 비활성화 (텍스트만 분석)
python simple_client_example.py --no-custom-tools

# 다른 문서로 테스트
python simple_client_example.py \
  --doc-json /path/to/other/doc.json \
  --image-dir /path/to/other/images/ \
  --query "차트를 분석해주세요" \
  -s api_key=sk_xxx
```

### curl로 요청

```bash
curl -X POST http://10.4.43.13:9024/v2/run \
  -H "Content-Type: application/json" \
  -d '{
    "doc_json_path": "/ex_disk2/mhpark/poc/docai/out/32_IM증권/00163f84.json",
    "doc_image_dir": "/ex_disk2/mhpark/poc/docai/out/img/32_IM증권/00163f84/",
    "user_query": "이 리포트의 목표주가를 알려주세요",
    "lang": "ko",
    "reasoner_api_key": "your-openai-api-key-here"
  }'
```

---

## 다량 요청 (session_id 활용)

세션을 사용하면 여러 요청의 결과를 누적하고, 한 번에 GCS로 업로드할 수 있습니다.

### 기본 사용법

```python
import requests

SESSION_ID = "batch_20240223_001"  # 고유한 세션 ID

# 1. 여러 문서/쿼리 처리 - 같은 session_id로 결과 누적
documents = [
    {"path": "/path/to/doc1.json", "query": "문서1 요약"},
    {"path": "/path/to/doc2.json", "query": "문서2 요약"},
    {"path": "/path/to/doc3.json", "query": "문서3 요약"},
]

API_KEY = "your-openai-api-key-here"  # 기본 모델 gpt-5.2 (OpenAI)

for doc in documents:
    response = requests.post("http://10.4.43.13:9024/v2/run", json={
        "doc_json_path": doc["path"],
        "user_query": doc["query"],
        "lang": "ko",
        "reasoner_api_key": API_KEY,
        "session_id": SESSION_ID  # 동일 세션으로 결과 누적
    })
    result = response.json()
    print(f"누적 샘플: {result['session_sample_count']}")

# 2. 세션 종료 및 GCS 업로드
final = requests.post("http://10.4.43.13:9024/v2/finalize_session", json={
    "session_id": SESSION_ID
})
print(f"GCS 경로: {final.json()['gcs_path']}")
print(f"총 샘플: {final.json()['sample_count']}")
```

---

## 헬스 체크

서버 시작 후, 클라이언트가 가장 먼저 확인해야 하는 것은 서버 상태입니다.

### GET /health

```bash
curl http://10.4.43.13:9024/health
```

#### 응답 예시

```json
{
    "status": "healthy",
    "sandbox_mode": false,
    "models_available": true,
    "version": "2.0.0"
}
```

#### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | string | 서버 상태 (`"healthy"`) |
| `sandbox_mode` | bool | Sandbox 모드 여부 (True면 더미 응답 반환) |
| `models_available` | bool | 모델 사용 가능 여부 |
| `version` | string | API 버전 |

#### 확인 사항

- `models_available: true` → 정상 동작 가능
- `sandbox_mode: true` → 실제 모델 호출 없이 테스트용 더미 응답 반환 (`DOC_AGENT_V2_SANDBOX=1`로 서버 시작 시)
- 연결 실패 시: 서버 주소/포트 확인, 서버 프로세스 실행 여부 확인

```python
import requests

# 서버 상태 확인
health = requests.get("http://10.4.43.13:9024/health").json()
assert health["status"] == "healthy", "서버가 정상이 아닙니다"
assert health["models_available"], "모델을 사용할 수 없습니다"

if health.get("sandbox_mode"):
    print("⚠️ Sandbox 모드입니다. 실제 분석이 아닌 더미 응답이 반환됩니다.")
```

---

## API 엔드포인트

### POST /v2/run

문서 분석 에이전트를 실행합니다.

#### 요청 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `doc_json_path` | string | O | docai JSON 파일 경로 |
| `user_query` | string | O | 사용자 질문 |
| `reasoner_api_key` | string | O | **Reasoner용 API 키 (필수, 기본 모델 gpt-5.2 → OpenAI 키)** |
| `doc_json_path_2` | string | X | 두 번째 문서 경로 (멀티 문서 모드) |
| `doc_image_dir` | string | X | 이미지 디렉토리 경로 |
| `lang` | string | X | 응답 언어. **반드시 `"ko"` 또는 `"en"`** (기본값: `"en"`) |
| `custom_tools_path` | string | X | 커스텀 도구 .py 파일 경로 |
| `custom_rules` | string | X | 추가 규칙 (각 줄 `- `로 시작) |
| `session_id` | string | X | 세션 ID (대량 처리 시) |
| `tool_secrets` | object | X | 커스텀 도구에 전달할 비밀값 (아래 참조) |
| `reasoner_type` | string | X | Reasoner 타입: `"llm"` 또는 `"vl"` (기본값: `"llm"`) |
| `reasoner_model_name` | string | X | 모델 이름 (기본값: `"gpt-5.2"`. `"gpt-"` 접두사 → OpenAI, 그 외 → Novita) |
| `reasoner_model_max_length` | int | X | Reasoner 최대 출력 토큰 수. 미지정 시 모델별 기본값 (gpt-5.2: 32768, Novita: 16384) |
| `n_steps_max` | int | X | 최대 스텝 수 (기본값: 20) |
| `return_trace` | bool | X | 추론 과정 포함 여부 |
| `return_train_sample` | bool | X | 학습 샘플 포함 여부 |

#### tool_secrets 사용법

`tool_secrets`는 커스텀 도구에 전달할 임의의 키-값 쌍입니다. API 키, DB 비밀번호 등을 요청 파라미터로 안전하게 전달할 수 있습니다.

```python
response = requests.post("http://10.4.43.13:9024/v2/run", json={
    "doc_json_path": "/path/to/doc.json",
    "user_query": "차트를 분석해주세요",
    "custom_tools_path": "/path/to/vl_tools.py",
    "tool_secrets": {
        "api_key": "sk_xxx",      # VL 모델용 API 키
        "db_password": "xxx",     # 다른 도구용
        "custom_token": "yyy"     # 또 다른 도구용
    }
})
```

#### Reasoner 설정 (reasoner_type, reasoner_model_name)

Reasoner는 에이전트의 추론을 담당하는 LLM입니다. 두 가지 모드를 지원합니다:

| reasoner_type | 설명 | 기본 모델 |
|---------------|------|-----------|
| `"llm"` | 텍스트 전용 모델 | `gpt-5.2` (OpenAI) |
| `"vl"` | Vision-Language 모델 (이미지 입력 지원) | 명시 필요 (예: `qwen/qwen2.5-vl-72b-instruct`) |

> **참고:** 기본 모델이 `gpt-5.2`이므로, VL 모드 사용 시 반드시 `reasoner_model_name`을 명시하세요.

**모델 라우팅 규칙:**
- `"gpt-"`로 시작하는 모델명 → OpenAI API 사용
- `"local/"`로 시작하는 모델명 → 로컬 vLLM 사용
- 그 외 → Novita API 사용

**사용 예시:**

```python
# 1. 기본 LLM 모드 (gpt-5.2, 텍스트 전용) — 가장 간단한 형태
response = requests.post("http://10.4.43.13:9024/v2/run", json={
    "doc_json_path": "/path/to/doc.json",
    "user_query": "이 문서를 요약해주세요",
    "reasoner_api_key": "your-openai-api-key"  # 필수
    # reasoner_type 기본값 "llm", reasoner_model_name 기본값 "gpt-5.2"
})

# 2. VL 모드 (이미지 입력 지원) — 모델 명시 필요
response = requests.post("http://10.4.43.13:9024/v2/run", json={
    "doc_json_path": "/path/to/doc.json",
    "doc_image_dir": "/path/to/images/",
    "user_query": "차트를 분석해주세요",
    "reasoner_api_key": "your-novita-api-key",
    "reasoner_type": "vl",
    "reasoner_model_name": "qwen/qwen2.5-vl-72b-instruct"  # VL 모델 명시
})

# 3. 최대 출력 토큰 제한
response = requests.post("http://10.4.43.13:9024/v2/run", json={
    "doc_json_path": "/path/to/doc.json",
    "user_query": "고급 분석을 해주세요",
    "reasoner_api_key": "your-openai-api-key",
    "reasoner_model_max_length": 16384  # 기본 32768 대신 제한
})

# 4. 다른 Novita 모델 사용
response = requests.post("http://10.4.43.13:9024/v2/run", json={
    "doc_json_path": "/path/to/doc.json",
    "user_query": "분석해주세요",
    "reasoner_api_key": "your-novita-api-key",
    "reasoner_model_name": "qwen/qwen3-72b-instruct"  # Novita 자동 감지
})
```

**VL 모드의 이미지 입력:**

VL 모드에서 Tool Action이 `image_paths` 키를 반환하면, 해당 이미지가 다음 Reasoning 호출에 자동으로 포함됩니다.

```
1. Tool 실행 → {"result": "...", "image_paths": ["/tmp/chart.png"]}
2. 시스템이 이미지를 Base64 인코딩
3. 다음 Reasoning 호출에 이미지 포함 (multimodal message)
4. VL 모델이 이미지를 "보고" 분석
```

#### 응답 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `final_answer` | string | 에이전트의 최종 답변 |
| `steps_reasoning` | array | 각 스텝별 추론 정보 |
| `success` | bool | 성공 여부 |
| `total_tokens` | int | 사용된 토큰 수 |
| `total_duration_seconds` | float | 총 실행 시간 (초) |
| `num_steps` | int | 총 스텝 수 |
| `session_sample_count` | int | 세션 내 누적 샘플 수 (session_id 사용 시) |

### POST /v2/finalize_session

세션을 종료하고 누적된 JSONL을 GCS에 업로드합니다.

#### 요청

```json
{
    "session_id": "my_batch_001"
}
```

#### 응답

```json
{
    "session_id": "my_batch_001",
    "sample_count": 50,
    "gcs_path": "gs://mhpark_bucket/reasoning_api_output/my_batch_001/train.jsonl",
    "success": true
}
```

---

## 커스텀 Tool Action 작성법

### 필수 요소 요약

커스텀 도구는 **4개의 클래스 속성**과 **1개의 메서드**를 구현해야 합니다:

| 요소 | 타입 | 설명 |
|------|------|------|
| `name` | str | 도구 고유 이름 |
| `description` | str | LLM에게 보여줄 설명 (도구 사용 시점 결정에 영향) |
| `parameters` | dict | JSON Schema 형식의 파라미터 정의 |
| `tool_type` | str | `"search"` 또는 `"inference"` |
| `execute(args, context)` | method | 실행 메서드, 문자열 반환 |

### Skeleton 템플릿 사용 (권장)

`examples/tool_skeleton.py` 파일을 복사하여 시작하세요:

```bash
cp examples/tool_skeleton.py my_tools.py
```

### BaseTool 상속 (IDE 지원)

BaseTool을 상속하면 IDE에서 필수 요소를 자동완성으로 확인할 수 있습니다:

```python
from agent.core.base_tool import BaseTool

class MyTool(BaseTool):
    name = "my_tool"
    description = "도구 설명"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "입력값"}
        },
        "required": ["input"]
    }
    tool_type = "search"

    def execute(self, args: dict, context: dict) -> str:
        return f"결과: {args.get('input')}"
```

### 기본 구조 (상속 없이)

```python
class MyCustomTool:
    # =============================================
    # 필수 속성 (4개)
    # =============================================

    name = "my_tool"
    """
    도구 고유 이름 (필수)
    - LLM이 이 이름으로 도구를 호출합니다
    - 예약된 이름 사용 불가: search, ReadFullDocument, ReadFullText, GetPage
    """

    description = """도구의 기능을 설명합니다.
언제 이 도구를 사용해야 하는지 명확하게 작성하세요.
LLM이 이 설명을 보고 도구 사용 여부를 결정합니다."""
    """
    LLM에게 보여줄 설명 (필수)
    - 명확하고 구체적으로 작성
    - 언제 사용해야 하는지 포함
    """

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "검색할 키워드"
            },
            "limit": {
                "type": "integer",
                "description": "최대 결과 개수",
                "default": 10
            }
        },
        "required": ["query"]  # 필수 파라미터 목록
    }
    """
    파라미터 스키마 (필수)
    - JSON Schema 형식
    - properties: 각 파라미터 정의
    - required: 필수 파라미터 목록
    """

    tool_type = "search"
    """
    도구 타입 (필수)
    - "search": 정보 조회/검색
    - "inference": 콘텐츠 생성/변환
    """

    # =============================================
    # 필수 메서드
    # =============================================

    def execute(self, args: dict, context: dict) -> str:
        """
        도구 실행 (필수)

        Args:
            args: 파라미터 값 딕셔너리
            context: 실행 컨텍스트 (아래 참조)

        Returns:
            결과 문자열 (JSON dumps 권장)
        """
        query = args.get("query", "")
        limit = args.get("limit", 10)

        # 여기에 실제 로직 구현
        results = [{"result": f"Item {i}"} for i in range(limit)]

        return json.dumps(results, ensure_ascii=False)
```

### tool_type 종류

| tool_type | 용도 | 예시 |
|-----------|------|------|
| `"search"` | 정보 조회/검색 | 키워드 검색, 메타데이터 조회, DB 쿼리 |
| `"inference"` | 콘텐츠 생성/분석 | VL 모델 호출, 외부 API 호출, 복잡한 계산 |

### 이미지 출력 Tool (VL 모드 전용)

Tool Action이 이미지를 생성하거나 반환하는 경우, `image_paths` 키를 사용하면 VL 모드에서 해당 이미지가 다음 Reasoning 호출에 자동으로 포함됩니다.

**이미지 출력 규칙:**

| 키 | 타입 | 설명 |
|----|------|------|
| `image_paths` | `str` 또는 `List[str]` | 이미지 파일의 **절대 경로** |

**예시: 이미지를 반환하는 Tool**

```python
import json
import os

class ChartGeneratorTool:
    name = "generate_chart"
    description = "데이터를 기반으로 차트 이미지를 생성합니다."
    parameters = {
        "type": "object",
        "properties": {
            "data": {"type": "array", "description": "차트 데이터"},
            "chart_type": {"type": "string", "enum": ["bar", "line", "pie"]}
        },
        "required": ["data", "chart_type"]
    }
    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        # 차트 생성 로직...
        chart_path = "/tmp/generated_chart.png"
        self._create_chart(args["data"], args["chart_type"], chart_path)

        # image_paths 키로 이미지 경로 반환
        return json.dumps({
            "message": "차트 생성 완료",
            "image_paths": [chart_path]  # ← 이 키가 있으면 VL 모드에서 이미지 입력
        }, ensure_ascii=False)

    def _create_chart(self, data, chart_type, output_path):
        # matplotlib 등으로 차트 생성
        import matplotlib.pyplot as plt
        plt.figure()
        if chart_type == "bar":
            plt.bar(range(len(data)), data)
        plt.savefig(output_path)
        plt.close()
```

**VL 모드 흐름:**

```
┌──────────────────┐
│ reasoner_type:   │
│     "vl"         │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     ┌───────────────────────────────────────┐
│ Agent calls:     │────▶│ generate_chart                        │
│ generate_chart   │     │ Returns: {"image_paths": ["/tmp/..."]}│
└──────────────────┘     └───────────────────┬───────────────────┘
                                             │
                                             ▼
                         ┌───────────────────────────────────────┐
                         │ 시스템 자동 처리:                      │
                         │ 1. image_paths 키 감지                 │
                         │ 2. 이미지 파일 읽기                    │
                         │ 3. Base64 인코딩                       │
                         │ 4. 다음 LLM 호출에 포함                │
                         └───────────────────┬───────────────────┘
                                             │
                                             ▼
                         ┌───────────────────────────────────────┐
                         │ VL 모델이 이미지를 "보고" 분석         │
                         │ → 차트의 내용을 이해하고 답변          │
                         └───────────────────────────────────────┘
```

**지원 이미지 형식:**
- PNG (`image/png`)
- JPEG/JPG (`image/jpeg`)

**주의사항:**
- `reasoner_type: "llm"`인 경우 `image_paths`는 무시됨
- 이미지 경로는 반드시 **절대 경로** 사용
- 존재하지 않는 경로는 경고 출력 후 무시됨
- 큰 이미지는 토큰 사용량 증가 (권장: 1024x1024 이하)

### context 딕셔너리 내용

execute() 메서드의 두 번째 인자로 전달되는 컨텍스트:

| 키 | 타입 | 설명 |
|----|------|------|
| `user_query` | str | 사용자 질문 |
| `filenames` | list | 문서 파일명 목록 |
| `multi_docs` | list | 문서 페이지 데이터 `[[{page1}, {page2}], ...]` |
| `image_dir` | str/None | 이미지 디렉토리 경로 |
| `language` | str | `"ko"` 또는 `"en"` |
| `current_step` | int | 현재 에이전트 스텝 번호 |
| `tool_secrets` | dict/None | 클라이언트가 전달한 비밀값 |

### tool_secrets 사용 패턴

```python
def execute(self, args: dict, context: dict) -> str:
    # tool_secrets에서 값 추출 (fallback으로 환경변수)
    secrets = context.get("tool_secrets") or {}
    api_key = secrets.get("api_key") or os.environ.get("MY_API_KEY")

    if not api_key:
        return json.dumps({"error": "API key not provided"})

    # api_key 사용...
```

### 여러 도구를 하나의 파일에 정의

**하나의 .py 파일에 여러 Tool 클래스를 정의**하면 모두 자동으로 등록됩니다:

```python
# my_tools.py - 모든 클래스가 자동 등록됨

class Tool1:
    name = "tool1"
    description = "First tool"
    parameters = {"type": "object", "properties": {}}
    tool_type = "search"

    def execute(self, args, context):
        return "result1"

class Tool2:
    name = "tool2"
    description = "Second tool"
    parameters = {"type": "object", "properties": {}}
    tool_type = "inference"

    def execute(self, args, context):
        return "result2"

# 위 2개 도구가 모두 자동 등록됨
```

### 예약된 도구 이름 (사용 불가)

- `search`
- `ReadFullDocument`
- `ReadFullText`
- `GetPage`

---

## 예제: VL 이미지 분석 도구

```python
import os
import json
import base64
from openai import OpenAI

class AnalyzeImageTool:
    name = "analyze_image"
    description = """문서의 차트, 그래프, 표 등 시각적 요소를 분석합니다.
사용자가 시각적 데이터에 대해 질문할 때 이 도구를 사용하세요."""
    parameters = {
        "type": "object",
        "properties": {
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "분석할 페이지 번호"
            },
            "analysis_focus": {
                "type": "string",
                "enum": ["chart", "table", "diagram", "general"],
                "description": "분석 유형"
            }
        },
        "required": ["page_numbers"]
    }
    tool_type = "inference"

    def __init__(self):
        self.model = "qwen/qwen2.5-vl-72b-instruct"

    def _get_client(self, context: dict):
        """Get OpenAI client with API key from context or environment."""
        secrets = context.get("tool_secrets") or {}
        api_key = secrets.get("api_key") or os.environ.get("NOVITA_API_KEY", "")
        if not api_key:
            raise ValueError("API key not provided")
        return OpenAI(
            base_url="https://api.novita.ai/v3/openai",
            api_key=api_key
        )

    def execute(self, args: dict, context: dict) -> str:
        page_numbers = args.get("page_numbers", [])
        focus = args.get("analysis_focus", "general")
        image_dir = context.get("image_dir")
        language = context.get("language", "en")

        if not image_dir:
            return json.dumps({"error": "No image directory"})

        results = []
        client = self._get_client(context)

        for page_num in page_numbers:
            image_path = f"{image_dir}/page_{page_num}_image0.png"
            if not os.path.exists(image_path):
                results.append({"page": page_num, "error": "Image not found"})
                continue

            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()

            lang_instruction = "Answer in Korean." if language == "ko" else "Answer in English."
            response = client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Analyze this {focus}. {lang_instruction}"},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        }}
                    ]
                }],
                max_tokens=2000
            )

            results.append({
                "page": page_num,
                "analysis": response.choices[0].message.content
            })

        return json.dumps(results, ensure_ascii=False)
```

---

## 예제: 외부 DB 검색 도구

```python
import json

class SearchDatabaseTool:
    name = "search_db"
    description = """외부 데이터베이스에서 관련 정보를 검색합니다.
문서에 없는 추가 정보가 필요할 때 사용하세요."""
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "검색 쿼리"
            },
            "limit": {
                "type": "integer",
                "description": "최대 결과 수",
                "default": 10
            }
        },
        "required": ["query"]
    }
    tool_type = "search"

    def execute(self, args: dict, context: dict) -> str:
        secrets = context.get("tool_secrets") or {}
        db_url = secrets.get("db_url")
        db_password = secrets.get("db_password")

        if not db_url or not db_password:
            return json.dumps({"error": "DB credentials not provided"})

        # DB 연결 및 검색 로직
        # results = db.search(args["query"], limit=args.get("limit", 10))

        return json.dumps({
            "query": args["query"],
            "results": ["result1", "result2"]  # 실제 구현 시 DB 결과
        }, ensure_ascii=False)
```

---

## 커스텀 규칙 (Custom Rules)

에이전트에게 추가 지시사항을 전달할 수 있습니다. 각 규칙은 `- `로 시작합니다.

```python
custom_rules = """- 차트나 표 분석 요청 시 반드시 analyze_visual 도구를 사용하세요
- 수치 데이터가 필요하면 extract_table로 정확한 값을 추출하세요
- 시각적 요소 분석 전에 GetPage로 페이지 내용을 먼저 확인하세요
- 분석 결과에 항상 페이지 번호를 명시하세요"""

response = requests.post("http://10.4.43.13:9024/v2/run", json={
    "doc_json_path": doc_path,
    "user_query": "차트를 분석해주세요",
    "custom_tools_path": tools_path,
    "custom_rules": custom_rules
})
```

---

## Docai 문서 형식

### JSON 구조

```json
{
    "id": "document_uuid",
    "outputs": [{
        "file_name": "원본파일.pdf",
        "html_parsed": {
            "1": ["페이지1 텍스트1", "페이지1 텍스트2"],
            "2": ["페이지2 텍스트1"],
            "3": ["페이지3 텍스트1", "페이지3 텍스트2", "페이지3 텍스트3"]
        }
    }]
}
```

### 이미지 디렉토리 구조

```
/path/to/images/{document_id}/
├── page_1_image0.png
├── page_2_image0.png
├── page_3_image0.png
└── ...
```

### 이미지 접근 방법

```python
def execute(self, args: dict, context: dict) -> str:
    page_num = args["page_number"]
    image_dir = context["image_dir"]

    # 이미지 경로: page_{번호}_image0.png
    image_path = f"{image_dir}/page_{page_num}_image0.png"

    if os.path.exists(image_path):
        with open(image_path, "rb") as f:
            image_bytes = f.read()
```

---

## 주의사항

1. **lang 파라미터**: 반드시 `"ko"` 또는 `"en"` 중 하나만 사용
2. **이미지 파일명**: `page_{페이지번호}_image0.png` 형식 고정
3. **예약된 도구 이름**: `search`, `ReadFullDocument`, `ReadFullText`, `GetPage`는 사용 불가
4. **세션 ID**: 동시에 여러 배치 처리 시 고유한 ID 사용
5. **도구 반환값**: 반드시 문자열(`str`) 반환, JSON 데이터는 `json.dumps()` 사용
6. **tool_secrets**: 민감한 정보는 `tool_secrets`로 전달

---

## 문제 해결

### 도구가 로드되지 않음

- `.py` 파일 경로가 절대 경로인지 확인
- 필수 속성(`name`, `description`, `parameters`, `tool_type`)이 모두 있는지 확인
- `tool_type`이 `"search"` 또는 `"inference"` 인지 확인
- `execute` 메서드가 정의되어 있는지 확인
- `execute` 메서드가 `args`와 `context` 2개 인자를 받는지 확인

### 이미지를 찾을 수 없음

- `doc_image_dir` 경로가 올바른지 확인
- 이미지 파일명이 `page_{번호}_image0.png` 형식인지 확인
- 페이지 번호가 1부터 시작하는지 확인

### 세션 관련 오류

- 세션 ID가 고유한지 확인
- `/v2/finalize_session` 호출 전에 최소 1개 이상의 요청이 있어야 함

### VL 도구 오류

- `tool_secrets.api_key` 설정 확인
- `openai` 패키지 설치 확인: `pip install openai`
- API 할당량 초과 여부 확인

### API Key 오류

```
ValueError: API key not provided
```

해결 방법:
1. 요청에 `tool_secrets` 추가: `"tool_secrets": {"api_key": "sk_xxx"}`
2. 또는 CLI에서 `-s api_key=sk_xxx` 옵션 사용

### Reasoner 관련 오류

**모델을 찾을 수 없음:**
```
ValueError: Model 'xxx' not found for role 'reasoning'
```
→ `reasoner_model_name`이 올바른지 확인 (Novita/OpenAI에서 지원하는 모델인지)

**VL 모드에서 이미지가 전달되지 않음:**
- `reasoner_type: "vl"` 설정 확인
- Tool 반환값에 `image_paths` 키가 있는지 확인
- 이미지 경로가 **절대 경로**인지 확인
- 이미지 파일이 실제로 존재하는지 확인

**OpenAI API 호출 실패:**
- `reasoner_model_name`이 `"gpt-"`로 시작하는지 확인
- `reasoner_api_key`에 유효한 OpenAI API 키가 전달되었는지 확인

**Novita API 호출 실패:**
- `reasoner_api_key`에 유효한 Novita API 키가 전달되었는지 확인
- 모델명이 Novita에서 지원하는 형식인지 확인 (예: `qwen/qwen2.5-vl-72b-instruct`)

**`reasoner_api_key` 누락 (422 에러):**
```json
{"detail": [{"msg": "Field required", "type": "missing", "loc": ["body", "reasoner_api_key"]}]}
```
→ `reasoner_api_key`는 필수 파라미터입니다. 기본 모델(gpt-5.2)은 OpenAI 키가 필요합니다.

---

## 빠른 참조표

### Reasoner 모드 비교

| 항목 | `reasoner_type: "llm"` | `reasoner_type: "vl"` |
|------|------------------------|------------------------|
| 입력 | 텍스트만 | 텍스트 + 이미지 |
| 기본 모델 | `gpt-5.2` (OpenAI) | 명시 필요 (예: `qwen/qwen2.5-vl-72b-instruct`) |
| Tool 이미지 출력 | 무시됨 | 다음 호출에 포함 |
| 용도 | 일반 문서 분석 | 시각적 요소 분석 |

### 모델 라우팅

| 모델명 패턴 | API | 예시 |
|------------|-----|------|
| `"gpt-*"` | OpenAI | `"gpt-4o"`, `"gpt-5.2"` |
| `"local/*"` | 로컬 vLLM | `"local/my-model"` |
| 그 외 | Novita | `"qwen/qwen2.5-vl-72b-instruct"` |

### 필수 파라미터

| 파라미터 | 용도 |
|---------|------|
| `reasoner_api_key` | **필수**. 기본 모델(gpt-5.2) → OpenAI API 키, Novita 모델 → Novita API 키 |
