from __future__ import annotations

import json

from exaone.tool_formatting import (
    RunIndexStore,
    ToolResultFormatter,
    infer_result_format,
    is_already_enveloped,
    normalize_tool_result_for_envelope,
    resolve_result_format,
)


def _format(raw: object, *, tool_call_id: str = "abc123", result_format: dict | None = None) -> dict:
    store = RunIndexStore()
    formatter = ToolResultFormatter(index_store=store)
    text = formatter.format(
        tool_call_id=tool_call_id,
        tool_name="web_search",
        raw_result=raw,
        result_format=result_format,
    )
    return json.loads(text)


def test_envelope_stamps_index_per_hit() -> None:
    raw = {
        "results": [
            {"site_name": "A", "url": "https://a", "snippet": "da"},
            {"site_name": "B", "url": "https://b", "snippet": "db"},
        ]
    }
    envelope = _format(raw, result_format=resolve_result_format("web_search", raw))
    # Envelope no longer carries top-level tool_call_id/tool_name — that
    # metadata lives on the outer OpenAI `tool` message instead. Each entry
    # still carries its Index for citation.
    assert "tool_call_id" not in envelope
    assert "tool_name" not in envelope
    assert envelope["results"][0]["Index"] == "abc123.0"
    assert envelope["results"][1]["Index"] == "abc123.1"
    assert envelope["results"][0]["url"] == "https://a"


def test_citable_registers_index_store() -> None:
    store = RunIndexStore()
    formatter = ToolResultFormatter(index_store=store)
    raw = {"results": [{"url": "https://a", "site_name": "A"}]}
    fmt = {"list_path": "results", "citable": True, "index_payload_keys": ["url", "site_name"]}
    formatter.format(
        tool_call_id="vyh608",
        tool_name="web_search",
        raw_result=raw,
        result_format=fmt,
    )
    assert store.get("vyh608.0") == {"url": "https://a", "site_name": "A"}


def test_is_already_enveloped_skips_reformat() -> None:
    raw = {"results": [{"Index": "abc123.0", "text": "x"}]}
    assert is_already_enveloped(raw) is True


def test_is_already_enveloped_rejects_unindexed_results_list() -> None:
    raw = {"results": [{"url": "https://a"}]}
    assert is_already_enveloped(raw) is False


def test_infer_brave_web_search_format() -> None:
    fmt = infer_result_format({"results": []}, "web_search")
    assert fmt["list_path"] == "results"
    assert fmt["citable"] is True


def test_brave_mcp_plain_text_result_envelopes_hits() -> None:
    raw = {
        "result": (
            "Title: LG AI Research\n"
            "Description: AI research hub\n"
            "URL: https://www.lgresearch.ai/\n"
            "\n"
            "Title: Case study\n"
            "Description: More info\n"
            "URL: https://example.com/case"
        )
    }
    fmt = resolve_result_format("web_search", raw)
    store = RunIndexStore()
    formatter = ToolResultFormatter(index_store=store)
    envelope = json.loads(
        formatter.format(
            tool_call_id="hnn536",
            tool_name="web_search",
            raw_result=raw,
            result_format=fmt,
        )
    )
    assert len(envelope["results"]) == 2
    assert envelope["results"][0]["Index"] == "hnn536.0"
    assert envelope["results"][0]["url"] == "https://www.lgresearch.ai/"
    assert envelope["results"][1]["title"] == "Case study"


def test_normalize_web_search_data_web_shape_to_results() -> None:
    raw = {
        "success": True,
        "data": {
            "web": [
                {
                    "query_idx": 0,
                    "site_name": "LG AI Research",
                    "snippet": ["Official site", "Research hub"],
                    "url": "https://www.lgresearch.ai/",
                }
            ]
        },
        "queries": ["LG AI"],
    }
    normalized = normalize_tool_result_for_envelope(raw, "web_search", "results")
    assert isinstance(normalized.get("results"), list)
    row = normalized["results"][0]
    assert row["site_name"] == "LG AI Research"
    assert row["snippet"] == ["Official site", "Research hub"]
    assert row["url"] == "https://www.lgresearch.ai/"
    assert row["query_idx"] == 0


def test_web_search_format_uses_new_index_payload_keys() -> None:
    fmt = resolve_result_format("web_search", {"results": []})
    assert fmt["index_payload_keys"] == ["url", "site_name", "snippet"]
    assert fmt["passthrough_keys"] == ["queries", "per_query_errors"]


def test_web_search_passthrough_keys_propagate_to_envelope() -> None:
    raw = {
        "success": True,
        "data": {
            "web": [
                {"query_idx": 0, "site_name": "A", "snippet": "snip", "url": "https://a"},
            ]
        },
        "queries": ["q"],
        "per_query_errors": [{"query_idx": 1, "query": "", "error": "empty or non-string"}],
    }
    fmt = resolve_result_format("web_search", raw)
    raw_normalized = normalize_tool_result_for_envelope(raw, "web_search", "results")
    store = RunIndexStore()
    formatter = ToolResultFormatter(index_store=store)
    envelope = json.loads(
        formatter.format(
            tool_call_id="abc999",
            tool_name="web_search",
            raw_result=raw_normalized,
            result_format=fmt,
        )
    )
    assert envelope["queries"] == ["q"]
    assert envelope["per_query_errors"][0]["error"] == "empty or non-string"
    # Citable payload is projected to the new key set.
    assert store.get("abc999.0") == {"url": "https://a", "site_name": "A", "snippet": "snip"}


def test_web_extract_format_is_non_citable() -> None:
    raw = {"results": [{"url": "https://a", "contents": "text"}]}
    fmt = resolve_result_format("web_extract", raw)
    assert fmt["citable"] is False


def test_unknown_tool_format_returns_empty() -> None:
    raw = {"output": "some result"}
    fmt = resolve_result_format("doc_tool", raw)
    assert fmt == {}
