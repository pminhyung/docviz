"""canvas 툴셋 단위 + 통합 테스트 (서버 stateless / history 재구성 시나리오).

검증 영역:
  - canvas_id 포맷 (정규식 ^canvas_[1-9]\\d{4}$).
  - create_canvasdoc: 입력 본문에 마커 섞여 와도 strip되어 plain으로 저장, 빈 name 거절.
  - get_canvas_status: 빈 history / create로 복원 / 최신 update 우선 / 실패 update skip /
                       prior status 응답은 source로 쓰지 않음 / 다중 doc 순서 / explicit active override.
  - update_canvasdoc: root 전체 교체, 부분 블록 patch, batch에서 spec 독립성,
                     empty/missing/unknown block_id 거절, 연속 update가 latest content를 이어받음.
  - Registry-level: model_tools 등록·dispatch round-trip, handle_function_call의 messages kw 전달,
                    run_agent._NEVER_PARALLEL_TOOLS에 캔버스 3종 포함 (병렬 실행 시 race 방지).
"""

import json
import re

import pytest

from tools.canvas_tool import (
    get_canvas_status,
    create_canvasdoc,
    update_canvasdoc,
    _new_canvas_id,
)


# ---------------------------------------------------------------------------
# Helpers: 합성 history fixture
# ---------------------------------------------------------------------------

_CALL_ID_COUNTER = 0


def _tool_msg(name: str, result: dict) -> dict:
    """Hermes canonical chat 메시지 shape (role=tool, name, content, tool_call_id)."""
    global _CALL_ID_COUNTER
    _CALL_ID_COUNTER += 1
    return {
        "role": "tool",
        "name": name,
        "content": json.dumps(result),
        "tool_call_id": f"call_test_{_CALL_ID_COUNTER}",
    }


def _create_in_history(name="PRD", type="document", content="# Title\n\nbody"):
    """create_canvasdoc 1회 호출 + 그 응답을 tool 메시지로 감싼 history 반환.
    대부분의 케이스가 '이미 생성된 문서가 있는' 상태에서 시작하므로 공통 fixture."""
    result = json.loads(create_canvasdoc(name=name, type=type, content=content))
    history = [_tool_msg("create_canvasdoc", result)]
    return result, history


# ---------------------------------------------------------------------------
# canvas_id format
# ---------------------------------------------------------------------------

def test_canvas_id_format():
    for _ in range(200):
        cid = _new_canvas_id()
        assert re.fullmatch(r"canvas_[1-9]\d{4}", cid), f"unexpected format: {cid}"


# ---------------------------------------------------------------------------
# create_canvasdoc
# ---------------------------------------------------------------------------

def test_create_returns_flat_with_canvas_id():
    result = json.loads(create_canvasdoc(
        name="PRD", type="document",
        content="# Title\n\nSome body.",
    ))
    assert re.fullmatch(r"canvas_[1-9]\d{4}", result["canvas_id"])
    assert result["name"] == "PRD"
    assert result["type"] == "document"
    assert "[canvas-block id:" not in result["content"]
    assert "# Title" in result["content"]
    assert "is_active" not in result


def test_create_strips_input_markers():
    result = json.loads(create_canvasdoc(
        name="PRD", type="document",
        content="[canvas-block id:99]\n# Title\n",
    ))
    assert "[canvas-block id:" not in result["content"]
    assert "# Title" in result["content"]


def test_create_rejects_empty_name():
    result = json.loads(create_canvasdoc(name="", type="document", content="x"))
    assert "error" in result


def test_create_default_type_when_blank():
    result = json.loads(create_canvasdoc(
        name="X", type="", content="# T",
    ))
    assert result["type"] == "document"


# ---------------------------------------------------------------------------
# get_canvas_status
# ---------------------------------------------------------------------------

def test_get_status_empty_history():
    result = json.loads(get_canvas_status(conversation_history=[]))
    ctx = result["canvas_context"]
    assert ctx["has_active_canvas"] is False
    assert ctx["active_canvas_id"] is None
    assert ctx["canvases"] == []


def test_get_status_recovers_from_create():
    created, history = _create_in_history(name="PRD", content="# Title\n\nbody")
    result = json.loads(get_canvas_status(conversation_history=history))
    ctx = result["canvas_context"]
    assert ctx["has_active_canvas"] is True
    assert ctx["active_canvas_id"] == created["canvas_id"]
    [canvas] = ctx["canvases"]
    assert canvas["canvas_id"] == created["canvas_id"]
    assert canvas["name"] == "PRD"
    assert "[canvas-block id:" in canvas["content"]
    assert canvas["is_active"] is True


def test_get_status_uses_latest_update():
    created, history = _create_in_history(content="# Old")
    update_result = {
        "results": [{
            "status": "ok",
            "canvas_id": created["canvas_id"],
            "name": "PRD",
            "type": "document",
            "content": "# New",
            "updated_block_ids": ["root"],
        }],
        "applied": 1,
        "total": 1,
    }
    history.append(_tool_msg("update_canvasdoc", update_result))

    result = json.loads(get_canvas_status(conversation_history=history))
    canvas = result["canvas_context"]["canvases"][0]
    plain = re.sub(r"\[canvas-block id:[^\]]+\]\n?", "", canvas["content"])
    assert "# New" in plain
    assert "# Old" not in plain


def test_get_status_skips_failed_updates():
    created, history = _create_in_history(content="# Original")
    failed = {
        "results": [{
            "status": "error",
            "canvas_id": created["canvas_id"],
            "error": "unknown block_id(s): ['99']",
        }],
        "applied": 0,
        "total": 1,
    }
    history.append(_tool_msg("update_canvasdoc", failed))

    result = json.loads(get_canvas_status(conversation_history=history))
    canvas = result["canvas_context"]["canvases"][0]
    plain = re.sub(r"\[canvas-block id:[^\]]+\]\n?", "", canvas["content"])
    assert "# Original" in plain


def test_get_status_ignores_prior_status_responses():
    created, history = _create_in_history(content="# Plain")
    prior_status = {
        "canvas_context": {
            "has_active_canvas": True,
            "active_canvas_id": created["canvas_id"],
            "canvases": [{
                "canvas_id": created["canvas_id"],
                "name": "PRD",
                "type": "document",
                "is_active": True,
                "content": "[canvas-block id:1]\n# OldMarkerView\n",
            }],
        }
    }
    history.append(_tool_msg("get_canvas_status", prior_status))

    result = json.loads(get_canvas_status(conversation_history=history))
    canvas = result["canvas_context"]["canvases"][0]
    plain = re.sub(r"\[canvas-block id:[^\]]+\]\n?", "", canvas["content"])
    assert "# Plain" in plain
    assert "# OldMarkerView" not in plain


def test_get_status_multi_docs_orders_by_creation():
    a, history = _create_in_history(name="A", content="# A")
    b_result = json.loads(create_canvasdoc(
        name="B", type="document", content="# B"
    ))
    history.append(_tool_msg("create_canvasdoc", b_result))

    result = json.loads(get_canvas_status(conversation_history=history))
    ctx = result["canvas_context"]
    assert ctx["active_canvas_id"] == b_result["canvas_id"]
    assert [c["canvas_id"] for c in ctx["canvases"]] == [
        a["canvas_id"], b_result["canvas_id"]
    ]


def test_get_status_explicit_active_override():
    a, history = _create_in_history(name="A", content="# A")
    b_result = json.loads(create_canvasdoc(
        name="B", type="document", content="# B"
    ))
    history.append(_tool_msg("create_canvasdoc", b_result))

    result = json.loads(get_canvas_status(
        conversation_history=history,
        active_canvas_id=a["canvas_id"],
    ))
    assert result["canvas_context"]["active_canvas_id"] == a["canvas_id"]


def test_get_status_explicit_active_unknown_falls_back():
    a, history = _create_in_history(name="A", content="# A")
    result = json.loads(get_canvas_status(
        conversation_history=history,
        active_canvas_id="canvas_99999",
    ))
    assert result["canvas_context"]["active_canvas_id"] == a["canvas_id"]


# ---------------------------------------------------------------------------
# update_canvasdoc
# ---------------------------------------------------------------------------

def test_update_whole_rewrite():
    created, history = _create_in_history(content="# Old")
    result = json.loads(update_canvasdoc(
        updates=[{
            "canvas_id": created["canvas_id"],
            "blocks": {"root": "# New\n\nNew body."},
        }],
        conversation_history=history,
    ))
    assert result["total"] == 1 and result["applied"] == 1
    [r] = result["results"]
    assert r["status"] == "ok"
    assert r["canvas_id"] == created["canvas_id"]
    assert r["name"] == "PRD"
    assert r["type"] == "document"
    assert "[canvas-block id:" not in r["content"]
    assert "# New" in r["content"] and "# Old" not in r["content"]
    assert r["updated_block_ids"] == ["root"]
    assert "is_active" not in r


def test_update_partial_block():
    created, history = _create_in_history(
        content="# Title\n\n## Overview\nfoo\n\n## Risks\nbar",
    )
    status = json.loads(get_canvas_status(conversation_history=history))
    tagged = status["canvas_context"]["canvases"][0]["content"]
    assert "[canvas-block id:" in tagged
    available_ids = re.findall(r"\[canvas-block id:([^\]]+)\]", tagged)
    # Need a block id for ## Overview — assume second block (id 2) exists.
    assert "2" in available_ids

    result = json.loads(update_canvasdoc(
        updates=[{
            "canvas_id": created["canvas_id"],
            "blocks": {"2": "## Overview\nUPDATED foo"},
        }],
        conversation_history=history,
    ))
    [r] = result["results"]
    assert r["status"] == "ok"
    assert "[canvas-block id:" not in r["content"]
    assert "UPDATED foo" in r["content"]
    assert "bar" in r["content"]
    assert "is_active" not in r


def test_update_batch_partial_success():
    created, history = _create_in_history(content="# Old")
    result = json.loads(update_canvasdoc(
        updates=[
            {"canvas_id": created["canvas_id"],
             "blocks": {"root": "# New"}},
            {"canvas_id": "canvas_99999",
             "blocks": {"root": "# Ghost"}},
        ],
        conversation_history=history,
    ))
    assert result["total"] == 2 and result["applied"] == 1
    ok, err = result["results"]
    assert ok["status"] == "ok" and "# New" in ok["content"]
    assert err["status"] == "error"
    assert "not found in conversation_history" in err["error"]
    assert err["canvas_id"] == "canvas_99999"


def test_update_rejects_empty_updates():
    result = json.loads(update_canvasdoc(updates=[]))
    assert "error" in result


def test_update_spec_rejects_empty_blocks():
    created, history = _create_in_history()
    result = json.loads(update_canvasdoc(
        updates=[{"canvas_id": created["canvas_id"], "blocks": {}}],
        conversation_history=history,
    ))
    assert result["applied"] == 0
    [r] = result["results"]
    assert r["status"] == "error"


def test_update_spec_rejects_missing_canvas_id():
    result = json.loads(update_canvasdoc(
        updates=[{"canvas_id": "", "blocks": {"root": "y"}}],
        conversation_history=[],
    ))
    assert result["applied"] == 0
    [r] = result["results"]
    assert r["status"] == "error"


def test_update_spec_rejects_unknown_block_id():
    created, history = _create_in_history(content="# Title\n\nbody")
    result = json.loads(update_canvasdoc(
        updates=[{"canvas_id": created["canvas_id"], "blocks": {"999": "ghost"}}],
        conversation_history=history,
    ))
    assert result["applied"] == 0
    [r] = result["results"]
    assert r["status"] == "error"
    assert "unknown block_id" in r["error"]
    assert "999" in r["error"]


def test_update_then_update_uses_latest_content():
    created, history = _create_in_history(content="# v1\n\nbody1")
    first = json.loads(update_canvasdoc(
        updates=[{"canvas_id": created["canvas_id"],
                  "blocks": {"root": "# v2\n\nbody2"}}],
        conversation_history=history,
    ))
    history.append(_tool_msg("update_canvasdoc", first))

    second = json.loads(update_canvasdoc(
        updates=[{"canvas_id": created["canvas_id"],
                  "blocks": {"root": "# v3"}}],
        conversation_history=history,
    ))
    [r] = second["results"]
    assert r["status"] == "ok"
    assert "# v3" in r["content"]
    assert "v1" not in r["content"] and "v2" not in r["content"]


# ---------------------------------------------------------------------------
# Registry-level sanity
# ---------------------------------------------------------------------------

def test_registry_picks_up_canvas_tools():
    import model_tools  # discover_builtin_tools side effect
    from tools.registry import registry

    names = registry.get_all_tool_names()
    assert {"get_canvas_status", "create_canvasdoc",
            "update_canvasdoc"}.issubset(set(names))
    assert registry.get_toolset_for_tool("get_canvas_status") == "canvas"
    assert registry.get_toolset_for_tool("create_canvasdoc") == "canvas"
    assert registry.get_toolset_for_tool("update_canvasdoc") == "canvas"


def test_dispatch_create_then_update():
    """canonical chat messages — full registry dispatch round-trip."""
    import model_tools  # noqa: F401 — import side effect
    from tools.registry import registry

    history = []
    created_raw = registry.dispatch(
        "create_canvasdoc",
        {"name": "demo", "type": "document", "content": "# Hi"},
        conversation_history=history,
    )
    created = json.loads(created_raw)
    history.append({
        "role": "tool", "name": "create_canvasdoc",
        "content": created_raw, "tool_call_id": "call_1",
    })
    cid = created["canvas_id"]
    assert "[canvas-block id:" not in created["content"]

    status_raw = registry.dispatch(
        "get_canvas_status", {}, conversation_history=history,
    )
    status = json.loads(status_raw)
    tagged = status["canvas_context"]["canvases"][0]["content"]
    assert "[canvas-block id:" in tagged

    batch_raw = registry.dispatch(
        "update_canvasdoc",
        {"updates": [{"canvas_id": cid, "blocks": {"1": "# Hi-v2"}}]},
        conversation_history=history,
    )
    batch = json.loads(batch_raw)
    assert batch["applied"] == 1 and batch["total"] == 1
    [updated] = batch["results"]
    assert updated["status"] == "ok"
    assert "# Hi-v2" in updated["content"]
    assert "[canvas-block id:" not in updated["content"]
    assert updated["canvas_id"] == cid


def test_handle_function_call_forwards_messages():
    """handle_function_call's messages kw must propagate to dispatch as conversation_history."""
    from model_tools import handle_function_call

    history = []
    created_raw = handle_function_call(
        "create_canvasdoc",
        {"name": "demo", "type": "document", "content": "# Hi"},
        messages=history,
    )
    created = json.loads(created_raw)
    history.append({
        "role": "tool", "name": "create_canvasdoc",
        "content": created_raw, "tool_call_id": "call_1",
    })
    batch_raw = handle_function_call(
        "update_canvasdoc",
        {"updates": [{"canvas_id": created["canvas_id"],
                      "blocks": {"root": "# Hi-v2"}}]},
        messages=history,
    )
    batch = json.loads(batch_raw)
    assert batch["applied"] == 1
    assert batch["results"][0]["name"] == "demo"


def test_canvas_in_never_parallel_set():
    """run_agent's _NEVER_PARALLEL_TOOLS guards canvas correctness."""
    import importlib

    run_agent = importlib.import_module("run_agent")
    assert "create_canvasdoc" in run_agent._NEVER_PARALLEL_TOOLS
    assert "update_canvasdoc" in run_agent._NEVER_PARALLEL_TOOLS
    assert "get_canvas_status" in run_agent._NEVER_PARALLEL_TOOLS
