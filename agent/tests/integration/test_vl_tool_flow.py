"""Integration tests for VL tools using context["call_vl"] and context["record_training"]."""

import json
import os
import tempfile
import base64
import pytest

# Add project root to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agent.examples.vl_tools import (
    AnalyzePageImageTool,
    ExtractTableTool,
    ComparePageImagesTool,
    _load_page_image,
)


@pytest.fixture
def image_dir():
    """Create a temporary directory with fake page images."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fake images for pages 1, 2, 3
        for page_num in range(1, 4):
            path = os.path.join(tmpdir, f"page_{page_num}_image0.png")
            with open(path, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n" + bytes(f"page{page_num}", "utf-8"))
        yield tmpdir


@pytest.fixture
def mock_context(image_dir):
    """Build a mock context dict with call_vl and record_training stubs."""
    vl_calls = []
    training_records = []

    def mock_call_vl(messages, temperature=0.2, max_tokens=2000):
        vl_calls.append({"messages": messages, "temperature": temperature, "max_tokens": max_tokens})
        return "VL model analysis result"

    def mock_record_training(task_type, conversations):
        training_records.append({"task_type": task_type, "conversations": conversations})

    ctx = {
        "image_dir": image_dir,
        "language": "en",
        "call_vl": mock_call_vl,
        "record_training": mock_record_training,
    }
    return ctx, vl_calls, training_records


class TestAnalyzePageImageTool:
    def test_calls_call_vl(self, mock_context):
        """call_vl should be invoked with multimodal messages."""
        ctx, vl_calls, _ = mock_context
        tool = AnalyzePageImageTool()
        result = tool.execute({"page_numbers": [1]}, ctx)

        assert len(vl_calls) == 1
        msg = vl_calls[0]["messages"][0]
        assert msg["role"] == "user"
        assert isinstance(msg["content"], list)
        # Should have text + image_url parts
        types = [part["type"] for part in msg["content"]]
        assert "text" in types
        assert "image_url" in types

    def test_records_training(self, mock_context):
        """record_training should be called with task_type="vl_analysis"."""
        ctx, _, training_records = mock_context
        tool = AnalyzePageImageTool()
        tool.execute({"page_numbers": [1]}, ctx)

        assert len(training_records) == 1
        assert training_records[0]["task_type"] == "vl_analysis"
        convs = training_records[0]["conversations"]
        assert len(convs) == 2
        assert convs[0]["role"] == "user"
        assert convs[0]["loss_masking"] is True
        assert convs[1]["role"] == "assistant"
        assert convs[1]["loss_masking"] is False

    def test_multiple_pages(self, mock_context):
        """Multiple pages should produce multiple VL calls and training records."""
        ctx, vl_calls, training_records = mock_context
        tool = AnalyzePageImageTool()
        result_str = tool.execute({"page_numbers": [1, 2]}, ctx)
        result = json.loads(result_str)

        assert len(result) == 2
        assert len(vl_calls) == 2
        assert len(training_records) == 2

    def test_analysis_focus(self, mock_context):
        """Different analysis_focus should produce different prompts."""
        ctx, vl_calls, _ = mock_context
        tool = AnalyzePageImageTool()

        tool.execute({"page_numbers": [1], "analysis_focus": "chart"}, ctx)
        text_part = vl_calls[0]["messages"][0]["content"][0]["text"]
        assert "chart" in text_part.lower() or "graph" in text_part.lower()


class TestExtractTableTool:
    def test_json_output(self, mock_context):
        """Tool should return VL model output (expected to be JSON)."""
        ctx, vl_calls, _ = mock_context
        tool = ExtractTableTool()
        result = tool.execute({"page_number": 1}, ctx)

        assert len(vl_calls) == 1
        # Result is the raw VL model output
        assert result == "VL model analysis result"

    def test_records_training(self, mock_context):
        """record_training should be called for table extraction."""
        ctx, _, training_records = mock_context
        tool = ExtractTableTool()
        tool.execute({"page_number": 1}, ctx)

        assert len(training_records) == 1
        assert training_records[0]["task_type"] == "vl_analysis"


class TestComparePageImagesTool:
    def test_multi_image_content(self, mock_context):
        """VL call should include multiple image_url parts."""
        ctx, vl_calls, _ = mock_context
        tool = ComparePageImagesTool()
        result_str = tool.execute(
            {"page_numbers": [1, 2], "comparison_focus": "test"},
            ctx,
        )

        assert len(vl_calls) == 1
        content = vl_calls[0]["messages"][0]["content"]
        image_parts = [p for p in content if p["type"] == "image_url"]
        assert len(image_parts) == 2

        result = json.loads(result_str)
        assert result["pages_compared"] == [1, 2]

    def test_less_than_2_pages_error(self, mock_context):
        """Should return error when fewer than 2 pages provided."""
        ctx, _, _ = mock_context
        tool = ComparePageImagesTool()
        result_str = tool.execute(
            {"page_numbers": [1], "comparison_focus": "test"},
            ctx,
        )
        result = json.loads(result_str)
        assert "error" in result


class TestErrorHandling:
    def test_missing_image_dir(self):
        """Should return error when image_dir not in context."""
        ctx = {"language": "en", "call_vl": lambda m, **kw: "ok"}
        tool = AnalyzePageImageTool()
        result_str = tool.execute({"page_numbers": [1]}, ctx)
        result = json.loads(result_str)
        assert "error" in result
        assert "image" in result["error"].lower()

    def test_missing_image_file(self):
        """Should return error for non-existent page images."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = {
                "image_dir": tmpdir,
                "language": "en",
                "call_vl": lambda m, **kw: "ok",
                "record_training": lambda t, c: None,
            }
            tool = AnalyzePageImageTool()
            result_str = tool.execute({"page_numbers": [999]}, ctx)
            result = json.loads(result_str)
            assert result[0]["error"]
            assert "not found" in result[0]["error"].lower()

    def test_missing_call_vl(self):
        """Should return error when call_vl not in context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = {"image_dir": tmpdir, "language": "en"}
            tool = AnalyzePageImageTool()
            result_str = tool.execute({"page_numbers": [1]}, ctx)
            result = json.loads(result_str)
            assert "error" in result


class TestLoadPageImage:
    def test_load_existing_image(self, image_dir):
        """Should load and base64-encode existing image."""
        b64, error = _load_page_image(image_dir, 1)
        assert error == ""
        assert len(b64) > 0
        # Verify it's valid base64
        decoded = base64.b64decode(b64)
        assert decoded[:4] == b"\x89PNG"

    def test_load_missing_image(self, image_dir):
        """Should return error for non-existent image."""
        b64, error = _load_page_image(image_dir, 999)
        assert b64 == ""
        assert "not found" in error.lower()
