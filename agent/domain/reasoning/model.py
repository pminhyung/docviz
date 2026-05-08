"""
Reasoning domain models — immutable value objects.

AgentResponse and ToolInvocation represent parsed LLM output.
No side effects, no I/O dependencies.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ToolInvocation:
    """A parsed tool invocation from <tool_invoke> JSON."""

    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResponse:
    """
    Parsed agent response — mirrors the dict returned by
    ``run_agent_v2.py:_parse_agent_response`` (L642-670).

    All fields are optional because the LLM may omit any tag.
    """

    observation: Optional[str] = None
    reasoning: Optional[str] = None
    step_name: Optional[str] = None
    tool_invoke: Optional[ToolInvocation] = None
    final_answer: Optional[str] = None
    raw: str = ""

    @property
    def has_final_answer(self) -> bool:
        return self.final_answer is not None

    @property
    def has_tool_invoke(self) -> bool:
        return self.tool_invoke is not None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to legacy dict format identical to
        ``_parse_agent_response`` output.

        Only includes keys whose values are not None, matching
        the original dict-building behaviour.
        """
        result: Dict[str, Any] = {}
        if self.observation is not None:
            result["observation"] = self.observation
        if self.reasoning is not None:
            result["reasoning"] = self.reasoning
        if self.step_name is not None:
            result["step_name"] = self.step_name
        if self.final_answer is not None:
            result["final_answer"] = self.final_answer
        if self.tool_invoke is not None:
            result["tool_invoke"] = {
                "name": self.tool_invoke.name,
                "arguments": self.tool_invoke.arguments,
            }
        return result
