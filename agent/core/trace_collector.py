"""
Trace Collector

Collects step-by-step execution traces with redaction for secure export.
"""

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional


# Redaction placeholders
SYSTEM_PROMPT_REDACTED = "__SYSTEM_PROMPT_REDACTED__"
API_KEY_REDACTED = "[REDACTED]"
TOOL_ARGS_REDACTED = "__ARGS_REDACTED__"


@dataclass
class TraceStep:
    """A single step in the agent trace"""
    step_number: int
    step_type: str  # "tool_invoke", "final_answer", "doc_summary", etc.
    observation: Optional[str] = None
    reasoning: Optional[str] = None
    step_name: Optional[str] = None
    action: Optional[str] = None  # Tool name only
    action_args: Optional[Dict[str, Any]] = None  # Redacted in export
    action_result: Optional[str] = None  # Redacted in export
    final_answer: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: int = 0
    duration_seconds: float = 0.0
    timestamp: Optional[str] = None
    raw_response: Optional[str] = None  # Full LLM response, redacted in export

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self, redact: bool = True) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Args:
            redact: Whether to redact sensitive information

        Returns:
            Dictionary representation
        """
        result = {
            "step_number": self.step_number,
            "step_type": self.step_type,
            "observation": self.observation,
            "reasoning": self.reasoning,
            "step_name": self.step_name,
            "action": self.action,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
        }

        if self.final_answer:
            result["final_answer"] = self.final_answer

        if redact:
            # Redact action args and results
            if self.action_args:
                result["action_args"] = TOOL_ARGS_REDACTED
            if self.action_result:
                result["action_result"] = self._redact_content(self.action_result)
        else:
            result["action_args"] = self.action_args
            result["action_result"] = self.action_result
            result["raw_response"] = self.raw_response

        return result

    def _redact_content(self, content: str) -> str:
        """Redact sensitive content from action results"""
        if not content:
            return content

        # Truncate long content
        if len(content) > 1000:
            return content[:500] + "... [TRUNCATED] ..." + content[-200:]

        return content


@dataclass
class TraceSession:
    """Full session trace with metadata"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_query: str = ""
    filenames: List[str] = field(default_factory=list)
    language: str = "ENGLISH"
    steps: List[TraceStep] = field(default_factory=list)
    total_tokens: int = 0
    total_duration_seconds: float = 0.0
    success: bool = False
    error: Optional[str] = None
    inputs_used: List[Dict[str, Any]] = field(default_factory=list)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    prompt_pack_id: Optional[str] = None
    prompt_hash: Optional[str] = None
    override_hash: Optional[str] = None

    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now().isoformat()

    def add_step(self, step: TraceStep) -> None:
        """Add a step to the trace"""
        self.steps.append(step)
        self.total_tokens += step.tokens_used
        self.total_duration_seconds += step.duration_seconds

    def finish(self, success: bool = True, error: Optional[str] = None) -> None:
        """Mark the session as finished"""
        self.end_time = datetime.now().isoformat()
        self.success = success
        self.error = error

    def add_input(self, input_type: str, content: str, source: str = "") -> None:
        """
        Record an input fed to the model.

        Args:
            input_type: Type of input (e.g., "doc_search", "web_search", "user_turn")
            content: The input content (will be truncated for storage)
            source: Source of the input (e.g., filename, URL)
        """
        self.inputs_used.append({
            "type": input_type,
            "source": source,
            "content_preview": content[:500] if content else "",
            "content_length": len(content) if content else 0,
            "timestamp": datetime.now().isoformat(),
        })

    def to_dict(self, redact: bool = True) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Args:
            redact: Whether to redact sensitive information

        Returns:
            Dictionary representation
        """
        return {
            "session_id": self.session_id,
            "user_query": self.user_query,
            "filenames": self.filenames,
            "language": self.language,
            "steps": [step.to_dict(redact=redact) for step in self.steps],
            "total_tokens": self.total_tokens,
            "total_duration_seconds": self.total_duration_seconds,
            "num_steps": len(self.steps),
            "success": self.success,
            "error": self.error,
            "inputs_used": self.inputs_used if not redact else len(self.inputs_used),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "prompt_pack_id": self.prompt_pack_id,
            "prompt_hash": self.prompt_hash,
            "override_hash": self.override_hash,
        }


class TraceCollector:
    """
    Collects execution traces for agent sessions.

    Usage:
        collector = TraceCollector()
        session = collector.start_session(
            user_query="What is in the document?",
            filenames=["doc1.pdf"]
        )
        # ... agent execution ...
        step = collector.record_step(
            step_type="tool_invoke",
            observation="...",
            reasoning="...",
            action="search",
            action_args={"query": ["test"]},
            model_used="qwen3"
        )
        collector.finish_session()
    """

    def __init__(self, redact_by_default: bool = True):
        """
        Initialize the collector.

        Args:
            redact_by_default: Whether to redact traces by default
        """
        self.redact_by_default = redact_by_default
        self._current_session: Optional[TraceSession] = None
        self._step_counter = 0
        self._step_start_time: Optional[float] = None

    @property
    def current_session(self) -> Optional[TraceSession]:
        """Get the current session"""
        return self._current_session

    def start_session(
        self,
        user_query: str,
        filenames: List[str],
        language: str = "ENGLISH",
        prompt_pack_id: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        override_hash: Optional[str] = None,
    ) -> TraceSession:
        """
        Start a new trace session.

        Args:
            user_query: The user's query
            filenames: List of document filenames
            language: The language setting
            prompt_pack_id: The prompt pack ID
            prompt_hash: Hash of the runtime prompt
            override_hash: Hash of any patch override

        Returns:
            The new session
        """
        self._current_session = TraceSession(
            user_query=user_query,
            filenames=filenames,
            language=language,
            prompt_pack_id=prompt_pack_id,
            prompt_hash=prompt_hash,
            override_hash=override_hash,
        )
        self._step_counter = 0
        return self._current_session

    def start_step(self) -> None:
        """Mark the start of a step for timing"""
        self._step_start_time = time.time()

    def record_step(
        self,
        step_type: str,
        observation: Optional[str] = None,
        reasoning: Optional[str] = None,
        step_name: Optional[str] = None,
        action: Optional[str] = None,
        action_args: Optional[Dict[str, Any]] = None,
        action_result: Optional[str] = None,
        final_answer: Optional[str] = None,
        model_used: Optional[str] = None,
        tokens_used: int = 0,
        raw_response: Optional[str] = None,
    ) -> TraceStep:
        """
        Record a step in the trace.

        Args:
            step_type: Type of step
            observation: Observation text
            reasoning: Reasoning text
            step_name: Step name text
            action: Tool name (without args)
            action_args: Tool arguments (will be redacted)
            action_result: Tool result (will be redacted)
            final_answer: Final answer if this is the last step
            model_used: Model that generated this step
            tokens_used: Tokens used for this step
            raw_response: Raw LLM response

        Returns:
            The recorded step
        """
        if self._current_session is None:
            raise RuntimeError("No active session. Call start_session first.")

        self._step_counter += 1

        duration = 0.0
        if self._step_start_time:
            duration = time.time() - self._step_start_time
            self._step_start_time = None

        step = TraceStep(
            step_number=self._step_counter,
            step_type=step_type,
            observation=observation,
            reasoning=reasoning,
            step_name=step_name,
            action=action,
            action_args=action_args,
            action_result=action_result,
            final_answer=final_answer,
            model_used=model_used,
            tokens_used=tokens_used,
            duration_seconds=duration,
            raw_response=raw_response,
        )

        self._current_session.add_step(step)
        return step

    def record_input(
        self,
        input_type: str,
        content: str,
        source: str = ""
    ) -> None:
        """
        Record an input fed to the model.

        Args:
            input_type: Type of input
            content: The input content
            source: Source of the input
        """
        if self._current_session is None:
            raise RuntimeError("No active session. Call start_session first.")

        self._current_session.add_input(input_type, content, source)

    def finish_session(
        self,
        success: bool = True,
        error: Optional[str] = None
    ) -> TraceSession:
        """
        Finish the current session.

        Args:
            success: Whether the session succeeded
            error: Error message if failed

        Returns:
            The finished session
        """
        if self._current_session is None:
            raise RuntimeError("No active session.")

        self._current_session.finish(success=success, error=error)
        session = self._current_session
        self._current_session = None
        return session

    def export_session(
        self,
        session: Optional[TraceSession] = None,
        redact: bool = None
    ) -> Dict[str, Any]:
        """
        Export a session to dictionary.

        Args:
            session: Session to export (uses current if None)
            redact: Whether to redact (uses default if None)

        Returns:
            Dictionary representation
        """
        if session is None:
            session = self._current_session

        if session is None:
            raise RuntimeError("No session to export.")

        if redact is None:
            redact = self.redact_by_default

        return session.to_dict(redact=redact)


def redact_api_keys(text: str) -> str:
    """
    Redact API keys from text.

    Args:
        text: Text that may contain API keys

    Returns:
        Text with API keys redacted
    """
    if not text:
        return text

    # Common API key patterns
    patterns = [
        r"(sk-[a-zA-Z0-9]{20,})",  # OpenAI keys
        r"(tgp_v1_[a-zA-Z0-9]{20,})",  # Together keys
        r"(AIza[a-zA-Z0-9_-]{35})",  # Google API keys
        r"(Bearer\s+[a-zA-Z0-9_-]{20,})",  # Bearer tokens
        r"(api[_-]?key['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9_-]{20,})",  # Generic API keys
    ]

    result = text
    for pattern in patterns:
        result = re.sub(pattern, API_KEY_REDACTED, result, flags=re.IGNORECASE)

    return result


def redact_system_prompt(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Redact system prompts from message list.

    Args:
        messages: List of message dictionaries

    Returns:
        Messages with system prompts redacted
    """
    result = []
    for msg in messages:
        if msg.get("role") == "system":
            result.append({
                "role": "system",
                "content": SYSTEM_PROMPT_REDACTED,
            })
        else:
            result.append(msg.copy())
    return result
