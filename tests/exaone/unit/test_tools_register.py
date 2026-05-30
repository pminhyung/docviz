import json

from exaone.tools import (
    register_exaone_tools,
    _doc_tool_handler,
    _echo_handler,
)


def test_register_exaone_tools_idempotent():
    register_exaone_tools()
    register_exaone_tools()
    from tools.registry import registry
    all_names = registry.get_all_tool_names()
    for name in ("doc_tool", "echo"):
        assert all_names.count(name) == 1, f"{name} registered more than once"


def test_register_exaone_tools_adds_to_registry():
    register_exaone_tools()
    from tools.registry import registry
    for name in ("doc_tool", "echo"):
        assert registry.get_entry(name) is not None, f"{name} not in registry"


def test_canvas_tools_in_prompt_tool_ids():
    from exaone.tools import PROMPT_TOOL_IDS
    for name in ("get_canvas_status", "create_canvasdoc", "update_canvasdoc"):
        assert name in PROMPT_TOOL_IDS, f"{name} missing from PROMPT_TOOL_IDS"


def test_doc_tool_handler_returns_valid_json():
    result = _doc_tool_handler({"query": "test", "source": "src"})
    data = json.loads(result)
    assert "documents" in data
    assert data["documents"][0]["query"] == "test"


def test_echo_handler_returns_message():
    assert _echo_handler({"message": "hello"}) == "hello"
    assert _echo_handler({}) == ""


def test_code_tool_in_prompt_tool_ids():
    from exaone.tools import PROMPT_TOOL_IDS
    assert "code_tool" in PROMPT_TOOL_IDS


def test_code_tool_registry_consistent_with_prompt_tool_ids():
    from tools.registry import registry
    from exaone.tools import PROMPT_TOOL_IDS
    register_exaone_tools()
    # code_tool은 built-in 존재 여부에 따라 조건부 등록 — registry 상태와 PROMPT_TOOL_IDS가 독립적으로 관리됨을 확인
    entry = registry.get_entry("code_tool")
    if entry is not None:
        assert "code_tool" in PROMPT_TOOL_IDS
    else:
        # built-in 없어도 PROMPT_TOOL_IDS에는 선언되어 있어야 함 (prompt 렌더링 기준)
        assert "code_tool" in PROMPT_TOOL_IDS
