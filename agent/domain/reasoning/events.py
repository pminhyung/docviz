"""
Domain events for the reasoning loop.

Defined here for Phase 1; wired into the agent loop in Phase 3.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class DocSummaryCompleted:
    """Emitted after the document summary step finishes."""

    prompt: str
    summary: str


@dataclass(frozen=True)
class StepCompleted:
    """Emitted after each reasoning step in the agent loop."""

    action_state: List[Dict[str, Any]]
    response: str
    step_number: int


@dataclass(frozen=True)
class ToolExtractionCompleted:
    """Emitted after a tool (ReadFullDocument / ReadFullText) finishes."""

    tool_name: str
    messages: List[Dict[str, Any]]
    result: str
