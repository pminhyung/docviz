#!/usr/bin/env python3
"""
Test script to verify custom tool workflow from client perspective.

This tests:
1. ToolRegistry loading from .py file
2. Session accumulation with proper v2 format
3. Document loader with docai format

Run: python -m pytest agent/tests/test_custom_tool_flow.py -v
Or: python agent/tests/test_custom_tool_flow.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.core.tool_registry import ToolRegistry, ToolValidationError
from agent.core.tool_actions import ToolContext
from agent.core.session_manager import SessionManager
from agent.core.document_loader import DocumentLoader, DocumentFormat
from agent.export.training_jsonl import convert_base_train_sample, TrainingSample


def test_tool_registry_loading():
    """Test loading custom tools from .py file."""
    print("\n=== Test: ToolRegistry Loading ===")

    # Create a simple custom tool file
    tool_code = '''
class SimpleTestTool:
    name = "test_tool"
    description = "A simple test tool"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string"}
        },
        "required": ["input"]
    }
    tool_type = "search"

    def execute(self, args, context):
        return f"Echo: {args.get('input', '')}"
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(tool_code)
        tool_path = f.name

    try:
        # Use include_builtin=False to test only custom tool loading
        registry = ToolRegistry(include_builtin=False)
        loaded = registry.load_from_file(tool_path)

        assert "test_tool" in loaded, f"Expected test_tool in {loaded}"
        assert registry.has_tool("test_tool")

        # Test execution
        context = ToolContext(
            user_query="test",
            filenames=["doc.pdf"],
            multi_docs=[[]],
            image_dir=None,
            language="en",
            current_step=1
        )

        result = registry.execute("test_tool", {"input": "hello"}, context)
        assert "Echo: hello" in result

        # Test prompt generation
        tools = registry.get_tools_for_prompt()
        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"

        print("✓ ToolRegistry loading works correctly")
        return True

    finally:
        os.unlink(tool_path)


def test_session_accumulation_format():
    """Test that session accumulates samples in v2 format."""
    print("\n=== Test: Session Accumulation Format ===")

    # Create a base train_sample (as returned by runner)
    base_sample = {
        "df_idx": 0,
        "user_query": "What is this document about?",
        "filenames": ["test.pdf"],
        "reasoning": [
            [
                {"role": "system", "content": "Runtime prompt here", "loss_masking": True},
                {"role": "user", "content": "Question", "loss_masking": True},
                {"role": "assistant", "content": "Answer", "loss_masking": False},
            ]
        ],
        "readfulldocument": [],
        "readfulltext": [],
        "doc_step": [],
    }

    # Convert to v2 format
    v2_sample = convert_base_train_sample(
        base_train_sample=base_sample,
        train_system_prompt="Training system prompt",
        runtime_prompt_hash="abc123",
        session=None,
        language="ENGLISH",
        override_hash=None,
        metadata={"custom_tools": ["analyze_chart"]}
    )

    # Verify v2 format
    sample_dict = v2_sample.to_dict()

    assert "version" in sample_dict, "Missing version field"
    assert sample_dict["version"] == "2.0"
    assert "train_system_prompt" in sample_dict
    assert "runtime_prompt_hash" in sample_dict
    assert sample_dict["runtime_prompt_hash"] == "abc123"
    assert "metadata" in sample_dict
    assert "custom_tools" in sample_dict["metadata"]

    # Check system prompt transformation in reasoning
    reasoning = sample_dict["reasoning"]
    assert len(reasoning) > 0
    for turn in reasoning[0]:
        if turn.get("role") == "system":
            assert "ChatEXAONE" in turn["content"], "chatexaone_sys not prepended"
            assert "Training system prompt" in turn["content"], "train_system_prompt missing"
            assert "__SYSTEM_PROMPT_REDACTED__" not in turn["content"], "still redacted"

    print("✓ Session accumulation format is correct")
    return True


def test_docai_format_parsing():
    """Test parsing of docai JSON format."""
    print("\n=== Test: Docai Format Parsing ===")

    # Create docai format document
    docai_doc = {
        "id": "test-uuid",
        "outputs": [{
            "file_name": "original_report.pdf",
            "html_parsed": {
                "1": ["Page 1 paragraph 1", "Page 1 paragraph 2"],
                "2": ["Page 2 content"],
                "3": ["Page 3 line 1", "Page 3 line 2", "Page 3 line 3"]
            }
        }]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(docai_doc, f)
        doc_path = f.name

    try:
        loader = DocumentLoader()
        doc = loader.load_single_document(doc_path)

        assert doc.format_detected == DocumentFormat.DOCAI
        assert doc.filename == "original_report.pdf"
        assert doc.total_pages == 3

        # Verify page content
        assert len(doc.pages) == 3
        assert "Page 1 paragraph 1" in doc.pages[0]["content"]
        assert doc.pages[0]["page"] == 1
        assert doc.pages[1]["page"] == 2
        assert doc.pages[2]["page"] == 3

        print("✓ Docai format parsing works correctly")
        return True

    finally:
        os.unlink(doc_path)


def test_session_manager():
    """Test SessionManager accumulation and cleanup."""
    print("\n=== Test: SessionManager ===")

    manager = SessionManager()
    test_session_id = "test_session_12345"

    try:
        # Append samples
        count1 = manager.append_sample(test_session_id, {"sample": 1})
        count2 = manager.append_sample(test_session_id, {"sample": 2})

        assert count1 == 1
        assert count2 == 2

        # Verify file exists
        jsonl_path = manager.finalize(test_session_id)
        assert os.path.exists(jsonl_path)

        # Read and verify content
        with open(jsonl_path, 'r') as f:
            lines = f.readlines()
        assert len(lines) == 2

        samples = [json.loads(line) for line in lines]
        assert samples[0]["sample"] == 1
        assert samples[1]["sample"] == 2

        print("✓ SessionManager works correctly")
        return True

    finally:
        manager.cleanup(test_session_id)


def test_tool_validation():
    """Test that invalid tools are rejected."""
    print("\n=== Test: Tool Validation ===")

    # Test missing required attributes
    invalid_tools = [
        # Missing name
        '''
class MissingName:
    description = "test"
    parameters = {}
    tool_type = "search"
    def execute(self, args, context): pass
''',
        # Invalid tool_type
        '''
class InvalidType:
    name = "test"
    description = "test"
    parameters = {}
    tool_type = "invalid"
    def execute(self, args, context): pass
''',
        # Missing execute
        '''
class NoExecute:
    name = "test"
    description = "test"
    parameters = {}
    tool_type = "search"
''',
    ]

    # Use include_builtin=False to test only custom tool validation
    registry = ToolRegistry(include_builtin=False)

    for i, code in enumerate(invalid_tools):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            path = f.name

        try:
            try:
                registry.load_from_file(path)
                print(f"✗ Invalid tool {i} was not rejected")
                return False
            except (ToolValidationError, ValueError):
                pass  # Expected
        finally:
            os.unlink(path)

    print("✓ Invalid tools are correctly rejected")
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Custom Tool Flow Tests")
    print("=" * 60)

    results = []
    tests = [
        test_tool_registry_loading,
        test_session_accumulation_format,
        test_docai_format_parsing,
        test_session_manager,
        test_tool_validation,
    ]

    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False))

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")

    print(f"\nTotal: {passed}/{total} passed")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
