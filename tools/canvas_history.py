"""대화 히스토리에서 캔버스 문서의 최신 상태를 복원하는 스캐너 (stateless 서버용).

캔버스 툴셋은 서버에 in-memory 상태를 두지 않고, 매 호출마다
``conversation_history``를 거꾸로 훑어 canvas_id별 최신 plain 본문 + 메타를 재구성한다.

전제 message 형태 (canonical, provider adapter 적용 前):
    {"role": "tool", "name": <tool_name>, "content": <json_str>, "tool_call_id": ...}

source of truth:
  - create_canvasdoc 응답
  - update_canvasdoc.results[] 중 status=="ok" 항목
  (둘 다 마커 없는 plain markdown을 담고 있다.)

skip 대상:
  - get_canvas_status 응답 (마커 부착된 view일 뿐 source가 아님 → 재주입 시 오염 위험)
  - status=="error" update 항목
  - role != "tool" 메시지

공개 API:
  - find_known_canvases(history) : 모든 canvas의 최신 상태 리스트 (last_touched 오름차순)
  - find_latest_doc(history, id) : 특정 canvas_id의 최신 상태 (없으면 None)
"""

import json
from typing import Any, Dict, List, Optional


def _parse_tool_result(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """in: 한 history 메시지 / out: parse된 tool result dict (또는 None).

    content가 string이면 그대로 json.loads.
    멀티모달 모델은 [{"type":"text","text":"..."}] 리스트로 감싸기도 하므로 text만 concat 후 parse.
    role!="tool"이거나 malformed면 None.
    """
    if not isinstance(item, dict):
        return None
    if item.get("role") != "tool":
        return None
    raw = item.get("content")
    if isinstance(raw, list):
        parts = [
            b.get("text") for b in raw
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        raw = "".join(p for p in parts if p)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def find_known_canvases(
    history: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """in: 대화 history / out: 발견된 모든 canvas의 최신 상태 리스트.

    각 항목: {canvas_id, name, type, content, last_touched}
      - last_touched: 가장 최근 source-of-truth 응답의 history index.
      - 순서: last_touched 오름차순 → 호출 측이 [-1]을 active로 선택할 수 있게 정렬.

    구현은 2-pass:
      1) 뒤에서 앞으로 스캔하며 canvas_id별 최신 content + meta 수집 (이미 본 id는 skip).
      2) 앞에서 뒤로 한 번 더 훑어 create_canvasdoc의 name/type으로 backfill
         (update 응답이 name을 비워둔 케이스 대비; create가 가장 안정적인 label).
    """
    if not history:
        return []

    latest_content: Dict[str, str] = {}
    meta: Dict[str, Dict[str, Any]] = {}
    last_touched: Dict[str, int] = {}

    for i in range(len(history) - 1, -1, -1):
        item = history[i]
        result = _parse_tool_result(item)
        if result is None:
            continue
        tool_name = item.get("name", "")

        if tool_name == "update_canvasdoc":
            for r in result.get("results", []) or []:
                if not isinstance(r, dict):
                    continue
                if r.get("status") != "ok":
                    continue
                cid = r.get("canvas_id")
                if not cid:
                    continue
                if cid not in latest_content:
                    latest_content[cid] = r.get("content", "")
                    last_touched.setdefault(cid, i)
                meta.setdefault(cid, {
                    "name": r.get("name", ""),
                    "type": r.get("type", "document"),
                })
        elif tool_name == "create_canvasdoc":
            cid = result.get("canvas_id")
            if not cid:
                continue
            if cid not in latest_content:
                latest_content[cid] = result.get("content", "")
                last_touched.setdefault(cid, i)
            meta.setdefault(cid, {
                "name": result.get("name", ""),
                "type": result.get("type", "document"),
            })

    # Forward pass to backfill name/type from the original create_canvasdoc,
    # which holds the most stable label even if later updates omitted name/type.
    for item in history:
        result = _parse_tool_result(item)
        if result is None:
            continue
        if item.get("name") != "create_canvasdoc":
            continue
        cid = result.get("canvas_id")
        if cid and cid in meta:
            meta[cid] = {
                "name": result.get("name", "") or meta[cid].get("name", ""),
                "type": result.get("type", "") or meta[cid].get("type", "document"),
            }

    canvas_ids = sorted(meta.keys(), key=lambda c: last_touched[c])
    return [{
        "canvas_id": cid,
        "name": meta[cid]["name"],
        "type": meta[cid]["type"] or "document",
        "content": latest_content[cid],
        "last_touched": last_touched[cid],
    } for cid in canvas_ids]


def find_latest_doc(
    history: List[Dict[str, Any]],
    canvas_id: str,
) -> Optional[Dict[str, Any]]:
    """in: history + canvas_id / out: {canvas_id, name, type, content} 또는 None.

    update_canvasdoc가 한 spec의 baseline을 찾을 때 사용 (find_known_canvases는 무거우므로).
    뒤에서 앞으로 스캔하며 최신 update의 content를 잡고, create를 만나면 name/type을
    backfill한 뒤 break.
    """
    if not canvas_id or not history:
        return None
    content: Optional[str] = None
    name = ""
    type_ = "document"

    for i in range(len(history) - 1, -1, -1):
        item = history[i]
        result = _parse_tool_result(item)
        if result is None:
            continue
        tool_name = item.get("name", "")

        if content is None and tool_name == "update_canvasdoc":
            for r in result.get("results", []) or []:
                if not isinstance(r, dict):
                    continue
                if r.get("status") == "ok" and r.get("canvas_id") == canvas_id:
                    content = r.get("content", "")
                    name = r.get("name", "") or name
                    type_ = r.get("type", "") or type_
                    break

        if tool_name == "create_canvasdoc" and result.get("canvas_id") == canvas_id:
            if content is None:
                content = result.get("content", "")
            # Prefer create's name/type as the stable label.
            name = result.get("name", "") or name
            type_ = result.get("type", "") or type_
            break

    if content is None:
        return None
    return {
        "canvas_id": canvas_id,
        "name": name,
        "type": type_ or "document",
        "content": content,
    }


__all__ = [
    "find_known_canvases",
    "find_latest_doc",
]
