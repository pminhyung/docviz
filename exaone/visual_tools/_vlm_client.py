"""VLM client adapter for visual_tools.

Wraps agent.auxiliary_client.async_call_llm with the OpenAI chat-messages
shape that visual_tools needs:

    [{"role": "system", "content": <extract-from-image-system-prompt>},
     {"role": "user",   "content": [
        {"type": "text",      "text": "<context (caption/desc/category) + GOAL>"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
     ]}]

Production: deployer points AUXILIARY_VISION_MODEL (or hermes config
auxiliary.vision.model) to the main agent's VLM model when available.
Shim: model often differs from the main agent's chat model when the main
model isn't multimodal (e.g. main = DeepSeek text-only, vision = Qwen2.5-VL
via a separate auxiliary endpoint). The chat-messages shape stays the same.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_EXTRACT = (
    "You are an expert at extracting information from images for a research "
    "agent. Given an image (a figure / chart / diagram / photo from a "
    "document or web page) and a goal, produce a focused, factual "
    "extraction that answers the goal. Read all visible text. Describe "
    "axes, units, legend, and quantitative values when present. If the "
    "image does not contain information relevant to the goal, say so "
    "explicitly rather than inventing content."
)

CONTEXT_TEMPLATE = (
    "<image-context>\n"
    "Category: {category}\n"
    "Caption: {caption}\n"
    "Description: {description}\n"
    "</image-context>\n\n"
    "GOAL:\n{goal}"
)


def _b64_data_url(png_bytes: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(png_bytes).decode('ascii')}"


def build_vlm_messages(
    *,
    png_bytes: bytes,
    goal: str,
    category: str = "",
    caption: str = "",
    description: str = "",
) -> list[dict[str, Any]]:
    """Assemble OpenAI chat-messages with one image + goal."""
    text_part = CONTEXT_TEMPLATE.format(
        category=category or "(unknown)",
        caption=caption or "(none)",
        description=description or "(none)",
        goal=goal,
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT_EXTRACT},
        {"role": "user", "content": [
            {"type": "text", "text": text_part},
            {"type": "image_url",
             "image_url": {"url": _b64_data_url(png_bytes)}},
        ]},
    ]


def _resolve_vlm_model() -> str | None:
    # AUXILIARY_VISION_MODEL is the convention used by Hermes auxiliary
    # vision routing (tools/vision_tools.py:793 reads the same env).
    val = os.environ.get("AUXILIARY_VISION_MODEL", "").strip()
    return val or None


async def call_vlm(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    model: str | None = None,
) -> str:
    """Invoke the VLM and return its text content (or empty on failure)."""
    try:
        from agent.auxiliary_client import async_call_llm, extract_content_or_reasoning
    except Exception as exc:
        logger.warning("auxiliary_client unavailable: %s", exc)
        return ""
    effective_model = model or _resolve_vlm_model()
    call_kwargs: dict[str, Any] = {
        "task": "vision_analyze",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if effective_model:
        call_kwargs["model"] = effective_model
    try:
        response = await async_call_llm(**call_kwargs)
    except Exception:
        logger.exception("VLM call_llm failed")
        return ""
    return extract_content_or_reasoning(response) or ""
