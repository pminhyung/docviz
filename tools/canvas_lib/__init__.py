"""캔버스 AST 파서 + 블록 단위 patch 적용기 묶음.

원본 출처: chatexaone-harness/scripts/mcp_servers/canvas_mcp/canvas_lib/
해당 디렉터리에서 본 harness로 vendor-in한 코드이며, canvas_tool에서만 사용한다.

공개 API:
  - CanvasDocument        : 단일 문서 표현 (parse/format/prompt 생성)
  - apply_block_updates   : {block_id, block_content} 리스트로 직접 patch
  - apply_tool_edits      : <tool_call> XML을 받아 parse 후 patch (시뮬레이션용)
  - extract_tool_updates  : XML → updates 리스트만 추출
"""

from .canvas_document import CanvasDocument
from .canvas_tool_applicator import (
    apply_block_updates,
    apply_tool_edits,
    extract_tool_updates,
)

__all__ = [
    "CanvasDocument",
    "apply_block_updates",
    "apply_tool_edits",
    "extract_tool_updates",
]
