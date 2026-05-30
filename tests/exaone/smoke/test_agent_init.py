import pytest

from exaone.config import bootstrap_gateway_env
from exaone.agent import ExaoneAgent


@pytest.mark.smoke
def test_run_conversation_qa_mode_general():
    bootstrap_gateway_env()

    agent = ExaoneAgent(qa_mode="general", reasoning=False, max_iterations=3)
    result = agent.run_conversation(user_message="1 + 1은 얼마야?")

    assert result is not None
    assert result.get("final_response"), "final_response should not be empty"


@pytest.mark.smoke
def test_run_conversation_toolset_web_tools():
    bootstrap_gateway_env()

    agent = ExaoneAgent(toolset="web_tools", reasoning=False, max_iterations=3)
    result = agent.run_conversation(user_message="안녕, 간단히 인사해줘.")

    assert result is not None
    assert result.get("final_response"), "final_response should not be empty"
