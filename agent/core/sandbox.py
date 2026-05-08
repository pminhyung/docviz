"""
Sandbox Mode for Document Agent V2

Provides deterministic stub LLM responses for testing and demos
without requiring external API keys.

Enable via:
- Environment variable: DOC_AGENT_V2_SANDBOX=1
- Python: set_sandbox_mode(True)
"""

import os
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Global sandbox mode flag
_SANDBOX_MODE: bool = False


def is_sandbox_mode() -> bool:
    """Check if sandbox mode is enabled."""
    global _SANDBOX_MODE
    # Check environment variable first
    env_val = os.environ.get("DOC_AGENT_V2_SANDBOX", "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    return _SANDBOX_MODE


def set_sandbox_mode(enabled: bool) -> None:
    """Enable or disable sandbox mode programmatically."""
    global _SANDBOX_MODE
    _SANDBOX_MODE = enabled


@dataclass
class StubUsage:
    """Stub usage object mimicking OpenAI usage response"""
    prompt_tokens: int = 100
    completion_tokens: int = 150
    total_tokens: int = 250


@dataclass
class StubChoice:
    """Stub choice object mimicking OpenAI choice response"""
    index: int
    message: "StubMessage"
    finish_reason: str = "stop"


@dataclass
class StubMessage:
    """Stub message object mimicking OpenAI message response"""
    role: str
    content: str


@dataclass
class StubResponse:
    """Stub response object mimicking OpenAI chat completion response"""
    id: str = "sandbox-response-001"
    object: str = "chat.completion"
    created: int = 1700000000
    model: str = "sandbox-stub-model"
    choices: List[StubChoice] = None
    usage: StubUsage = None

    def __post_init__(self):
        if self.choices is None:
            self.choices = []
        if self.usage is None:
            self.usage = StubUsage()


class SandboxResponseGenerator:
    """
    Generates deterministic stub responses for sandbox mode.

    Response sequence:
    1. Document summary call -> Returns a summary
    2. First reasoning call -> Returns tool_invoke (search)
    3. Second reasoning call -> Returns final_answer with citation
    """

    # Deterministic stub responses
    DOC_SUMMARY_RESPONSE = """Based on the document overview, this document contains information about example topics for demonstration purposes.

Key sections include:
- Introduction to the main concepts
- Detailed explanations with examples
- Summary and conclusions

The document appears to be structured for educational purposes."""

    TOOL_INVOKE_RESPONSE = """<observation>
I have reviewed the document overview and understand the user's question. I need to search the document for relevant information.
</observation>

<reasoning>
To answer the user's question accurately, I should first search the document to find relevant sections. This will help me provide a well-informed answer with proper citations.
</reasoning>

<step_name>Searching document for relevant content</step_name>

<tool_invoke>
{"name": "search", "arguments": {"source": "doc", "query": ["main topic", "key information"], "document_number": [1]}}
</tool_invoke>"""

    FINAL_ANSWER_RESPONSE = """<observation>
The search results provide relevant information from the document that addresses the user's question.
</observation>

<reasoning>
Based on the document content I've reviewed, I can now provide a comprehensive answer. The document discusses example topics and contains structured information that I can reference.
</reasoning>

<step_name>Generating final answer</step_name>

<final_answer>
Based on my analysis of the document [1], here is the answer to your question:

The document primarily discusses example topics for demonstration purposes. Key points include:

1. **Main Topic**: The document serves as a demonstration of the document agent system capabilities [1].

2. **Structure**: The content is organized in a clear, accessible format suitable for testing and validation [1].

3. **Purpose**: This document is designed to validate the end-to-end pipeline including document loading, search, and answer generation [1].

The information is presented in a structured manner that allows for easy reference and citation.
</final_answer>"""

    def __init__(self):
        """Initialize the response generator."""
        self._call_count = 0
        self._total_tokens = 0

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> StubResponse:
        """
        Generate a deterministic stub response.

        Args:
            messages: The conversation messages
            **kwargs: Additional arguments (ignored in sandbox)

        Returns:
            StubResponse mimicking OpenAI response
        """
        self._call_count += 1

        # Determine which response to return based on context
        raw_content = messages[-1]["content"] if messages else ""
        if isinstance(raw_content, list):
            # VL multimodal: content is a list of parts, extract text only
            last_message = " ".join(
                part.get("text", "") for part in raw_content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        else:
            last_message = raw_content
        last_message_lower = last_message.lower()

        # Check if this is a document summary call (DOC_STEP_PROMPT patterns)
        doc_summary_patterns = [
            "retrieval-optimized summary",
            "what topics and subjects each document covers",
            "overview of documents",
            "your task is to write",
            "document covers",
        ]
        is_doc_summary = any(
            pattern in last_message_lower for pattern in doc_summary_patterns
        )

        # Check if this is after a tool result (action_result)
        has_action_result = "<action_result>" in last_message

        if is_doc_summary and not has_action_result:
            content = self.DOC_SUMMARY_RESPONSE
        elif has_action_result:
            content = self.FINAL_ANSWER_RESPONSE
        else:
            content = self.TOOL_INVOKE_RESPONSE

        # Create stub response
        usage = StubUsage(
            prompt_tokens=len(str(messages)) // 4,
            completion_tokens=len(content) // 4,
            total_tokens=len(str(messages)) // 4 + len(content) // 4
        )
        self._total_tokens += usage.total_tokens

        response = StubResponse(
            id=f"sandbox-{self._call_count:04d}",
            choices=[
                StubChoice(
                    index=0,
                    message=StubMessage(role="assistant", content=content)
                )
            ],
            usage=usage
        )

        return response

    @property
    def call_count(self) -> int:
        """Get total number of calls made."""
        return self._call_count

    @property
    def total_tokens(self) -> int:
        """Get total tokens used (stub count)."""
        return self._total_tokens

    def reset(self) -> None:
        """Reset call count and token tracking."""
        self._call_count = 0
        self._total_tokens = 0


class SandboxProxyClient:
    """
    Sandbox proxy client that provides stub responses.

    Drop-in replacement for ProxyClient in sandbox mode.
    """

    def __init__(self):
        """Initialize sandbox client."""
        self._generator = SandboxResponseGenerator()
        self.chat = _SandboxChatCompletions(self)

    def _complete(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> StubResponse:
        """Generate a stub completion."""
        return self._generator.generate_response(messages, **kwargs)

    @property
    def total_tokens(self) -> int:
        """Get total tokens used."""
        return self._generator.total_tokens

    @property
    def total_calls(self) -> int:
        """Get total API calls made."""
        return self._generator.call_count

    def reset_tracking(self) -> None:
        """Reset usage tracking."""
        self._generator.reset()


class _SandboxChatCompletions:
    """Chat completions interface for sandbox."""

    def __init__(self, client: SandboxProxyClient):
        self._client = client
        self.completions = self

    def create(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> StubResponse:
        """Create a stub chat completion."""
        return self._client._complete(messages, **kwargs)


# Stub search results for tool execution
SANDBOX_SEARCH_RESULTS = [
    {
        "Index": 1,
        "page": 1,
        "filename": "example_document.json",
        "content": "This is a sandbox document page containing example content. The main topic covers demonstration purposes and testing scenarios for the document agent system."
    },
    {
        "Index": 2,
        "page": 2,
        "filename": "example_document.json",
        "content": "Additional content from page 2. This section provides more details about the example topics and serves as reference material for citations."
    }
]


def get_sandbox_search_results() -> str:
    """Get deterministic search results for sandbox mode."""
    return json.dumps(SANDBOX_SEARCH_RESULTS, ensure_ascii=False)


SANDBOX_DOCUMENT_SUMMARY = """## Document Summary (Sandbox Mode)

The document contains example content structured for demonstration:

**Page 1**: Introduction and main topic overview
- Covers fundamental concepts
- Provides context for the demo

**Page 2**: Supporting details and examples
- Expands on main topics
- Contains reference material

This is a sandbox summary for testing the full pipeline without external API calls."""


def get_sandbox_document_extraction() -> str:
    """Get deterministic document extraction for sandbox mode."""
    return SANDBOX_DOCUMENT_SUMMARY
