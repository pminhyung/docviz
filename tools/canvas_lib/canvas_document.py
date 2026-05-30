"""캔버스 문서 1건의 권위 표현(parse/format/prompt 생성)을 담는 모델.

현재 canvas_tool.py 흐름에서는 직접 사용하지 않으며(canvas_tool은
markers.py facade만 사용), 시뮬레이션·평가 코드용으로 vendor된 객체이다.
"""

import random
from .ast_parser_lib import parse_markdown, format_canvas_with_ids, DocNode

class CanvasDocument:
    """Canvas 문서 1건. 생성 시 즉시 markdown→AST 파싱한다."""
    def __init__(self, content: str, doc_id: str = None, title: str = "Untitled"):
        self.raw_content = content
        self.title = title
        # doc_id 미지정 시 5자리 랜덤 ID 자동 할당 (충돌 확률 ≈ 1/90000).
        self.id = doc_id if doc_id else str(random.randint(10000, 99999))
        self.ast = parse_markdown(content) if content else None

    def update_content(self, new_content: str):
        """본문 갱신 + AST 재파싱."""
        self.raw_content = new_content
        self.ast = parse_markdown(new_content) if new_content else None

    def to_string_with_ids(self, reindex: bool = False) -> str:
        """out: 블록마다 [canvas-block id:...] 부착된 문자열.
        reindex=True면 id를 1부터 재부여(get_canvas_status가 사용하는 방식)."""
        if not self.ast:
            return ""
        return format_canvas_with_ids(self.ast, reindex=reindex)

    def to_markdown(self) -> str:
        """AST → markdown 역변환 (round-trip 검증용).
        주의: 블록 사이 공백은 기본 1줄로 정규화된다."""
        if not self.ast or not hasattr(self.ast, 'children'):
            return ""

        output = []
        for node in self.ast.children:
            if hasattr(node, 'markdown') and node.markdown:
                output.append(node.markdown)

        return "\n\n".join(output)

    def get_prompt_context_block(self, include_legacy_root: bool = False) -> str:
        """모델 프롬프트에 끼워 넣을 'Active Canvas' 컨텍스트 블록 생성.

        include_legacy_root=True면 맨 앞에 root 블록(전체 교체용 reserved)을
        붙인다 — V2 update 프롬프트가 쓰는 형태.
        """
        formatted_content = self.to_string_with_ids()

        if include_legacy_root:
            formatted_content = "[canvas-block id:root]\n(Reserved root block for full-canvas replacement. Content omitted.)\n\n" + formatted_content

        context = f"""## Canvas List:
None

---

## Active Canvas: canvas_{self.id} (name: "{self.title}", type: document)
BEGIN_CANVAS
{formatted_content}
END_CANVAS"""
        return context

    @property
    def is_empty(self) -> bool:
        return not self.raw_content or not self.raw_content.strip()

    def format_full_input(self, user_query: str, selection: dict = None, search_results: list = None) -> str:
        """update 모델 호출용 최종 입력 문자열 조립.

        in:
          - user_query     : 자연어 요청
          - selection      : {'target_block_ids': [...], 'selected_text': '...'}
          - search_results : 검색 결과 리스트 (JSON 직렬화되어 본문에 삽입)
        out: 'Active Canvas + User Selection + User Request' 합쳐진 prompt 문자열.
        """
        # 1) Canvas Context (Active Canvas + BEGIN/END)
        context_block = self.get_prompt_context_block(include_legacy_root=True)

        # 2) User Selection
        if selection:
            target_ids = selection.get("target_block_ids", [])
            selected_txt = selection.get("selected_text", "")
            selection_part = f"## User Selection:\ntarget_block_ids: {target_ids}\nselected_text:\n{selected_txt}"
        else:
            selection_part = "## User Selection:\nNone"

        # 3) User Request (검색 결과 + 질문)
        request_lines = ["## User Request:"]
        if search_results:
            request_lines.append("Search Results:")
            import json
            request_lines.append(json.dumps(search_results, ensure_ascii=False, indent=2))
            request_lines.append("")

        request_lines.append(f"\"{user_query}\"")

        user_request_part = "\n".join(request_lines)

        return f"{context_block}\n\n{selection_part}\n\n{user_request_part}"
