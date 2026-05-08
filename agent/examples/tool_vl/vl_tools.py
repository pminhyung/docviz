"""
VL (Vision-Language) Tools for Document Image Analysis

context["call_vl"]과 context["record_training"]을 사용하는 커스텀 VL 도구.
API 키나 내부 import 없이 파이프라인 서비스만으로 동작한다.

Usage:
    /v2/run 요청의 custom_tools_path에 이 파일 경로를 전달:
    {
        "custom_tools_path": "examples/tool_vl/vl_tools.py",
        "doc_image_dir": "/path/to/images/"
    }

Tools defined:
    - analyze_page_image: 페이지 이미지의 시각적 요소 분석
    - extract_table: 테이블 이미지에서 구조화 데이터 추출
    - compare_page_images: 여러 페이지 이미지 비교 분석

서비스 callable (context dict 경유):
    - context["call_vl"](messages, temperature, max_tokens) -> str
    - context["record_training"](task_type, conversations) -> None (optional, auto-recorded)
"""
import os
import json
import base64


def _load_page_image(image_dir: str, page_num: int) -> tuple:
    """Load a page image as base64."""
    image_path = os.path.join(image_dir, f"page_{page_num}_image0.png")
    if not os.path.exists(image_path):
        return "", f"Image not found: {image_path}"
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode(), ""


class AnalyzePageImageTool:
    """Analyzes visual elements in document page images."""
    name = "analyze_page_image"
    description = """Analyzes visual elements in document page images including:
- Charts and graphs (line, bar, pie charts)
- Tables with numerical data
- Diagrams and flowcharts
- Financial data visualizations

Use this tool when the user asks about visual content that cannot be fully understood from text alone."""

    parameters = {
        "type": "object",
        "properties": {
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Page numbers containing visual elements to analyze (1-indexed)"
            },
            "document_number": {
                "type": "integer",
                "description": "Document number (1-indexed, default: 1)",
                "default": 1
            },
            "analysis_focus": {
                "type": "string",
                "enum": ["chart", "table", "diagram", "general"],
                "description": "Type of visual element to focus on",
                "default": "general"
            },
            "question": {
                "type": "string",
                "description": "Specific question about the visual content"
            }
        },
        "required": ["page_numbers"]
    }
    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        page_numbers = args.get("page_numbers", [])
        analysis_focus = args.get("analysis_focus", "general")
        question = args.get("question", "")
        image_dir = context.get("image_dir")
        language = context.get("language", "en")
        call_vl = context.get("call_vl")

        if not image_dir:
            return json.dumps({"error": "No image directory provided. Pass doc_image_dir in the API request."}, ensure_ascii=False)
        if not call_vl:
            return json.dumps({"error": "call_vl not available in context. VL model is not configured."}, ensure_ascii=False)
        if not page_numbers:
            return json.dumps({"error": "No page numbers provided"}, ensure_ascii=False)

        results = []
        for page_num in page_numbers:
            result = self._analyze_page(page_num, image_dir, analysis_focus, question, language, call_vl)
            results.append(result)

        return json.dumps(results, ensure_ascii=False, indent=2)

    def _analyze_page(self, page_num, image_dir, analysis_focus, question, language, call_vl) -> dict:
        b64_data, error = _load_page_image(image_dir, page_num)
        if error:
            return {"page": page_num, "error": error}

        lang_instruction = "Answer in Korean." if language == "ko" else "Answer in English."
        extra = f"\nAdditional question: {question}" if question else ""

        prompt = f"""Analyze the visual content ({analysis_focus}) in this image:
- Identify all visual elements
- Extract key information from each element
- Explain the meaning of the data{extra}
{lang_instruction}"""

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_data}"}},
            ],
        }]

        try:
            analysis = call_vl(messages, temperature=0.2, max_tokens=2000)
            return {"page": page_num, "analysis_type": analysis_focus, "analysis": analysis}
        except Exception as e:
            return {"page": page_num, "error": str(e)}


class ExtractTableTool:
    """Extracts structured data from table images."""
    name = "extract_table"
    description = """Extracts structured data from table images.
Returns data in JSON format with headers and rows.
Use when you need specific numerical values or structured data from tables."""

    parameters = {
        "type": "object",
        "properties": {
            "page_number": {
                "type": "integer",
                "description": "Page number containing the table (1-indexed)"
            },
            "document_number": {
                "type": "integer",
                "description": "Document number (1-indexed, default: 1)",
                "default": 1
            },
            "table_description": {
                "type": "string",
                "description": "Brief description of which table to extract"
            }
        },
        "required": ["page_number"]
    }
    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        page_num = args.get("page_number")
        image_dir = context.get("image_dir")
        call_vl = context.get("call_vl")

        if not image_dir:
            return json.dumps({"error": "No image directory provided"}, ensure_ascii=False)
        if not call_vl:
            return json.dumps({"error": "call_vl not available in context"}, ensure_ascii=False)
        if page_num is None:
            return json.dumps({"error": "page_number is required"}, ensure_ascii=False)

        b64_data, error = _load_page_image(image_dir, page_num)
        if error:
            return json.dumps({"page": page_num, "error": error}, ensure_ascii=False)

        prompt = """Extract table data from this image. Return JSON with:
{"table_title": "...", "headers": [...], "rows": [[...], ...], "notes": "..."}"""

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_data}"}},
            ],
        }]

        try:
            return call_vl(messages, temperature=0.1, max_tokens=3000)
        except Exception as e:
            return json.dumps({"page": page_num, "error": str(e)}, ensure_ascii=False)


class ComparePageImagesTool:
    """Compares visual elements across multiple page images."""
    name = "compare_page_images"
    description = """Compares visual elements (charts, tables) across multiple page images.
Useful for comparing data trends, finding differences, tracking changes."""

    parameters = {
        "type": "object",
        "properties": {
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Page numbers to compare (2-4 pages, 1-indexed)"
            },
            "comparison_focus": {
                "type": "string",
                "description": "What aspect to compare"
            }
        },
        "required": ["page_numbers", "comparison_focus"]
    }
    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        page_numbers = args.get("page_numbers", [])
        comparison_focus = args.get("comparison_focus", "general comparison")
        image_dir = context.get("image_dir")
        call_vl = context.get("call_vl")

        if not image_dir:
            return json.dumps({"error": "No image directory provided"}, ensure_ascii=False)
        if not call_vl:
            return json.dumps({"error": "call_vl not available in context"}, ensure_ascii=False)
        if len(page_numbers) < 2:
            return json.dumps({"error": "At least 2 pages required for comparison"}, ensure_ascii=False)

        page_numbers = page_numbers[:4]
        images_content = []
        valid_pages = []
        for page_num in page_numbers:
            b64_data, error = _load_page_image(image_dir, page_num)
            if not error:
                images_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_data}"}})
                valid_pages.append(page_num)

        if len(valid_pages) < 2:
            return json.dumps({"error": f"Not enough valid images. Valid pages: {valid_pages}"}, ensure_ascii=False)

        prompt = f"Compare visual elements in pages {valid_pages}. Focus: {comparison_focus}"
        content = [{"type": "text", "text": prompt}] + images_content
        messages = [{"role": "user", "content": content}]

        try:
            analysis = call_vl(messages, temperature=0.2, max_tokens=3000)
            return json.dumps({"pages_compared": valid_pages, "focus": comparison_focus, "analysis": analysis}, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
