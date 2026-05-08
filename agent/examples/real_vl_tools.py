"""
Real VL Tools for Document Image Analysis

This file contains custom tools that use Vision-Language models (Qwen3-VL)
to analyze visual elements in document images.

Usage:
    Pass this file path as custom_tools_path in the API request

Requires:
    - NOVITA_API_KEY environment variable set
    - openai package installed

Tools defined:
    - analyze_visual: Analyzes charts, tables, diagrams
    - extract_table: Extracts structured data from tables
"""
import os
import json
import base64
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class AnalyzeVisualTool:
    """
    Analyzes visual elements in document pages including charts, tables, and diagrams.
    Uses Qwen3-VL model via Novita AI API.
    """
    name = "analyze_visual"
    description = """Analyzes visual elements in document pages including:
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
                "description": "Page numbers containing visual elements to analyze"
            },
            "analysis_focus": {
                "type": "string",
                "enum": ["chart", "table", "diagram", "general"],
                "description": "Type of visual element to focus on"
            },
            "question": {
                "type": "string",
                "description": "Specific question about the visual content"
            }
        },
        "required": ["page_numbers"]
    }
    tool_type = "inference"

    def __init__(self):
        if OpenAI is None:
            raise ImportError("openai package is required. Install with: pip install openai")

        self.model = "qwen/qwen2.5-vl-72b-instruct"
        self._client = None

    def _get_client(self, context: dict):
        """Get OpenAI client with API key from context or environment."""
        secrets = context.get("tool_secrets") or {}
        api_key = secrets.get("api_key") or os.environ.get("NOVITA_API_KEY", "")
        if not api_key:
            raise ValueError("API key not provided. Set tool_secrets.api_key in request or NOVITA_API_KEY env var.")

        return OpenAI(
            base_url="https://api.novita.ai/v3/openai",
            api_key=api_key
        )

    def execute(self, args: dict, context: dict) -> str:
        page_numbers = args.get("page_numbers", [])
        analysis_focus = args.get("analysis_focus", "general")
        question = args.get("question", "")
        image_dir = context.get("image_dir")
        language = context.get("language", "en")

        if not image_dir:
            return json.dumps({
                "error": "No image directory provided. Pass doc_image_dir in the API request."
            }, ensure_ascii=False)

        if not page_numbers:
            return json.dumps({
                "error": "No page numbers provided"
            }, ensure_ascii=False)

        results = []
        for page_num in page_numbers:
            result = self._analyze_page(page_num, image_dir, analysis_focus, question, language, context)
            results.append(result)

        return json.dumps(results, ensure_ascii=False, indent=2)

    def _analyze_page(
        self,
        page_num: int,
        image_dir: str,
        analysis_focus: str,
        question: str,
        language: str,
        context: dict
    ) -> dict:
        """Analyze a single page image."""
        image_path = f"{image_dir}/page_{page_num}_image0.png"

        if not os.path.exists(image_path):
            return {
                "page": page_num,
                "error": f"Image not found: {image_path}"
            }

        try:
            # Load and encode image
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()

            # Build analysis prompt
            prompt = self._build_prompt(analysis_focus, question, language)

            # Get client with API key from context
            client = self._get_client(context)

            # Call VL model
            response = client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        }}
                    ]
                }],
                max_tokens=2000
            )

            analysis = response.choices[0].message.content

            return {
                "page": page_num,
                "analysis_type": analysis_focus,
                "analysis": analysis
            }

        except Exception as e:
            return {
                "page": page_num,
                "error": str(e)
            }

    def _build_prompt(self, focus: str, question: str, language: str) -> str:
        """Build the analysis prompt based on focus type."""
        lang_instruction = "Answer in Korean." if language == "ko" else "Answer in English."

        prompts = {
            "chart": f"""Analyze the chart/graph in this image:
1. Chart type (line graph, bar chart, pie chart, etc.)
2. What the X-axis and Y-axis represent
3. Key data points and trends
4. Core insights and implications
{f"Additional question: {question}" if question else ""}
{lang_instruction}""",

            "table": f"""Analyze the table in this image:
1. Table structure (row/column headers)
2. Key data values and their meanings
3. Comparisons or patterns in the data
4. Summary of key figures
{f"Additional question: {question}" if question else ""}
{lang_instruction}""",

            "diagram": f"""Analyze the diagram/flowchart in this image:
1. Diagram type (flowchart, system diagram, process flow, etc.)
2. Main components and their roles
3. Relationships or flow between elements
4. Overall meaning and purpose
{f"Additional question: {question}" if question else ""}
{lang_instruction}""",

            "general": f"""Analyze the visual content in this image in detail:
- Identify all visual elements (charts, tables, diagrams, images, etc.)
- Extract key information from each element
- Explain the meaning of the data or information
- Highlight important insights
{f"Additional question: {question}" if question else ""}
{lang_instruction}"""
        }

        return prompts.get(focus, prompts["general"])


class ExtractTableDataTool:
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
                "description": "Page number containing the table"
            },
            "table_description": {
                "type": "string",
                "description": "Brief description of which table to extract (if multiple tables exist on the page)"
            }
        },
        "required": ["page_number"]
    }
    tool_type = "inference"

    def __init__(self):
        if OpenAI is None:
            raise ImportError("openai package is required. Install with: pip install openai")

        self.model = "qwen/qwen2.5-vl-72b-instruct"

    def _get_client(self, context: dict):
        """Get OpenAI client with API key from context or environment."""
        secrets = context.get("tool_secrets") or {}
        api_key = secrets.get("api_key") or os.environ.get("NOVITA_API_KEY", "")
        if not api_key:
            raise ValueError("API key not provided. Set tool_secrets.api_key in request or NOVITA_API_KEY env var.")

        return OpenAI(
            base_url="https://api.novita.ai/v3/openai",
            api_key=api_key
        )

    def execute(self, args: dict, context: dict) -> str:
        page_num = args.get("page_number")
        table_desc = args.get("table_description", "")
        image_dir = context.get("image_dir")
        language = context.get("language", "en")

        if not image_dir:
            return json.dumps({
                "error": "No image directory provided"
            }, ensure_ascii=False)

        if page_num is None:
            return json.dumps({
                "error": "page_number is required"
            }, ensure_ascii=False)

        image_path = f"{image_dir}/page_{page_num}_image0.png"

        if not os.path.exists(image_path):
            return json.dumps({
                "error": f"Image not found: {image_path}"
            }, ensure_ascii=False)

        try:
            # Load and encode image
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()

            # Build extraction prompt
            lang_instruction = "Answer in Korean." if language == "ko" else "Answer in English."

            prompt = f"""Extract table data from this image.
{f"Target table: {table_desc}" if table_desc else "Extract the main table visible in the image."}

Return the data in the following JSON format:
{{
    "table_title": "Title of the table if visible",
    "headers": ["Column1", "Column2", "Column3", ...],
    "rows": [
        ["Row1Value1", "Row1Value2", "Row1Value3", ...],
        ["Row2Value1", "Row2Value2", "Row2Value3", ...],
        ...
    ],
    "notes": "Any additional notes or footnotes from the table"
}}

Important:
- Preserve the exact values as shown in the table
- Include all rows and columns
- If values are numerical, keep them as strings with their original format
{lang_instruction}"""

            # Get client with API key from context
            client = self._get_client(context)

            # Call VL model
            response = client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        }}
                    ]
                }],
                max_tokens=3000
            )

            return response.choices[0].message.content

        except Exception as e:
            return json.dumps({
                "page": page_num,
                "error": str(e)
            }, ensure_ascii=False)


class CompareVisualsTools:
    """
    Compares visual elements across multiple pages.
    Useful for tracking trends or changes between documents.
    """
    name = "compare_visuals"
    description = """Compares visual elements (charts, tables) across multiple pages.
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
                "description": "Page numbers to compare (2-4 pages)"
            },
            "comparison_focus": {
                "type": "string",
                "description": "What aspect to compare (e.g., 'revenue trends', 'performance metrics')"
            }
        },
        "required": ["page_numbers", "comparison_focus"]
    }
    tool_type = "inference"

    def __init__(self):
        if OpenAI is None:
            raise ImportError("openai package is required")

        self.model = "qwen/qwen2.5-vl-72b-instruct"

    def _get_client(self, context: dict):
        """Get OpenAI client with API key from context or environment."""
        secrets = context.get("tool_secrets") or {}
        api_key = secrets.get("api_key") or os.environ.get("NOVITA_API_KEY", "")
        if not api_key:
            raise ValueError("API key not provided. Set tool_secrets.api_key in request or NOVITA_API_KEY env var.")

        return OpenAI(
            base_url="https://api.novita.ai/v3/openai",
            api_key=api_key
        )

    def execute(self, args: dict, context: dict) -> str:
        page_numbers = args.get("page_numbers", [])
        comparison_focus = args.get("comparison_focus", "general comparison")
        image_dir = context.get("image_dir")
        language = context.get("language", "en")

        if not image_dir:
            return json.dumps({"error": "No image directory"}, ensure_ascii=False)

        if len(page_numbers) < 2:
            return json.dumps({"error": "At least 2 pages required for comparison"}, ensure_ascii=False)

        if len(page_numbers) > 4:
            page_numbers = page_numbers[:4]  # Limit to 4 pages

        # Load all images
        images_content = []
        valid_pages = []

        for page_num in page_numbers:
            image_path = f"{image_dir}/page_{page_num}_image0.png"
            if os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode()
                images_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                })
                valid_pages.append(page_num)

        if len(valid_pages) < 2:
            return json.dumps({
                "error": f"Not enough valid images found. Valid pages: {valid_pages}"
            }, ensure_ascii=False)

        try:
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

            # Build message content with text first, then all images
            content = [{"type": "text", "text": prompt}] + images_content

            # Get client with API key from context
            client = self._get_client(context)

            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": content}],
                max_tokens=3000
            )

            return json.dumps({
                "pages_compared": valid_pages,
                "focus": comparison_focus,
                "analysis": response.choices[0].message.content
            }, ensure_ascii=False, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
