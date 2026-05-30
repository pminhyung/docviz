"""
exaone/auxiliary_tracer.py — Auxiliary LLM call logger for ExaoneAgent.

Writes one JSON file per auxiliary LLM call into the run's trace directory:
  auxiliary_compression_{N}.json    — context-compressor summariser
  auxiliary_web_extract_{N}.json    — web_extract summariser
  auxiliary_rd_extract_{N}.json     — ReadFullDocument EXTRACTOR_DOC_PROMPT
  auxiliary_finalizer.json          — iteration-limit finaliser

Each file schema:
  {
    "id": "",
    "conversations": [{"role": ..., "content": ...}, ...],
    "meta": { <f-string template variable values> }
  }

## SHARED LOGIC

Everything up to the end of ``write_rd_extract_log`` is kept
byte-identical on the ``master`` and ``sft-gen-ir-shim`` branches. When
you edit logic here, mirror the change to the other branch's
``exaone/auxiliary_tracer.py``. ir-shim extends this file below with
VLM/OCR loggers (``write_vlm_*_log``, ``write_vlm_ocr_log``) that are
specific to the ``mm_docqa`` mode — those helpers stay ir-shim-only and
must NOT be cherry-picked to master. The cross-branch sync table lives
in ``exaone/docqa_tools/_policy.md``.
"""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Optional

from exaone.compaction_tracer import _CURRENT_RUN_DIR

logger = logging.getLogger(__name__)

def bind_run(run_dir: Path):
    """Bind auxiliary tracer for the current run. Returns tokens for unbind_run."""
    from tools.web_tools import _WEB_EXTRACT_LOG_HOOK

    counter = [0]

    def _hook(
        url: str,
        raw_content: str,
        system_prompt: str,
        user_prompt: str,
        summary: Optional[str],
    ) -> None:
        counter[0] += 1
        write_web_extract_log(
            idx=counter[0],
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            assistant=summary or "",
            meta={"url": url, "raw_content": raw_content},
        )

    tok_hook = _WEB_EXTRACT_LOG_HOOK.set(_hook)
    return (tok_hook,)


def unbind_run(tokens) -> None:
    """Reset auxiliary tracer contextvars after run ends."""
    from tools.web_tools import _WEB_EXTRACT_LOG_HOOK

    (tok_hook,) = tokens
    _WEB_EXTRACT_LOG_HOOK.reset(tok_hook)


def _write(run_dir: Path, filename: str, data: dict) -> None:
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / filename).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug("auxiliary_tracer: wrote %s", run_dir / filename)
    except Exception:
        logger.exception("auxiliary_tracer: failed to write %s", filename)


def _write_compression(
    run_dir: Path,
    idx: int,
    user_prompt: str,
    assistant: str,
    meta: dict[str, Any],
) -> None:
    data = {
        "id": "",
        "conversations": [
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": assistant},
        ],
        "meta": meta,
    }
    _write(run_dir, f"auxiliary_compression_{idx}.json", data)


def write_compression_log(
    idx: int,
    user_prompt: str,
    assistant: str,
    meta: dict[str, Any],
) -> None:
    run_dir = _CURRENT_RUN_DIR.get()
    if run_dir is None:
        return
    _write_compression(run_dir, idx, user_prompt, assistant, meta)


def write_web_extract_log(
    idx: int,
    system_prompt: str,
    user_prompt: str,
    assistant: str,
    meta: dict[str, Any],
) -> None:
    run_dir = _CURRENT_RUN_DIR.get()
    if run_dir is None:
        return
    data = {
        "id": "",
        "conversations": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": assistant},
        ],
        "meta": meta,
    }
    _write(run_dir, f"auxiliary_web_extract_{idx}.json", data)


def _serialize_messages(messages: list[dict]) -> list[dict]:
    result = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content") or ""
        if isinstance(content, list):
            content = "\n".join(p.get("text", str(p)) for p in content if p)

        if role == "assistant":
            tool_calls = m.get("tool_calls") or []
            if tool_calls:
                parts = [f"<think>\n{content}\n</think>"]
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name", "")
                    args_raw = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    except Exception:
                        args = args_raw
                    tc_str = json.dumps({"name": name, "arguments": args}, ensure_ascii=False)
                    parts.append(f"<tool_call>\n{tc_str}\n</tool_call>")
                result.append({"role": "assistant", "content": "\n".join(parts)})
            else:
                result.append({"role": "assistant", "content": str(content)})
        elif role == "tool":
            tool_call_id = m.get("tool_call_id", "")
            name = m.get("name", "")
            try:
                parsed = json.loads(content) if isinstance(content, str) else content
            except Exception:
                parsed = content
            payload = json.dumps(
                {"tool_call_id": tool_call_id, "name": name, "content": parsed},
                ensure_ascii=False,
            )
            result.append({"role": "tool", "content": f"<tool_response>\n{payload}\n</tool_response>"})
        else:
            result.append({"role": role, "content": str(content)})
    return result


def write_finalizer_log(
    messages: list[dict],
    assistant: str,
) -> None:
    run_dir = _CURRENT_RUN_DIR.get()
    if run_dir is None:
        return
    all_messages = messages + [{"role": "assistant", "content": assistant}]
    data = {
        "id": "",
        "conversations": _serialize_messages(all_messages),
        "meta": {},
    }
    _write(run_dir, "auxiliary_finalizer.json", data)


# ─── RFD (ReadFullDocument) EXTRACTOR_DOC_PROMPT aux logging ────────────────
# RFD invokes an auxiliary LLM with the full-document text + the user goal to
# produce a goal-oriented extraction. The model's outer tool result carries
# only the extraction text; this writer preserves the (prompt, extraction)
# pair so a separate extractor model can be SFT-trained on it. Schema mirrors
# write_compression_log / write_web_extract_log so the same loader handles it.

_RD_SEQ_LOCK = __import__("threading").Lock()
_RD_SEQ: dict[str, int] = {}


def _next_rd_seq(run_dir_str: str) -> int:
    with _RD_SEQ_LOCK:
        n = _RD_SEQ.get(run_dir_str, 0) + 1
        _RD_SEQ[run_dir_str] = n
        return n


def write_rd_extract_log(
    *,
    system_prompt: str | None,
    user_prompt: str,
    assistant: str,
    meta: dict[str, Any],
) -> None:
    run_dir = _CURRENT_RUN_DIR.get()
    if run_dir is None:
        return
    seq = _next_rd_seq(str(run_dir))
    convs = []
    if system_prompt:
        convs.append({"role": "system", "content": system_prompt})
    convs.append({"role": "user", "content": user_prompt})
    convs.append({"role": "assistant", "content": assistant})
    data = {
        "id": "",
        "conversations": convs,
        "meta": meta,
    }
    _write(run_dir, f"auxiliary_rd_extract_{seq}.json", data)

# ─── ir-shim-only: visual_tools logging ─────────────────────────────────────────────────
# Race-safe per-(run_dir, kind) sequence counter shared by the visual writers
# below. get_visuals fires N concurrent VLM calls via asyncio.gather;
# analyze_visual can run alongside via concurrent batch workers. A
# process-wide counter would collide across task_ids — key by (run_dir, kind)
# so each run owns its own monotonic sequence per logger kind.

_SEQ_LOCK = __import__("threading").Lock()
_SEQ: dict[tuple[str, str], int] = {}


def _next_seq(kind: str) -> int:
    """Return next 1-based sequence number for the current run + kind.

    No-ops when no run is bound (returns 0 — handler decides to skip writes
    since aux logging is best-effort anyway).
    """
    run_dir = _CURRENT_RUN_DIR.get()
    if run_dir is None:
        return 0
    key = (str(run_dir), kind)
    with _SEQ_LOCK:
        n = _SEQ.get(key, 0) + 1
        _SEQ[key] = n
        return n


def write_vlm_analyze_log(
    messages: list[dict],
    assistant: str,
    meta: dict[str, Any],
) -> None:
    """analyze_visual VLM call — one auxiliary_vlm_analyze_<seq>.json file."""
    seq = _next_seq("vlm_analyze")
    if seq == 0:
        return
    run_dir = _CURRENT_RUN_DIR.get()
    data = {
        "id": "",
        "conversations": _serialize_messages(
            messages + [{"role": "assistant", "content": assistant}]
        ),
        "meta": meta,
    }
    _write(run_dir, f"auxiliary_vlm_analyze_{seq}.json", data)


def write_vlm_get_visuals_log(
    messages: list[dict],
    assistant: str,
    meta: dict[str, Any],
) -> None:
    """One per-image VLM call inside a get_visuals batch."""
    seq = _next_seq("vlm_get_visuals")
    if seq == 0:
        return
    run_dir = _CURRENT_RUN_DIR.get()
    data = {
        "id": "",
        "conversations": _serialize_messages(
            messages + [{"role": "assistant", "content": assistant}]
        ),
        "meta": meta,
    }
    _write(run_dir, f"auxiliary_vlm_get_visuals_{seq}.json", data)


def write_vlm_ocr_log(
    image_uri: str,
    ocr_text: str,
    meta: dict[str, Any],
) -> None:
    """OCR run — flat {image_uri, ocr_text, meta} schema, not a chat turn."""
    seq = _next_seq("vlm_ocr")
    if seq == 0:
        return
    run_dir = _CURRENT_RUN_DIR.get()
    data = {
        "image_uri": image_uri,
        "ocr_text": ocr_text,
        "meta": meta,
    }
    _write(run_dir, f"tool_ocr_{seq}.json", data)
