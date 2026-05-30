import pytest
from unittest.mock import MagicMock, patch

from exaone.agent import ExaoneAgent
from exaone.aliasing import RandomShortAliaser
from exaone.tool_formatting import new_run_formatting
from tools.registry import registry


# --- init ---

def test_agent_init_qa_mode_general():
    agent = ExaoneAgent(qa_mode="general", reasoning=False)
    assert agent._qa_mode == "general"
    assert agent._system_blocks_text
    assert "identity" in agent._system_blocks
    assert agent._system_blocks["tool_list"]


def test_agent_init_toolset_web_tools():
    agent = ExaoneAgent(toolset="web_tools", reasoning=False)
    assert agent._qa_mode is None
    assert agent._configured_toolset == "web_tools"


def test_agent_init_enabled_toolsets():
    agent = ExaoneAgent(enabled_toolsets=["exaone-tools"], reasoning=False)
    assert agent._qa_mode is None
    assert agent._configured_toolset == ["exaone-tools"]


def test_agent_init_reasoning_false():
    agent = ExaoneAgent(reasoning=False)
    assert not agent._reasoning_enabled
    extra = agent.request_overrides.get("extra_body", {})
    assert extra.get("chat_template_kwargs", {}).get("enable_thinking") is False


def test_agent_init_reasoning_true_no_override():
    agent = ExaoneAgent(reasoning=True)
    assert agent._reasoning_enabled
    extra = agent.request_overrides.get("extra_body", {})
    assert extra.get("chat_template_kwargs", {}).get("enable_thinking") is not False


# --- system prompt ---

def test_build_system_prompt_no_duplicate_identity():
    agent = ExaoneAgent.__new__(ExaoneAgent)
    identity = "ChatEXAONE identity block"
    agent._system_blocks_text = f"{identity}\n\ntool list here"
    prompt = agent._build_system_prompt()
    assert prompt.count(identity) == 1


def _mk_tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name}}


def test_select_tools_skips_temporarily_unavailable_registered_tools(monkeypatch):
    agent = ExaoneAgent.__new__(ExaoneAgent)
    agent.tools = [_mk_tool("get_canvas_status"), _mk_tool("code_tool")]

    monkeypatch.setattr(
        registry,
        "get_all_tool_names",
        lambda: ["web_search", "web_extract", "get_canvas_status", "code_tool"],
    )

    selected = agent._select_tools("search")
    assert selected == []


def test_select_tools_raises_for_unknown_tool_name(monkeypatch):
    agent = ExaoneAgent.__new__(ExaoneAgent)
    agent.tools = [_mk_tool("get_canvas_status")]

    monkeypatch.setattr(registry, "get_all_tool_names", lambda: ["get_canvas_status"])

    with pytest.raises(ValueError, match="Unknown tool name"):
        agent._select_tools(["not_a_real_tool"])


def test_select_tools_expands_hermes_toolset(monkeypatch):
    agent = ExaoneAgent.__new__(ExaoneAgent)
    agent.tools = [_mk_tool("web_search"), _mk_tool("web_extract")]

    monkeypatch.setattr(
        "toolsets.get_toolset",
        lambda name: {"tools": ["web_search", "web_extract"]} if name == "web_tools" else None,
    )

    selected = agent._select_tools(["web_tools"])
    names = [t["function"]["name"] for t in selected]
    assert "web_search" in names
    assert "web_extract" in names


def test_select_tools_deduplicates(monkeypatch):
    agent = ExaoneAgent.__new__(ExaoneAgent)
    agent.tools = [_mk_tool("web_search"), _mk_tool("web_extract")]

    monkeypatch.setattr("toolsets.get_toolset", lambda name: None)
    monkeypatch.setattr(registry, "get_all_tool_names", lambda: ["web_search", "web_extract"])

    selected = agent._select_tools(["web_search", "web_search", "web_extract"])
    names = [t["function"]["name"] for t in selected]
    assert names.count("web_search") == 1
    assert names.count("web_extract") == 1


def test_select_tools_expands_exaone_toolset():
    """EXAONE_TOOLSET 경로 — Hermes get_toolset를 거치지 않는 별도 분기."""
    agent = ExaoneAgent.__new__(ExaoneAgent)
    agent.tools = [_mk_tool("web_search"), _mk_tool("web_extract")]

    selected = agent._select_tools(["web_tools"])
    names = [t["function"]["name"] for t in selected]
    assert "web_search" in names
    assert "web_extract" in names


def test_execute_tool_calls_aliases_and_formats():
    agent = ExaoneAgent.__new__(ExaoneAgent)
    agent._tool_aliaser = RandomShortAliaser()
    agent._tool_formatter = None

    tc = MagicMock()
    tc.id = "call-abc"
    tc.function.name = "web_search"
    assistant_msg = MagicMock()
    assistant_msg.tool_calls = [tc]

    messages = [{"role": "assistant", "tool_calls": [{"id": "call-abc", "function": {"name": "web_search"}}]}]

    def fake_super_execute(*_):
        messages.append({"role": "tool", "tool_call_id": tc.id, "name": "web_search", "content": '{"result": "ok"}'})

    with patch.object(ExaoneAgent.__bases__[0], "_execute_tool_calls", fake_super_execute):
        agent._execute_tool_calls(assistant_msg, messages, "task-1")

    aliased_id = tc.id
    assert aliased_id != "call-abc"
    assert len(aliased_id) == 6
    tool_msg = messages[-1]
    assert tool_msg["role"] == "tool"


def test_execute_tool_calls_invokes_formatter_when_set():
    agent = ExaoneAgent.__new__(ExaoneAgent)
    agent._tool_aliaser = None
    _, agent._tool_formatter = new_run_formatting()

    tc = MagicMock()
    tc.id = "call-xyz"
    tc.function.name = "web_search"
    assistant_msg = MagicMock()
    assistant_msg.tool_calls = []

    messages: list = []

    def fake_super_execute(*_):
        messages.append({
            "role": "tool",
            "tool_call_id": "call-xyz",
            "name": "web_search",
            "content": '{"results": [{"title": "T", "url": "http://x.com", "description": "D"}]}',
        })

    with patch.object(ExaoneAgent.__bases__[0], "_execute_tool_calls", fake_super_execute):
        agent._execute_tool_calls(assistant_msg, messages, "task-1")

    content = messages[-1]["content"]
    assert "Index" in content


def test_compress_context_writes_triplet_files(tmp_path):
    agent = ExaoneAgent.__new__(ExaoneAgent)
    agent._compaction_count = 0
    agent._current_run_dir = tmp_path
    agent.context_compressor = None

    pre = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    post = [{"role": "assistant", "content": "summary"}]

    def fake_super_compress(*_, **__):
        return post, "sys"

    with patch.object(ExaoneAgent.__bases__[0], "_compress_context", fake_super_compress):
        result, sys_out = agent._compress_context(pre, "sys")

    assert result == post
    triplet_files = list(tmp_path.glob("*_pre_compaction.json"))
    assert len(triplet_files) == 1
    assert list(tmp_path.glob("*_post_compaction.json"))
    assert list(tmp_path.glob("*_compaction_round_trip.json"))
