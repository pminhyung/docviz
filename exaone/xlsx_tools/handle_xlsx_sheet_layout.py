"""xlsx_sheet_layout — STUB. See pptx counterpart for the design note."""

from __future__ import annotations

from typing import Any

from tools.registry import tool_error


XLSX_SHEET_LAYOUT_SCHEMA: dict[str, Any] = {
    "name": "xlsx_sheet_layout",
    "description": (
        "Render XLSX sheet(s) as images for spatial/layout inspection. Same "
        "scope syntax as pdf_page_layout. NOT YET IMPLEMENTED in this "
        "build — calls return an error."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "scope": {"type": "array", "items": {"type": "string"}},
            "dpi": {"type": "integer", "enum": [100, 150, 200], "default": 150},
        },
        "required": ["scope"],
    },
}


async def handle_xlsx_sheet_layout(args: dict | None = None, **kwargs) -> str:
    return tool_error(
        "xlsx_sheet_layout is not implemented yet; use get_visuals for "
        "extracted figures instead."
    )
