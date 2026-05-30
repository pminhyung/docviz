"""
tests/exaone/smoke/test_web_extract.py — Verify auxiliary_web_extract_*.json is written.

Runs a query that forces the agent to call web_extract at least once
and checks that the log file is created in the run directory.

Run:
    pytest tests/exaone/smoke/test_web_extract.py -m smoke -v
"""
import json
from unittest.mock import patch

import pytest

from exaone.config import bootstrap_gateway_env
from exaone.agent import ExaoneAgent


@pytest.mark.smoke
def test_web_extract_log_is_written():
    bootstrap_gateway_env()

    agent = ExaoneAgent(toolset="web_tools", reasoning=False, max_iterations=3)
    # Lower the passthrough threshold to 1 so any extracted content triggers summarization.
    with patch("tools.web_tools.RAW_PASSTHROUGH_CHARS", 1):
        result = agent.run_conversation(
            user_message="LG AI Research 공식 홈페이지 URL을 찾아서 내용을 web_extract로 추출해줘."
        )

    assert result is not None, "run_conversation returned None"

    run_dir = agent._current_run_dir
    files = sorted(run_dir.glob("auxiliary_web_extract_*.json"))
    assert len(files) >= 1, f"auxiliary_web_extract_*.json not found in {run_dir}"

    data = json.loads(files[0].read_text())
    assert "conversations" in data
    assert "meta" in data
    assert "url" in data["meta"], "meta.url missing from web_extract log"
    roles = [m["role"] for m in data["conversations"]]
    assert "system" in roles
    assert "user" in roles
    assert "assistant" in roles
    assistant_content = next(m["content"] for m in data["conversations"] if m["role"] == "assistant")
    assert assistant_content, "web_extract summary (assistant content) is empty"
