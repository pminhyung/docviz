"""캔버스 블록 마커(`[canvas-block id:N]`) 처리 파사드.

canvas_tool.py가 쓰는 3가지 변환만 노출:
  - strip_markers : 마커 제거 → 순수 markdown
  - render_with_ids : 순수 markdown → 마커 부착 (id는 1부터 재부여)
  - ensure_markers : 이미 마커가 있으면 그대로, 없으면 render
ast_parser_lib(parse → format)와 canvas_tool_applicator(apply_block_updates)
위에 얇게 얹은 facade이다.
"""

import re

from .ast_parser_lib import parse_markdown, format_canvas_with_ids
from .canvas_tool_applicator import apply_block_updates  # re-export

# 줄 시작 위치의 `[canvas-block id:...]` 라인만 매칭 (본문 중간 등장은 보존).
_MARKER_PATTERN = re.compile(r"^\[canvas-block id:[^\]]+\]\n?", re.MULTILINE)


def strip_markers(content: str) -> str:
    """in: 마커 포함 markdown / out: 마커 라인 제거된 순수 markdown."""
    if not content:
        return content
    return _MARKER_PATTERN.sub("", content)


def render_with_ids(plain_markdown: str, title: str = "") -> str:
    """in: 순수 markdown / out: 블록마다 `[canvas-block id:N]\\n<블록>\\n` 부착.

    호출할 때마다 id를 1부터 재부여하므로, 모델에 노출되는 block_id는
    항상 최신 get_canvas_status의 값이어야 한다 (stale id 사용 금지).
    """
    if not plain_markdown:
        return ""
    ast = parse_markdown(plain_markdown)
    return format_canvas_with_ids(ast, reindex=True)


def ensure_markers(content: str, title: str = "") -> str:
    """이미 마커가 있으면 pass-through, 없으면 render_with_ids."""
    if not content:
        return ""
    if "[canvas-block id:" in content:
        return content
    return render_with_ids(content, title=title)


__all__ = [
    "strip_markers",
    "render_with_ids",
    "ensure_markers",
    "apply_block_updates",
]
