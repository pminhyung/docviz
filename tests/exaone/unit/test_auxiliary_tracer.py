import json

import pytest

from exaone.auxiliary_tracer import (
    _serialize_messages,
    _write,
    _write_compression,
    bind_run,
    unbind_run,
    write_compression_log,
    write_web_extract_log,
)


# --- _serialize_messages ---


def test_serialize_plain_messages():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    out = _serialize_messages(msgs)
    assert out == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_serialize_assistant_with_tool_calls():
    msgs = [
        {
            "role": "assistant",
            "content": "thinking",
            "tool_calls": [
                {"function": {"name": "web_search", "arguments": '{"query": "foo"}'}}
            ],
        }
    ]
    out = _serialize_messages(msgs)
    assert out[0]["role"] == "assistant"
    assert "<think>" in out[0]["content"]
    assert "<tool_call>" in out[0]["content"]
    assert '"name": "web_search"' in out[0]["content"]


def test_serialize_tool_role():
    msgs = [
        {
            "role": "tool",
            "tool_call_id": "abc",
            "name": "web_search",
            "content": '{"results": []}',
        }
    ]
    out = _serialize_messages(msgs)
    assert out[0]["role"] == "tool"
    assert "<tool_response>" in out[0]["content"]
    assert "web_search" in out[0]["content"]


def test_serialize_list_content():
    msgs = [{"role": "user", "content": [{"text": "part1"}, {"text": "part2"}]}]
    out = _serialize_messages(msgs)
    assert out[0]["content"] == "part1\npart2"


def test_serialize_assistant_no_tool_calls():
    msgs = [{"role": "assistant", "content": "done", "tool_calls": []}]
    out = _serialize_messages(msgs)
    assert out[0]["content"] == "done"
    assert "<think>" not in out[0]["content"]


# --- _write ---


def test_write_creates_json_file(tmp_path):
    _write(tmp_path, "out.json", {"id": "", "conversations": []})
    f = tmp_path / "out.json"
    assert f.exists()
    data = json.loads(f.read_text())
    assert data["conversations"] == []


# --- _write_compression ---


def test_write_compression_creates_indexed_file(tmp_path):
    _write_compression(tmp_path, 3, "user_p", "asst_p", {"foo": "bar"})
    f = tmp_path / "auxiliary_compression_3.json"
    assert f.exists()
    data = json.loads(f.read_text())
    assert data["conversations"][0] == {"role": "user", "content": "user_p"}
    assert data["conversations"][1] == {"role": "assistant", "content": "asst_p"}
    assert data["meta"]["foo"] == "bar"


# --- write_compression_log / write_web_extract_log ---


def test_write_compression_log_noop_without_run_dir():
    write_compression_log(1, "u", "a", {})  # should not raise


def test_write_web_extract_log_with_run_dir(tmp_path):
    from exaone.compaction_tracer import _CURRENT_RUN_DIR

    tok = _CURRENT_RUN_DIR.set(tmp_path)
    try:
        write_web_extract_log(1, "sys", "usr", "asst", {"url": "http://x"})
        assert (tmp_path / "auxiliary_web_extract_1.json").exists()
    finally:
        _CURRENT_RUN_DIR.reset(tok)


# --- bind_run / unbind_run ---


def test_bind_sets_hook_unbind_resets(tmp_path):
    from tools.web_tools import _WEB_EXTRACT_LOG_HOOK

    assert _WEB_EXTRACT_LOG_HOOK.get() is None
    tokens = bind_run(tmp_path)
    assert _WEB_EXTRACT_LOG_HOOK.get() is not None
    unbind_run(tokens)
    assert _WEB_EXTRACT_LOG_HOOK.get() is None


def test_web_extract_hook_counter_increments(tmp_path):
    from exaone.compaction_tracer import _CURRENT_RUN_DIR
    from tools.web_tools import _WEB_EXTRACT_LOG_HOOK

    tok_dir = _CURRENT_RUN_DIR.set(tmp_path)
    tokens = bind_run(tmp_path)
    hook = _WEB_EXTRACT_LOG_HOOK.get()
    hook("http://a", "raw1", "sys", "usr", "sum1")
    hook("http://b", "raw2", "sys", "usr", "sum2")
    unbind_run(tokens)
    _CURRENT_RUN_DIR.reset(tok_dir)
    assert (tmp_path / "auxiliary_web_extract_1.json").exists()
    assert (tmp_path / "auxiliary_web_extract_2.json").exists()
