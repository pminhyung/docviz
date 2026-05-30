"""Thin async client for the lgair IR service.

Ported from:
    - lgair model/services/docsearch/doc_search_client.py (add_doc, find_docs)
    - lgair model/services/docsearch/doc_search_service.py (_get_ir_params)

Wire formats preserved exactly so any deployment with an existing
DOC_SEARCH endpoint works as-is.

## SHARED LOGIC

This file is kept byte-identical on the ``master`` and ``sft-gen-ir-shim``
branches. When you edit the logic here, mirror the change to the other
branch's ``exaone/docqa_tools/_ir_client.py`` before merging. The
branches' divergence (idx-only interface, Mode A/B selection) lives in
``handle_parse_web_and_doc.py`` / ``handle_doc_search.py`` / ``handle_*.py``
— NOT here. See ``exaone/docqa_tools/_policy.md`` for the cross-branch
sync table.

## Document flow policy (background)

See ``exaone/docqa_tools/_policy.md`` for the full ranking / ingestion
policy and the production vs ir-shim differences. The short version:

- IR's own ``rerank`` + ``score`` is the ranking primitive for both
  branches. The previous selector microservice helper (``find_score``)
  has been removed — lgair's production pipeline already relied on
  ``rerank=1`` returning sorted results with a ``score`` field, and we
  do the same. (ir-shim Mode A keeps a separate ``sft_pipeline``
  selector locally; that one is unrelated to this client.)
- ``search_fid`` with ``search_pass=1`` doubles as a "is this fid
  indexed?" probe — see ``find_docs(..., search_pass=1)``.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Iterable, List

import aiohttp


DEFAULT_TOP_N = 16
DEFAULT_TIMEOUT_SECONDS = 30


# ─── URL / env resolution ────────────────────────────────────────────────────

def _resolve_ir_url() -> str:
    url = os.environ.get("EXAONE_IR_URL") or os.environ.get("DOC_SEARCH")
    if not url:
        raise RuntimeError(
            "IR URL not configured. "
            "Set EXAONE_IR_URL (preferred) or DOC_SEARCH."
        )
    return url


def _resolve_timeout() -> int:
    raw = os.environ.get("EXAONE_IR_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


def _resolve_top_n() -> int:
    raw = os.environ.get("EXAONE_IR_TOP_N", str(DEFAULT_TOP_N))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_TOP_N


# ─── add_doc — index a parsed document into IR ───────────────────────────────

async def add_doc(
    *,
    user_id: int,
    file_kind: str,
    file_id: str,
    filename: str,
    parsed_docs: List[Dict[str, Any]],
    request_id: str | None = None,
) -> List[int]:
    """POST request_type=add for each parsed page; return doc_ids on success.

    Each entry in ``parsed_docs`` must carry: doc_id, slide_num, context,
    html_context. Matches the wire format of lgair add_doc exactly.
    """
    url = _resolve_ir_url()
    rid = request_id or uuid.uuid4().hex

    request_messages = [
        {
            "request_type": "add",
            "fid": file_id,
            "doc_id": doc["doc_id"],
            "doc_type": file_kind,
            "owner_1": "LG_AI_RESEARCH",
            "owner_2": "1",
            "owner_3": str(user_id),
            "title": filename,
            "context": doc["context"],
            "html_context": doc["html_context"],
            "page_number": doc["slide_num"],
        }
        for doc in parsed_docs
    ]

    data = {
        "inputs": [{"params": [request_messages]}],
        "params": {"inputs_format": "json"},
    }

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=_resolve_timeout())
    ) as session:
        async with session.post(
            url, headers={"X-request-id": rid}, json=data
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"IR add HTTP {resp.status}")
            result = await resp.json()

    recv = result["outputs"][0]
    if isinstance(recv, dict) and recv.get("code") == 104 and recv.get("message") == "Exist Fid":
        return [0]
    if not isinstance(recv, dict):
        raise RuntimeError("IR add returned invalid format")
    if "code" in recv:
        raise RuntimeError(f"IR add error: {recv.get('message')}")
    fail_id = recv.get("results", {}).get("fail_id")
    if fail_id:
        raise RuntimeError(f"IR add fail_id: {fail_id}")
    return recv["results"]["success_id"]


# ─── find_docs — retrieve top-k by query ────────────────────────────────────

def build_search_params(
    *,
    query: str,
    fids: Iterable[str | int],
    reformulated: dict | None = None,
    top_n: int | None = None,
    rerank: bool = True,
    search_pass: int = 0,
) -> Dict[str, Any]:
    """Mirror lgair _get_ir_params: build the request_type=search_fid params.

    ``search_pass=1`` skips the actual search and returns the indexed pages
    for the given fids — used by ``parse_web_and_doc`` as a "is this fid already
    indexed?" probe (and as the source of pages when rehydrating the cache
    from IR without re-running the parser).
    """
    return {
        "inputs": [
            {
                "request_type": "search_fid",
                "question": query,
                "top_n": top_n or _resolve_top_n(),
                "rerank": 1 if rerank else 0,
                "fids": [str(f) for f in fids],
                "reformulated_query": reformulated or {},
                "search_pass": int(search_pass),
            }
        ],
        "params": {"inputs_format": "json"},
    }


async def find_docs(
    *,
    query: str,
    fids: Iterable[str | int],
    has_attached_doc: bool = True,
    reformulated: dict | None = None,
    top_n: int | None = None,
    rerank: bool = True,
    search_pass: int = 0,
    request_id: str | None = None,
) -> List[Dict[str, Any]]:
    """POST search_fid to IR; return hits list (possibly empty).

    Ranking uses IR's own ``rerank=1`` output; the response contains a
    ``score`` field per hit which callers should sort by directly (no
    external selector pass — see module docstring).
    """
    url = _resolve_ir_url()
    rid = request_id or uuid.uuid4().hex
    params = build_search_params(
        query=query,
        fids=fids,
        reformulated=reformulated,
        top_n=top_n,
        rerank=rerank,
        search_pass=search_pass,
    )

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=_resolve_timeout())
    ) as session:
        async with session.post(
            url, headers={"X-request-id": rid}, json=params
        ) as resp:
            if resp.status != 200:
                if not has_attached_doc:
                    return []
                raise RuntimeError(f"IR search HTTP {resp.status}")
            payload = await resp.json()

    if not payload:
        return []
    outputs = payload.get("outputs") or []
    if not outputs or outputs[0] == []:
        return []
    first = outputs[0]
    # IR ships the hit list double-encoded in some deployments:
    # ``outputs=[b'[{"fid": ..., "score": ...}]']`` (bytes / JSON string)
    # rather than a plain Python list — see ir_api.md's success
    # example. Decode here so callers always see ``list[dict]``.
    import json as _json
    if isinstance(first, (bytes, bytearray)):
        first = first.decode("utf-8", errors="replace")
    if isinstance(first, str):
        try:
            first = _json.loads(first)
        except Exception:
            return []
    if isinstance(first, dict):
        # ``outputs=[{"code": ..., "message": ...}]`` is IR's error
        # envelope; treat it as "no hits" so callers can retry or fall
        # through to the parser path.
        return []
    if not isinstance(first, list):
        return []
    return [h for h in first if isinstance(h, dict)]


# NOTE: An earlier revision had ``find_score`` (selector microservice
# rerank). It was removed because IR ``find_docs(rerank=1)`` already
# returns a ``score`` field that lgair production used directly. See
# _policy.md "Selector" entry. ir-shim Mode A's separate sft_pipeline
# selector lives in ``exaone/sft_gen/shim/selector_client.py``.
