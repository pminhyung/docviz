"""
Sample VL (Vision-Language) Tools

Example custom tools for document analysis using vision models.
This file demonstrates how to create custom tools that can be
loaded dynamically by the agent API.

IMPORTANT: This file uses duck typing - no imports from agent are needed!
The tool class must have these attributes:
- name: str (unique tool name)
- description: str (LLM-visible description)
- parameters: dict (JSON Schema)
- tool_type: str ("search" or "inference")
- execute(args: dict, context: dict) -> str (execution method)

Usage:
    POST /v2/run
    {
        "doc_json_path": "/path/to/docai/out/category/hash.json",
        "doc_image_dir": "/path/to/docai/out/img/category/hash/",
        "user_query": "Analyze the chart on page 4",
        "custom_tools_path": "/path/to/this/sample_vl_tools.py"
    }
"""

import base64
import json
import os
from typing import Any, Dict


class AnalyzeChartTool:
    """
    Analyzes charts and graphs in document images using a VL model.

    This tool uses Qwen2-VL via Novita AI API to analyze visual elements
    in document pages.
    """

    name = "analyze_chart"
    description = "Analyzes charts, graphs, and visual elements in document images using a vision model. Returns detailed analysis of visual data."
    parameters = {
        "type": "object",
        "properties": {
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Page numbers containing charts or visual elements to analyze"
            },
            "analysis_focus": {
                "type": "string",
                "description": "Optional focus area for analysis (e.g., 'trends', 'comparisons', 'data points')",
                "default": "general"
            }
        },
        "required": ["page_numbers"]
    }
    tool_type = "inference"  # This tool uses LLM/VLM

    def __init__(self):
        """Initialize the VL client."""
        # Using Novita AI as the VL model provider
        # You can replace this with any OpenAI-compatible API
        try:
            from openai import OpenAI
            self.client = OpenAI(
                base_url="https://api.novita.ai/v3/openai",
                api_key=os.environ.get("NOVITA_API_KEY", "")
            )
        except ImportError:
            self.client = None

    def execute(self, args: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        Execute chart analysis on specified pages.

        Args:
            args: Tool arguments
                - page_numbers: List of page numbers to analyze
                - analysis_focus: Optional focus area
            context: Execution context (dict)
                - user_query: str
                - filenames: list
                - multi_docs: list
                - image_dir: str or None
                - language: str
                - current_step: int

        Returns:
            JSON string with analysis results
        """
        page_numbers = args.get("page_numbers", [])
        analysis_focus = args.get("analysis_focus", "general")
        image_dir = context.get("image_dir")
        language = context.get("language", "en")

        if not image_dir:
            return json.dumps({
                "error": "No image directory available",
                "message": "This document does not have associated images"
            }, ensure_ascii=False)

        if not self.client:
            return json.dumps({
                "error": "VL client not initialized",
                "message": "OpenAI package not installed or API key not set"
            }, ensure_ascii=False)

        results = []

        for page_num in page_numbers:
            # Try common image naming patterns
            image_paths = [
                f"{image_dir}/page_{page_num}_image0.png",
                f"{image_dir}/page_{page_num}.png",
                f"{image_dir}/{page_num}.png",
            ]

            image_path = None
            for path in image_paths:
                if os.path.exists(path):
                    image_path = path
                    break

            if not image_path:
                results.append({
                    "page": page_num,
                    "error": "Image not found",
                    "searched_paths": image_paths
                })
                continue

            try:
                # Read and encode image
                with open(image_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode()

                # Build prompt based on language and focus
                if language == "ko":
                    prompt = f"이 페이지의 차트/그래프를 상세히 분석해주세요. 분석 초점: {analysis_focus}"
                else:
                    prompt = f"Please analyze the chart/graph in this page in detail. Analysis focus: {analysis_focus}"

                # Call VL model
                response = self.client.chat.completions.create(
                    model="qwen/qwen2.5-vl-72b-instruct",
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

                results.append({
                    "page": page_num,
                    "analysis": response.choices[0].message.content,
                    "focus": analysis_focus
                })

            except Exception as e:
                results.append({
                    "page": page_num,
                    "error": str(e)
                })

        return json.dumps(results, ensure_ascii=False)


class ExtractTableDataTool:
    """
    Extracts structured data from tables in document images.
    """

    name = "extract_table"
    description = "Extracts structured tabular data from document images. Returns data in JSON format with rows and columns."
    parameters = {
        "type": "object",
        "properties": {
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Page numbers containing tables to extract"
            },
            "output_format": {
                "type": "string",
                "enum": ["json", "markdown"],
                "description": "Output format for extracted table data",
                "default": "json"
            }
        },
        "required": ["page_numbers"]
    }
    tool_type = "inference"

    def __init__(self):
        try:
            from openai import OpenAI
            self.client = OpenAI(
                base_url="https://api.novita.ai/v3/openai",
                api_key=os.environ.get("NOVITA_API_KEY", "")
            )
        except ImportError:
            self.client = None

    def execute(self, args: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Extract table data from specified pages."""
        page_numbers = args.get("page_numbers", [])
        output_format = args.get("output_format", "json")
        image_dir = context.get("image_dir")
        language = context.get("language", "en")

        if not image_dir:
            return json.dumps({"error": "No image directory available"}, ensure_ascii=False)

        if not self.client:
            return json.dumps({"error": "VL client not initialized"}, ensure_ascii=False)

        results = []

        for page_num in page_numbers:
            image_path = f"{image_dir}/page_{page_num}_image0.png"

            if not os.path.exists(image_path):
                results.append({"page": page_num, "error": "Image not found"})
                continue

            try:
                with open(image_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode()

                if language == "ko":
                    prompt = f"""이 페이지의 표 데이터를 추출해주세요.
출력 형식: {output_format}
- json: {{"headers": [...], "rows": [[...], [...]]}}
- markdown: | col1 | col2 | ... |"""
                else:
                    prompt = f"""Extract the table data from this page.
Output format: {output_format}
- json: {{"headers": [...], "rows": [[...], [...]]}}
- markdown: | col1 | col2 | ... |"""

                response = self.client.chat.completions.create(
                    model="qwen/qwen2.5-vl-72b-instruct",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{image_b64}"
                            }}
                        ]
                    }],
                    max_tokens=4000
                )

                results.append({
                    "page": page_num,
                    "format": output_format,
                    "data": response.choices[0].message.content
                })

            except Exception as e:
                results.append({"page": page_num, "error": str(e)})

        return json.dumps(results, ensure_ascii=False)


class SimpleSearchTool:
    """
    A simple example of a search-type custom tool.

    This demonstrates how to create a search tool that performs
    custom filtering or ranking on document pages.
    """

    name = "filter_pages"
    description = "Filters document pages by keyword presence. Returns pages containing any of the specified keywords."
    parameters = {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords to search for in page content"
            },
            "document_number": {
                "type": "integer",
                "description": "Document number to search (1-based)",
                "default": 1
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Whether search is case-sensitive",
                "default": False
            }
        },
        "required": ["keywords"]
    }
    tool_type = "search"  # This is a search/retrieval tool

    def execute(self, args: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Filter pages by keyword."""
        keywords = args.get("keywords", [])
        doc_num = args.get("document_number", 1)
        case_sensitive = args.get("case_sensitive", False)
        multi_docs = context.get("multi_docs", [])

        if not keywords:
            return json.dumps({"error": "No keywords provided"}, ensure_ascii=False)

        if doc_num < 1 or doc_num > len(multi_docs):
            return json.dumps({"error": f"Document {doc_num} not found"}, ensure_ascii=False)

        pages = multi_docs[doc_num - 1]
        matching_pages = []

        for page in pages:
            content = page.get("content", "")
            if not case_sensitive:
                content = content.lower()
                check_keywords = [k.lower() for k in keywords]
            else:
                check_keywords = keywords

            if any(kw in content for kw in check_keywords):
                matching_pages.append({
                    "Index": len(matching_pages) + 1,
                    "filename": page.get("filename"),
                    "page": page.get("page"),
                    "content": page.get("content", "")[:500] + "..."
                })

        return json.dumps(matching_pages, ensure_ascii=False)
