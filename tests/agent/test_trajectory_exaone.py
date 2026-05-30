from unittest.mock import MagicMock

from run_agent import AIAgent


def test_convert_to_trajectory_sharegpt_format():
    agent = MagicMock()
    agent._format_tools_for_system_message.return_value = "[]"
    messages = [
        {"role": "user", "content": "LG AI Research에 대해 검색해줘"},
        {
            "role": "assistant",
            "content": "",
            "reasoning": "need search",
            "tool_calls": [
                {
                    "id": "pzn377",
                    "function": {"name": "web_search", "arguments": '{"query": "LG AI Research"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "pzn377",
            "name": "web_search",
            "content": '{"results": []}',
        },
        {"role": "assistant", "content": "답변", "reasoning": "done"},
    ]
    traj = AIAgent._convert_to_trajectory_format(
        agent, messages, "LG AI Research에 대해 검색해줘", True
    )
    assert traj[0]["from"] == "system"
    assert "value" in traj[0]
    assert traj[1] == {"from": "human", "value": "LG AI Research에 대해 검색해줘"}
    assert traj[2]["from"] == "gpt"
    assert "<tool_call>" in traj[2]["value"]
    assert traj[3]["from"] == "tool"
    assert "<tool_response>" in traj[3]["value"]
    assert traj[4]["from"] == "gpt"
    assert "답변" in traj[4]["value"]


def test_convert_to_trajectory_preserves_multiturn_user_order():
    agent = MagicMock()
    agent._format_tools_for_system_message.return_value = "[]"
    messages = [
        {"role": "user", "content": "첫 질문"},
        {"role": "assistant", "content": "첫 답변"},
        {"role": "user", "content": "마지막 질문"},
        {"role": "assistant", "content": "마지막 답변"},
    ]
    traj = AIAgent._convert_to_trajectory_format(
        agent, messages, "마지막 질문", True
    )
    human_turns = [item for item in traj if item.get("from") == "human"]
    assert [turn["value"] for turn in human_turns] == ["첫 질문", "마지막 질문"]
