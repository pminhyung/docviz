"""
LLM Custom Tools for Document Text Analysis

context["call_llm"]을 사용하는 텍스트 기반 커스텀 도구.
VL 모델 없이 동작하며, 자동 학습 데이터 기록 덕분에
record_training() 호출이 불필요.

Usage:
    /v2/run 요청의 custom_tools_path에 이 파일 경로를 전달:
    {
        "custom_tools_path": "examples/tool_llm/llm_tools.py"
    }

Tools defined:
    - summarize_page: 특정 페이지 LLM 요약
    - extract_key_facts: 핵심 사실 추출 → JSON
"""
import json


class SummarizePageTool:
    """Summarize a specific document page using LLM."""
    name = "summarize_page"
    description = """Summarize a specific page of the document using LLM.
Provides a concise summary focusing on main topics and key information.
Use when you need a quick overview of a particular page."""

    parameters = {
        "type": "object",
        "properties": {
            "page_number": {
                "type": "integer",
                "description": "Page number to summarize (1-indexed)"
            },
            "document_number": {
                "type": "integer",
                "description": "Document number (1-indexed, default: 1)",
                "default": 1
            },
            "focus": {
                "type": "string",
                "description": "Optional focus area for the summary",
                "default": ""
            }
        },
        "required": ["page_number"]
    }
    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        page_num = args.get("page_number")
        doc_num = args.get("document_number", 1) - 1
        focus = args.get("focus", "")
        language = context.get("language", "en")
        call_llm = context.get("call_llm")
        multi_docs = context.get("multi_docs", [])

        if not call_llm:
            return json.dumps({"error": "call_llm not available in context"}, ensure_ascii=False)

        if doc_num < 0 or doc_num >= len(multi_docs):
            return json.dumps({"error": f"Document {doc_num+1} not found"}, ensure_ascii=False)

        pages = multi_docs[doc_num]
        target_page = None
        for page in pages:
            if page.get("page") == page_num or page.get("page_number") == page_num:
                target_page = page
                break

        if target_page is None and page_num <= len(pages):
            target_page = pages[page_num - 1]

        if target_page is None:
            return json.dumps({"error": f"Page {page_num} not found in document {doc_num+1}"}, ensure_ascii=False)

        content = target_page.get("content", "")
        lang_instruction = "Answer in Korean." if language == "ko" else "Answer in English."
        focus_instruction = f"\nFocus on: {focus}" if focus else ""

        messages = [
            {"role": "system", "content": "You are a helpful document analysis assistant."},
            {"role": "user", "content": f"Summarize the following page content concisely.{focus_instruction}\n{lang_instruction}\n\n{content}"},
        ]

        result = call_llm(messages, role="extraction")
        # Auto-recorded by pipeline — no record_training() needed
        return result


class ExtractKeyFactsTool:
    """Extract key facts from document pages as structured JSON."""
    name = "extract_key_facts"
    description = """Extract key facts from document pages and return as structured JSON.
Returns: {"facts": [{"fact": "...", "page": N, "category": "..."}]}
Use when you need structured data extraction from document text."""

    parameters = {
        "type": "object",
        "properties": {
            "page_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Page numbers to extract facts from (1-indexed)"
            },
            "document_number": {
                "type": "integer",
                "description": "Document number (1-indexed, default: 1)",
                "default": 1
            },
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional categories to focus on (e.g., ['financial', 'technical'])"
            }
        },
        "required": ["page_numbers"]
    }
    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        page_numbers = args.get("page_numbers", [])
        doc_num = args.get("document_number", 1) - 1
        categories = args.get("categories", [])
        language = context.get("language", "en")
        call_llm = context.get("call_llm")
        multi_docs = context.get("multi_docs", [])

        if not call_llm:
            return json.dumps({"error": "call_llm not available in context"}, ensure_ascii=False)

        if doc_num < 0 or doc_num >= len(multi_docs):
            return json.dumps({"error": f"Document {doc_num+1} not found"}, ensure_ascii=False)

        pages = multi_docs[doc_num]
        combined_content = ""
        for page_num in page_numbers:
            for page in pages:
                pn = page.get("page", page.get("page_number"))
                if pn == page_num:
                    combined_content += f"\n--- Page {page_num} ---\n{page.get('content', '')}"
                    break

        if not combined_content:
            return json.dumps({"error": "No matching pages found"}, ensure_ascii=False)

        lang_instruction = "Answer in Korean." if language == "ko" else "Answer in English."
        cat_instruction = f"\nFocus categories: {', '.join(categories)}" if categories else ""

        messages = [
            {"role": "system", "content": "You are a fact extraction assistant. Return valid JSON only."},
            {"role": "user", "content": f"""Extract key facts from the following pages.{cat_instruction}
Return JSON: {{"facts": [{{"fact": "...", "page": N, "category": "..."}}]}}
{lang_instruction}

{combined_content}"""},
        ]

        result = call_llm(messages, role="extraction")
        # Auto-recorded by pipeline
        return result
