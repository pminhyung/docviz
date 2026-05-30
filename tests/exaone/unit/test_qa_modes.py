import pytest

from exaone.qa_modes import QA_MODES, QaModeConfig, validate_qa_mode_prompt_files, validate_exclusive_modes, resolve_qa_mode


def test_validate_qa_mode_prompt_files_general_exists():
    config = validate_qa_mode_prompt_files("general")
    assert config.name == "general"
    assert "web_tools" in config.toolset


def test_validate_qa_mode_prompt_files_research_exists():
    config = validate_qa_mode_prompt_files("research")
    assert config.name == "research"
    assert "web_tools" in config.toolset


def test_validate_qa_mode_prompt_files_canvas_exists():
    config = validate_qa_mode_prompt_files("canvas")
    assert config.name == "canvas"


def test_validate_exclusive_modes_raises_when_both_set():
    with pytest.raises(ValueError):
        validate_exclusive_modes(toolset="web_tools", qa_mode="general")


def test_validate_exclusive_modes_allows_either_alone():
    validate_exclusive_modes(toolset="web_tools", qa_mode=None)
    validate_exclusive_modes(toolset=None, qa_mode="general")
    validate_exclusive_modes(toolset=None, qa_mode=None)


def test_resolve_qa_mode_known_returns_config():
    config = resolve_qa_mode("general")
    assert config.name == "general"
    assert config.identity_name == "default"


def test_resolve_qa_mode_unknown_raises_value_error():
    with pytest.raises(ValueError, match="Unknown qa_mode"):
        resolve_qa_mode("not_a_real_mode")


def test_resolve_qa_mode_empty_string_raises_value_error():
    with pytest.raises(ValueError):
        resolve_qa_mode("   ")


def test_validate_qa_mode_prompt_files_missing_raises_runtime_error(monkeypatch):
    monkeypatch.setitem(
        QA_MODES,
        "broken-mode",
        QaModeConfig(
            name="broken-mode",
            toolset=[],
            identity_name="missing_identity_file",
            style_name="missing_style_file",
        ),
    )
    with pytest.raises(RuntimeError):
        validate_qa_mode_prompt_files("broken-mode")
