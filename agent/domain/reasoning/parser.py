"""
Stateless response parser — pure function, zero dependencies.

Exact replica of ``run_agent_v2.py:_parse_agent_response`` (L642-670)
expressed as a free function returning an ``AgentResponse`` dataclass.
"""

import json
from typing import Optional

from .model import AgentResponse, ToolInvocation


def _extract_tag(response: str, tag: str) -> Optional[str]:
    """
    Extract text between ``<tag>`` and ``</tag>`` using str.split().

    Returns ``None`` when either the open or close tag is missing,
    exactly matching the original ``if ... in response`` guards.
    """
    open_tag = f"<{tag}>"
    close_tag = f"</{tag}>"
    if open_tag not in response or close_tag not in response:
        return None
    return response.split(open_tag)[1].split(close_tag)[0].strip()


def _parse_tool_invoke(response: str) -> Optional[ToolInvocation]:
    """
    Parse ``<tool_invoke>`` JSON block.

    Returns ``None`` on missing tags or malformed JSON, matching the
    original try/except JSONDecodeError path.
    """
    open_tag = "<tool_invoke>"
    close_tag = "</tool_invoke>"
    if open_tag not in response or close_tag not in response:
        return None
    try:
        tool_json = response.split(open_tag)[1].split(close_tag)[0].strip()
        data = json.loads(tool_json)
        return ToolInvocation(
            name=data.get("name", ""),
            arguments=data.get("arguments", {}),
        )
    except (json.JSONDecodeError, AttributeError):
        print("[Warning] Failed to parse tool_invoke JSON")
        return None


def parse_agent_response(response: str) -> AgentResponse:
    """
    Parse an LLM response string into an ``AgentResponse``.

    This is a pure-function equivalent of
    ``AgentV2Runner._parse_agent_response`` (L642-670).
    The ``to_dict()`` method on the returned object produces
    an identical dict to the original implementation.
    """
    return AgentResponse(
        observation=_extract_tag(response, "observation"),
        reasoning=_extract_tag(response, "reasoning"),
        step_name=_extract_tag(response, "step_name"),
        tool_invoke=_parse_tool_invoke(response),
        final_answer=_extract_tag(response, "final_answer"),
        raw=response,
    )
