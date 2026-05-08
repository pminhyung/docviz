"""Unit tests for sandbox VL multimodal message handling.

Verifies that SandboxResponseGenerator correctly handles both:
- Standard string content messages
- VL multimodal list content messages (text + image_url)
"""

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agent.core.sandbox import SandboxResponseGenerator


class TestSandboxVLContent:
    def setup_method(self):
        self.gen = SandboxResponseGenerator()

    def test_string_content(self):
        """Standard string content should work as before."""
        messages = [
            {"role": "user", "content": "What is the document about?"},
        ]
        resp = self.gen.generate_response(messages)
        assert resp.choices[0].message.content
        assert isinstance(resp.choices[0].message.content, str)

    def test_list_content_vl(self):
        """VL multimodal list content should not crash."""
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": "Analyze this chart showing revenue trends"},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64,iVBORw0KGgoAAAANS"
                }},
            ]},
        ]
        resp = self.gen.generate_response(messages)
        assert resp.choices[0].message.content
        assert isinstance(resp.choices[0].message.content, str)

    def test_empty_messages(self):
        """Empty messages list should not crash."""
        messages = []
        resp = self.gen.generate_response(messages)
        assert resp.choices[0].message.content
        assert isinstance(resp.choices[0].message.content, str)

    def test_list_content_with_doc_summary_pattern(self):
        """VL message containing doc summary patterns should be detected."""
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": "Write a retrieval-optimized summary of this document"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ]},
        ]
        resp = self.gen.generate_response(messages)
        # Should detect doc_summary pattern and return appropriate response
        assert resp.choices[0].message.content
