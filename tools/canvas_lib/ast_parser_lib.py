"""markdown-it 기반 Canvas AST 파서.

핵심 입출력:
  - parse_markdown(md)        : markdown 문자열 → DocNode (블록 트리)
  - format_canvas_with_ids    : DocNode → `[canvas-block id:N]\\n<블록>\\n...` 문자열

설계 메모:
  - 노드 타입과 inline 파서는 라인 기반 fallback 구현인 ast_parser.py에서 재사용.
  - 본 파일은 markdown-it commonmark 토큰을 같은 AST 스키마로 변환하는 어댑터.
  - list_item은 atomic block으로 취급하므로 list_item의 자식은 marker 출력 시 재귀하지 않는다.
"""

import re
from typing import List, Dict, Union, Optional
from dataclasses import dataclass
from markdown_it import MarkdownIt

# 노드 스키마와 inline 파서는 ast_parser.py에서 재사용 (호환 유지).
from .ast_parser import (
    DocNode, BlockNode, HeadingNode, ParagraphNode, BlockquoteNode,
    ListNode, ListItemNode, HrNode, CodeBlockNode,
    Span, InlineNode, TextNode, StrongNode, CodeInlineNode,
    simple_hash_base36
)

class LineMapper:
    """markdown-it 토큰의 [start_line, end_line]를 문자 인덱스 Span으로 변환."""
    def __init__(self, text: str):
        self.text = text
        self.lines = text.split('\n')
        self.line_offsets = []
        current_offset = 0
        for line in self.lines:
            self.line_offsets.append(current_offset)
            current_offset += len(line) + 1  # +1 for newline

    def get_span(self, map_range: Optional[List[int]]) -> Optional[Span]:
        """Convert [start_line, end_line] to Span(start_char, end_char)."""
        if not map_range:
            return None
        
        start_line, end_line = map_range
        # Clamp to valid lines
        start_line = max(0, min(start_line, len(self.lines)))
        end_line = max(0, min(end_line, len(self.lines)))
        
        if start_line >= len(self.line_offsets):
            return None
            
        start_char = self.line_offsets[start_line]
        
        # End line in markdown-it is exclusive, so we take the start of that line
        # but usually we want to include the previous newline?
        # Let's say lines 0-1 (content on line 0). end_line=1.
        # offset[1] is the start of line 1. So it includes the newline of line 0.
        # This matches the 'raw' typical behavior.
        
        if end_line >= len(self.line_offsets):
            end_char = len(self.text)
        else:
            end_char = self.line_offsets[end_line]
            
        # Exclude trailing newline to match original parser behavior
        # and preserve block separation during updates
        if end_char > start_char and self.text[end_char-1] == '\n':
            end_char -= 1
            
        return Span(start_char, end_char)

def parse_markdown(md_text: str) -> DocNode:
    """in: markdown 문자열 / out: 블록 노드 트리(DocNode).

    토큰을 스택으로 순회하면서 컨테이너(list/list_item/blockquote)는 push,
    *_close 토큰이 나오면 pop한다. heading/paragraph/code/hr은 leaf로 즉시 append.
    """
    md = MarkdownIt('commonmark')
    tokens = md.parse(md_text)
    mapper = LineMapper(md_text)

    root = DocNode(id='doc', children=[], span=Span(0, len(md_text)))
    stack: List[Union[DocNode, BlockNode, ListItemNode]] = [root]
    
    # ID tracking
    block_id_counter = 0
    def generate_id(content: str, type_: str) -> str:
        nonlocal block_id_counter
        block_id_counter += 1
        return str(block_id_counter)

    def parse_inlines(content: str, token_map: Optional[List[int]]) -> List[InlineNode]:
        # For now, we reuse the existing simple regex inline parser from ast_parser
        # because markdown-it inline tokens are flat and need re-nesting too.
        # To save time and maintain similarity, we call the old inline parser 
        # but with the correct base offset.
        
        if not token_map:
            return []
            
        span = mapper.get_span(token_map)
        if not span:
            return []
            
        # The content string might be slightly different than raw slice if escapes happened?
        # But for 'commonmark' usually map corresponds to the block.
        # Let's use the 'content' logic from ast_parser.
        
        # Slight hack: Import the private/internal inline parser function if possible
        # Or just re-implement a basic one here.
        # The old parser's `parse_inline` needs `base_start` and `id_gen`.
        
        from .ast_parser import parse_inline
        
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
        
        # Generating inline IDs requires a counter
        local_counter = 0
        def inline_id_gen():
            nonlocal local_counter
            local_counter += 1
            return f"i-{span.start}-{local_counter}" # Make it unique per block
            
        # We pass the content string and its start position
        # NOTE: 'content' in token might technically exclude block markers (like # or - )
        # But parse_inline expects raw text? No, it expects content text.
        # The old parser passed 'h["content"]' which was regex group 2.
        
        # Calculate real start of content relative to block start?
        # This is tricky without exact column info.
        # For simple cases (patching), we might just treat the whole block as text for inlines?
        # Or just parse the 'content' string provided by token.
        
        # Critical: The Span for inline nodes must be accurate relative to document.
        # markdown-it doesn't give column info by default.
        # So we might lose exact inline spans unless we search in the raw line.
        
        # FALLBACK: Create one big TextNode for the whole content if verified inline editing isn't critical yet.
        # OR: Search for the content string within the block span.
        
        return parse_inline(content, span.start, inline_id_gen)

    # Iteration
    i = 0
    while i < len(tokens):
        token = tokens[i]
        
        if token.type == 'heading_open':
            # Create Heading Node
            span = mapper.get_span(token.map)
            level = int(token.tag[1:])
            
            # Find the inline token for content
            content = ""
            if i + 1 < len(tokens) and tokens[i+1].type == 'inline':
                content = tokens[i+1].content
                
            node_id = generate_id(content, 'heading')
            node = HeadingNode(
                id=node_id,
                level=level,
                span=span,
                markdown=md_text[span.start:span.end] if span else "",
                children=[] # Inlines populated later or now?
            )
            
            # Populate inlines (simplification)
            # We can use the 'inline' token which follows
            if i + 1 < len(tokens) and tokens[i+1].type == 'inline':
                inline_token = tokens[i+1]
                # We need to approximate start/end of content
                # For '# Header', content starts at +2.
                # For now, let's just make a text node if strict inline span isn't required for BLOCK patching.
                # Block patching replaces the whole block anyway.
                # So InlineNode spans are less critical unless we do sub-block edits.
                
                # Let's populate children using our helper
                node.children = parse_inlines(content, token.map)

            stack[-1].children.append(node)
            # Headings are atomic in our AST (children are inlines, not blocks)
            # But markdown-it has _open and _close.
            # We don't push to stack because it's a leaf block in our Doc model (contains Inlines, not Blocks).
            # Wait, DocNode children are BlockNodes.
            
        elif token.type == 'paragraph_open':
            span = mapper.get_span(token.map)
            content = ""
            if i + 1 < len(tokens) and tokens[i+1].type == 'inline':
                content = tokens[i+1].content
            
            node_id = generate_id(content, 'paragraph')
            node = ParagraphNode(
                id=node_id,
                span=span,
                markdown=md_text[span.start:span.end] if span else "",
                children=parse_inlines(content, token.map)
            )
            stack[-1].children.append(node)
            
        elif token.type == 'bullet_list_open' or token.type == 'ordered_list_open':
            span = mapper.get_span(token.map)
            is_ordered = (token.type == 'ordered_list_open')
            # Extract list raw content? It's huge.
            # We don't have the full raw content easily without slicing the span.
            raw_content = md_text[span.start:span.end] if span else ""
            
            node_id = generate_id("", 'orderedList' if is_ordered else 'bulletList')
            node = ListNode(
                id=node_id,
                ordered=is_ordered,
                items=[],
                span=span,
                markdown=raw_content
            )
            stack[-1].children.append(node)
            # It's a container, push to stack
            stack.append(node)
            
        elif token.type == 'list_item_open':
            span = mapper.get_span(token.map)
            raw_content = md_text[span.start:span.end] if span else ""
            
            # Item ID?
            # We assume the first child content determines ID or random?
            # Let's use raw content for ID to be stable-ish
            node_id = generate_id(raw_content, 'listItem')
            
            node = ListItemNode(
                id=node_id,
                children=[],
                span=span,
                markdown=raw_content
            )
            
            # Parent must be a List
            if isinstance(stack[-1], ListNode):
                stack[-1].items.append(node)
                stack.append(node)
            else:
                # Should not happen in valid markdown
                pass
                
        elif token.type == 'blockquote_open':
            span = mapper.get_span(token.map)
            raw_content = md_text[span.start:span.end] if span else ""
            node_id = generate_id(raw_content, 'blockquote')
            
            node = BlockquoteNode(
                id=node_id,
                children=[],
                span=span,
                markdown=raw_content
            )
            stack[-1].children.append(node)
            stack.append(node)
            
        elif token.type == 'fence' or token.type == 'code_block':
            span = mapper.get_span(token.map)
            content = token.content
            info = token.info if hasattr(token, 'info') else ""
            
            node_id = generate_id(content, 'codeBlock')
            node = CodeBlockNode(
                id=node_id,
                language=info,
                text=content,
                span=span,
                markdown=md_text[span.start:span.end] if span else ""
            )
            stack[-1].children.append(node)

        elif token.type == 'hr':
            span = mapper.get_span(token.map)
            node_id = generate_id('---', 'horizontalRule')
            node = HrNode(
                id=node_id,
                span=span,
                markdown=md_text[span.start:span.end] if span else ""
            )
            stack[-1].children.append(node)
            
        # Handle Close tokens
        elif token.type.endswith('_list_close') or \
             token.type == 'list_item_close' or \
             token.type == 'blockquote_close':
            
            stack.pop()

        i += 1
        
    return root

def format_canvas_with_ids(ast_node, reindex=False):
    """in: DocNode / out: `[canvas-block id:N]\\n<block>\\n` 반복된 단일 문자열.

    reindex=True면 id를 1부터 새로 부여 (get_canvas_status가 항상 이렇게 호출).
    list는 atomic block으로 print하고 list_item 자식은 재귀하지 않는다(중복 방지).
    doc/blockquote는 wrapper로 보고 자기 자신은 print하지 않고 children으로 재귀.
    """
    if not ast_node: return ""
    output = []

    reindex_counter = 1

    def traverse(nodes):
        nonlocal reindex_counter
        for node in nodes:
            # We only care about Block nodes (which have 'markdown' content populated)
            # Inline nodes (TextNode, etc.) usually have empty 'markdown' in this parser setup
            # and we don't want to expose them as blocks anyway.
            node_type = getattr(node, 'type', '')
            
            # Print Block content
            if hasattr(node, "id") and hasattr(node, "markdown"):
                # Filter out inline types just in case they are reached
                     # Fix for Duplication: Do NOT print container types that we recurse into?
                     # MERGE OPTIMIZATION: We DO print lists now, and we DO NOT recurse into items.
                     # So lists are atomic blocks.
                     # We skip 'doc' and 'blockquote' from printing themselves as they are just wrappers (we recurse for them).
                      if node_type not in ['doc', 'blockquote']:
                          markdown = node.markdown.strip()
                          if markdown:
                              if reindex:
                                  node.id = str(reindex_counter)
                                  reindex_counter += 1
                              output.append(f"[canvas-block id:{node.id}]")
                              output.append(markdown)
                              output.append("")
            
            # Recurse Logic
            # Fix for List Item Duplication:
            # List Items are treated as atomic blocks in this view, so we DO NOT recurse into their children
            # (which are usually Paragraphs containing the same text).
            if node_type == 'list_item':
                continue

            # 1. Structure Hierarchy (Headings nesting)
            if hasattr(node, "sub_blocks") and node.sub_blocks:
                traverse(node.sub_blocks)
            
            # 2. Container Blocks (Doc, Blockquote)
            # These have 'children' that are Blocks.
            # We exclude list_item here as handled above.
            if hasattr(node, "children") and node.children:
                if node_type in ['doc', 'blockquote']:
                    traverse(node.children)
            
            # 3. List Items (ListNode has 'items')
            # MERGE OPTIMIZATION: Do NOT recurse into list items.
            # Only recurse if we wanted granular items.
            # if hasattr(node, "items") and node.items:
            #     traverse(node.items)

    if hasattr(ast_node, "children"): 
        traverse(ast_node.children)
    elif hasattr(ast_node, "items"): 
        traverse(ast_node.items)
    
    return "\n".join(output)
