"""
exaone/tracer.py — Run traces and training trajectories for ExaoneAgent.

Writes one directory per run_conversation() call:
  <trace_log_dir>/<UTC-timestamp>/<query-id>/
    raw_run_result.json   — full RunResult-compatible trace
    trajectory.json       — ShareGPT conversations (from/value) for completed runs
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from copy import deepcopy

if TYPE_CHECKING:
    from run_agent import AIAgent

logger = logging.getLogger(__name__)


def log_trace(
    *,
    user_message: str,
    result: dict,
    tools: list,
    system_prompt: str,
    system_blocks: dict | None = None,
    session_id: str | None,
    trace_log_dir: Path,
    agent: "AIAgent | None" = None,
    run_dir: Path | None = None,
    save_raw: bool = True,
    save_trajectory: bool = True,
) -> None:
    """Write raw_run_result.json and/or trajectory.json for this run."""
    from exaone.tools import PROMPT_TOOL_IDS

    messages = result.get("messages", [])
    run_id = str(uuid.uuid4())
    completed = result.get("completed", False)

    trace = {
        "query_id": run_id,
        "user_query": user_message,
        "system_prompt": system_prompt,
        "system_blocks": system_blocks or {},
        # Full turn transcript (input/output messages) for exact replay/debugging.
        # Kept alongside structured slices below for compatibility.
        "messages": _copy_messages_for_trace(messages),
        "available_tools": [t["function"]["name"] for t in tools],
        "tool_ids": list(PROMPT_TOOL_IDS),
        "tool_schemas": tools,
        "model_responses": _extract_model_responses(messages, result.get("last_reasoning")),
        "tool_results": _extract_tool_results(messages),
        "events": [],
        "final_answer": result.get("final_response"),
        "loop_error": (
            None if completed
            else {"type": "incomplete", "message": result.get("turn_exit_reason") or "unknown"}
        ),
        "meta": {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "model": result.get("model"),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
            "reasoning_tokens": result.get("reasoning_tokens", 0),
            "cache_read_tokens": result.get("cache_read_tokens", 0),
            "cache_write_tokens": result.get("cache_write_tokens", 0),
            "api_calls": result.get("api_calls", 0),
            "completed": completed,
            "turn_exit_reason": result.get("turn_exit_reason"),
        },
    }

    if run_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = trace_log_dir / ts / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

    if save_raw:
        (run_dir / "raw_run_result.json").write_text(
            json.dumps(trace, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )
        _upload_to_gcp(trace)

    if save_trajectory and agent is not None:
        conversations = agent._convert_to_trajectory_format(messages, user_message, completed)
        traj_entry = {
            "conversations": conversations,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": result.get("model"),
            "completed": completed,
        }
        (run_dir / "trajectory.json").write_text(
            json.dumps(traj_entry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    logger.debug("ExaoneAgent: trace written to %s", run_dir)


def _copy_messages_for_trace(messages: list) -> list:
    """Return a detached copy of messages for raw trace payload."""
    try:
        return deepcopy(messages)
    except Exception:
        return [dict(m) if isinstance(m, dict) else {"role": "unknown", "content": str(m)} for m in messages]


def _extract_model_responses(messages: list, last_reasoning: str | None) -> list:
    responses = []
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    for i, msg in enumerate(assistant_msgs):
        tool_calls_raw = msg.get("tool_calls") or []
        parsed_calls = []
        for tc in tool_calls_raw:
            fn = tc.get("function", {})
            try:
                arguments = json.loads(fn.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            parsed_calls.append({"id": tc.get("id"), "name": fn.get("name"), "arguments": arguments})
        is_last = i == len(assistant_msgs) - 1
        reasoning = msg.get("reasoning_content") or (last_reasoning if is_last else None)
        responses.append({
            "final_output": msg.get("content") or "",
            "reasoning_content": reasoning or None,
            "tool_calls": parsed_calls,
            "finish_reason": "tool_calls" if tool_calls_raw else "stop",
            "usage": None,
        })
    return responses


def _extract_tool_results(messages: list) -> list:
    results = []
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        content = msg.get("content") or ""
        results.append({
            "tool_call_id": msg.get("tool_call_id"),
            "tool_name": msg.get("name"),
            "output_text": content,
            "is_error": _is_tool_error(content),
            "error_code": None,
        })
    return results


def _is_tool_error(content: str) -> bool:
    try:
        parsed = json.loads(content)
        return isinstance(parsed, dict) and "error" in parsed
    except (json.JSONDecodeError, TypeError):
        return False


def _upload_to_gcp(trace: dict) -> None:
    """GCP upload placeholder — implement with BigQuery/GCS/Cloud Logging as needed."""
    pass
