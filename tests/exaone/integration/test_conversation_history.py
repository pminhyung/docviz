import json
from pathlib import Path

import pytest

from exaone.agent import ExaoneAgent
from exaone.batch_runner import _exaone_process_single_prompt

_JSONL = Path(__file__).parents[3] / "data/test_datasets/batch_runner_test.jsonl"
_ALL_CASES = [json.loads(line) for line in _JSONL.read_text().splitlines() if line.strip()]
_CONFIG = {"reasoning": False, "max_iterations": 5, "verbose": False}

_HISTORY_CASE_IDX = 14  # case 15: conversation_history 포함


@pytest.mark.integration
def test_conversation_history_passed_through(monkeypatch):
    prompt_data = _ALL_CASES[_HISTORY_CASE_IDX]
    captured = {}

    original_run = ExaoneAgent.run_conversation

    def _capture(self, *args, **kwargs):
        captured["conversation_history"] = kwargs.get("conversation_history") or []
        return original_run(self, *args, **kwargs)

    monkeypatch.setattr(ExaoneAgent, "run_conversation", _capture)

    result = _exaone_process_single_prompt(
        _HISTORY_CASE_IDX, prompt_data, batch_num=1, config=_CONFIG
    )

    assert result["success"] is True, f"unexpected failure: {result.get('error')}"
    assert result["trajectory"], "trajectory should not be empty"
    assert captured["conversation_history"] == prompt_data["conversation_history"]
