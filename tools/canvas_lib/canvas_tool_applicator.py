"""모델이 만든 update 결과를 실제 markdown 문자열에 패치 적용하는 모듈.

핵심 API:
  - extract_tool_updates(xml)              : <tool_call> XML → [{block_id, block_content}]
  - apply_tool_edits(raw_text, xml)        : raw markdown + XML → 패치 적용된 markdown
  - apply_block_updates(raw_text, updates) : raw markdown + updates 리스트 → 패치 적용된 markdown

전략은 AST 재구성이 아니라 **문자열 마커 split-replace** —
`[canvas-block id:N]`를 anchor로 잡아 다음 마커 직전까지가 그 블록의 본문이라고 보고 교체한다.
(AST 재파싱 시 id가 새로 부여되어 LLM이 가진 컨텍스트와 mismatch나는 문제를 회피.)
"""

import re
import sys
import uuid
from typing import Dict, Optional, List
from .canvas_document import CanvasDocument


# 원본 applicator는 stdout으로 print했으나, stdio MCP 서버는 stdout이 JSON-RPC 채널이므로
# 진단 로그는 stderr로 라우팅해야 한다. (harness 로그에는 남는다.)
def _log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def extract_tool_updates(tool_xml: str) -> List[Dict[str, str]]:
    """in: <tool_call>update_canvasdoc ...</tool_call> 문자열
    out: [{'block_id', 'block_content'}, ...] (root 업데이트도 포함).

    XML 안의 <arg_key>/<arg_value> 쌍을 순차 스캔해 block_id 다음에 오는 block_content와 짝짓는다.
    'None' 문자열은 None으로 변환하고, LLM이 literal `\\n`로 escape한 줄바꿈은 실제 개행으로 복원.
    """
    updates = []
    
    # 1. Regex to find the tool call block
    # We look for <tool_call>update_canvasdoc ... </tool_call>
    # There might be multiple tool calls (though usually one for update_canvasdoc)
    tool_matches = re.finditer(r'<tool_call>update_canvasdoc(.*?)</tool_call>', tool_xml, re.DOTALL)
    
    for tm in tool_matches:
        inner = tm.group(1)
        
        # 2. Extract block_id and block_content pairs
        # The prompt structure enforces: 
        # <arg_key>block_id</arg_key><arg_value>ID</arg_value>
        # <arg_key>block_content</arg_key><arg_value>CONTENT</arg_value>
        
        # We can scan sequentially
        # Find all keys and values
        args = re.findall(r'<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>', inner, re.DOTALL)
        
        current_id = None
        
        for key, value in args:
            key = key.strip()
            # value might have leading/trailing newlines which we generally want to preserve for content,
            # but for IDs we should strip.
            
            if key == 'block_id':
                current_id = value.strip()
                if current_id == 'None': current_id = None
                
            elif key == 'block_content':
                content = value # Do NOT strip content recklessly, but maybe strictly needed? 
                # Usually standard markdown blocks don't need leading/trailing whitespace around the meaningful text,
                # but `format_canvas_with_ids` adds newlines.
                # Let's strip only external wrapper whitespace if any.
                # Actually, the model output might include extra indentation.
                # We'll valid strip basic start/end whitespace.
                if content.strip() == 'None':
                    content = None
                else:
                    # Unescape literal \n sequences often produced by LLMs in XML/JSON
                    content = content.replace('\\n', '\n')
                    content = content.strip()
                
                if current_id and content is not None:
                    updates.append({
                        'block_id': current_id,
                        'block_content': content
                    })
                # Reset ID after using it (pairs come in order)
                current_id = None
    return updates

def apply_tool_edits(raw_text: str, tool_xml: str) -> str:
    """in: 마커 부착된 markdown + tool_call XML / out: 패치 후 순수 markdown.

    내부적으로 extract_tool_updates → apply_block_updates와 동일 로직을 수행.
    시뮬레이션/평가 코드에서 XML 형태로 들어올 때 쓰는 진입점.
    """
    def finalize_doc(text: str) -> str:
        # 모든 마커 라인을 떼고 reserved root 안내 문구도 제거 → 순수 markdown 반환.
        clean = re.sub(r'\[canvas-block id:[^\]]+\]\n?', '', text)
        clean = clean.replace("(Reserved root block for full-canvas replacement. Content omitted.)", "")
        return clean.strip()

    if not tool_xml or "<tool_call>" not in tool_xml:
        return finalize_doc(raw_text)
        
    updates = extract_tool_updates(tool_xml)
    if not updates:
        return finalize_doc(raw_text)

    # 마커가 박힌 문자열 상에서 직접 split-replace한다 (AST 우회).
    current_text = raw_text

    for up in updates:
        b_id = up['block_id']
        b_content = up['block_content']

        if b_id == 'root':
            # root는 전체 본문 교체 신호.
            return finalize_doc(b_content)

        marker = f"[canvas-block id:{b_id}]"

        if marker not in current_text:
            # stale id 등 — 해당 블록은 그냥 skip하고 다음 update로 진행.
            _log(f"[Applicator] Warning: Block ID {b_id} not found.")
            continue

        parts = current_text.split(marker)
        if len(parts) < 2:
            continue

        pre = parts[0]
        post = parts[1]

        # 이 블록의 끝 = 다음 `[canvas-block id:` 직전 (또는 EOF).
        next_match = re.search(r'\[canvas-block id:', post)
        
        if next_match:
            # 치환 전: 기존 블록 내용 추출 (다음 블록 시작 직전까지)
            old_content = post[:next_match.start()].strip()
            _log(f"\n{'='*60}")
            _log(f"[REPLACE] block_id: {b_id}")
            _log(f"[BEFORE ] 기존 내용:\n  {old_content[:150]}")
            _log(f"[AFTER  ] 새로운 내용:\n  {(b_content or '(삭제됨)')[:150]}")
            _log(f"{'='*60}")
            
            # We preserve everything from the start of the next block onwards
            rest = post[next_match.start():]
            # Pattern: [id]\nContent\n\n[next-id]
            if b_content:
                new_block_str = f"\n{b_content}\n\n"
            else:
                # If content is empty, just provide the newline for the ID itself
                new_block_str = f"\n"
            current_text = pre + marker + new_block_str + rest
        else:
            # EOF
            old_content = post.strip()
            _log(f"\n{'='*60}")
            _log(f"[REPLACE] block_id: {b_id} (마지막 블록)")
            _log(f"[BEFORE ] 기존 내용:\n  {old_content[:150]}")
            _log(f"[AFTER  ] 새로운 내용:\n  {(b_content or '(삭제됨)')[:150]}")
            _log(f"{'='*60}")
            new_block_str = f"\n{b_content}\n" if b_content else "\n"
            current_text = pre + marker + new_block_str

    return finalize_doc(current_text)


def apply_block_updates(raw_text: str, updates: List[Dict[str, str]]) -> str:
    """in: 마커 부착된 markdown + [{block_id, block_content}, ...]
    out: 패치 후 순수 markdown (마커 제거됨).

    canvas_tool.update_canvasdoc가 호출하는 진입점.
    block_id='root'면 본문 전체 교체, 그 외는 마커 anchor split-replace.
    알 수 없는 block_id는 경고 후 skip (전체 fail 아님).
    """
    def finalize_doc(text: str) -> str:
        clean = re.sub(r'\[canvas-block id:[^\]]+\]\n?', '', text)
        clean = clean.replace("(Reserved root block for full-canvas replacement. Content omitted.)", "")
        return clean.strip()

    if not updates:
        return finalize_doc(raw_text)

    current_text = raw_text
    for up in updates:
        b_id = up['block_id']
        b_content = up['block_content']

        if b_id == 'root':
            return finalize_doc(b_content)

        marker = f"[canvas-block id:{b_id}]"
        if marker not in current_text:
            _log(f"[Applicator] Warning: Block ID {b_id} not found.")
            continue

        parts = current_text.split(marker)
        if len(parts) < 2:
            continue
        pre = parts[0]
        post = parts[1]

        next_match = re.search(r'\[canvas-block id:', post)
        if next_match:
            old_content = post[:next_match.start()].strip()
            _log(f"\n{'='*60}")
            _log(f"[REPLACE] block_id: {b_id}")
            _log(f"[BEFORE ] 기존 내용:\n  {old_content[:150]}")
            _log(f"[AFTER  ] 새로운 내용:\n  {(b_content or '(삭제됨)')[:150]}")
            _log(f"{'='*60}")
            rest = post[next_match.start():]
            if b_content:
                new_block_str = f"\n{b_content}\n\n"
            else:
                new_block_str = "\n"
            current_text = pre + marker + new_block_str + rest
        else:
            old_content = post.strip()
            _log(f"\n{'='*60}")
            _log(f"[REPLACE] block_id: {b_id} (마지막 블록)")
            _log(f"[BEFORE ] 기존 내용:\n  {old_content[:150]}")
            _log(f"[AFTER  ] 새로운 내용:\n  {(b_content or '(삭제됨)')[:150]}")
            _log(f"{'='*60}")
            new_block_str = f"\n{b_content}\n" if b_content else "\n"
            current_text = pre + marker + new_block_str

    return finalize_doc(current_text)
