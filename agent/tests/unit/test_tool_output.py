"""Unit tests for core/tool_output.py — pure functions for tool output processing."""

import json
import os
import tempfile
import pytest

from agent.core.tool_output import (
    parse_tool_output,
    parse_images,
    build_multimodal_message,
)
from agent.core.model_router import ToolOutput, ImageRef


class TestParseToolOutput:
    def test_plain_text(self):
        result = parse_tool_output("Simple text response")
        assert isinstance(result, ToolOutput)
        assert result.text == "Simple text response"
        assert result.has_images is False
        assert result.images == []

    def test_output_type_image(self):
        output = json.dumps({
            "output_type": "image",
            "text": "Chart analysis",
            "images": [
                {"source": "base64", "data": "iVBOR...", "mime_type": "image/png"},
            ],
        })
        result = parse_tool_output(output)
        assert result.has_images is True
        assert result.text == "Chart analysis"
        assert len(result.images) == 1
        assert result.images[0].source == "base64"

    def test_output_type_mixed(self):
        output = json.dumps({
            "output_type": "mixed",
            "text": "Text + images",
            "images": [
                {"source": "path", "path": "/tmp/a.png"},
                {"source": "url", "url": "https://img.com/b.png"},
            ],
        })
        result = parse_tool_output(output)
        assert result.has_images is True
        assert len(result.images) == 2

    def test_legacy_image_paths(self):
        output = json.dumps({
            "image_paths": ["/tmp/img1.png", "/tmp/img2.png"],
            "result": "done",
        })
        result = parse_tool_output(output)
        assert result.has_images is True
        assert len(result.images) == 2
        assert all(img.source == "path" for img in result.images)

    def test_json_no_images(self):
        output = json.dumps({"result": "data", "score": 0.9})
        result = parse_tool_output(output)
        assert result.has_images is False

    def test_invalid_json(self):
        result = parse_tool_output("not json {{{")
        assert result.has_images is False
        assert result.text == "not json {{{"


class TestParseImages:
    def test_empty_list(self):
        assert parse_images([]) == []

    def test_non_dict_items_skipped(self):
        result = parse_images(["not a dict", 42, None])
        assert result == []

    def test_valid_images(self):
        data = [
            {"source": "base64", "data": "abc", "mime_type": "image/jpeg"},
            {"source": "path", "path": "/tmp/x.png"},
        ]
        result = parse_images(data)
        assert len(result) == 2
        assert result[0].source == "base64"
        assert result[0].data == "abc"
        assert result[1].source == "path"
        assert result[1].path == "/tmp/x.png"

    def test_defaults(self):
        result = parse_images([{}])
        assert len(result) == 1
        assert result[0].source == "path"  # default
        assert result[0].mime_type == "image/png"  # default


class TestBuildMultimodalMessage:
    def test_text_only(self):
        tool_output = ToolOutput(text="hello", images=[], has_images=False)
        msg = build_multimodal_message(tool_output)
        assert msg["role"] == "user"
        assert len(msg["content"]) == 1
        assert msg["content"][0]["type"] == "text"
        assert "hello" in msg["content"][0]["text"]

    def test_with_base64_image(self):
        img = ImageRef(source="base64", data="iVBORw0K", mime_type="image/png")
        tool_output = ToolOutput(text="chart", images=[img], has_images=True)
        msg = build_multimodal_message(tool_output)
        assert len(msg["content"]) == 2
        assert msg["content"][1]["type"] == "image_url"
        assert "data:image/png;base64,iVBORw0K" in msg["content"][1]["image_url"]["url"]

    def test_with_url_image(self):
        img = ImageRef(source="url", url="https://img.com/photo.jpg")
        tool_output = ToolOutput(text="photo", images=[img], has_images=True)
        msg = build_multimodal_message(tool_output)
        assert len(msg["content"]) == 2
        assert msg["content"][1]["image_url"]["url"] == "https://img.com/photo.jpg"

    def test_with_path_image(self):
        # Create a temp image file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes
            tmp_path = f.name

        try:
            img = ImageRef(source="path", path=tmp_path, mime_type="image/png")
            tool_output = ToolOutput(text="local", images=[img], has_images=True)
            msg = build_multimodal_message(tool_output)
            assert len(msg["content"]) == 2
            assert msg["content"][1]["type"] == "image_url"
            assert "data:image/png;base64," in msg["content"][1]["image_url"]["url"]
        finally:
            os.unlink(tmp_path)

    def test_missing_path_image_skipped(self):
        img = ImageRef(source="path", path="/nonexistent/path.png")
        tool_output = ToolOutput(text="missing", images=[img], has_images=True)
        msg = build_multimodal_message(tool_output)
        # Only text, image is skipped
        assert len(msg["content"]) == 1
