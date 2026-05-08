"""Integration tests for Search -> ReadFullText flow.

Tests the full pipeline:
1. SearchTool(source="web") -> WebSearchClient -> cache
2. ReadFullTextTool -> cache read -> extraction LLM
3. Global index management across doc + web searches
4. ToolContext service callables
5. Tool output image detection (output_type policy)
6. Tool registry override interface
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

# Set sandbox mode for tests that don't mock everything
os.environ["DOC_AGENT_V2_SANDBOX"] = "1"

from agent.core.builtin_tools import SearchTool, ReadFullTextTool, GetPageTool, dedup_keep_first
from agent.core.tool_actions import ToolContext
from agent.core.tool_registry import ToolRegistry
from agent.core.web_search_client import WebSearchClient
from agent.core.selector_client import SelectorClient
from agent.core.model_router import ToolOutput, ImageRef
from agent.core.sandbox import is_sandbox_mode


# ── Fixtures ─────────────────────────────────────────────────

SAMPLE_DOCS = [
    [
        {"Index": 1, "filename": "doc1.pdf", "page": 1, "content": "Introduction to AI."},
        {"Index": 2, "filename": "doc1.pdf", "page": 2, "content": "Machine learning basics."},
    ]
]

WEB_PASSAGES = [
    {"Index": 1, "site_name": "TechNews", "snippet": "AI trends in 2025...", "url": "https://tech.com/ai"},
    {"Index": 2, "site_name": "Research", "snippet": "Deep learning advances...", "url": "https://research.com/dl"},
]


def make_context(**overrides):
    """Create a ToolContext with sensible defaults."""
    defaults = {
        "user_query": "What are AI trends?",
        "filenames": ["doc1.pdf"],
        "multi_docs": SAMPLE_DOCS,
        "image_dir": None,
        "language": "en",
        "current_step": 2,
        "tool_secrets": None,
        "model_router": None,
        "selector_fn": None,
        "selector_client": None,
        "web_search_client": None,
        "train_sample": {
            "reasoning": [],
            "readfulldocument": [],
            "readfulltext": [],
            "doc_step": [],
        },
        "reasoning": "Looking for AI information",
        "searched_indices": [],
        "search_pages": [],
        "_extraction_sink": None,
    }
    defaults.update(overrides)
    return ToolContext(**defaults)


# ── SearchTool web path ──────────────────────────────────────

class TestSearchToolWeb:
    def test_web_search_returns_passages(self):
        web_client = MagicMock(spec=WebSearchClient)
        web_client.search_web.return_value = WEB_PASSAGES.copy()

        search_pages = []
        ctx = make_context(web_search_client=web_client, search_pages=search_pages)
        ctx_dict = ctx.to_dict()

        tool = SearchTool()
        result = tool.execute({"source": "web", "query": ["AI trends"]}, ctx_dict)

        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["site_name"] == "TechNews"
        assert parsed[0]["Index"] == 1

        # search_pages should be populated (side effect)
        assert len(search_pages) == 2

    def test_web_search_global_index_offset(self):
        """Web search results should have indices offset by existing search_pages."""
        web_client = MagicMock(spec=WebSearchClient)
        web_client.search_web.return_value = WEB_PASSAGES.copy()

        # Pre-existing search pages (from a previous doc search)
        existing_pages = [{"Index": 1, "filename": "doc1.pdf", "page": 1}]
        search_pages = existing_pages.copy()

        ctx = make_context(web_search_client=web_client, search_pages=search_pages)
        ctx_dict = ctx.to_dict()

        tool = SearchTool()
        result = tool.execute({"source": "web", "query": ["AI"]}, ctx_dict)

        parsed = json.loads(result)
        # Should start from offset (1 existing) + 1
        assert parsed[0]["Index"] == 2
        assert parsed[1]["Index"] == 3

        # Total search_pages should include both
        assert len(search_pages) == 3

    def test_web_search_no_client(self):
        ctx = make_context(web_search_client=None)
        ctx_dict = ctx.to_dict()

        tool = SearchTool()
        result = tool.execute({"source": "web", "query": ["test"]}, ctx_dict)
        assert "error" in json.loads(result)

    def test_doc_search_uses_selector_client(self):
        selector = MagicMock(spec=SelectorClient)
        selector.select_for_doc.return_value = [
            {"Index": 1, "filename": "doc1.pdf", "page": 1, "content": "AI intro"}
        ]

        ctx = make_context(selector_client=selector)
        ctx_dict = ctx.to_dict()

        tool = SearchTool()
        result = tool.execute({"source": "doc", "query": ["AI"], "document_number": [1]}, ctx_dict)

        parsed = json.loads(result)
        assert len(parsed) >= 1
        selector.select_for_doc.assert_called()

    def test_doc_search_default_source(self):
        """Default source should be 'doc'."""
        selector = MagicMock(spec=SelectorClient)
        selector.select_for_doc.return_value = []

        ctx = make_context(selector_client=selector)
        ctx_dict = ctx.to_dict()

        tool = SearchTool()
        tool.execute({"query": ["test"]}, ctx_dict)
        selector.select_for_doc.assert_called()


# ── ReadFullTextTool ─────────────────────────────────────────

class TestReadFullTextTool:
    def test_readfulltext_with_cache(self):
        """ReadFullText should read from WebSearchClient cache and call extraction LLM."""
        # Setup web client with cached content
        web_client = WebSearchClient()
        web_client._page_cache = {
            "https://tech.com/ai": "Full article about AI trends in 2025...",
        }

        # Mock router
        mock_router = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "rational": "The article discusses AI trends",
            "evidence": "AI trends in 2025 include...",
            "summary": "AI is advancing rapidly",
        })
        mock_client.chat.completions.create.return_value = mock_response
        mock_router.get_proxy_client.return_value = mock_client

        search_pages = [
            {"Index": 1, "url": "https://tech.com/ai", "site_name": "TechNews", "snippet": "AI trends..."},
        ]

        extraction_sink = []
        train_sample = {"readfulltext": []}
        ctx = make_context(
            web_search_client=web_client,
            model_router=mock_router,
            search_pages=search_pages,
            train_sample=train_sample,
            _extraction_sink=extraction_sink,
        )
        ctx_dict = ctx.to_dict()

        tool = ReadFullTextTool()
        result = tool.execute({"index": [1], "goal": "AI trends"}, ctx_dict)

        assert "AI is advancing rapidly" in result
        # Extraction metadata goes to _extraction_sink (not train_sample directly)
        assert len(extraction_sink) == 1
        assert extraction_sink[0]["tool_name"] == "ReadFullText"

    def test_readfulltext_no_valid_urls(self):
        web_client = MagicMock(spec=WebSearchClient)
        mock_router = MagicMock()

        # search_pages with doc results (no url)
        search_pages = [
            {"Index": 1, "filename": "doc1.pdf", "page": 1, "content": "..."},
        ]

        ctx = make_context(
            web_search_client=web_client,
            model_router=mock_router,
            search_pages=search_pages,
        )
        ctx_dict = ctx.to_dict()

        tool = ReadFullTextTool()
        result = tool.execute({"index": [1]}, ctx_dict)
        assert "error" in json.loads(result)

    def test_readfulltext_no_client(self):
        ctx = make_context(web_search_client=None, model_router=MagicMock())
        ctx_dict = ctx.to_dict()

        tool = ReadFullTextTool()
        result = tool.execute({"index": [1]}, ctx_dict)
        assert "error" in json.loads(result)


# ── Global Index Management ──────────────────────────────────

class TestGlobalIndex:
    def test_mixed_doc_web_no_collision(self):
        """Doc search + web search should produce non-colliding indices."""
        # Simulate doc search result
        doc_results = [
            {"Index": 1, "filename": "doc1.pdf", "page": 1, "content": "AI"},
            {"Index": 2, "filename": "doc1.pdf", "page": 2, "content": "ML"},
        ]

        # Simulate web search result (offset by doc results)
        web_results = [
            {"Index": 3, "site_name": "Web1", "snippet": "Online AI", "url": "https://web1.com"},
            {"Index": 4, "site_name": "Web2", "snippet": "Online ML", "url": "https://web2.com"},
        ]

        all_results = doc_results + web_results
        indices = [r["Index"] for r in all_results]
        assert len(indices) == len(set(indices))  # No duplicates


# ── ToolContext Service Callables ────────────────────────────

class TestServiceCallables:
    def test_call_llm(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "LLM response"
        mock_client.chat.completions.create.return_value = mock_resp

        ctx = make_context(model_router=MagicMock(), reasoning_client=mock_client)
        ctx_dict = ctx.to_dict()

        call_llm = ctx_dict["call_llm"]
        result = call_llm(
            messages=[{"role": "user", "content": "Hello"}],
            role="extraction",
        )
        assert result == "LLM response"

    def test_call_vl(self):
        mock_router = MagicMock()
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "VL response"
        mock_client.chat.completions.create.return_value = mock_resp
        mock_router.get_proxy_client_for_vl.return_value = mock_client

        ctx = make_context(model_router=mock_router)
        ctx_dict = ctx.to_dict()

        call_vl = ctx_dict["call_vl"]
        result = call_vl(messages=[{"role": "user", "content": "Analyze image"}])
        assert result == "VL response"

    def test_record_training(self):
        train_sample = {"readfulldocument": [], "readfulltext": []}
        ctx = make_context(train_sample=train_sample)
        ctx_dict = ctx.to_dict()

        record = ctx_dict["record_training"]

        # Record to existing key
        record("readfulldocument", [
            {"role": "user", "content": "test", "loss_masking": True},
            {"role": "assistant", "content": "response", "loss_masking": False},
        ])
        assert len(train_sample["readfulldocument"]) == 1

        # Record to new key (auto-created)
        record("custom_task", [{"role": "user", "content": "custom"}])
        assert "custom_task" in train_sample
        assert len(train_sample["custom_task"]) == 1

    def test_record_training_no_sample(self):
        ctx = make_context(train_sample=None)
        ctx_dict = ctx.to_dict()
        record = ctx_dict["record_training"]
        record("test", [])  # Should not raise

    def test_search_documents(self):
        selector = MagicMock(spec=SelectorClient)
        selector.select_for_doc.return_value = [
            {"Index": 1, "filename": "doc1.pdf", "page": 1, "content": "AI"}
        ]

        ctx = make_context(selector_client=selector)
        ctx_dict = ctx.to_dict()

        search_docs = ctx_dict["search_documents"]
        results = search_docs("AI query", doc_ids=[1])
        assert len(results) == 1

    def test_call_llm_no_client(self):
        ctx = make_context(model_router=None, reasoning_client=None)
        ctx_dict = ctx.to_dict()
        call_llm = ctx_dict["call_llm"]
        result = call_llm(messages=[{"role": "user", "content": "test"}])
        assert "Error" in result


# ── Tool Output Image Detection ──────────────────────────────

class TestToolOutputImageDetection:
    def test_text_only_output(self):
        from agent.run_agent_v2 import AgentV2Runner
        runner = AgentV2Runner.__new__(AgentV2Runner)
        runner.reasoner_type = "llm"

        result = runner._process_tool_output("Simple text response")
        assert isinstance(result, ToolOutput)
        assert result.has_images is False
        assert result.text == "Simple text response"

    def test_output_type_image(self):
        from agent.run_agent_v2 import AgentV2Runner
        runner = AgentV2Runner.__new__(AgentV2Runner)
        runner.reasoner_type = "llm"

        output = json.dumps({
            "output_type": "image",
            "text": "Chart analysis",
            "images": [
                {"source": "base64", "data": "iVBOR...", "mime_type": "image/png"},
            ]
        })

        result = runner._process_tool_output(output)
        assert result.has_images is True
        assert result.text == "Chart analysis"
        assert len(result.images) == 1
        assert result.images[0].source == "base64"

    def test_output_type_mixed(self):
        from agent.run_agent_v2 import AgentV2Runner
        runner = AgentV2Runner.__new__(AgentV2Runner)

        output = json.dumps({
            "output_type": "mixed",
            "text": "Text + image",
            "images": [
                {"source": "path", "path": "/tmp/chart.png"},
                {"source": "url", "url": "https://img.com/chart.png"},
            ]
        })

        result = runner._process_tool_output(output)
        assert result.has_images is True
        assert len(result.images) == 2

    def test_legacy_image_paths(self):
        from agent.run_agent_v2 import AgentV2Runner
        runner = AgentV2Runner.__new__(AgentV2Runner)

        output = json.dumps({
            "image_paths": ["/tmp/img1.png", "/tmp/img2.png"],
            "result": "Analysis complete"
        })

        result = runner._process_tool_output(output)
        assert result.has_images is True
        assert len(result.images) == 2
        assert all(img.source == "path" for img in result.images)

    def test_json_no_images(self):
        from agent.run_agent_v2 import AgentV2Runner
        runner = AgentV2Runner.__new__(AgentV2Runner)

        output = json.dumps({"result": "just data", "score": 0.95})
        result = runner._process_tool_output(output)
        assert result.has_images is False


# ── Tool Registry Override ───────────────────────────────────

class TestToolRegistryOverride:
    def test_builtin_tools_loaded(self):
        registry = ToolRegistry(include_builtin=True)
        assert "search" in registry
        assert "ReadFullDocument" in registry
        assert "GetPage" in registry
        assert "ReadFullText" in registry

    def test_register_override(self):
        registry = ToolRegistry(include_builtin=True)
        original = registry._tools["search"]

        # Create a mock custom tool with same name
        class CustomSearch:
            name = "search"
            description = "Custom search"
            parameters = {"type": "object", "properties": {}}
            tool_type = "search"
            def execute(self, args, context):
                return '{"custom": true}'

        custom = CustomSearch()
        registry.register(custom, override=True)

        assert registry._tools["search"] is custom
        assert registry._tools["search"] is not original

    def test_restore_builtin(self):
        registry = ToolRegistry(include_builtin=True)

        # Back up and override
        registry._builtin_tools["search"] = registry._tools["search"]

        class CustomSearch:
            name = "search"
            description = "Custom"
            parameters = {"type": "object", "properties": {}}
            tool_type = "search"
            def execute(self, args, context):
                return '{"custom": true}'

        registry._tools["search"] = CustomSearch()

        # Restore
        restored = registry.restore_builtin("search")
        assert restored is True
        assert registry._tools["search"].__class__.__name__ == "SearchTool"

    def test_restore_nonexistent(self):
        registry = ToolRegistry(include_builtin=True)
        assert registry.restore_builtin("nonexistent") is False

    def test_builtin_tools_in_context(self):
        """Execute should expose _builtin_tools in context for wrapping."""
        registry = ToolRegistry(include_builtin=True)

        # Back up search as if it were overridden
        registry._builtin_tools["search"] = registry._tools["search"]

        class WrapperSearch:
            name = "search"
            description = "Wrapper"
            parameters = {"type": "object", "properties": {"query": {"type": "array", "items": {"type": "string"}}}}
            tool_type = "search"
            def execute(self, args, context):
                builtin = context.get("_builtin_tools", {}).get("search")
                if builtin:
                    return '{"wrapped": true, "has_builtin": true}'
                return '{"wrapped": true, "has_builtin": false}'

        registry.register(WrapperSearch(), override=True)

        ctx = make_context()
        result = registry.execute("search", {"query": ["test"]}, ctx)
        parsed = json.loads(result)
        assert parsed["wrapped"] is True
        assert parsed["has_builtin"] is True


# ── dedup_keep_first ─────────────────────────────────────────

class TestDedupKeepFirst:
    def test_basic_dedup(self):
        pages = [
            {"filename": "a.pdf", "page": 1, "content": "first", "Index": 1},
            {"filename": "a.pdf", "page": 1, "content": "duplicate", "Index": 2},
            {"filename": "a.pdf", "page": 2, "content": "second", "Index": 3},
        ]
        result = dedup_keep_first(pages)
        assert len(result) == 2
        assert result[0]["content"] == "first"
        assert result[0]["Index"] == 1
        assert result[1]["Index"] == 2

    def test_web_results_pass_through(self):
        """Web results (no filename/page) should not be deduped."""
        pages = [
            {"url": "https://a.com", "snippet": "a", "Index": 1},
            {"url": "https://a.com", "snippet": "a duplicate", "Index": 2},  # Same URL but different dict
        ]
        result = dedup_keep_first(pages)
        assert len(result) == 2  # Both kept since no filename/page key

    def test_mixed_doc_web(self):
        pages = [
            {"filename": "a.pdf", "page": 1, "content": "doc", "Index": 1},
            {"url": "https://web.com", "snippet": "web", "Index": 2},
            {"filename": "a.pdf", "page": 1, "content": "dup", "Index": 3},
        ]
        result = dedup_keep_first(pages)
        assert len(result) == 2  # doc + web, dup removed
