"""
Tool Output Processing

Pure functions for parsing tool output and building multimodal messages.
Extracted from run_agent_v2.py to keep the runner focused on orchestration.
"""

import base64
import json
import os
from typing import Dict, List, Any

from .model_router import ToolOutput, ImageRef


def parse_tool_output(tool_response: str) -> ToolOutput:
    """
    Parse tool output and detect images via output_type policy.

    Supports:
    1. output_type: "image" | "mixed" -> extract images from JSON
    2. Legacy: "image_paths" key -> extract file paths
    3. Default: text-only output

    Args:
        tool_response: Raw tool output string (usually JSON)

    Returns:
        ToolOutput with text and optional images
    """
    try:
        result = json.loads(tool_response)
        if isinstance(result, dict):
            # New policy: output_type field
            output_type = result.get("output_type", "text")
            if output_type in ("image", "mixed"):
                images = parse_images(result.get("images", []))
                return ToolOutput(
                    text=result.get("text", tool_response),
                    images=images,
                    has_images=bool(images),
                )

            # Legacy: image_paths key
            if "image_paths" in result:
                paths = result["image_paths"]
                if isinstance(paths, str):
                    paths = [paths]
                images = [
                    ImageRef(source="path", path=p)
                    for p in paths if isinstance(p, str)
                ]
                return ToolOutput(
                    text=tool_response,
                    images=images,
                    has_images=bool(images),
                )
    except json.JSONDecodeError:
        pass

    return ToolOutput(text=tool_response, images=[], has_images=False)


def parse_images(images_data: List[Dict]) -> List[ImageRef]:
    """Parse image references from tool output images list."""
    refs = []
    for img in images_data:
        if not isinstance(img, dict):
            continue
        refs.append(ImageRef(
            source=img.get("source", "path"),
            data=img.get("data", ""),
            path=img.get("path", ""),
            url=img.get("url", ""),
            mime_type=img.get("mime_type", "image/png"),
            caption=img.get("caption", ""),
        ))
    return refs


def build_multimodal_message(tool_output: ToolOutput) -> Dict[str, Any]:
    """
    Build a multimodal message from tool output with images.

    Converts ImageRef objects into OpenAI-compatible content array
    with image_url entries.

    Args:
        tool_output: ToolOutput with images

    Returns:
        Message dict with multimodal content
    """
    content: List[Dict[str, Any]] = [
        {"type": "text", "text": f"<action_result> {tool_output.text} </action_result>"}
    ]

    for img in tool_output.images:
        try:
            if img.source == "base64" and img.data:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{img.mime_type};base64,{img.data}"}
                })
            elif img.source == "path" and img.path:
                if os.path.exists(img.path):
                    with open(img.path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    ext = img.path.lower().split(".")[-1]
                    mime = img.mime_type or ("image/png" if ext == "png" else "image/jpeg")
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"}
                    })
                else:
                    print(f"[Warning] Image not found: {img.path}")
            elif img.source == "url" and img.url:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img.url}
                })
        except Exception as e:
            print(f"[Warning] Failed to process image: {e}")

    return {"role": "user", "content": content}
