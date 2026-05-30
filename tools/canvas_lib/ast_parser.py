"""Canvas AST 스키마 + 라인 기반 fallback 파서.

ast_parser_lib(markdown-it 기반)가 사용하는 노드 타입(DocNode, HeadingNode, ...)과
inline 파서(parse_inline)를 이 파일에서 정의·공급한다.
ast_parser_lib가 실패하거나 호출되지 않는 환경에서도 동일 스키마의 parse_markdown을
독립적으로 제공한다 (라인 기반 정규식 파서).

주요 in/out:
  - parse_markdown(md)            : markdown → DocNode (헤딩 hierarchy 포함)
  - build_hierarchy(flat_blocks)  : flat block list → heading level 기반 트리
  - find_all_blocks_in_range      : 문자 [start,end] 구간에 걸리는 leaf block 수집
  - simple_hash_base36            : 블록 안정 id 생성을 위한 32bit hash → base36
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Union, Literal, Dict, Any

# ----------------------------
# 1) AST 스키마 (노드 타입 정의)
# ----------------------------

NodeID = str
NodeType = Literal[
    "doc", "heading", "paragraph", "blockquote", "list", "list_item",
    "hr", "text", "strong", "code_inline", "code_block",
    "table", "table_row", "table_cell"
]

@dataclass
class Span:
    start: int  # 'from' is a reserved keyword in Python
    end: int    # 'to'

@dataclass
class AstNodeBase:
    id: NodeID
    type: NodeType
    markdown: str = ""
    span: Optional[Span] = None

@dataclass
class TextNode(AstNodeBase):
    type: Literal["text"] = "text"
    text: str = ""

@dataclass
class CodeInlineNode(AstNodeBase):
    type: Literal["code_inline"] = "code_inline"
    code: str = ""

@dataclass
class StrongNode(AstNodeBase):
    type: Literal["strong"] = "strong"
    children: List['InlineNode'] = field(default_factory=list)

InlineNode = Union[TextNode, StrongNode, CodeInlineNode]

@dataclass
class HeadingNode(AstNodeBase):
    type: Literal["heading"] = "heading"
    level: int = 1
    children: List[InlineNode] = field(default_factory=list)
    sub_blocks: List['BlockNode'] = field(default_factory=list) # For hierarchy support

@dataclass
class ParagraphNode(AstNodeBase):
    type: Literal["paragraph"] = "paragraph"
    children: List[InlineNode] = field(default_factory=list)

@dataclass
class BlockquoteNode(AstNodeBase):
    type: Literal["blockquote"] = "blockquote"
    children: List['BlockNode'] = field(default_factory=list)

@dataclass
class ListItemNode(AstNodeBase):
    type: Literal["list_item"] = "list_item"
    children: List['BlockNode'] = field(default_factory=list)

@dataclass
class ListNode(AstNodeBase):
    type: Literal["list"] = "list"
    ordered: bool = False
    items: List[ListItemNode] = field(default_factory=list)

@dataclass
class HrNode(AstNodeBase):
    type: Literal["hr"] = "hr"

@dataclass
class CodeBlockNode(AstNodeBase):
    type: Literal["code_block"] = "code_block"
    language: str = ""
    text: str = ""

# Table nodes omitted for simplicity as they weren't fully implemented in the reference parser logic provided
# but can be added if needed.

BlockNode = Union[
    HeadingNode, ParagraphNode, BlockquoteNode, ListNode, HrNode, CodeBlockNode
]

@dataclass
class DocNode(AstNodeBase):
    type: Literal["doc"] = "doc"
    children: List[BlockNode] = field(default_factory=list)


# ----------------------------
# 2) 블록 ID 생성 유틸 (markdown 내용 기반 안정 hash)
# ----------------------------

def simple_hash(s: str) -> str:
    hash_val = 0
    for char in s:
        code = ord(char)
        hash_val = ((hash_val << 5) - hash_val) + code
        hash_val &= 0xFFFFFFFF  # Convert to 32bit integer
    
    # Convert to base36 string
    return abs(hash_val).to_bytes((abs(hash_val).bit_length() + 7) // 8 or 1, 'big').hex() # Simplified hex for Python

def simple_hash_base36(s: str) -> str:
    # Python doesn't have a built-in base36 encoder for negative numbers exactly like JS
    # implementing a simple version
    hash_val = 0
    for char in s:
        code = ord(char)
        hash_val = ((hash_val << 5) - hash_val) + code
        hash_val &= 0xFFFFFFFF # Force 32-bit
    
    # Handle negative numbers for JS compatibility if needed, but for now just abs
    val = abs(hash_val)
    if val == 0: return "0"
    
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    res = ""
    while val > 0:
        val, r = divmod(val, 36)
        res = digits[r] + res
    return res

# ----------------------------
# 3) 라인 기반 블록 파서 유틸 (matcher들)
# ----------------------------

@dataclass
class Line:
    text: str
    start: int
    end: int
    raw: str

def to_lines(md: str) -> List[Line]:
    lines = []
    offset = 0
    raw_lines = md.split("\n")
    for raw in raw_lines:
        start = offset
        end = offset + len(raw)
        lines.append(Line(text=raw, start=start, end=end, raw=raw))
        offset = end + 1 # +1 for newline
    return lines

def is_blank(line: Line) -> bool:
    return len(line.text.strip()) == 0

def match_heading(line: Line):
    m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line.text)
    if not m:
        return None
    return {"level": len(m.group(1)), "content": m.group(2)}

def is_hr(line: Line) -> bool:
    return bool(re.match(r"^\s*---\s*$", line.text))

def match_blockquote(line: Line):
    m = re.match(r"^\s*>\s?(.*)$", line.text)
    if not m:
        return None
    return {"content": m.group(1)}

def match_list_item(line: Line):
    # indent
    indent_match = re.match(r"^(\s*)(.*)$", line.text)
    if not indent_match:
        return None
    indent = len(indent_match.group(1))
    rest = indent_match.group(2)
    
    # unordered: -, *
    m = re.match(r"^([-*])\s+(.+?)\s*$", rest)
    if m:
        return {"ordered": False, "indent": indent, "content": m.group(2)}
    
    # ordered: 1.
    m = re.match(r"^(\d+)\.\s+(.+?)\s*$", rest)
    if m:
        return {"ordered": True, "indent": indent, "content": m.group(2)}
    
    return None

# ----------------------------
# 4) Inline 파서 (`**bold**`, `` `code` `` 2종만 지원)
# ----------------------------

def parse_inline(text: str, base_start: int, id_gen) -> List[InlineNode]:
    """in: 한 블록의 raw text + 문서 내 base offset / out: InlineNode 리스트.

    backtick `code` 와 `**strong**` 만 처리하고 나머지는 TextNode.
    unbalanced marker(짝이 안 맞는 ` 또는 **)는 일반 텍스트로 흡수한다."""
    nodes: List[InlineNode] = []
    i = 0
    
    def push_text(s: str, start: int, end: int):
        if not s: return
        nodes.append(TextNode(
            id=id_gen(),
            text=s,
            span=Span(start, end)
        ))

    while i < len(text):
        # Code inline: `...`
        if text[i] == '`':
            end = text.find('`', i + 1)
            if end > i:
                code_content = text[i+1:end]
                nodes.append(CodeInlineNode(
                    id=id_gen(),
                    code=code_content,
                    span=Span(base_start + i, base_start + end + 1)
                ))
                i = end + 1
                continue
            # Fallthrough if no closing backtick (unbalanced)
        
        # Strong: **...**
        if text.startswith('**', i):
            end = text.find('**', i + 2)
            if end > i:
                inner = text[i+2:end]
                nodes.append(StrongNode(
                    id=id_gen(),
                    children=parse_inline(inner, base_start + i + 2, id_gen),
                    span=Span(base_start + i, base_start + end + 2)
                ))
                i = end + 2
                continue
            # Fallthrough if no closing stars (unbalanced)
        
        # Text
        next_special = len(text)
        next_backtick = text.find('`', i)
        next_star = text.find('**', i)
        
        # If we fell through (unbalanced marker at i), we must ensure we don't pick it up again as the "next special" at the same position 'i'.
        # We should treat the current character as text and look for the next special AFTER it.
        
        # Adjust search range if we are currently sitting on a potential marker start that failed matching
        search_start = i
        
        # Actually, simpler logic:
        # If we are at '`' or '**' but failed to match (fallthrough),
        # we treat the current marker characters as plain text.
        # But `next_backtick` / `next_star` searches from `i`.
        # If text[i] is '`', next_backtick will be i.
        # So next_special becomes i.
        # push_text(i:i) -> empty.
        # i = i -> Infinite loop.
        
        # FIX:
        # If next_special == i, it means we found a marker at 'i' that failed the check above.
        # We must advance at least 1 char.
        
        valid_next_special = len(text)
        
        # Find next ` OR ** strictly AFTER i (or at i if we are not currently at one?)
        # Actually, it's safer to just iterate:
        # If text[i] is a marker char that failed (unbalanced), we just consume it as text.
        
        if next_backtick != -1 and next_backtick < valid_next_special:
             # Only valid if it's NOT the one we just failed?
             # If next_backtick == i, we know it failed (otherwise we would have 'continue'd).
             # So we should skip it.
             if next_backtick == i:
                 # Look for next one
                 next_backtick = text.find('`', i + 1)
             
             if next_backtick != -1 and next_backtick < valid_next_special:
                 valid_next_special = next_backtick

        if next_star != -1 and next_star < valid_next_special:
            if next_star == i:
                 next_star = text.find('**', i + 1) # Advance past current failed star
            
            if next_star != -1 and next_star < valid_next_special:
                valid_next_special = next_star
        
        # If valid_next_special found, consume text up to that
        # If not, consume rest
        
        end_snippet = valid_next_special
        
        # Important: If we didn't find any future special, consume all.
        # If we found one, consume up to it.
        # The character at `i` (failed marker) is included in this text chunk.
        
        push_text(text[i:end_snippet], base_start + i, base_start + end_snippet)
        i = end_snippet
        
    return nodes

# ----------------------------
# 5) 메인 파서 (라인 기반)
# ----------------------------

def parse_markdown(md: str) -> DocNode:
    """in: markdown 문자열 / out: heading 계층이 적용된 DocNode.

    블록 우선순위: blank → hr → heading → blockquote → list → codeblock → paragraph(fallback).
    각 블록의 id는 strip된 텍스트의 base36 hash + 중복 카운터로 안정성을 확보한다.
    """
    lines = to_lines(md)
    children: List[BlockNode] = []

    id_map: Dict[str, int] = {}
    
    def strip_markdown(text: str) -> str:
        t = text
        t = re.sub(r"\*\*(.*?)\*\*", r"\1", t) # Bold
        t = re.sub(r"\*(.*?)\*", r"\1", t)     # Italic
        t = re.sub(r"`(.*?)`", r"\1", t)       # Code
        t = re.sub(r"==(.*?)==", r"\1", t)     # Highlight
        t = re.sub(r"~~(.*?)~~", r"\1", t)     # Strikethrough
        t = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", t) # Link
        t = re.sub(r"^#+\s+", "", t)           # Heading
        t = re.sub(r"^[-*]\s+", "", t)         # List
        t = re.sub(r"^\d+\.\s+", "", t)        # Ordered List
        t = re.sub(r"^>\s+", "", t)            # Blockquote
        return t

    def generate_id(text: str, type_: str) -> str:
        content_text = strip_markdown(text or "")
        normalized = content_text.strip().lower()
        hash_key = simple_hash_base36(normalized + type_)
        count = id_map.get(hash_key, 0)
        id_map[hash_key] = count + 1
        return f"b_{hash_key}_{count}"
    
    inline_counter = 0
    def inline_id_gen():
        nonlocal inline_counter
        inline_counter += 1
        return f"i-{inline_counter}"

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        
        # 1. Blank
        if is_blank(line):
            idx += 1
            continue
            
        # 2. HR
        if is_hr(line):
            id_ = generate_id(line.text, 'horizontalRule')
            children.append(HrNode(
                id=id_,
                span=Span(line.start, line.end),
                markdown=line.text
            ))
            idx += 1
            continue
            
        # 3. Heading
        h = match_heading(line)
        if h:
            id_ = generate_id(line.text, 'heading')
            # Calculate content offset for inline parsing
            # # Heading -> offset is start + 2 (if space)
            # ## Heading -> offset is start + 3
            prefix_len = h['level'] + (1 if line.text[h['level']] == ' ' else 0)
            content_offset = line.start + prefix_len
            
            children.append(HeadingNode(
                id=id_,
                level=h['level'],
                children=parse_inline(h['content'], content_offset, inline_id_gen),
                span=Span(line.start, line.end),
                markdown=line.text
            ))
            idx += 1
            continue
            
        # 4. Blockquote
        bq = match_blockquote(line)
        if bq:
            content = bq['content']
            raw_text = line.text
            end_idx = idx
            
            next_idx = idx + 1
            while next_idx < len(lines):
                next_line = lines[next_idx]
                next_bq = match_blockquote(next_line)
                if next_bq:
                    content += "\n" + next_bq['content']
                    raw_text += "\n" + next_line.text
                    end_idx = next_idx
                    next_idx += 1
                else:
                    break
            
            id_ = generate_id(raw_text, 'blockquote')
            # Simplified: Blockquote contains one paragraph for now
            p_id = generate_id(content, 'paragraph')
            children.append(BlockquoteNode(
                id=id_,
                children=[ParagraphNode(
                    id=p_id,
                    children=parse_inline(content, line.start + 1, inline_id_gen), # +1 for '>'
                    span=Span(line.start, lines[end_idx].end),
                    markdown=content
                )],
                span=Span(line.start, lines[end_idx].end),
                markdown=raw_text
            ))
            idx = end_idx + 1
            continue
            
        # 5. List
        li = match_list_item(line)
        if li:
            is_ordered = li['ordered']
            list_items: List[ListItemNode] = []
            end_idx = idx
            raw_text = ""
            
            next_idx = idx
            while next_idx < len(lines):
                next_line = lines[next_idx]
                next_li = match_list_item(next_line)
                
                # Check if it continues the list (same type)
                if not next_li or next_li['ordered'] != is_ordered:
                    break
                    
                item_id = generate_id(next_line.text, 'listItem')
                p_id = generate_id(next_li['content'], 'paragraph')
                
                # indent + marker length calculation
                # marker is 1 char (- or *) or digits + dot
                marker_len = 1
                if is_ordered:
                    marker_match = re.match(r"^\d+\.", next_line.text.strip())
                    if marker_match:
                        marker_len = len(marker_match.group(0))
                
                content_offset = next_line.start + next_li['indent'] + marker_len + 1 # +1 for space
                
                list_items.append(ListItemNode(
                    id=item_id,
                    children=[ParagraphNode(
                        id=p_id,
                        children=parse_inline(next_li['content'], content_offset, inline_id_gen),
                        span=Span(next_line.start, next_line.end),
                        markdown=next_li['content']
                    )],
                    span=Span(next_line.start, next_line.end),
                    markdown=next_line.text
                ))
                
                raw_text += ("\n" if raw_text else "") + next_line.text
                end_idx = next_idx
                next_idx += 1
                
            list_type = 'orderedList' if is_ordered else 'bulletList'
            list_id = generate_id(raw_text, list_type)
            
            children.append(ListNode(
                id=list_id,
                ordered=is_ordered,
                items=list_items,
                span=Span(line.start, lines[end_idx].end),
                markdown=raw_text
            ))
            idx = end_idx + 1
            continue
            
        # 6. Code Block
        if line.text.strip().startswith('```'):
            lang = line.text.strip()[3:]
            code_content = ""
            raw_text = line.text
            end_idx = idx
            
            next_idx = idx + 1
            while next_idx < len(lines):
                next_line = lines[next_idx]
                raw_text += "\n" + next_line.text
                if next_line.text.strip().startswith('```'):
                    end_idx = next_idx
                    next_idx += 1
                    break
                code_content += ("\n" if code_content else "") + next_line.text
                end_idx = next_idx
                next_idx += 1
                
            id_ = generate_id(code_content, 'codeBlock')
            children.append(CodeBlockNode(
                id=id_,
                language=lang,
                text=code_content,
                span=Span(line.start, lines[end_idx].end),
                markdown=raw_text
            ))
            idx = next_idx
            continue
            
        # 7. Paragraph (Fallback)
        p_content = line.text
        raw_text = line.text
        end_idx = idx
        
        next_idx = idx + 1
        while next_idx < len(lines):
            next_line = lines[next_idx]
            # Break on block starters
            if (is_blank(next_line) or is_hr(next_line) or match_heading(next_line) or 
                match_blockquote(next_line) or match_list_item(next_line) or 
                next_line.text.strip().startswith('```')):
                break
            
            p_content += "\n" + next_line.text
            raw_text += "\n" + next_line.text
            end_idx = next_idx
            next_idx += 1
            
        id_ = generate_id(p_content, 'paragraph')
        children.append(ParagraphNode(
            id=id_,
            children=parse_inline(p_content, line.start, inline_id_gen),
            span=Span(line.start, lines[end_idx].end),
            markdown=raw_text
        ))
        idx = next_idx
        
    # Build Hierarchy
    hierarchy = build_hierarchy(children)

    return DocNode(
        id='doc',
        children=hierarchy,
        span=Span(0, len(md))
    )

def build_hierarchy(flat_nodes: List[BlockNode]) -> List[BlockNode]:
    """in: flat block list / out: heading level 기반 트리(상위 헤딩의 sub_blocks에 자식 부착)."""
    root_nodes = []
    stack = [] # Stack of (HeadingNode, level)

    for node in flat_nodes:
        if node.type == "heading":
            # Pop stack until we find a parent with lower level
            while stack and stack[-1].level >= node.level:
                stack.pop()
            
            if stack:
                # Add to current parent's sub_blocks
                stack[-1].sub_blocks.append(node)
            else:
                # Root level node
                root_nodes.append(node)
            
            # Helper: Add sub_blocks field dynamically if it doesn't exist (e.g. for existing objects)
            # But here we updated the dataclass, so it should be fine.
            # Make sure sub_blocks is initialized if it wasn't by default (it is factory list)
            
            # Push self to stack
            stack.append(node)
        else:
            # Non-heading node (Paragraph, List, etc.)
            if stack:
                stack[-1].sub_blocks.append(node)
            else:
                root_nodes.append(node)
    
    return root_nodes

# ----------------------------
# 6) 블록 검색 유틸
# ----------------------------

def find_all_blocks_in_range(node: Union[DocNode, BlockNode, ListItemNode], start: int, end: int) -> List[BlockNode]:
    """in: 트리 루트 + 문자 [start,end] / out: 해당 구간과 겹치는 leaf block 리스트.
    selection 기반 부분 편집을 지원하기 위한 헬퍼."""
    results = []
    
    # Leaf Blocks
    is_leaf = node.type in ['paragraph', 'heading', 'code_block', 'hr']
    
    if is_leaf:
        if node.span and node.span.start <= end and node.span.end >= start:
            results.append(node)
        return results
        
    # Container Blocks
    children = []
    if isinstance(node, DocNode): children = node.children
    elif isinstance(node, BlockquoteNode): children = node.children
    elif isinstance(node, ListNode): children = node.items
    elif isinstance(node, ListItemNode): children = node.children
    
    for child in children:
        if not child.span or (child.span.start <= end and child.span.end >= start):
            results.extend(find_all_blocks_in_range(child, start, end))
            
    return results
