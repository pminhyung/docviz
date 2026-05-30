"""
tests/exaone/smoke/test_compression.py — Trigger context compression (~2 rounds) in ExaoneAgent.

Builds a synthetic history large enough to exceed the threshold, then patches
the compressor so the preflight loop compresses twice before dropping below
the threshold.

Run:
    pytest tests/exaone/smoke/test_compression.py -m smoke -v
"""
import json

import pytest

from exaone.config import bootstrap_gateway_env
from exaone.agent import ExaoneAgent

_LOREM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris. "
    "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum. "
    "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia. "
)


@pytest.mark.smoke
def test_compression_writes_auxiliary_files():
    bootstrap_gateway_env()

    agent = ExaoneAgent(qa_mode="general", reasoning=False)

    cc = agent.context_compressor
    assert cc is not None, "context_compressor not found"

    # Low threshold so preflight fires; protect_last_n=5 so ~7 messages remain
    # after first pass, still exceeding threshold → second pass fires.
    cc.threshold_tokens = 200
    cc.protect_first_n = 1
    cc.protect_last_n = 5

    # 15 turns = 30 messages → well above preflight guard (protect_first+last+1=7)
    history = []
    for i in range(15):
        history.append({"role": "user", "content": f"[turn {i+1}] {_LOREM * 4}"})
        history.append({"role": "assistant", "content": f"[turn {i+1} reply] {_LOREM * 4}"})

    result = agent.run_conversation(
        user_message="위의 대화를 한 문장으로 요약해줘.",
        conversation_history=history,
    )

    assert result is not None, "run_conversation returned None"
    assert agent._compaction_count >= 1, "No compression occurred"

    run_dir = agent._current_run_dir
    files = sorted(run_dir.glob("auxiliary_compression_*.json"))
    assert len(files) >= 1, f"auxiliary_compression_*.json not found in {run_dir}"

    data = json.loads(files[0].read_text())
    assert "conversations" in data
    assert "meta" in data
    roles = [m["role"] for m in data["conversations"]]
    assert roles == ["user", "assistant"], f"unexpected roles: {roles}"
    assert all(m["content"] for m in data["conversations"]), "compression conversation has empty content"
