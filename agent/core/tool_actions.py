"""
Tool Action Types and Context

This module defines the tool action context and type constants used
for custom tool execution. Clients do not import this module - they
use duck typing instead.

Service Callables:
    ToolContext exposes service callables (call_llm, call_vl, record_training,
    search_documents) so that external custom tools can use pipeline services
    without importing internal modules.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Any, Optional


# Tool type constants (for duck typing validation)
TOOL_TYPE_SEARCH = "search"
TOOL_TYPE_INFERENCE = "inference"
VALID_TOOL_TYPES = {TOOL_TYPE_SEARCH, TOOL_TYPE_INFERENCE}


@dataclass
class ToolContext:
    """
    Context passed to tool execution.

    ┌──────────────────────────────────────────────────────────┐
    │ DESIGN INTENT: 커스텀 툴 확장 계약                        │
    │                                                          │
    │ Client는 이 context의 dict 변환(to_dict())을 통해        │
    │ 모든 파이프라인 서비스에 접근한다.                         │
    │ 어떤 internal import도 필요하지 않다.                     │
    │                                                          │
    │ 서비스 callable:                                         │
    │   context["call_llm"](messages, role, temperature, ...)  │
    │   context["call_vl"](messages, temperature, max_tokens)  │
    │   context["record_training"](task_type, conversations)   │
    │   context["search_documents"](query, doc_ids)            │
    │                                                          │
    │ 이 계약을 변경하면 모든 client 커스텀 툴이 깨진다.       │
    └──────────────────────────────────────────────────────────┘

    Attributes:
        user_query: The user's question
        filenames: List of document filenames
        multi_docs: Document pages data (List[List[Dict]])
        image_dir: Path to image directory (if available)
        language: Output language ('ko' or 'en')
        current_step: Current agent step number
        tool_secrets: Secret values for custom tools (e.g., API keys)

        # Built-in tools context (optional)
        model_router: ModelRouter instance for LLM calls
        selector_fn: Selector function for document search (legacy, use selector_client)
        selector_client: SelectorClient instance
        web_search_client: WebSearchClient instance
        train_sample: Training sample dict for recording
        reasoning: Current reasoning text (for search context)
        searched_indices: List of searched document indices (mutable, for side effects)
        search_pages: Global search result accumulator (mutable, shared)
        _extraction_sink: List for builtin tools to append extraction metadata
                          (thread-safe: created fresh per _execute_tool call)
    """
    user_query: str
    filenames: List[str]
    multi_docs: List[List[Dict[str, Any]]]
    image_dir: Optional[str]
    language: str
    current_step: int
    tool_secrets: Optional[Dict[str, Any]] = None

    # Built-in tools context
    model_router: Optional[Any] = None
    reasoning_client: Optional[Any] = None  # ProxyClient for reasoning model
    selector_fn: Optional[Callable] = None
    selector_client: Optional[Any] = None
    web_search_client: Optional[Any] = None
    train_sample: Optional[Dict[str, Any]] = None
    reasoning: Optional[str] = None
    searched_indices: Optional[List[int]] = None
    search_pages: Optional[List[Dict[str, Any]]] = None
    _extraction_sink: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for passing to client tools.

        Includes service callables (call_llm, call_vl, record_training,
        search_documents) so external tools can use pipeline services
        without importing internal modules.

        Returns:
            Dictionary with all context fields + service callables
        """
        result = {
            "user_query": self.user_query,
            "filenames": self.filenames,
            "multi_docs": self.multi_docs,
            "image_dir": self.image_dir,
            "language": self.language,
            "current_step": self.current_step,
            "tool_secrets": self.tool_secrets,
            # Built-in tools context
            "model_router": self.model_router,
            "selector_fn": self.selector_fn,
            "selector_client": self.selector_client,
            "web_search_client": self.web_search_client,
            "train_sample": self.train_sample,
            "reasoning": self.reasoning,
            "searched_indices": self.searched_indices,
            "search_pages": self.search_pages if self.search_pages is not None else [],
            "_extraction_sink": self._extraction_sink,
        }

        # Bind service callables
        result["call_llm"] = self._make_call_llm()
        result["call_vl"] = self._make_call_vl()
        result["record_training"] = self._make_record_training()
        result["search_documents"] = self._make_search_documents()

        return result

    def _make_call_llm(self) -> Callable:
        """Create a callable that wraps ModelRouter for LLM calls.

        Uses the reasoning client (configured by user's reasoner_api_key) so
        that custom tools always use the model+key the user specified.
        """
        reasoning_client = self.reasoning_client

        def call_llm(
            messages: List[Dict],
            role: str = "extraction",
            temperature: float = 0.2,
            max_tokens: int = 16384,
        ) -> str:
            """Call LLM via the reasoning client.

            Args:
                messages: OpenAI-format messages
                role: Ignored (kept for backward compat). Always uses reasoning client.
                temperature: Sampling temperature
                max_tokens: Max output tokens

            Returns:
                Model response text
            """
            if reasoning_client is None:
                return "[Error] reasoning_client not available in context"
            resp = reasoning_client.chat.completions.create(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content

        return call_llm

    def _make_call_vl(self) -> Callable:
        """Create a callable that wraps ModelRouter for VL (vision-language) calls."""
        router = self.model_router

        def call_vl(
            messages: List[Dict],
            temperature: float = 0.2,
            max_tokens: int = 2000,
        ) -> str:
            """Call VL model via pipeline's ModelRouter.

            Args:
                messages: OpenAI-format messages (can include image_url content)
                temperature: Sampling temperature
                max_tokens: Max output tokens

            Returns:
                Model response text
            """
            if router is None:
                return "[Error] model_router not available in context"
            client = router.get_proxy_client_for_vl()
            resp = client.chat.completions.create(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content

        return call_vl

    def _make_record_training(self) -> Callable:
        """Create a callable for recording training data."""
        train_sample = self.train_sample

        def record_training(
            task_type: str,
            conversations: List[Dict],
        ) -> None:
            """Record training data for a task.

            Args:
                task_type: Task category key (e.g., "readfulldocument", "readfulltext", custom)
                conversations: List of conversation turns
                    [{"role": "user", "content": ..., "loss_masking": True}, ...]
            """
            if train_sample is None:
                return
            # Initialize key if it doesn't exist
            if task_type not in train_sample:
                train_sample[task_type] = []
            train_sample[task_type].append(conversations)

        return record_training

    def _make_search_documents(self) -> Callable:
        """Create a callable for document search via SelectorClient."""
        selector_client = self.selector_client
        multi_docs = self.multi_docs
        filenames = self.filenames

        def search_documents(
            query: str,
            doc_ids: Optional[List[int]] = None,
        ) -> List[Dict]:
            """Search documents via SelectorClient.

            Args:
                query: Search query
                doc_ids: 1-indexed document numbers (default: all)

            Returns:
                List of page dicts [{Index, filename, page, content}, ...]
            """
            if selector_client is None:
                return []
            if doc_ids is None:
                doc_ids = list(range(1, len(multi_docs) + 1))

            results = []
            for doc_id in doc_ids:
                selected = selector_client.select_for_doc(
                    query=query,
                    reasoning="",
                    multi_docs=multi_docs,
                    doc_id=doc_id,
                    filenames=filenames,
                )
                results.extend(selected)
            return results

        return search_documents

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolContext":
        """
        Create ToolContext from a dictionary.

        Args:
            data: Dictionary with context fields

        Returns:
            ToolContext instance
        """
        return cls(
            user_query=data.get("user_query", ""),
            filenames=data.get("filenames", []),
            multi_docs=data.get("multi_docs", []),
            image_dir=data.get("image_dir"),
            language=data.get("language", "en"),
            current_step=data.get("current_step", 0),
            tool_secrets=data.get("tool_secrets"),
            # Built-in tools context
            model_router=data.get("model_router"),
            selector_fn=data.get("selector_fn"),
            selector_client=data.get("selector_client"),
            web_search_client=data.get("web_search_client"),
            train_sample=data.get("train_sample"),
            reasoning=data.get("reasoning"),
            searched_indices=data.get("searched_indices"),
            search_pages=data.get("search_pages"),
        )


def validate_tool_type(tool_type: str) -> bool:
    """
    Validate that a tool type is valid.

    Args:
        tool_type: The tool type string to validate

    Returns:
        True if valid, False otherwise
    """
    return tool_type in VALID_TOOL_TYPES
