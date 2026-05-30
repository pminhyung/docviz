"""Canvas Toolset — 서버 stateless, 매 호출마다 history에서 문서 상태 복원.

3개 tool이 하나의 toolset("canvas")으로 묶여 있다:
  - get_canvas_status : 현재 canvas 목록 + 마커 부착된 본문 반환 (active 자동/명시)
  - create_canvasdoc  : 새 문서 생성 → flat {canvas_id, name, type, content(plain)} 반환
  - update_canvasdoc  : 한 번에 여러 spec(canvas_id+blocks) batch 적용 → results[] 반환

핵심 in/out 패턴:
  - 입력에는 절대 doc 본문을 받지 않는다 (canvas_id만 받음).
  - 서버는 conversation_history(kw로 주입)를 매번 다시 스캔해 baseline을 복원.
  - 응답의 content는 항상 plain markdown (마커 없음).
    마커가 포함된 view는 오직 get_canvas_status의 응답뿐 → 다음 update_canvasdoc의 block_id는
    반드시 직전 get_canvas_status에서 받은 것을 써야 함 (stale id는 잘못된 블록을 patch).

원본 참조: chatexaone-harness/scripts/mcp_servers/canvas_mcp/server.py
"""

import random
import re
from typing import Any, Dict, List, Optional

from tools.registry import registry, tool_error, tool_result
from tools.canvas_lib.markers import (
    strip_markers as _strip_markers,
    render_with_ids as _render_with_ids,
    ensure_markers as _ensure_markers,
    apply_block_updates,
)
from tools.canvas_history import (
    find_known_canvases,
    find_latest_doc,
)


# ---------------------------------------------------------------------------
# canvas_id generation
# ---------------------------------------------------------------------------
def _new_canvas_id() -> str:
    """out: `canvas_<5자리 정수, 첫자리 1~9>`. 충돌 확률 ≈ 1/90000."""
    return f"canvas_{random.randint(10000, 99999)}"


# ---------------------------------------------------------------------------
# get_canvas_status
# ---------------------------------------------------------------------------
def get_canvas_status(
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    active_canvas_id: Optional[str] = None,
) -> str:
    """in: conversation_history(kw 주입) + optional active_canvas_id override
    out: tool_result(canvas_context={has_active_canvas, active_canvas_id, canvases[]}).

    canvases[i].content는 [canvas-block id:N] 마커가 부착된 view (id는 매번 1부터 재부여).
    이게 모델이 다음 update_canvasdoc 호출에 쓸 유일한 권위 있는 block_id 소스이다."""
    history = conversation_history or []
    docs = find_known_canvases(history)

    # 명시된 active_canvas_id가 실제 history에 없으면 무효화 후 자동 선택으로 fallback.
    if active_canvas_id and not any(
        d["canvas_id"] == active_canvas_id for d in docs
    ):
        active_canvas_id = None
    if not active_canvas_id and docs:
        # 자동 선택: 가장 최근에 touch된 문서를 active로.
        active_canvas_id = max(docs, key=lambda d: d["last_touched"])["canvas_id"]

    canvases = []
    for d in docs:
        canvases.append({
            "canvas_id": d["canvas_id"],
            "name": d["name"],
            "type": d["type"],
            "is_active": d["canvas_id"] == active_canvas_id,
            "content": _ensure_markers(d["content"], title=d["name"]),
        })

    return tool_result(canvas_context={
        "has_active_canvas": active_canvas_id is not None,
        "active_canvas_id": active_canvas_id,
        "canvases": canvases,
    })


# ---------------------------------------------------------------------------
# create_canvasdoc — content is plain markdown (no markers)
# ---------------------------------------------------------------------------
def create_canvasdoc(name: str, type: str, content: str) -> str:
    """in: name, type('document'|'code/<lang>'), content(plain markdown)
    out: tool_result(canvas_id, name, type, content) — content는 항상 plain (마커 제거됨).

    LLM이 실수로 마커가 포함된 본문을 넘기더라도 _strip_markers로 정리한다."""
    if not name:
        return tool_error("name must be non-empty")
    canvas_id = _new_canvas_id()
    plain = _strip_markers(content or "")
    return tool_result(
        canvas_id=canvas_id,
        name=name,
        type=type or "document",
        content=plain,
    )


# ---------------------------------------------------------------------------
# update_canvasdoc — batch block edits
# ---------------------------------------------------------------------------
def _apply_one_update(
    spec: Dict[str, Any],
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """in: 한 spec({canvas_id, blocks}) + history / out: result dict (status: 'ok'|'error').

    실패 케이스(모두 status='error' dict로 반환, raise 없음):
      - spec이 dict가 아님 / canvas_id 누락 / blocks 비어있음
      - history에서 해당 canvas_id를 찾을 수 없음
      - blocks에 알 수 없는 block_id 포함 → 부분 적용 없이 spec 전체 실패
    성공: {status:'ok', canvas_id, name, type, content(plain), updated_block_ids}."""
    if not isinstance(spec, dict):
        return {"status": "error", "error": "spec must be an object"}

    canvas_id = spec.get("canvas_id") or ""
    blocks = spec.get("blocks") or {}

    if not canvas_id:
        return {"status": "error", "error": "canvas_id is required"}
    if not blocks or not isinstance(blocks, dict):
        return {
            "status": "error",
            "canvas_id": canvas_id,
            "error": "blocks is empty — nothing to update",
        }

    doc = find_latest_doc(history, canvas_id)
    if doc is None:
        return {
            "status": "error",
            "canvas_id": canvas_id,
            "error": (
                "canvas_id not found in conversation_history "
                "(no prior create_canvasdoc / successful update_canvasdoc)"
            ),
        }
    plain = doc["content"]
    name = doc["name"]
    type_ = doc["type"]

    # plain → 마커 부착(id 1부터 재부여) → applicator에 넘길 baseline 확보.
    tagged = _render_with_ids(plain, title=name)
    available_ids = set(re.findall(r"\[canvas-block id:([^\]]+)\]", tagged))
    requested_ids = {str(k) for k in blocks.keys()}
    # 'root'는 전체 교체용 reserved id이므로 unknown 검사에서 제외.
    unknown = requested_ids - available_ids - {"root"}
    if unknown:
        return {
            "status": "error",
            "canvas_id": canvas_id,
            "error": (
                f"unknown block_id(s): {sorted(unknown)}. "
                f"available: {sorted(available_ids - {'root'})} "
                f"(plus 'root' for whole rewrite). "
                f"call get_canvas_status to refresh block_ids."
            ),
        }

    block_updates = [
        {"block_id": str(bid), "block_content": "" if c is None else str(c)}
        for bid, c in blocks.items()
    ]
    try:
        patched = apply_block_updates(tagged, block_updates)
    except Exception as e:
        return {"status": "error", "canvas_id": canvas_id, "error": str(e)}

    new_plain = _strip_markers(patched)
    return {
        "status": "ok",
        "canvas_id": canvas_id,
        "name": name,
        "type": type_,
        "content": new_plain,
        "updated_block_ids": [u["block_id"] for u in block_updates],
    }


def update_canvasdoc(
    updates: List[Dict[str, Any]],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """in: updates=[{canvas_id, blocks:{block_id:content}}, ...] + history(kw)
    out: tool_result(results=[...], applied=N, total=M).

    각 spec은 독립적으로 처리 — 한 spec 실패가 다른 spec을 막지 않는다.
    배치 내 모든 spec은 같은 pre-call baseline을 보므로, 동일 doc에 대한 분할 spec은
    뒤 것이 앞 것을 덮어쓴다 → doc당 spec 1개 권장."""
    if updates is None:
        return tool_error("updates is empty — pass at least one update spec")
    if not isinstance(updates, list):
        return tool_error("updates must be a list of spec objects")
    if not updates:
        return tool_error("updates is empty — pass at least one update spec")

    history = conversation_history or []
    results = [_apply_one_update(spec, history) for spec in updates]
    applied = sum(1 for r in results if r.get("status") == "ok")
    return tool_result(
        results=results,
        applied=applied,
        total=len(results),
    )


def check_canvas_requirements() -> bool:
    return True


# ---------------------------------------------------------------------------
# Schemas — LLM에 노출되는 tool 명세 (description은 영문 그대로 유지: 모델 입력)
# ---------------------------------------------------------------------------
GET_CANVAS_STATUS_SCHEMA = {
    "name": "get_canvas_status",
    "description": (
        "Returns the current canvas registry view: which docs exist, "
        "which one is active, and each doc's marker-tagged content.\n\n"
        "Takes no doc content as input — the server reconstructs each "
        "doc's latest content by scanning conversation_history for prior "
        "`create_canvasdoc` and successful `update_canvasdoc` responses.\n\n"
        "Use this when:\n"
        "- At the START of any turn that touches a canvas (read, "
        "summarize, whole rewrite, or partial edit). The user may have "
        "edited the doc via UI between turns, so prior "
        "`create_canvasdoc` / `update_canvasdoc` responses in history "
        "are not necessarily the current body.\n"
        "- Immediately before a partial `update_canvasdoc` — REQUIRED "
        "additionally because block_ids are reassigned from 1 on every "
        "status call and stale ids will silently target the wrong "
        "block.\n\n"
        "Response: `canvas_context` with `has_active_canvas`, "
        "`active_canvas_id`, and `canvases[]`. Each entry's `content` "
        "is annotated with `[canvas-block id:N]` markers — this is the "
        "ONLY response shape in which markers appear, and the only "
        "authoritative source of block_ids for your next "
        "`update_canvasdoc` call. Do not invent ids from memory."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "active_canvas_id": {
                "type": "string",
                "description": (
                    "Optional explicit override for which doc is active. "
                    "If omitted, the server picks the most recently touched "
                    "doc (latest create_canvasdoc or successful "
                    "update_canvasdoc)."
                ),
            },
        },
        "required": [],
    },
}

CREATE_CANVASDOC_SCHEMA = {
    "name": "create_canvasdoc",
    "description": (
        "Open a new canvas document — a server-assigned, iterable "
        "artifact intended for block-level refinement.\n\n"
        "Use when the user's request asks for a document-style artifact "
        "the user is likely to refine further: drafts, plans, reports, "
        "articles, structured writeups, longer code held together as one "
        "unit. Do NOT use for short factoid lookups, single-line answers, "
        "or conversational replies — those don't benefit from block-level "
        "iteration.\n\n"
        "Server assigns a fresh `canvas_id` (format: `canvas_<5digits>`) "
        "and returns a flat `{canvas_id, name, type, content}`. "
        "`content` in the response is plain markdown — never contains "
        "`[canvas-block id:N]` markers (markers are emitted only by "
        "`get_canvas_status`). The just-created doc becomes the active "
        "canvas (visible via the next `get_canvas_status` call). For "
        "later block-level edits, call `get_canvas_status` first to "
        "receive a marker-tagged view; the server reconstructs this "
        "create response from conversation history."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Human-readable doc name. Used as display label. "
                    "Pick something specific: 'Outline: renewables vs "
                    "global GDP' beats 'Outline'."
                ),
            },
            "type": {
                "type": "string",
                "description": (
                    "`'document'` for prose; `'code/<lang>'` for code "
                    "(e.g. `'code/python'`)."
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "Initial markdown body. Plain — do NOT include "
                    "`[canvas-block id:N]` markers. Markers are only "
                    "emitted by `get_canvas_status`; this response, like "
                    "all create/update responses, stays plain."
                ),
            },
        },
        "required": ["name", "type", "content"],
    },
}

UPDATE_CANVASDOC_SCHEMA = {
    "name": "update_canvasdoc",
    "description": (
        "Apply one or more block-level edits to canvas docs. Each spec "
        "in `updates[]` targets one doc by `canvas_id`.\n\n"
        "Use when an existing canvas doc needs revision — either a "
        "whole-doc rewrite or block-level patches.\n\n"
        "**Tool-intrinsic precursor for ANY edit (whole rewrite OR "
        "partial)**: call `get_canvas_status` first. The user may have "
        "edited the doc via UI between turns, so prior responses in "
        "history may not match the current body — confirm against a "
        "fresh status read before writing. For partial edits, the "
        "`block_id`s you pass MUST also come from that response's "
        "marker-tagged content; ids are reassigned from 1 every status "
        "call, so stale ids silently target the wrong block. You do NOT "
        "pass the doc body; the server resolves each spec's doc by "
        "scanning conversation_history for the latest `create_canvasdoc` "
        "or successful `update_canvasdoc` response with that "
        "`canvas_id`.\n\n"
        "Two modes per spec:\n"
        "- Whole rewrite: `blocks={'root': '<full new body>'}` — resets "
        "the doc.\n"
        "- Partial edit: `blocks={'<block_id>': '<full new content of "
        "that block>', ...}` — provide the COMPLETE new content of each "
        "block, never a fragment or diff. If any `block_id` is not "
        "present in the current doc, the WHOLE spec fails with "
        "`unknown block_id(s)` (no partial application); re-call "
        "`get_canvas_status` for fresh markers and retry.\n\n"
        "For docs whose `type` starts with `'code/'`, prefer whole "
        "rewrite — partial edits on code risk breaking imports, "
        "indentation, or fences.\n\n"
        "Response: `{results, applied, total}`. Each `results[i]` "
        "carries `status: 'ok'|'error'`. On ok: `content` (plain "
        "markdown, no markers — becomes the next history-scan "
        "source-of-truth), `updated_block_ids`, `name`, `type`. "
        "On error: `error` (plus `canvas_id` when known). "
        "Specs are independent — one failing spec does NOT abort the "
        "others.\n\n"
        "Batch semantics: multiple specs in one `updates[]` are applied "
        "independently and all see the same pre-call baseline. Send one "
        "spec per doc per call. Splitting edits to the same doc across "
        "multiple specs would cause the second spec to overwrite the "
        "first — they don't observe each other."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "updates": {
                "type": "array",
                "description": (
                    "One or more update specs. Each spec is applied "
                    "independently and produces one entry in `results[]`."
                ),
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "canvas_id": {
                            "type": "string",
                            "description": (
                                "From the doc's prior create/update "
                                "response. Server looks up name/type/"
                                "current_content via history scan."
                            ),
                        },
                        "blocks": {
                            "type": "object",
                            "description": (
                                "Map of block_id (or 'root') to the "
                                "full new content of that block."
                            ),
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "required": ["canvas_id", "blocks"],
                },
            },
        },
        "required": ["updates"],
    },
}


# 3개 tool 모두 toolset="canvas" 묶음 — registry.dispatch 시 kw로 conversation_history가 주입됨.
registry.register(
    name="get_canvas_status",
    toolset="canvas",
    schema=GET_CANVAS_STATUS_SCHEMA,
    handler=lambda args, **kw: get_canvas_status(
        conversation_history=kw.get("conversation_history"),
        active_canvas_id=args.get("active_canvas_id"),
    ),
    check_fn=check_canvas_requirements,
    emoji="🎨",
)
registry.register(
    name="create_canvasdoc",
    toolset="canvas",
    schema=CREATE_CANVASDOC_SCHEMA,
    handler=lambda args, **kw: create_canvasdoc(
        name=args.get("name", ""),
        type=args.get("type", "document"),
        content=args.get("content", ""),
    ),
    check_fn=check_canvas_requirements,
    emoji="🎨",
)
registry.register(
    name="update_canvasdoc",
    toolset="canvas",
    schema=UPDATE_CANVASDOC_SCHEMA,
    handler=lambda args, **kw: update_canvasdoc(
        updates=args.get("updates"),
        conversation_history=kw.get("conversation_history"),
    ),
    check_fn=check_canvas_requirements,
    emoji="🎨",
)
