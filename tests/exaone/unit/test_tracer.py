import json
from unittest.mock import MagicMock

from exaone.tracer import log_trace


def _result(**kwargs):
    return {
        "completed": True,
        "final_response": "답변",
        "messages": [
            {"role": "user", "content": "질문"},
            {"role": "assistant", "content": "답변"},
        ],
        "model": "test-model",
        "input_tokens": 10,
        "output_tokens": 5,
        "api_calls": 1,
        **kwargs,
    }


def test_save_raw_writes_file(tmp_path):
    log_trace(
        user_message="질문",
        result=_result(),
        tools=[],
        system_prompt="sys",
        session_id=None,
        trace_log_dir=tmp_path,
        run_dir=tmp_path,
        save_raw=True,
        save_trajectory=False,
    )
    f = tmp_path / "raw_run_result.json"
    assert f.exists()
    data = json.loads(f.read_text())
    assert data["user_query"] == "질문"
    assert data["meta"]["completed"] is True


def test_save_raw_false_skips_file(tmp_path):
    log_trace(
        user_message="질문",
        result=_result(),
        tools=[],
        system_prompt="sys",
        session_id=None,
        trace_log_dir=tmp_path,
        run_dir=tmp_path,
        save_raw=False,
        save_trajectory=False,
    )
    assert not (tmp_path / "raw_run_result.json").exists()


def test_save_trajectory_writes_file(tmp_path):
    agent = MagicMock()
    agent._convert_to_trajectory_format.return_value = [
        {"from": "human", "value": "질문"},
        {"from": "gpt", "value": "답변"},
    ]
    log_trace(
        user_message="질문",
        result=_result(),
        tools=[],
        system_prompt="sys",
        session_id=None,
        trace_log_dir=tmp_path,
        agent=agent,
        run_dir=tmp_path,
        save_raw=False,
        save_trajectory=True,
    )
    f = tmp_path / "trajectory.json"
    assert f.exists()
    data = json.loads(f.read_text())
    assert data["completed"] is True
    assert any(t["from"] == "human" for t in data["conversations"])


def test_save_trajectory_false_skips_file(tmp_path):
    agent = MagicMock()
    log_trace(
        user_message="질문",
        result=_result(),
        tools=[],
        system_prompt="sys",
        session_id=None,
        trace_log_dir=tmp_path,
        agent=agent,
        run_dir=tmp_path,
        save_raw=False,
        save_trajectory=False,
    )
    assert not (tmp_path / "trajectory.json").exists()


def test_save_raw_loop_error_when_not_completed(tmp_path):
    log_trace(
        user_message="질문",
        result={**_result(), "completed": False, "turn_exit_reason": "max_iterations"},
        tools=[],
        system_prompt="sys",
        session_id=None,
        trace_log_dir=tmp_path,
        run_dir=tmp_path,
        save_raw=True,
        save_trajectory=False,
    )
    data = json.loads((tmp_path / "raw_run_result.json").read_text())
    assert data["loop_error"] is not None
    assert data["loop_error"]["type"] == "incomplete"
    assert data["loop_error"]["message"] == "max_iterations"
    assert data["meta"]["completed"] is False


def test_save_raw_includes_system_blocks(tmp_path):
    blocks = {"identity": "ID", "tool_list": "TOOLS", "style": "", "custom": "", "memory": ""}
    log_trace(
        user_message="질문",
        result=_result(),
        tools=[],
        system_prompt="sys",
        system_blocks=blocks,
        session_id=None,
        trace_log_dir=tmp_path,
        run_dir=tmp_path,
        save_raw=True,
        save_trajectory=False,
    )
    data = json.loads((tmp_path / "raw_run_result.json").read_text())
    assert data["system_blocks"]["identity"] == "ID"
