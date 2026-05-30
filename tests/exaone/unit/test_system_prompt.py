import pytest
from datetime import datetime, timezone, timedelta

from exaone.system_prompt import compose_system_prompt, load_prompt_blocks, compose_tool_list_for_tools

_KST = timezone(timedelta(hours=9))


def test_load_prompt_blocks_reads_identity():
    blocks = load_prompt_blocks()
    assert "ChatEXAONE" in blocks["identity"]


def test_compose_tool_list_includes_tools():
    tool_list = compose_tool_list_for_tools(["web_search", "web_extract"], strict=True)
    assert "web_search" in tool_list
    assert "web_extract" in tool_list


def test_current_date_substituted_in_identity():
    blocks = load_prompt_blocks()
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    assert "{current_date}" not in blocks["identity"], "Placeholder was not substituted"
    assert today in blocks["identity"], f"Expected KST date {today} in identity"


def test_compose_system_prompt_skips_empty_blocks():
    blocks = {"identity": "ID", "tool_list": "", "style": None, "custom": "", "memory": "MEM"}
    result = compose_system_prompt(blocks)
    assert "ID" in result
    assert "MEM" in result
    assert "tool_list" not in result
    assert result == "ID\n\nMEM"


def test_compose_system_prompt_block_order():
    blocks = {"identity": "IDENT", "tool_list": "TOOLS", "style": "STYLE", "custom": "", "memory": ""}
    result = compose_system_prompt(blocks)
    assert result.index("IDENT") < result.index("TOOLS") < result.index("STYLE")


def test_compose_tool_list_for_tools_reads_descriptions():
    text = compose_tool_list_for_tools(["web_search", "echo"], strict=True)
    assert "# Available Tool list:" in text
    assert "web_search" in text
    assert "echo" in text


def test_compose_tool_list_for_tools_missing_raises_runtime_error():
    with pytest.raises(RuntimeError):
        compose_tool_list_for_tools(["missing_tool_name"], strict=True)


def test_load_prompt_blocks_strict_returns_expected_structure():
    blocks = load_prompt_blocks(identity_name="default", style_name="default", strict=True)
    assert isinstance(blocks["identity"], str) and blocks["identity"]
    assert set(blocks.keys()) >= {"identity", "style", "tool_list", "custom", "memory"}


def test_load_prompt_blocks_strict_missing_file_raises_runtime_error():
    with pytest.raises(RuntimeError):
        load_prompt_blocks(identity_name="nonexistent_file", strict=True)
