"""
커스텀 Tool 템플릿

이 파일을 복사하여 커스텀 Tool을 만드세요.
내부 코드를 import할 필요 없습니다.

사용법:
    1. 이 파일을 복사하여 my_tools.py 생성
    2. 클래스 속성과 execute() 구현
    3. API 호출 시 custom_tools_path에 파일 경로 전달

필수 요소:
    - name (str): 고유 이름
    - description (str): LLM에게 보여줄 설명
    - parameters (dict): JSON Schema 파라미터
    - tool_type (str): "search" 또는 "inference"
    - execute(self, args: dict, context: dict) -> str

context에서 사용 가능한 서비스:
    - context["call_llm"](messages, role, temperature, max_tokens) -> str
    - context["call_vl"](messages, temperature, max_tokens) -> str
    - context["record_training"](task_type, conversations) -> None
    - context["search_documents"](query, doc_ids) -> list[dict]
"""
import json
import os
import base64


# =============================================================================
# 예시 1: 기본 검색 Tool
# =============================================================================

class MySearchTool:
    """문서 데이터를 조회하는 기본 tool."""

    name = "my_search"
    description = """문서에서 특정 정보를 검색합니다.
사용자가 특정 데이터를 찾을 때 이 도구를 사용하세요."""

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "검색할 키워드 또는 질문"
            },
            "doc_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "검색할 문서 번호 (1-indexed)"
            }
        },
        "required": ["query"]
    }

    tool_type = "search"

    def execute(self, args: dict, context: dict) -> str:
        query = args["query"]
        doc_ids = args.get("doc_ids")

        # context["search_documents"]로 문서 검색
        pages = context["search_documents"](query, doc_ids)

        return json.dumps(pages, ensure_ascii=False)


# =============================================================================
# 예시 2: LLM을 활용하는 분석 Tool + 학습 데이터 기록
# =============================================================================

class SummarizePageTool:
    """페이지를 LLM으로 요약하고 학습 데이터를 기록하는 tool."""

    name = "summarize_page"
    description = """지정된 페이지를 LLM으로 요약합니다.
사용자가 특정 페이지의 핵심 내용을 알고 싶을 때 사용하세요."""

    parameters = {
        "type": "object",
        "properties": {
            "page_number": {
                "type": "integer",
                "description": "요약할 페이지 번호 (1-indexed)"
            },
            "focus": {
                "type": "string",
                "description": "요약 포커스 (예: '재무', '기술', '전체')"
            }
        },
        "required": ["page_number"]
    }

    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        page_num = args["page_number"]
        focus = args.get("focus", "전체 내용")

        # 문서에서 페이지 내용 가져오기
        pages = context["multi_docs"][0]
        page_content = ""
        for p in pages:
            if p.get("page") == page_num:
                page_content = p.get("content", "")
                break

        if not page_content:
            return json.dumps({"error": f"Page {page_num} not found"})

        # ---- context["call_llm"]으로 LLM 호출 ----
        prompt = f"다음 내용을 '{focus}' 관점에서 핵심만 요약:\n\n{page_content[:10000]}"
        result = context["call_llm"](
            messages=[{"role": "user", "content": prompt}],
            role="extraction",
            temperature=0.2,
            max_tokens=2000,
        )

        # ---- context["record_training"]으로 학습 데이터 기록 ----
        context["record_training"]("page_summary", [
            {"role": "user", "content": prompt, "loss_masking": True},
            {"role": "assistant", "content": result, "loss_masking": False},
        ])

        return result


# =============================================================================
# 예시 3: VL 모델을 활용하는 이미지 분석 Tool
# =============================================================================

class AnalyzeImageTool:
    """페이지 이미지를 VL 모델로 분석하는 tool."""

    name = "analyze_image"
    description = """문서 페이지의 차트, 표, 다이어그램 등을 시각적으로 분석합니다.
텍스트만으로 파악하기 어려운 시각적 요소를 분석할 때 사용하세요."""

    parameters = {
        "type": "object",
        "properties": {
            "page_number": {
                "type": "integer",
                "description": "분석할 페이지 번호"
            },
            "question": {
                "type": "string",
                "description": "이미지에 대한 질문"
            }
        },
        "required": ["page_number"]
    }

    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        page_num = args["page_number"]
        question = args.get("question", "이 이미지의 내용을 분석해주세요")

        image_dir = context.get("image_dir")
        if not image_dir:
            return json.dumps({"error": "doc_image_dir가 API 요청에 필요합니다"})

        # 이미지 로드
        image_path = os.path.join(image_dir, f"page_{page_num}_image0.png")
        if not os.path.exists(image_path):
            return json.dumps({"error": f"이미지 없음: {image_path}"})

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        # ---- context["call_vl"]으로 VL 모델 호출 ----
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{b64}"
                }},
            ],
        }]

        result = context["call_vl"](
            messages,
            temperature=0.2,
            max_tokens=2000,
        )

        # ---- 학습 데이터 기록 ----
        context["record_training"]("vl_analysis", [
            {"role": "user", "content": question, "loss_masking": True},
            {"role": "assistant", "content": result, "loss_masking": False},
        ])

        return json.dumps({
            "page": page_num,
            "analysis": result,
        }, ensure_ascii=False)


# =============================================================================
# 예시 4: 외부 API를 호출하는 Tool (tool_secrets 사용)
# =============================================================================

class ExternalAPITool:
    """외부 API를 호출하는 tool. API 키는 tool_secrets로 전달받는다."""

    name = "call_external"
    description = """외부 API에서 추가 정보를 가져옵니다.
문서에 없는 실시간 정보가 필요할 때 사용하세요."""

    parameters = {
        "type": "object",
        "properties": {
            "endpoint": {
                "type": "string",
                "enum": ["stock_price", "weather", "news"],
                "description": "호출할 API 종류"
            },
            "params": {
                "type": "object",
                "description": "API 파라미터"
            }
        },
        "required": ["endpoint"]
    }

    tool_type = "search"

    def execute(self, args: dict, context: dict) -> str:
        endpoint = args["endpoint"]
        params = args.get("params", {})

        # tool_secrets에서 API 키 가져오기
        secrets = context.get("tool_secrets") or {}
        api_key = secrets.get("api_key")

        if not api_key:
            return json.dumps({"error": "tool_secrets에 api_key를 전달해주세요"})

        # 여기에 실제 API 호출 구현
        # import requests
        # resp = requests.get(f"https://api.example.com/{endpoint}", headers={"Authorization": f"Bearer {api_key}"}, params=params)
        # return resp.text

        return json.dumps({
            "endpoint": endpoint,
            "data": {"sample": "result"},
        }, ensure_ascii=False)
