"""Unit tests for domain/reasoning — parser and model."""

import pytest

from agent.domain.reasoning.model import AgentResponse, ToolInvocation
from agent.domain.reasoning.parser import (
    _extract_tag,
    _parse_tool_invoke,
    parse_agent_response,
)


# ── _extract_tag ────────────────────────────────────────────


class TestExtractTag:
    def test_present(self):
        assert _extract_tag("<obs>hello</obs>", "obs") == "hello"

    def test_missing(self):
        assert _extract_tag("no tags here", "obs") is None

    def test_empty(self):
        assert _extract_tag("<obs></obs>", "obs") == ""

    def test_whitespace(self):
        assert _extract_tag("<obs>  spaced  </obs>", "obs") == "spaced"

    def test_no_close(self):
        assert _extract_tag("<obs>unclosed", "obs") is None

    def test_no_open(self):
        assert _extract_tag("text</obs>", "obs") is None


# ── parse_agent_response — normal cases ─────────────────────


class TestParseNormal:
    FULL_RESPONSE = (
        "<observation>I see docs</observation>\n"
        "<reasoning>Need to search</reasoning>\n"
        "<step_name>Search step</step_name>\n"
        '<tool_invoke>\n{"name": "search", "arguments": {"query": "test"}}\n</tool_invoke>'
    )

    def test_all_fields(self):
        parsed = parse_agent_response(self.FULL_RESPONSE)
        assert parsed.observation == "I see docs"
        assert parsed.reasoning == "Need to search"
        assert parsed.step_name == "Search step"
        assert parsed.has_tool_invoke
        assert parsed.tool_invoke.name == "search"
        assert parsed.tool_invoke.arguments == {"query": "test"}
        assert not parsed.has_final_answer

    def test_raw_preserved(self):
        parsed = parse_agent_response(self.FULL_RESPONSE)
        assert parsed.raw == self.FULL_RESPONSE


# ── parse_agent_response — final_answer branch ──────────────


class TestParseFinalAnswer:
    FINAL_RESPONSE = (
        "<observation>Found info</observation>\n"
        "<reasoning>Synthesizing</reasoning>\n"
        "<step_name>Final</step_name>\n"
        "<final_answer>The answer is 42.</final_answer>"
    )

    def test_extracted(self):
        parsed = parse_agent_response(self.FINAL_RESPONSE)
        assert parsed.has_final_answer
        assert parsed.final_answer == "The answer is 42."

    def test_no_other_tags(self):
        parsed = parse_agent_response("<final_answer>solo</final_answer>")
        assert parsed.has_final_answer
        assert parsed.observation is None
        assert parsed.reasoning is None
        assert not parsed.has_tool_invoke


# ── parse_agent_response — malformed input ───────────────────


class TestParseMalformed:
    def test_bad_json(self):
        bad = '<tool_invoke>{"name": broken}</tool_invoke>'
        parsed = parse_agent_response(bad)
        assert not parsed.has_tool_invoke
        assert parsed.tool_invoke is None

    def test_empty_string(self):
        parsed = parse_agent_response("")
        assert parsed.observation is None
        assert parsed.reasoning is None
        assert not parsed.has_final_answer
        assert not parsed.has_tool_invoke
        assert parsed.raw == ""

    def test_partial(self):
        partial = "<observation>only obs</observation>"
        parsed = parse_agent_response(partial)
        assert parsed.observation == "only obs"
        assert parsed.reasoning is None
        assert parsed.step_name is None


# ── to_dict — legacy compatibility ──────────────────────────


class TestToDict:
    def test_round_trip(self):
        response_str = (
            "<observation>obs</observation>\n"
            "<reasoning>rsn</reasoning>\n"
            '<tool_invoke>\n{"name": "search", "arguments": {"q": "x"}}\n</tool_invoke>'
        )
        parsed = parse_agent_response(response_str)
        d = parsed.to_dict()

        assert d["observation"] == "obs"
        assert d["reasoning"] == "rsn"
        assert d["tool_invoke"] == {"name": "search", "arguments": {"q": "x"}}
        assert "final_answer" not in d  # None values excluded

    def test_legacy_compat(self):
        """to_dict() output matches original _parse_agent_response dict format."""
        response_str = "<final_answer>done</final_answer>"
        parsed = parse_agent_response(response_str)
        d = parsed.to_dict()

        assert d == {"final_answer": "done"}
        # No extra keys
        assert "observation" not in d
        assert "tool_invoke" not in d
