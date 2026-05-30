"""Thin async client for the lgair doc_parser microservice.

Ported from lgair: ``model/dao/doc_dao.py::_parse_doc``.
Wire contract preserved so any deployment with DOC_PARSER URL works as-is.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Dict, Tuple

import aiohttp


SUPPORTED_EXTENSIONS = ("pdf", "pptx", "docx", "hwpx", "hwp")

DEFAULT_PARSER_VERSION = "3.0"
DEFAULT_WEB_PARSER_VERSION = "3.3"
DEFAULT_TIMEOUT_SECONDS = 60


def _resolve_url() -> str:
    url = os.environ.get("EXAONE_DOC_PARSER_URL") or os.environ.get("DOC_PARSER")
    if not url:
        raise RuntimeError(
            "doc_parser URL not configured. "
            "Set EXAONE_DOC_PARSER_URL (preferred) or DOC_PARSER."
        )
    return url


def _resolve_timeout() -> int:
    raw = os.environ.get("EXAONE_DOC_PARSER_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


async def parse_document(
    *,
    filename: str,
    raw_bytes: bytes,
    request_id: str | None = None,
    version: str = DEFAULT_PARSER_VERSION,
) -> Tuple[Dict[str, list], Dict[str, list]]:
    """POST file to doc_parser; return (html_parsed, list_parsed).

    Both returned dicts are keyed by page/slide number (as string)
    mapping to a list of parsed content strings.

    Wire format mirrors lgair exactly so deployments can keep the same
    DOC_PARSER service.
    """
    url = _resolve_url()
    timeout = _resolve_timeout()
    rid = request_id or uuid.uuid4().hex

    form = aiohttp.FormData()
    form.add_field("inputs", raw_bytes, filename=filename)
    form.add_field(
        "params",
        json.dumps(
            {"inputs_format": "bytes", "filename": filename, "version": version}
        ),
    )

    headers = {"X-request-id": rid}

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout)
    ) as session:
        async with session.post(url, headers=headers, data=form) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"doc_parser HTTP {resp.status}: {body[:300]}"
                )
            payload = await resp.json()

    outputs = payload.get("outputs") or []
    if not outputs:
        raise RuntimeError("doc_parser returned no outputs")
    result = outputs[0] or {}
    return result.get("html_parsed", {}), result.get("list_parsed", {})


async def parse_web(
    *,
    url: str,
    request_id: str | None = None,
    version: str = DEFAULT_WEB_PARSER_VERSION,
) -> Tuple[Dict[str, list], Dict[str, list]]:
    """POST a URL to doc_parser via the WebParser request_type.

    Wire shape per BE 명세:

        params = {
            "inputs_format": "bytes",
            "version":       "3.3",
            "file_id":       "dummy_id",
            "request_type":  "WebParser",
            "url":           <input_url>,
        }

    Response shape matches ``parse_document`` so downstream code can
    treat the result uniformly: ``(html_parsed, list_parsed)`` two
    page-keyed dicts.

    The ``file_id`` field is a parser-side placeholder ("dummy_id")
    and does NOT round-trip to anything we cache; the caller is
    responsible for deriving its own fid (e.g. hash of the URL) when
    populating the per-task document cache.
    """
    parser_url = _resolve_url()
    timeout = _resolve_timeout()
    rid = request_id or uuid.uuid4().hex

    body = {
        "inputs_format": "bytes",
        "version":       version,
        "file_id":       "dummy_id",
        "request_type":  "WebParser",
        "url":           url,
    }
    form = aiohttp.FormData()
    form.add_field("params", json.dumps(body))

    headers = {"X-request-id": rid}

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout)
    ) as session:
        async with session.post(parser_url, headers=headers, data=form) as resp:
            if resp.status != 200:
                err = await resp.text()
                raise RuntimeError(
                    f"web_parser HTTP {resp.status}: {err[:300]}"
                )
            payload = await resp.json()

    outputs = payload.get("outputs") or []
    if not outputs:
        raise RuntimeError("web_parser returned no outputs")
    result = outputs[0] or {}
    return result.get("html_parsed", {}), result.get("list_parsed", {})
