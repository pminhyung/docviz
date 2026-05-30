import pytest
from unittest.mock import patch

from exaone.batch_runner import _resolve_prompt_and_history, _normalize_history_messages, _exaone_process_batch_worker


def test_prompt_only():
    prompt, history = _resolve_prompt_and_history({"prompt": "hello"})
    assert prompt == "hello"
    assert history == []


def test_prompt_with_history():
    hist = [{"role": "user", "content": "이전"}, {"role": "assistant", "content": "답변"}]
    prompt, history = _resolve_prompt_and_history({"prompt": "새 질문", "conversation_history": hist})
    assert prompt == "새 질문"
    assert len(history) == 2


def test_history_key_alias():
    hist = [{"role": "user", "content": "이전"}]
    prompt, history = _resolve_prompt_and_history({"prompt": "질문", "history": hist})
    assert prompt == "질문"
    assert history[0]["role"] == "user"


def test_history_without_prompt_raises():
    with pytest.raises(ValueError, match="prompt is required"):
        _resolve_prompt_and_history({"conversation_history": [{"role": "user", "content": "q"}]})


def test_empty_prompt_raises():
    with pytest.raises(ValueError, match="prompt is required"):
        _resolve_prompt_and_history({"prompt": "   "})


def test_messages_extracts_last_user_turn():
    messages = [
        {"role": "user", "content": "첫 질문"},
        {"role": "assistant", "content": "답변"},
        {"role": "user", "content": "마지막 질문"},
    ]
    prompt, history = _resolve_prompt_and_history({"messages": messages})
    assert prompt == "마지막 질문"
    assert len(history) == 2


def test_messages_prompt_overrides_last_user_content():
    messages = [{"role": "user", "content": "원래 질문"}]
    prompt, history = _resolve_prompt_and_history({"prompt": "덮어쓴 질문", "messages": messages})
    assert prompt == "덮어쓴 질문"


def test_messages_no_user_turn_raises():
    with pytest.raises(ValueError, match="at least one user turn"):
        _resolve_prompt_and_history({"messages": [{"role": "assistant", "content": "답변"}]})


def test_messages_empty_last_user_content_raises():
    with pytest.raises(ValueError, match="empty"):
        _resolve_prompt_and_history({"messages": [{"role": "user", "content": "  "}]})


# _normalize_history_messages

def test_normalize_none_returns_empty():
    assert _normalize_history_messages(None) == []


def test_normalize_empty_string_returns_empty():
    assert _normalize_history_messages("   ") == []


def test_normalize_json_string_parsed():
    raw = '[{"role": "user", "content": "hi"}]'
    result = _normalize_history_messages(raw)
    assert len(result) == 1
    assert result[0]["role"] == "user"


def test_normalize_list_passthrough():
    raw = [{"role": "assistant", "content": "hello"}]
    result = _normalize_history_messages(raw)
    assert result[0]["content"] == "hello"


def test_normalize_missing_content_defaults_to_empty_string():
    raw = [{"role": "user"}]
    result = _normalize_history_messages(raw)
    assert result[0]["content"] == ""


def test_normalize_non_list_raises():
    with pytest.raises(ValueError, match="list"):
        _normalize_history_messages({"role": "user", "content": "hi"})


def test_normalize_non_dict_entry_raises():
    with pytest.raises(ValueError, match="dicts"):
        _normalize_history_messages(["not a dict"])


def test_normalize_missing_role_raises():
    with pytest.raises(ValueError, match="role"):
        _normalize_history_messages([{"content": "hi"}])


# _exaone_process_batch_worker

def _fake_single_result(prompt_index, success=True):
    return {
        "success": success,
        "prompt_index": prompt_index,
        "trajectory": [{"from": "human", "value": "q"}, {"from": "gpt", "value": "a"}],
        "tool_stats": {"web_search": {"count": 1, "success": 1, "failure": 0}},
        "reasoning_stats": {"total_assistant_turns": 1, "turns_with_reasoning": 0, "turns_without_reasoning": 1},
        "completed": True,
        "partial": False,
        "api_calls": 1,
        "toolsets_used": ["general"],
        "metadata": {"batch_num": 1, "timestamp": "2026-01-01T00:00:00"},
    }


def test_worker_processes_single_prompt(tmp_path):
    config = {"reasoning": False, "max_iterations": 5, "verbose": False}
    batch_data = [(0, {"prompt": "안녕"})]

    with patch("exaone.batch_runner._exaone_process_single_prompt", side_effect=lambda idx, *_: _fake_single_result(idx)):
        result = _exaone_process_batch_worker((1, batch_data, str(tmp_path), set(), config))

    assert result["processed"] == 1
    assert result["skipped"] == 0
    assert result["tool_stats"]["web_search"]["count"] == 1
    output = list(tmp_path.glob("batch_1.jsonl"))
    assert len(output) == 1


def test_worker_skips_completed_prompts(tmp_path):
    config = {"reasoning": False, "max_iterations": 5, "verbose": False}
    batch_data = [(0, {"prompt": "이미완료"})]

    with patch("exaone.batch_runner._exaone_process_single_prompt") as mock_fn:
        result = _exaone_process_batch_worker((1, batch_data, str(tmp_path), {0}, config))

    mock_fn.assert_not_called()
    assert result["processed"] == 0
    assert result["skipped"] == 1
