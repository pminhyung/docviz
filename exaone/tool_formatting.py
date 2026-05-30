"""Universal tool-result Index envelope for ExaoneAgent (scaffold-compatible)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_DOC_SEARCH_PASSTHROUGH = [
    "queries",
    "document_idx",
    "per_query_errors",
    "backend",
]


# Per-tool result_format (prototype tool_specs/*.yaml equivalent).
TOOL_RESULT_FORMATS: dict[str, dict[str, Any]] = {
    "web_search": {
        "list_path": "results",
        "citable": True,
        "index_payload_keys": ["url", "site_name", "snippet"],
        "passthrough_keys": ["queries", "per_query_errors"],
    },
    # Doc-grounded tools: every entry becomes a citable chunk with its
    # own Index. parsing_tools (parse_web_and_doc, list_documents) are
    # intentionally absent — those tools prepare the chunk pool, they
    # are not themselves cited in the final answer.
    #
    # Note: the agent only ever sees ``document_idx`` for documents. fids
    # never appear in any output envelope — the handlers resolve idx <-> fid
    # internally via the per-task attachment table.
    "doc_search": {
        "list_path": "data.doc",
        "citable": True,
        "index_payload_keys": ["document_idx", "page", "title", "snippet"],
        "passthrough_keys": _DOC_SEARCH_PASSTHROUGH,
    },
    "get_document_chunks": {
        "list_path": "results",
        "citable": True,
        "index_payload_keys": ["document_idx", "page", "text"],
        "passthrough_keys": ["missing"],
    },
    "ReadFullDocument": {
        "list_path": None,
        "citable": True,
        "index_payload_keys": ["document_idx", "filename", "goal", "text"],
    },
    # visual_tools: same envelope policy as docqa above. get_visuals rows are
    # citable images (each with analysis/ocr_text/metadata); analyze_visual
    # is a single-image inspection result. Payload keeps the fields
    # analyze_visual's resolver needs to load the actual PNG (fid, page, idx).
    "get_visuals": {
        "list_path": "data.results",
        "citable": True,
        "index_payload_keys": [
            "document_idx", "page", "category", "caption",
            "fid", "img_idx", "selector_score",
        ],
    },
    "analyze_visual": {
        "list_path": None,
        "citable": True,
        "index_payload_keys": ["image_source", "goal", "applied_ops"],
    },
}


@dataclass
class RunIndexStore:
    """Per-run map of ``<tcid>.<n>`` → entry payload."""

    entries: dict[str, dict[str, Any]] = field(default_factory=dict)

    def register(self, *, index: str, payload: dict[str, Any]) -> None:
        self.entries[index] = dict(payload)

    def get(self, index: str) -> dict[str, Any] | None:
        return self.entries.get(index)

    def reset(self) -> None:
        self.entries.clear()


@dataclass
class ToolResultFormatter:
    index_store: RunIndexStore

    def format(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        raw_result: Any,
        result_format: dict[str, Any] | None,
    ) -> str:
        spec = result_format or {}
        list_path = spec.get("list_path")
        index_payload_keys = spec.get("index_payload_keys")
        citable = bool(spec.get("citable", False))
        passthrough_keys = spec.get("passthrough_keys") or []

        raw_result = normalize_tool_result_for_envelope(raw_result, tool_name, list_path)
        items, raw_top = _extract_items(raw_result=raw_result, list_path=list_path)

        annotated_items: list[dict[str, Any]] = []
        for n, item in enumerate(items):
            index = f"{tool_call_id}.{n}"
            if isinstance(item, dict):
                entry: dict[str, Any] = {"Index": index, **item}
                payload = _project_payload(entry=entry, keys=index_payload_keys)
            elif isinstance(item, str):
                entry = {"Index": index, "text": item}
                payload = {"text": item}
            else:
                entry = {"Index": index, "value": item}
                payload = {"value": item}
            annotated_items.append(entry)
            if citable:
                self.index_store.register(index=index, payload=payload)

        # `tool_call_id` / `tool_name` deliberately omitted from the envelope.
        # The outer `tool` message already carries both (per OpenAI message
        # schema), so embedding them here too would just duplicate metadata in
        # every tool result's content. Each entry's `Index = "<tcid>.<n>"`
        # preserves per-hit linkage to the originating tool_call.
        envelope: dict[str, Any] = {"results": annotated_items}
        if isinstance(raw_top, dict):
            for key in passthrough_keys:
                if key in raw_top and key not in envelope:
                    envelope[key] = raw_top[key]

        return json.dumps(envelope, ensure_ascii=False)


def parse_tool_result_content(content: str | Any) -> Any:
    if isinstance(content, (dict, list)):
        return content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content
    return content


def is_already_enveloped(raw: Any) -> bool:
    """An envelope is identified by `results` being a list whose entries carry `Index`.

    Empty-results envelopes are also accepted as long as the `results` key is
    present and is a list — that's the shape produced by ``ToolResultFormatter``
    when a tool returns no hits.
    """
    if not isinstance(raw, dict):
        return False
    results = raw.get("results")
    if not isinstance(results, list):
        return False
    if not results:
        return True
    first = results[0]
    return isinstance(first, dict) and "Index" in first


def infer_result_format(raw_result: Any, tool_name: str) -> dict[str, Any]:
    """Heuristic when no explicit TOOL_RESULT_FORMATS entry exists."""
    name = (tool_name or "").lower()
    if isinstance(raw_result, dict) and "results" in raw_result:
        if "brave" in name or "web_search" in name or "local_search" in name:
            return {
                "list_path": "results",
                "citable": True,
                "index_payload_keys": ["url", "site_name", "snippet"],
            }
        return {"list_path": "results", "citable": False}
    return {}


def resolve_result_format(tool_name: str, raw_result: Any) -> dict[str, Any]:
    if tool_name in TOOL_RESULT_FORMATS:
        return dict(TOOL_RESULT_FORMATS[tool_name])
    return infer_result_format(raw_result, tool_name)


def new_run_formatting() -> tuple[RunIndexStore, ToolResultFormatter]:
    store = RunIndexStore()
    return store, ToolResultFormatter(index_store=store)


# Task-keyed mirror of RunIndexStore so handlers (which only receive task_id,
# not the agent instance) can resolve `<tcid>.<n>` Index strings the model
# echoes from prior tool results. visual_tools uses this to turn an
# analyze_visual `image` Index into the underlying ImageMeta.
# Registered by ExaoneAgent.run_conversation; unregistered at run end so
# concurrent batch workers don't see each other's stores.
_INDEX_STORES_BY_TASK: dict[str, RunIndexStore] = {}


def register_index_store_for_task(task_id: str, store: RunIndexStore) -> None:
    if task_id:
        _INDEX_STORES_BY_TASK[task_id] = store


def unregister_index_store_for_task(task_id: str) -> None:
    _INDEX_STORES_BY_TASK.pop(task_id, None)


def get_index_store_for_task(task_id: str) -> RunIndexStore | None:
    return _INDEX_STORES_BY_TASK.get(task_id)


def parse_brave_search_text(text: str) -> list[dict[str, str]]:
    """Parse @modelcontextprotocol/server-brave-search plain-text hits into dict rows."""
    entries: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        if not block.strip():
            continue
        title = description = url = ""
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("Title:"):
                title = line[len("Title:") :].strip()
            elif line.startswith("Description:"):
                description = line[len("Description:") :].strip()
            elif line.startswith("URL:"):
                url = line[len("URL:") :].strip()
        if title or description or url:
            entries.append({"title": title, "description": description, "url": url})
    return entries


def normalize_tool_result_for_envelope(
    raw_result: Any, tool_name: str, list_path: str | None
) -> Any:
    """Brave MCP returns ``{\"result\": \"Title:...\\nURL:...\"}``, not a ``results`` list."""
    if list_path == "data.doc":
        # doc_search returns {"success": true, "data": {"doc": [...]}, ...}.
        # The formatter walks list_path natively via _extract_items, so we
        # don't need to flatten here — return as-is.
        return raw_result
    if list_path != "results" or not isinstance(raw_result, dict):
        return raw_result
    existing = raw_result.get("results")
    if isinstance(existing, list) and existing:
        return raw_result

    # Built-in web_search returns {"success": true, "data": {"web": [...]}}.
    # Normalize this shape so the citation envelope can index web hits.
    data = raw_result.get("data")
    if isinstance(data, dict):
        web_rows = data.get("web")
        if isinstance(web_rows, list):
            normalized_rows: list[dict[str, Any]] = []
            for item in web_rows:
                if isinstance(item, dict):
                    row: dict[str, Any] = {
                        "site_name": item.get("site_name", ""),
                        "snippet": item.get("snippet", ""),
                        "url": item.get("url", ""),
                    }
                    if "query_idx" in item:
                        row["query_idx"] = item["query_idx"]
                    normalized_rows.append(row)
                elif isinstance(item, str):
                    normalized_rows.append({"site_name": "", "snippet": item, "url": ""})
            return {**raw_result, "results": normalized_rows}

    text = raw_result.get("result")
    if not isinstance(text, str) or not text.strip():
        return raw_result

    name = (tool_name or "").lower()
    if "brave" not in name and "web_search" not in name and "local_search" not in name:
        return raw_result

    parsed = parse_brave_search_text(text)
    if not parsed:
        return raw_result
    return {**raw_result, "results": parsed}


def _extract_items(*, raw_result: Any, list_path: str | None) -> tuple[list[Any], Any]:
    if list_path is None:
        if isinstance(raw_result, list):
            return list(raw_result), raw_result
        return [raw_result], raw_result

    if not isinstance(raw_result, dict):
        return [raw_result], raw_result

    cursor: Any = raw_result
    for segment in list_path.split("."):
        if not isinstance(cursor, dict) or segment not in cursor:
            return [], raw_result
        cursor = cursor[segment]

    if isinstance(cursor, list):
        return list(cursor), raw_result
    if cursor is None:
        return [], raw_result
    return [cursor], raw_result


def _project_payload(*, entry: dict[str, Any], keys: list[str] | None) -> dict[str, Any]:
    if not keys:
        return dict(entry)
    return {key: entry[key] for key in keys if key in entry}
