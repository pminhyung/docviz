"""
VL (Vision-Language) Tools for Document Image Analysis

context["call_vl"]과 context["record_training"]을 사용하는 커스텀 VL 도구.
API 키나 내부 import 없이 파이프라인 서비스만으로 동작한다.

Usage:
    /v2/run 요청의 custom_tools_path에 이 파일 경로를 전달:
    {
        "custom_tools_path": "examples/vl_tools.py",
        "doc_image_dir": "/path/to/images/"
    }

Tools defined:
    - analyze_page_image: 페이지 이미지의 시각적 요소 분석
    - extract_table: 테이블 이미지에서 구조화 데이터 추출
    - compare_page_images: 여러 페이지 이미지 비교 분석

서비스 callable (context dict 경유):
    - context["call_vl"](messages, temperature, max_tokens) -> str
    - context["record_training"](task_type, conversations) -> None
"""
import os
import json
import base64


def _load_page_image(image_dir: str, page_num: int) -> tuple:
    """Load a page image as base64.

    Args:
        image_dir: Directory containing page images
        page_num: Page number (1-indexed)

    Returns:
        (b64_data, error_msg) — one of them is empty string
    """
    image_path = os.path.join(image_dir, f"page_{page_num}_image0.png")
    if not os.path.exists(image_path):
        return "", f"Image not found: {image_path}"
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode(), ""


class AnalyzePageImageTool:
    """
    Analyzes visual elements in document page images.

    Uses context["call_vl"] to call the pipeline's VL model.
    Records VL analysis results as SFT training data via context["record_training"].
    """
    name = "analyze_page_image"
    description = """Analyzes visual elements in document page images including:
- Charts and graphs (line, bar, pie charts)
- Tables with numerical data
- Diagrams and flowcharts
- Financial data visualizations

Use this tool when the user asks about visual content that cannot be fully understood from text alone.
The tool calls a Vision-Language model to interpret the image."""

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
        record_training = context.get("record_training")

        if not image_dir:
            return json.dumps(
                {"error": "No image directory provided. Pass doc_image_dir in the API request."},
                ensure_ascii=False,
            )

        if not call_vl:
            return json.dumps(
                {"error": "call_vl not available in context. VL model is not configured."},
                ensure_ascii=False,
            )

        if not page_numbers:
            return json.dumps({"error": "No page numbers provided"}, ensure_ascii=False)

        results = []
        for page_num in page_numbers:
            result = self._analyze_page(
                page_num, image_dir, analysis_focus, question, language, call_vl, record_training,
            )
            results.append(result)

        return json.dumps(results, ensure_ascii=False, indent=2)

    def _analyze_page(
        self, page_num, image_dir, analysis_focus, question, language, call_vl, record_training,
    ) -> dict:
        """Analyze a single page image via VL model."""
        b64_data, error = _load_page_image(image_dir, page_num)
        if error:
            return {"page": page_num, "error": error}

        prompt = self._build_prompt(analysis_focus, question, language)

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{b64_data}"
                }},
            ],
        }]

        try:
            analysis = call_vl(messages, temperature=0.2, max_tokens=2000)

            # Record training data
            if record_training:
                record_training("vl_analysis", [
                    {"role": "user", "content": prompt, "loss_masking": True},
                    {"role": "assistant", "content": analysis, "loss_masking": False},
                ])

            return {
                "page": page_num,
                "analysis_type": analysis_focus,
                "analysis": analysis,
            }
        except Exception as e:
            return {"page": page_num, "error": str(e)}

    def _build_prompt(self, focus: str, question: str, language: str) -> str:
        lang_instruction = "Answer in Korean." if language == "ko" else "Answer in English."
        extra = f"\nAdditional question: {question}" if question else ""

        prompts = {
            "chart": f"""Analyze the chart/graph in this image:
1. Chart type (line graph, bar chart, pie chart, etc.)
2. What the X-axis and Y-axis represent
3. Key data points and trends
4. Core insights and implications{extra}
{lang_instruction}""",
            "table": f"""Analyze the table in this image:
1. Table structure (row/column headers)
2. Key data values and their meanings
3. Comparisons or patterns in the data
4. Summary of key figures{extra}
{lang_instruction}""",
            "diagram": f"""Analyze the diagram/flowchart in this image:
1. Diagram type (flowchart, system diagram, process flow, etc.)
2. Main components and their roles
3. Relationships or flow between elements
4. Overall meaning and purpose{extra}
{lang_instruction}""",
            "general": f"""Analyze the visual content in this image in detail:
- Identify all visual elements (charts, tables, diagrams, images, etc.)
- Extract key information from each element
- Explain the meaning of the data or information
- Highlight important insights{extra}
{lang_instruction}""",
        }
        return prompts.get(focus, prompts["general"])


class ExtractTableTool:
    """
    Extracts structured data from table images.
    Returns data in JSON format with headers and rows.
    """
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
                "description": "Brief description of which table to extract (if multiple tables on page)"
            }
        },
        "required": ["page_number"]
    }
    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        page_num = args.get("page_number")
        table_desc = args.get("table_description", "")
        image_dir = context.get("image_dir")
        language = context.get("language", "en")
        call_vl = context.get("call_vl")
        record_training = context.get("record_training")

        if not image_dir:
            return json.dumps({"error": "No image directory provided"}, ensure_ascii=False)

        if not call_vl:
            return json.dumps({"error": "call_vl not available in context"}, ensure_ascii=False)

        if page_num is None:
            return json.dumps({"error": "page_number is required"}, ensure_ascii=False)

        b64_data, error = _load_page_image(image_dir, page_num)
        if error:
            return json.dumps({"page": page_num, "error": error}, ensure_ascii=False)

        lang_instruction = "Answer in Korean." if language == "ko" else "Answer in English."
        target_desc = f"Target table: {table_desc}" if table_desc else "Extract the main table visible in the image."

        prompt = f"""Extract table data from this image.
{target_desc}

Return the data in the following JSON format:
{{
    "table_title": "Title of the table if visible",
    "headers": ["Column1", "Column2", "Column3", ...],
    "rows": [
        ["Row1Value1", "Row1Value2", "Row1Value3", ...],
        ...
    ],
    "notes": "Any additional notes or footnotes from the table"
}}

Important:
- Preserve the exact values as shown in the table
- Include all rows and columns
- If values are numerical, keep them as strings with their original format
{lang_instruction}"""

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{b64_data}"
                }},
            ],
        }]

        try:
            result = call_vl(messages, temperature=0.1, max_tokens=3000)

            if record_training:
                record_training("vl_analysis", [
                    {"role": "user", "content": prompt, "loss_masking": True},
                    {"role": "assistant", "content": result, "loss_masking": False},
                ])

            return result
        except Exception as e:
            return json.dumps({"page": page_num, "error": str(e)}, ensure_ascii=False)


class ComparePageImagesTool:
    """
    Compares visual elements across multiple page images.
    Useful for tracking trends or changes between pages/documents.
    """
    name = "compare_page_images"
    description = """Compares visual elements (charts, tables) across multiple page images.
Useful for:
- Comparing data trends across different time periods
- Finding differences between similar tables
- Tracking changes in metrics"""

    parameters = {
        "type": "object",
        "properties": {
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Page numbers to compare (2-4 pages, 1-indexed)"
            },
            "document_number": {
                "type": "integer",
                "description": "Document number (1-indexed, default: 1)",
                "default": 1
            },
            "comparison_focus": {
                "type": "string",
                "description": "What aspect to compare (e.g., 'revenue trends', 'performance metrics')"
            }
        },
        "required": ["page_numbers", "comparison_focus"]
    }
    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        page_numbers = args.get("page_numbers", [])
        comparison_focus = args.get("comparison_focus", "general comparison")
        image_dir = context.get("image_dir")
        language = context.get("language", "en")
        call_vl = context.get("call_vl")
        record_training = context.get("record_training")

        if not image_dir:
            return json.dumps({"error": "No image directory provided"}, ensure_ascii=False)

        if not call_vl:
            return json.dumps({"error": "call_vl not available in context"}, ensure_ascii=False)

        if len(page_numbers) < 2:
            return json.dumps({"error": "At least 2 pages required for comparison"}, ensure_ascii=False)

        # Limit to 4 pages
        page_numbers = page_numbers[:4]

        # Load all images
        images_content = []
        valid_pages = []
        for page_num in page_numbers:
            b64_data, error = _load_page_image(image_dir, page_num)
            if not error:
                images_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64_data}"},
                })
                valid_pages.append(page_num)

        if len(valid_pages) < 2:
            return json.dumps(
                {"error": f"Not enough valid images found. Valid pages: {valid_pages}"},
                ensure_ascii=False,
            )

        lang_instruction = "Answer in Korean." if language == "ko" else "Answer in English."
        prompt = f"""Compare the visual elements in these {len(valid_pages)} images (pages {valid_pages}).

Focus on: {comparison_focus}

Provide:
1. Summary of what each image shows
2. Key similarities between the images
3. Key differences between the images
4. Trends or patterns across the images
5. Insights from the comparison

{lang_instruction}"""

        content = [{"type": "text", "text": prompt}] + images_content
        messages = [{"role": "user", "content": content}]

        try:
            analysis = call_vl(messages, temperature=0.2, max_tokens=3000)

            if record_training:
                record_training("vl_analysis", [
                    {"role": "user", "content": prompt, "loss_masking": True},
                    {"role": "assistant", "content": analysis, "loss_masking": False},
                ])

            return json.dumps({
                "pages_compared": valid_pages,
                "focus": comparison_focus,
                "analysis": analysis,
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
