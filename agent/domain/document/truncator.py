"""
Document truncation — pure function with pluggable token counting.

Exact replica of ``run_agent_v2.py:_truncate_documents`` (L616-640).
"""

from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class TokenCounter(Protocol):
    """Strategy for counting tokens/characters in text."""

    def count(self, text: str) -> int: ...


class CharacterCounter:
    """Default counter — ``len()`` based, matching original behaviour."""

    def count(self, text: str) -> int:
        return len(text)


def truncate_documents(
    multi_docs: List[List[Dict[str, Any]]],
    max_length: int = 80000,
    counter: TokenCounter = None,
) -> str:
    """
    Truncate documents for summary input.

    Exact replica of ``AgentV2Runner._truncate_documents`` (L616-640).
    The ``counter`` parameter is an extension point — defaults to
    ``CharacterCounter`` (``len()``), preserving original behaviour.

    Break semantics: inner loop breaks on budget exhaustion,
    outer loop continues to next document.
    """
    if counter is None:
        counter = CharacterCounter()

    parts: List[str] = []
    current_length = 0

    for doc_idx, pages in enumerate(multi_docs):
        for page in pages:
            content = page.get("content", "")
            page_num = page.get("page", "?")
            chunk = f"[Doc{doc_idx + 1} Page{page_num}] {content}"

            if current_length + counter.count(chunk) > max_length:
                remaining = max_length - current_length
                if remaining > 100:
                    parts.append(chunk[:remaining] + "...")
                break

            parts.append(chunk)
            current_length += counter.count(chunk)

    return "\n\n".join(parts)
