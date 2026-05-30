"""canvas_history 스캐너(find_known_canvases / find_latest_doc) 단위 테스트.

핵심 검증:
  - create만 있으면 그게 곧 latest, update.ok가 있으면 그쪽이 우선.
  - status=='error' update와 get_canvas_status 응답은 source-of-truth에서 제외.
  - role!='tool', 비-JSON content는 무시. 멀티모달 content envelope도 지원.
  - find_known_canvases는 last_touched 오름차순 (마지막이 active).
"""

import json

import pytest

from tools.canvas_history import find_known_canvases, find_latest_doc


_CALL_ID_COUNTER = 0


def _tool_msg(name: str, result) -> dict:
    """canonical chat tool 메시지 생성 헬퍼 (테스트 fixture)."""
    global _CALL_ID_COUNTER
    _CALL_ID_COUNTER += 1
    return {
        "role": "tool",
        "name": name,
        "content": json.dumps(result) if not isinstance(result, str) else result,
        "tool_call_id": f"call_test_{_CALL_ID_COUNTER}",
    }


# ---------------------------------------------------------------------------
# find_known_canvases
# ---------------------------------------------------------------------------

def test_scanner_picks_create_when_no_updates():
    history = [_tool_msg("create_canvasdoc", {
        "canvas_id": "canvas_12345", "name": "A",
        "type": "document", "content": "# A",
    })]
    docs = find_known_canvases(history)
    assert len(docs) == 1
    assert docs[0]["content"] == "# A"
    assert docs[0]["name"] == "A"
    assert docs[0]["type"] == "document"


def test_scanner_skips_failed_updates():
    cid = "canvas_12345"
    history = [
        _tool_msg("create_canvasdoc", {
            "canvas_id": cid, "name": "A",
            "type": "document", "content": "# original",
        }),
        _tool_msg("update_canvasdoc", {
            "results": [{"status": "error", "canvas_id": cid,
                         "error": "unknown block_id"}],
            "applied": 0, "total": 1,
        }),
    ]
    docs = find_known_canvases(history)
    assert docs[0]["content"] == "# original"


def test_scanner_skips_get_status_responses():
    cid = "canvas_12345"
    history = [
        _tool_msg("create_canvasdoc", {
            "canvas_id": cid, "name": "A",
            "type": "document", "content": "# plain",
        }),
        _tool_msg("get_canvas_status", {
            "canvas_context": {"canvases": [{
                "canvas_id": cid, "name": "A", "type": "document",
                "is_active": True,
                "content": "[canvas-block id:1]\n# poisoned\n",
            }]},
        }),
    ]
    docs = find_known_canvases(history)
    assert "# plain" in docs[0]["content"]
    assert "poisoned" not in docs[0]["content"]


def test_scanner_latest_update_wins():
    cid = "canvas_12345"
    history = [
        _tool_msg("create_canvasdoc", {
            "canvas_id": cid, "name": "A",
            "type": "document", "content": "# v1",
        }),
        _tool_msg("update_canvasdoc", {
            "results": [{"status": "ok", "canvas_id": cid,
                         "name": "A", "type": "document",
                         "content": "# v2", "updated_block_ids": ["root"]}],
            "applied": 1, "total": 1,
        }),
        _tool_msg("update_canvasdoc", {
            "results": [{"status": "ok", "canvas_id": cid,
                         "name": "A", "type": "document",
                         "content": "# v3", "updated_block_ids": ["root"]}],
            "applied": 1, "total": 1,
        }),
    ]
    docs = find_known_canvases(history)
    assert "# v3" in docs[0]["content"]


def test_scanner_ignores_non_tool_messages():
    history = [
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "네"},
    ]
    assert find_known_canvases(history) == []


def test_scanner_handles_malformed_tool_result():
    history = [
        {"role": "tool", "name": "create_canvasdoc",
         "content": "not-json", "tool_call_id": "c1"},
        {"role": "tool", "name": "create_canvasdoc",
         "content": "{}", "tool_call_id": "c2"},
    ]
    docs = find_known_canvases(history)
    assert docs == []


def test_scanner_handles_multimodal_content_envelope():
    payload = {"canvas_id": "canvas_12345", "name": "A", "type": "document",
               "content": "# A"}
    history = [{
        "role": "tool", "name": "create_canvasdoc",
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "tool_call_id": "c1",
    }]
    docs = find_known_canvases(history)
    assert len(docs) == 1
    assert docs[0]["canvas_id"] == "canvas_12345"


def test_scanner_orders_by_last_touched():
    a = "canvas_11111"
    b = "canvas_22222"
    history = [
        _tool_msg("create_canvasdoc", {
            "canvas_id": a, "name": "A", "type": "document",
            "content": "# A",
        }),
        _tool_msg("create_canvasdoc", {
            "canvas_id": b, "name": "B", "type": "document",
            "content": "# B",
        }),
    ]
    docs = find_known_canvases(history)
    assert [d["canvas_id"] for d in docs] == [a, b]


def test_scanner_update_changes_last_touched():
    a = "canvas_11111"
    b = "canvas_22222"
    history = [
        _tool_msg("create_canvasdoc", {
            "canvas_id": a, "name": "A", "type": "document",
            "content": "# A",
        }),
        _tool_msg("create_canvasdoc", {
            "canvas_id": b, "name": "B", "type": "document",
            "content": "# B",
        }),
        _tool_msg("update_canvasdoc", {
            "results": [{"status": "ok", "canvas_id": a,
                         "name": "A", "type": "document",
                         "content": "# A2", "updated_block_ids": ["root"]}],
            "applied": 1, "total": 1,
        }),
    ]
    docs = find_known_canvases(history)
    assert [d["canvas_id"] for d in docs] == [b, a]


# ---------------------------------------------------------------------------
# find_latest_doc
# ---------------------------------------------------------------------------

def test_find_latest_doc_returns_none_for_unknown():
    assert find_latest_doc([], "canvas_xxxxx") is None
    history = [_tool_msg("create_canvasdoc", {
        "canvas_id": "canvas_12345", "name": "A",
        "type": "document", "content": "# A",
    })]
    assert find_latest_doc(history, "canvas_99999") is None


def test_find_latest_doc_prefers_update_over_create():
    cid = "canvas_12345"
    history = [
        _tool_msg("create_canvasdoc", {
            "canvas_id": cid, "name": "A",
            "type": "document", "content": "# v1",
        }),
        _tool_msg("update_canvasdoc", {
            "results": [{"status": "ok", "canvas_id": cid,
                         "name": "A", "type": "document",
                         "content": "# v2", "updated_block_ids": ["root"]}],
            "applied": 1, "total": 1,
        }),
    ]
    doc = find_latest_doc(history, cid)
    assert doc is not None
    assert doc["content"] == "# v2"
    assert doc["name"] == "A"


def test_find_latest_doc_skips_failed_update():
    cid = "canvas_12345"
    history = [
        _tool_msg("create_canvasdoc", {
            "canvas_id": cid, "name": "A",
            "type": "document", "content": "# original",
        }),
        _tool_msg("update_canvasdoc", {
            "results": [{"status": "error", "canvas_id": cid,
                         "error": "unknown block_id"}],
            "applied": 0, "total": 1,
        }),
    ]
    doc = find_latest_doc(history, cid)
    assert doc is not None
    assert doc["content"] == "# original"


def test_find_latest_doc_backfills_name_from_create():
    """update result without name/type — fallback to create's metadata."""
    cid = "canvas_12345"
    history = [
        _tool_msg("create_canvasdoc", {
            "canvas_id": cid, "name": "CreateName",
            "type": "document", "content": "# v1",
        }),
        _tool_msg("update_canvasdoc", {
            "results": [{"status": "ok", "canvas_id": cid,
                         "name": "", "type": "",
                         "content": "# v2",
                         "updated_block_ids": ["root"]}],
            "applied": 1, "total": 1,
        }),
    ]
    doc = find_latest_doc(history, cid)
    assert doc is not None
    assert doc["content"] == "# v2"
    assert doc["name"] == "CreateName"
    assert doc["type"] == "document"
