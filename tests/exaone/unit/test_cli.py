import json
import pytest
from unittest.mock import MagicMock, patch

from exaone.cli import main, _load_history


def _run(agent_mock, **kwargs):
    agent_mock.return_value.run_conversation.return_value = {"final_response": "ok"}
    main(**kwargs)
    return agent_mock.call_args


@patch("exaone.cli.bootstrap_gateway_env")
@patch("exaone.cli.ExaoneAgent")
def test_qa_mode_passed(agent_mock, _env):
    call = _run(agent_mock, query="q", qa_mode="general")
    assert call.kwargs.get("qa_mode") == "general"


@patch("exaone.cli.bootstrap_gateway_env")
@patch("exaone.cli.ExaoneAgent")
def test_toolset_passed(agent_mock, _env):
    call = _run(agent_mock, query="q", toolset="web_tools")
    assert call.kwargs.get("toolset") == "web_tools"


@patch("exaone.cli.bootstrap_gateway_env")
@patch("exaone.cli.ExaoneAgent")
def test_enabled_toolsets_passed(agent_mock, _env):
    call = _run(agent_mock, query="q", enabled_toolsets=["exaone-tools"])
    assert call.kwargs.get("enabled_toolsets") == ["exaone-tools"]


@patch("exaone.cli.bootstrap_gateway_env")
@patch("exaone.cli.ExaoneAgent")
def test_reasoning_false_passed(agent_mock, _env):
    call = _run(agent_mock, query="q", reasoning=False)
    assert call.kwargs.get("reasoning") is False


@patch("exaone.cli.bootstrap_gateway_env")
@patch("exaone.cli.ExaoneAgent")
def test_reasoning_string_false_converted(agent_mock, _env):
    call = _run(agent_mock, query="q", reasoning="false")
    assert call.kwargs.get("reasoning") is False


# --- _load_history 우선순위 ---

_HIST = [{"role": "user", "content": "hi"}]


def test_load_history_conversation_history_takes_priority(tmp_path):
    f = tmp_path / "h.json"
    f.write_text(json.dumps([{"role": "user", "content": "from_file"}]))
    result = _load_history(
        conversation_history=_HIST,
        history_json=json.dumps([{"role": "user", "content": "from_json"}]),
        history_file=str(f),
    )
    assert result[0]["content"] == "hi"


def test_load_history_json_over_file(tmp_path):
    f = tmp_path / "h.json"
    f.write_text(json.dumps([{"role": "user", "content": "from_file"}]))
    result = _load_history(
        history_json=json.dumps([{"role": "user", "content": "from_json"}]),
        history_file=str(f),
    )
    assert result[0]["content"] == "from_json"


def test_load_history_file(tmp_path):
    f = tmp_path / "h.json"
    f.write_text(json.dumps(_HIST))
    result = _load_history(history_file=str(f))
    assert result[0]["content"] == "hi"


def test_load_history_none_returns_empty():
    assert _load_history() == []


def test_load_history_invalid_role_raises():
    with pytest.raises((ValueError, TypeError, KeyError)):
        _load_history(conversation_history=[{"content": "no role"}])
