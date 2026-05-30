"""
exaone/tools.py — ExaoneAgent built-in/custom tool registration.
"""

import logging
from tools.registry import tool_result

logger = logging.getLogger(__name__)

EXAONE_TOOLSET_NAME = "exaone-tools"

PROMPT_TOOL_IDS = [
    "web_search",
    "web_extract",
    "doc_tool",
    "code_tool",
    "get_canvas_status",
    "create_canvasdoc",
    "update_canvasdoc",
    "echo",
    "parse_web_and_doc",
    "doc_search",
    "list_documents",
    "get_document_chunks",
    "ReadFullDocument",
    "get_visuals",
    "analyze_visual",
    "pdf_page_layout",
    "pptx_slide_layout",
    "docx_page_layout",
    "hwpx_page_layout",
    "xlsx_sheet_layout",
]

_CANVAS_TOOLS = ["get_canvas_status", "create_canvasdoc", "update_canvasdoc"]

EXAONE_TOOLSET: dict = {
    "web_tools": ["web_search", "web_extract"],
    "doc_tools": ["doc_tool"],
    "code_tools": ["code_tool"],
    "canvas_tools": [*_CANVAS_TOOLS, "web_search", "web_extract", "code_tool"],
    "parsing_tools": ["parse_web_and_doc"],
    "docqa_tools": [
        "doc_search",
        "list_documents",
        "get_document_chunks",
        "ReadFullDocument",
    ],
    # Multimodal capability groups — populated only in mm_docqa mode.
    "visual_tools": ["get_visuals", "analyze_visual"],
    "pdf_tools":    ["pdf_page_layout"],
    # Per-extension layout tools — same input shape as pdf_page_layout so
    # the model learns one schema. PPTX/DOCX/HWPX/XLSX are stubs awaiting
    # a libreoffice-based render path; calling them returns tool_error.
    "pptx_tools":   ["pptx_slide_layout"],
    "docx_tools":   ["docx_page_layout"],
    "hwpx_tools":   ["hwpx_page_layout"],
    "xlsx_tools":   ["xlsx_sheet_layout"],
    "img_tools": [],
}


_registered = False


def _doc_tool_handler(args: dict | None = None, **kwargs) -> str:
    payload = dict(args or {})
    query = payload.get("query", "")
    source = payload.get("source", "")
    return tool_result(
        success=True,
        data={
            "documents": [
                {
                    "id": "doc-template-0",
                    "source": source,
                    "title": "Template document result",
                    "content": (
                        "Template doc_tool response. Replace this handler with your "
                        "actual document retrieval backend."
                    ),
                    "score": 0.0,
                    "query": query,
                }
            ]
        },
        meta={"tool": "doc_tool", "template": True},
    )



def _echo_handler(args: dict | None = None, **kwargs) -> str:
    payload = dict(args or {})
    return payload.get("message", "")


def _register_docqa_and_parsing_tools(registry) -> list[str]:
    """Register the parsing_tools and docqa_tools custom tools."""
    from exaone.docqa_tools.handle_doc_search import (
        DOC_SEARCH_SCHEMA,
        handle_doc_search,
    )
    from exaone.docqa_tools.handle_get_document_chunks import (
        GET_DOCUMENT_CHUNKS_SCHEMA,
        handle_get_document_chunks,
    )
    from exaone.docqa_tools.handle_list_documents import (
        LIST_DOCUMENTS_SCHEMA,
        handle_list_documents,
    )
    from exaone.docqa_tools.handle_read_full_document import (
        READ_FULL_DOCUMENT_SCHEMA,
        handle_read_full_document,
    )
    from exaone.parsing_tools.handle_parse_web_and_doc import (
        PARSE_WEB_AND_DOC_SCHEMA,
        handle_parse_web_and_doc,
    )

    specs = [
        ("parse_web_and_doc",         PARSE_WEB_AND_DOC_SCHEMA,         handle_parse_web_and_doc,         "📑"),
        ("doc_search",          DOC_SEARCH_SCHEMA,          handle_doc_search,          "🔎"),
        ("list_documents",      LIST_DOCUMENTS_SCHEMA,      handle_list_documents,      "📚"),
        ("get_document_chunks", GET_DOCUMENT_CHUNKS_SCHEMA, handle_get_document_chunks, "📄"),
        ("ReadFullDocument",    READ_FULL_DOCUMENT_SCHEMA,  handle_read_full_document,  "📘"),
    ]

    names: list[str] = []
    for name, schema, handler, emoji in specs:
        registry.register(
            name=name,
            toolset=EXAONE_TOOLSET_NAME,
            schema=schema,
            handler=handler,
            is_async=True,
            emoji=emoji,
        )
        names.append(name)
    return names


def _register_visual_and_layout_tools(registry) -> list[str]:
    """Register visual_tools + per-extension page-layout tools."""
    from exaone.visual_tools.handle_get_visuals import (
        GET_VISUALS_SCHEMA, handle_get_visuals,
    )
    from exaone.visual_tools.handle_analyze_visual import (
        ANALYZE_VISUAL_SCHEMA, handle_analyze_visual,
    )
    from exaone.pdf_tools.handle_pdf_page_layout import (
        PDF_PAGE_LAYOUT_SCHEMA, handle_pdf_page_layout,
    )
    from exaone.pptx_tools.handle_pptx_slide_layout import (
        PPTX_SLIDE_LAYOUT_SCHEMA, handle_pptx_slide_layout,
    )
    from exaone.docx_tools.handle_docx_page_layout import (
        DOCX_PAGE_LAYOUT_SCHEMA, handle_docx_page_layout,
    )
    from exaone.hwpx_tools.handle_hwpx_page_layout import (
        HWPX_PAGE_LAYOUT_SCHEMA, handle_hwpx_page_layout,
    )
    from exaone.xlsx_tools.handle_xlsx_sheet_layout import (
        XLSX_SHEET_LAYOUT_SCHEMA, handle_xlsx_sheet_layout,
    )
    specs = [
        ("get_visuals",       GET_VISUALS_SCHEMA,       handle_get_visuals,       "🖼️"),
        ("analyze_visual",    ANALYZE_VISUAL_SCHEMA,    handle_analyze_visual,    "👁️"),
        ("pdf_page_layout",   PDF_PAGE_LAYOUT_SCHEMA,   handle_pdf_page_layout,   "📐"),
        ("pptx_slide_layout", PPTX_SLIDE_LAYOUT_SCHEMA, handle_pptx_slide_layout, "📐"),
        ("docx_page_layout",  DOCX_PAGE_LAYOUT_SCHEMA,  handle_docx_page_layout,  "📐"),
        ("hwpx_page_layout",  HWPX_PAGE_LAYOUT_SCHEMA,  handle_hwpx_page_layout,  "📐"),
        ("xlsx_sheet_layout", XLSX_SHEET_LAYOUT_SCHEMA, handle_xlsx_sheet_layout, "📐"),
    ]
    names: list[str] = []
    for name, schema, handler, emoji in specs:
        registry.register(
            name=name,
            toolset=EXAONE_TOOLSET_NAME,
            schema=schema,
            handler=handler,
            is_async=True,
            emoji=emoji,
        )
        names.append(name)
    return names


def _register_template_tools(registry) -> list[str]:
    """Register placeholder custom tools for doc workflows."""
    names: list[str] = []

    registry.register(
        name="doc_tool",
        toolset=EXAONE_TOOLSET_NAME,
        schema={
            "name": "doc_tool",
            "description": "Template custom tool for document-grounded tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Document query or retrieval instruction."},
                    "source": {"type": "string", "description": "Optional document source id/path."},
                },
                "required": ["query"],
            },
        },
        handler=_doc_tool_handler,
    )
    names.append("doc_tool")

    return names


def register_exaone_tools() -> None:
    """Register ExaoneAgent built-in + custom template tools."""
    global _registered
    if _registered:
        return

    try:
        from tools.registry import discover_builtin_tools, registry
        from toolsets import create_custom_toolset

        # Ensure built-in tools are imported before looking them up.
        discover_builtin_tools()

        tool_names: list[str] = []
        for builtin in ("web_search", "web_extract", "code_tool", *_CANVAS_TOOLS):
            if registry.get_entry(builtin) is not None:
                tool_names.append(builtin)
            else:
                logger.warning("ExaoneAgent: built-in tool '%s' not found in registry", builtin)

        registry.register(
            name="echo",
            toolset=EXAONE_TOOLSET_NAME,
            schema={
                "name": "echo",
                "description": "Returns the input message as-is. Used for toolset union testing.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Any string"},
                    },
                    "required": ["message"],
                },
            },
            handler=_echo_handler,
        )
        tool_names.append("echo")

        tool_names.extend(_register_template_tools(registry))
        tool_names.extend(_register_docqa_and_parsing_tools(registry))
        tool_names.extend(_register_visual_and_layout_tools(registry))

        create_custom_toolset(EXAONE_TOOLSET_NAME, "ExaoneAgent custom tools", tools=tool_names)
        logger.info(
            "ExaoneAgent: registered toolset '%s' with %d tool(s): %s",
            EXAONE_TOOLSET_NAME,
            len(tool_names),
            ", ".join(tool_names),
        )
    except Exception:
        logger.exception("ExaoneAgent: built-in/custom tool registration failed")

    _registered = True
