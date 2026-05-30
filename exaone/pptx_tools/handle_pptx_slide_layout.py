"""pptx_slide_layout — STUB.

Mirrors pdf_page_layout's input schema so the model learns one consistent
shape across extensions. Render path (likely libreoffice headless → PDF →
fitz) is left for a future implementer; calling this today returns a
tool_error so the agent can fall back to other strategies.
"""

from __future__ import annotations

from typing import Any

from tools.registry import tool_error


PPTX_SLIDE_LAYOUT_SCHEMA: dict[str, Any] = {
    "name": "pptx_slide_layout",
    "description": (
        "Render PPTX slide(s) as images for spatial/layout inspection. "
        "Same scope syntax as pdf_page_layout. NOT YET IMPLEMENTED in this "
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


async def handle_pptx_slide_layout(args: dict | None = None, **kwargs) -> str:
    return tool_error(
        "pptx_slide_layout is not implemented yet; use get_visuals for "
        "extracted figures instead."
    )
