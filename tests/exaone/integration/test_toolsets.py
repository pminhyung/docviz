import json
from pathlib import Path

import pytest

from exaone.agent import ExaoneAgent
from exaone.batch_runner import _exaone_process_single_prompt

_JSONL = Path(__file__).parents[3] / "data/test_datasets/batch_runner_test.jsonl"
_ALL_CASES = [json.loads(line) for line in _JSONL.read_text().splitlines() if line.strip()]
_CONFIG = {"reasoning": False, "max_iterations": 5, "verbose": False}

_EXECUTE_CODE_PROMPT = Path(__file__).parents[3] / "exaone/prompts/tools/execute_code.txt"
_EXECUTE_CODE_JSONL_INDICES = {11, 12, 13}  # cases 12~14: execute_code 관련

_ec = pytest.mark.xdist_group("execute_code_cases")

@pytest.fixture()
def execute_code_prompt_file():
    _EXECUTE_CODE_PROMPT.write_text(
        "# Tool: execute_code\n\n- Executes Python code and returns stdout/stderr.\n",
        encoding="utf-8",
    )
    yield
    _EXECUTE_CODE_PROMPT.unlink(missing_ok=True)

# (idx_in_jsonl, expected_success, expected_tools)
_CASES = [
    (0,  True,  {"web_search", "web_extract", "code_tool"}),  # 1: no fields → general
    (1,  True,  {"web_search", "web_extract", "code_tool"}),  # 2: qa_mode=general
    (2,  True,  {"web_search", "web_extract"}),               # 3: toolset=web_tools
    (3,  True,  {"code_tool"}),                               # 4: toolset=code_tools
    (4,  True,  {"web_search"}),                              # 5: toolset=web_search
    (5,  True,  {"web_search", "web_extract", "code_tool"}),  # 6: toolset=[web_tools, code_tools]
    (6,  True,  {"web_search", "web_extract"}),               # 7: enabled_toolsets=web_tools
    (7,  True,  {"code_tool"}),                               # 8: enabled_toolsets=code_tools + qa_mode
    (8,  True,  {"code_tool"}),                               # 9: enabled_toolsets=code_tools + toolset
    (9,  True,  {"web_search", "doc_tool"}),                  # 10: enabled_toolsets=[web_search, doc_tool]
    (10, False, None),                                        # 11: qa_mode + toolset 동시 → 에러
    pytest.param(11, True,  {"execute_code"},               marks=_ec),  # 12
    pytest.param(12, True,  {"execute_code"},               marks=_ec),  # 13
    pytest.param(13, True,  {"execute_code", "web_search"}, marks=_ec),  # 14
]


@pytest.mark.integration
@pytest.mark.parametrize(
    "jsonl_idx,expected_success,expected_tools",
    _CASES,
    ids=[f"case{i + 1}" for i in range(len(_CASES))],
)
def test_toolset_case(jsonl_idx, expected_success, expected_tools, monkeypatch, request):
    if jsonl_idx in _EXECUTE_CODE_JSONL_INDICES:
        request.getfixturevalue("execute_code_prompt_file")

    prompt_data = _ALL_CASES[jsonl_idx]
    captured = {}

    original_run = ExaoneAgent.run_conversation

    def _capture(self, *args, **kwargs):
        captured["valid_tool_names"] = set(self.valid_tool_names)
        return original_run(self, *args, **kwargs)

    monkeypatch.setattr(ExaoneAgent, "run_conversation", _capture)

    result = _exaone_process_single_prompt(jsonl_idx, prompt_data, batch_num=1, config=_CONFIG)

    assert result["success"] is expected_success, f"success mismatch: {result.get('error')}"

    if expected_success:
        assert result["trajectory"], "trajectory should not be empty"
        assert captured["valid_tool_names"] == expected_tools, (
            f"expected tools {expected_tools}, got {captured.get('valid_tool_names')}"
        )
    else:
        assert "mutually exclusive" in result.get("error", "").lower()
