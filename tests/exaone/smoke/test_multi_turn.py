"""
tests/exaone/smoke/test_multi_turn.py — Verify multi-turn conversation_history handling.

Runs two separate agent.run_conversation() calls and passes the first turn's
messages as conversation_history to the second, verifying context is preserved.

Run:
    pytest tests/exaone/smoke/test_multi_turn.py -m smoke -v
"""
import pytest

from exaone.config import bootstrap_gateway_env
from exaone.agent import ExaoneAgent


@pytest.mark.smoke
def test_multi_turn_conversation_history():
    bootstrap_gateway_env()

    agent = ExaoneAgent(qa_mode="general", reasoning=False, max_iterations=3)

    # 1st turn — provide information
    result1 = agent.run_conversation(
        user_message="내 이름은 테스트유저야. 기억해줘."
    )
    assert result1 is not None, "1st turn returned None"

    # Build minimal history from 1st turn
    history = [
        {"role": "user", "content": "내 이름은 테스트유저야. 기억해줘."},
        {"role": "assistant", "content": result1.get("final_response", "")},
    ]

    # 2nd turn — reference the information from 1st turn
    result2 = agent.run_conversation(
        user_message="내 이름이 뭐야?",
        conversation_history=history,
    )
    assert result2 is not None, "2nd turn returned None"

    response = result2.get("final_response", "")
    assert "테스트유저" in response, f"Name not recalled in response: {response}"

    # Verify history was threaded into the message list
    messages = result2.get("messages", [])
    contents = " ".join(m.get("content", "") or "" for m in messages if isinstance(m.get("content"), str))
    assert "내 이름은 테스트유저야" in contents, "conversation_history not found in result messages"
    assert "내 이름이 뭐야" in contents, "2nd turn user message not found in result messages"
