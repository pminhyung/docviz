"""Dev IR Files API uploader for ir-shim Mode B (HERMES_DOC_SOURCE=remote).

In Mode B the SFT batch wants to run the production end-to-end flow
(parser → IR add → search), but the SFT environment has no upstream
"Files API" layer to assign each file a fid. This module fills that
gap by posting each file to the lgresearch Dev Files API
(``https://dev-api.lgresearch.ai/v1/files``) and returning the
``id`` it issues — which is what we use as the IR fid throughout the
agent loop.

The wire matches the public API doc verbatim:

    POST /v1/files
      headers: x-api-key
      body:    multipart/form-data, field name "files"
      response 200: {"result_code": 200, "files": [{"id": "...", "name": "..."}]}

Authentication: the Dev API key from ``ir_api.md`` is accepted via the
``EXAONE_FILES_API_KEY`` env var (falls back to ``LGRESEARCH_API_KEY``).

Rate limits documented in ir_api.md: 10 req/s, 100 req/min, 10000/day on
Dev. Batches that upload many files should serialise with a small
``sleep`` between batches (the SFT script handles this; this module
exposes ``upload_many`` for convenience but each call is independent).

## Document flow policy (background)

See ``exaone/docqa_tools/_policy.md`` — section "ir-shim — Mode B".
This module is the only piece that exists on ir-shim and not on
master: master assumes an upstream system (or the same Files API) has
already handed the agent a fid, so the agent simply trusts the
``file_id`` it receives.

This module does NOT call the IR ``add_doc`` endpoint. The Files API
layer triggers the parser server-side and the IR add happens as part
of the file becoming ``status=ready``. ``parse_web_and_doc`` then probes
``find_docs(search_pass=1)`` and rehydrates from IR, exactly as
production does.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from urllib.parse import unquote

import aiohttp

from exaone.docqa_tools._attachments import Attachment, register_attachments, set_fid

logger = logging.getLogger(__name__)


DEFAULT_DEV_URL = "https://dev-api.lgresearch.ai"
DEFAULT_UPLOAD_TIMEOUT = 120  # seconds; parser pre-build runs server-side
_READY_POLL_INTERVAL = 2.0
_DEFAULT_READY_TIMEOUT = 180  # seconds


@dataclass(frozen=True)
class UploadedFile:
    fid: str
    filename: str
    local_path: str
    status: str = "uploaded"


def _resolve_base_url() -> str:
    return (
        os.getenv("EXAONE_FILES_API_URL")
        or os.getenv("LGRESEARCH_FILES_API_URL")
        or DEFAULT_DEV_URL
    ).rstrip("/")


def _resolve_api_key() -> str:
    key = (
        os.getenv("EXAONE_FILES_API_KEY")
        or os.getenv("LGRESEARCH_API_KEY")
        or ""
    ).strip()
    if not key:
        raise RuntimeError(
            "Files API key not configured. Set EXAONE_FILES_API_KEY "
            "(preferred) or LGRESEARCH_API_KEY. See ir_api.md for the "
            "Dev key."
        )
    return key


async def upload_file(
    *,
    file_path: str | Path,
    session: aiohttp.ClientSession | None = None,
    upsert: bool = True,
) -> UploadedFile:
    """Upload one file to the Dev Files API; return the issued fid + name.

    The Files API performs the parser pre-build server-side. By the time
    the response comes back the file is registered but may still be in
    ``processing`` state; use ``wait_until_ready`` if downstream code
    needs the file searchable immediately.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"upload source not found: {path}")

    url = f"{_resolve_base_url()}/v1/files"
    headers = {"x-api-key": _resolve_api_key()}

    async def _do(sess: aiohttp.ClientSession) -> UploadedFile:
        form = aiohttp.FormData()
        form.add_field("files", path.read_bytes(), filename=path.name)
        form.add_field("upsert", "true" if upsert else "false")
        async with sess.post(url, headers=headers, data=form) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200 or body.get("result_code") != 200:
                raise RuntimeError(
                    f"Files API upload failed ({resp.status}): "
                    f"{body.get('description') or body}"
                )
        files = body.get("files") or []
        if not files:
            raise RuntimeError("Files API upload returned no files entry")
        entry = files[0]
        # Dev Files API sometimes echoes the filename URL-encoded; undo
        # that so the model sees a human-readable name in the [Attached
        # documents] block.
        raw_name = entry.get("name") or path.name
        return UploadedFile(
            fid=str(entry["id"]),
            filename=unquote(raw_name),
            local_path=str(path),
        )

    if session is None:
        timeout = aiohttp.ClientTimeout(total=DEFAULT_UPLOAD_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as own:
            return await _do(own)
    return await _do(session)


async def query_files(
    *,
    file_ids: List[str],
    session: aiohttp.ClientSession | None = None,
) -> List[dict]:
    """POST /v1/files/query — fetch status for the given file_ids."""
    if not file_ids:
        return []
    url = f"{_resolve_base_url()}/v1/files/query"
    headers = {
        "x-api-key": _resolve_api_key(),
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {"file_ids": [str(f) for f in file_ids]}

    async def _do(sess: aiohttp.ClientSession) -> List[dict]:
        async with sess.post(url, headers=headers, json=payload) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200 or body.get("result_code") != 200:
                raise RuntimeError(
                    f"Files API query failed ({resp.status}): "
                    f"{body.get('description') or body}"
                )
            return body.get("files") or []

    if session is None:
        timeout = aiohttp.ClientTimeout(total=DEFAULT_UPLOAD_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as own:
            return await _do(own)
    return await _do(session)


async def wait_until_ready(
    *,
    file_ids: List[str],
    poll_interval: float = _READY_POLL_INTERVAL,
    timeout_seconds: float = _DEFAULT_READY_TIMEOUT,
    session: aiohttp.ClientSession | None = None,
) -> dict[str, str]:
    """Poll ``/v1/files/query`` until every fid reaches ``ready`` or ``failed``.

    Returns ``{fid: final_status}``. Times out with ``RuntimeError`` if
    any file is still ``processing`` after ``timeout_seconds``.
    """
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    pending = {str(f) for f in file_ids}
    final: dict[str, str] = {}
    while pending and asyncio.get_event_loop().time() < deadline:
        infos = await query_files(file_ids=list(pending), session=session)
        for entry in infos:
            fid = str(entry.get("id"))
            status = str(entry.get("status", "")).lower()
            if status in ("ready", "failed"):
                final[fid] = status
                pending.discard(fid)
        if pending:
            await asyncio.sleep(poll_interval)
    if pending:
        raise RuntimeError(
            f"Files API: timed out waiting for {sorted(pending)} to leave processing"
        )
    return final


async def upload_many(
    *,
    paths: List[str | Path],
    inter_request_sleep: float = 0.1,
) -> List[UploadedFile]:
    """Sequential upload helper. Respects the documented 10 req/s limit.

    Concurrent uploads occasionally trip the Files API rate limiter and
    the API gives no retryable error code — sequential with a short
    sleep is the cheapest reliable shape.
    """
    timeout = aiohttp.ClientTimeout(total=DEFAULT_UPLOAD_TIMEOUT)
    out: List[UploadedFile] = []
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for p in paths:
            uploaded = await upload_file(file_path=p, session=session)
            out.append(uploaded)
            if inter_request_sleep:
                await asyncio.sleep(inter_request_sleep)
    return out


def inject_into_task(
    *,
    task_id: str,
    uploaded: List[UploadedFile],
    starting_idx: int = 1,
) -> List[Attachment]:
    """Register the uploaded files with the per-task attachment table.

    After this call the main agent loop can refer to each file by
    ``document_idx`` (1-based by default) and ``parse_web_and_doc`` will
    resolve the idx via ``_attachments.get_fid_by_idx`` and probe IR
    with the matching fid — same shape as production master.
    """
    entries: List[Attachment] = []
    for offset, uf in enumerate(uploaded):
        idx = starting_idx + offset
        entries.append(
            Attachment(idx=idx, file_path=uf.local_path, filename=uf.filename)
        )
    register_attachments(task_id=task_id, entries=entries)
    for entry, uf in zip(entries, uploaded):
        set_fid(task_id=task_id, idx=entry.idx, fid=uf.fid)
    return entries


async def upload_and_register(
    *,
    task_id: str,
    paths: List[str | Path],
    starting_idx: int = 1,
    wait_ready: bool = True,
    ready_timeout_seconds: float = _DEFAULT_READY_TIMEOUT,
) -> List[Attachment]:
    """Top-level convenience for the SFT script.

    Upload every path to Dev Files API, optionally wait for each to
    become ``status=ready`` (so the agent's first ``parse_web_and_doc``
    probe hits IR right away), then register the resulting fids into
    the per-task attachment table.
    """
    uploaded = await upload_many(paths=paths)
    if wait_ready and uploaded:
        await wait_until_ready(
            file_ids=[uf.fid for uf in uploaded],
            timeout_seconds=ready_timeout_seconds,
        )
    return inject_into_task(
        task_id=task_id, uploaded=uploaded, starting_idx=starting_idx,
    )
