"""End-to-end preflight for ir-shim Mode A (local) and Mode B (remote).

What this does:
  - Wires up an ExaoneAgent against the live vLLM at the configured base URL.
  - Registers a small set of attached PDFs (Mode A: 2 docs from the local
    docai corpus; Mode B: same docs uploaded to the Dev Files API).
  - Runs a question that forces doc_parsing → doc_search → final answer
    so the trajectory has at least one tool round-trip in it.
  - Prints the final answer, the tool-call sequence, and a quick sanity
    check on the envelopes returned by each tool.

Mode A is gated by EXAONE_PARSED_ROOT (we point it at /poc/docai/out).
Mode B is gated by EXAONE_FILES_API_KEY (dev key from ir_api.md) plus
EXAONE_IR_URL (the chatexaone gw-qa endpoint).

Run from the ir-shim worktree:
    PYTHONPATH=. python scripts/preflight_modes.py local
    PYTHONPATH=. python scripts/preflight_modes.py remote
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import List

# Force the env defaults BEFORE the agent imports kick in.
os.environ.setdefault("HERMES_EXAONE_AGENT", "1")
os.environ.setdefault("EXAONE_BASE_URL", "http://10.1.211.148:8000/v1")
os.environ.setdefault("EXAONE_MODEL", "deepseek-v4-flash")
os.environ.setdefault("EXAONE_API_KEY", "EMPTY")
os.environ.setdefault("HERMES_HOME", "/tmp/preflight_hermes")
os.environ.setdefault("EXAONE_TRACE_DIR", "/tmp/preflight_traces")


def _sample_docs(n: int = 2) -> List[str]:
    """Pick the first ``n`` documents from file_mapping that actually exist.

    Avoids the shell-side encoding hassle with Korean filenames.
    """
    mapping_path = Path(
        os.environ.get("EXAONE_PARSED_ROOT", "/ex_disk2/mhpark/poc/docai/out")
    ) / "file_mapping.json"
    mapping = json.loads(mapping_path.read_text())
    out: List[str] = []
    for _fid, info in mapping.items():
        p = info["absolute_path"].replace("/./", "/")
        if Path(p).is_file():
            out.append(p)
            if len(out) >= n:
                break
    return out


SAMPLE_DOCS: List[str] = []  # filled by main() once env is set.


def _check_local_corpus() -> None:
    root = Path(os.environ.get("EXAONE_PARSED_ROOT", ""))
    if not root.is_dir() or not (root / "file_mapping.json").is_file():
        raise SystemExit(
            "EXAONE_PARSED_ROOT must point at a directory containing "
            "file_mapping.json (set to /ex_disk2/mhpark/poc/docai/out)."
        )
    global SAMPLE_DOCS
    SAMPLE_DOCS = _sample_docs(2)
    if len(SAMPLE_DOCS) < 2:
        raise SystemExit("could not find 2 sample docs in file_mapping.json")
    print(f"[sample-docs] {SAMPLE_DOCS}")


async def _register_local_attachments(task_id: str) -> List[dict]:
    from exaone.docqa_tools._attachments import Attachment, register_attachments

    entries = [
        Attachment(idx=i + 1, file_path=p, filename=Path(p).name)
        for i, p in enumerate(SAMPLE_DOCS)
    ]
    register_attachments(task_id=task_id, entries=entries)
    return [{"idx": a.idx, "filename": a.filename} for a in entries]


async def _register_remote_attachments(task_id: str) -> List[dict]:
    from exaone.sft_gen.upload_to_ir import upload_and_register

    if not os.environ.get("EXAONE_FILES_API_KEY"):
        raise SystemExit(
            "EXAONE_FILES_API_KEY not set. See ir_api.md for the Dev key."
        )
    if not os.environ.get("EXAONE_IR_URL"):
        raise SystemExit(
            "EXAONE_IR_URL not set. Set it to the chatexaone IR endpoint."
        )
    # wait_ready=False — the dev parser can take minutes on a fresh
    # upload. doc_parsing's IR probe (search_pass=1) returns empty when
    # the file is still ``processing`` and falls through to the local
    # parser → add_doc path, which keeps the preflight end-to-end while
    # the dev Files-API parser warms up in the background.
    attached = await upload_and_register(
        task_id=task_id, paths=SAMPLE_DOCS, wait_ready=False,
    )
    return [{"idx": a.idx, "filename": a.filename, "file_path": a.file_path} for a in attached]


def _build_prompt(attachments: List[dict], question: str) -> str:
    listing = "\n".join(f"[{a['idx']}] {a['filename']}" for a in attachments)
    return (
        "[Attached documents]\n"
        f"{listing}\n\n"
        "[Question]\n"
        f"{question}\n"
    )


async def _run(mode: str) -> None:
    if mode == "local":
        os.environ["HERMES_DOC_SOURCE"] = "local"
        os.environ.setdefault(
            "EXAONE_PARSED_ROOT", "/ex_disk2/mhpark/poc/docai/out",
        )
        _check_local_corpus()
    elif mode == "remote":
        os.environ["HERMES_DOC_SOURCE"] = "remote"
        global SAMPLE_DOCS
        if not SAMPLE_DOCS:
            SAMPLE_DOCS = _sample_docs(2)
            if len(SAMPLE_DOCS) < 2:
                raise SystemExit(
                    "could not find 2 sample docs in file_mapping.json"
                )
            print(f"[sample-docs] {SAMPLE_DOCS}")
    else:
        raise SystemExit(f"unknown mode: {mode}")

    # Late import — agent code reads env at import time in a few places.
    from exaone.agent import ExaoneAgent

    task_id = f"preflight-{uuid.uuid4().hex[:8]}"
    if mode == "local":
        attachments = await _register_local_attachments(task_id)
    else:
        attachments = await _register_remote_attachments(task_id)

    question = (
        "첨부된 문서들에서 다루는 핵심 주제를 2~3문장으로 요약해줘. "
        "각 주장에는 reference id (Index)를 붙여."
    )
    prompt = _build_prompt(attachments, question)
    print(f"--- mode={mode} task_id={task_id} ---")
    print(f"attachments: {attachments}")
    print(f"prompt:\n{prompt}\n")

    agent = ExaoneAgent(qa_mode="taskbot", reasoning=False, max_iterations=5)
    result = agent.run_conversation(
        prompt, task_id=task_id,
    )

    print("--- final response ---")
    print((result.get("final_response") or "")[:2000])

    messages = result.get("messages") or []
    tool_call_events: List[dict] = []
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                tool_call_events.append({
                    "tool": fn.get("name"),
                    "args": fn.get("arguments"),
                })
        elif role == "tool":
            content = m.get("content") or ""
            try:
                payload = json.loads(content) if isinstance(content, str) else content
            except Exception:
                payload = None
            tool_call_events.append({
                "tool_result_for": m.get("name"),
                "success": payload.get("success") if isinstance(payload, dict) else None,
                "result_count": len(payload.get("results", []))
                if isinstance(payload, dict) and isinstance(payload.get("results"), list)
                else None,
            })

    print("--- tool-call sequence ---")
    for ev in tool_call_events:
        print(ev)
    print("--- summary ---")
    print({"final_chars": len(result.get("final_response") or ""),
           "events": len(tool_call_events),
           "completed": result.get("completed")})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["local", "remote"])
    args = parser.parse_args()
    asyncio.run(_run(args.mode))


if __name__ == "__main__":
    main()
