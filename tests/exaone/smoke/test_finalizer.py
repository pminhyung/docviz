"""
tests/exaone/smoke/test_finalizer.py — Trigger _handle_max_iterations in ExaoneAgent.

Runs ExaoneAgent with max_iterations=2 so the iteration budget is exhausted,
causing _handle_max_iterations to fire and write auxiliary_finalizer.json.

Run:
    pytest tests/exaone/smoke/test_finalizer.py -m smoke -v
"""
import json

import pytest

from exaone.config import bootstrap_gateway_env
from exaone.agent import ExaoneAgent


@pytest.mark.smoke
def test_finalizer_writes_auxiliary_file():
    bootstrap_gateway_env()

    agent = ExaoneAgent(
        toolset="web_tools",
        reasoning=False,
        max_iterations=2,
    )

    # Requires 3+ separate web_search calls → hits iteration limit before finishing
    result = agent.run_conversation(
        user_message=(
            "다음 세 주제를 반드시 각각 별도의 web_search 호출로 검색해서 요약해줘: "
            "(1) LG AI Research (2) OpenAI (3) Anthropic. "
            "각 검색은 반드시 순서대로 하나씩 수행해."
        ),
    )

    assert result is not None, "run_conversation returned None"

    run_dir = agent._current_run_dir
    finalizer_path = run_dir / "auxiliary_finalizer.json"
    assert finalizer_path.exists(), f"auxiliary_finalizer.json not found at: {finalizer_path}"

    data = json.loads(finalizer_path.read_text())
    assert "conversations" in data
    assert "meta" in data
    assistant_msgs = [m for m in data["conversations"] if m["role"] == "assistant"]
    assert assistant_msgs, "no assistant message in finalizer conversations"
    assert assistant_msgs[-1]["content"], "finalizer assistant content is empty"
