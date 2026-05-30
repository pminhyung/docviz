"""canvas markers facade(strip_markers/render_with_ids/ensure_markers/apply_block_updates)의 단위 테스트.

검증 포인트:
  - strip은 줄 시작 마커만 제거 (본문 중간 등장은 보존), idempotent, empty-safe.
  - render는 항상 id를 1부터 재부여하고, 빈 입력은 빈 문자열.
  - ensure는 마커 있으면 pass-through, 없으면 render.
  - apply_block_updates는 형제 블록 보존, 'root' 키는 전체 교체.
  - render→strip 라운드트립으로 텍스트 손실 없음, 코드 펜스는 1개 블록(원자 단위)."""

import pytest

from tools.canvas_lib.markers import (
    strip_markers,
    render_with_ids,
    ensure_markers,
    apply_block_updates,
)


def test_strip_markers_line_start_only():
    """`[canvas-block id:N]` in mid-line text must not be stripped."""
    body = "Some text mentioning [canvas-block id:7] inline.\n"
    assert strip_markers(body) == body


def test_strip_markers_at_line_start():
    marked = "[canvas-block id:1]\n# Heading\n\n[canvas-block id:2]\nbody"
    out = strip_markers(marked)
    assert "[canvas-block id:" not in out
    assert "# Heading" in out
    assert "body" in out


def test_strip_markers_idempotent():
    marked = "[canvas-block id:1]\n# H\n"
    once = strip_markers(marked)
    twice = strip_markers(once)
    assert once == twice


def test_strip_markers_empty():
    assert strip_markers("") == ""


def test_render_with_ids_reindexes_from_1():
    out = render_with_ids("# A\n\n# B\n\n# C")
    assert "[canvas-block id:1]" in out
    assert "[canvas-block id:2]" in out
    assert "[canvas-block id:3]" in out
    assert "[canvas-block id:4]" not in out


def test_render_block_order_stable():
    md = "# A\n\nparagraph\n\n- item1\n- item2"
    assert render_with_ids(md) == render_with_ids(md)


def test_render_with_ids_empty():
    assert render_with_ids("") == ""


def test_ensure_markers_passes_through_already_marked():
    marked = "[canvas-block id:1]\n# H\n"
    assert ensure_markers(marked) == marked


def test_ensure_markers_renders_plain():
    plain = "# A\n\n# B"
    out = ensure_markers(plain)
    assert "[canvas-block id:1]" in out
    assert "[canvas-block id:2]" in out


def test_apply_block_updates_preserves_siblings():
    tagged = render_with_ids("# A\n\n# B\n\n# C")
    patched = apply_block_updates(tagged, [
        {"block_id": "2", "block_content": "# B-updated"},
    ])
    assert "# A" in patched
    assert "# B-updated" in patched
    assert "# C" in patched


def test_apply_block_updates_root_replaces_all():
    tagged = render_with_ids("# A\n\n# B\n\n# C")
    patched = apply_block_updates(tagged, [
        {"block_id": "root", "block_content": "# Z only"},
    ])
    assert "# Z only" in patched
    assert "# A" not in patched
    assert "# B" not in patched
    assert "# C" not in patched


def test_render_strip_roundtrip_preserves_text():
    md = "# Title\n\nFirst paragraph.\n\n## Sub\n\n- a\n- b"
    out = strip_markers(render_with_ids(md))
    # Content should still contain all the unique pieces.
    assert "# Title" in out
    assert "First paragraph." in out
    assert "## Sub" in out
    assert "- a" in out
    assert "- b" in out


def test_render_code_fence_is_atomic_block():
    """Code fence must be a single block (one marker), not per-line."""
    md = "```python\nprint('hi')\nprint('there')\n```"
    out = render_with_ids(md)
    # Exactly one canvas-block marker for the fenced code.
    assert out.count("[canvas-block id:") == 1
    assert "```python" in out
    assert "print('hi')" in out
