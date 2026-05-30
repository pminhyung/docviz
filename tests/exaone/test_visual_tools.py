"""Tests for visual_tools building blocks — scope parser, render cache,
auxiliary_tracer sequence isolation, mm_docqa style/identity drift.

These focus on the units that are easy to test without an LLM endpoint.
End-to-end handler tests require VLM/OCR backends and live elsewhere.
"""

from __future__ import annotations

import pytest

from exaone.visual_tools._render_cache import (
    lookup_render,
    register_render,
    reset_task,
)
from exaone.visual_tools._scope import ScopeItem, parse_scope


# ─── parse_scope ─────────────────────────────────────────────────────────


def test_parse_scope_basic_cases():
    assert parse_scope(["1"]) == [ScopeItem(1, None)]
    assert parse_scope(["1@5"]) == [ScopeItem(1, 5)]
    assert parse_scope(["2@10", "3", "5@7"]) == [
        ScopeItem(2, 10), ScopeItem(3, None), ScopeItem(5, 7),
    ]
    # whitespace tolerance
    assert parse_scope(["  1 @ 5  "]) == [ScopeItem(1, 5)]


@pytest.mark.parametrize("bad", [
    "ds-deflt.0@5",   # legacy Hermes-style ref string (not allowed)
    "0",              # idx must be >= 1
    "-1@5",
    "@5",
    "1@notint",
    "1@0",            # page must be >= 1
])
def test_parse_scope_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_scope([bad])


# ─── render_cache ────────────────────────────────────────────────────────


def test_render_cache_roundtrip_isolated_per_task():
    reset_task("t1"); reset_task("t2")
    register_render(task_id="t1", fid="abc", page=5, png_bytes=b"PNG-T1-P5")
    register_render(task_id="t2", fid="abc", page=5, png_bytes=b"PNG-T2-P5")
    assert lookup_render(task_id="t1", fid="abc", page=5) == b"PNG-T1-P5"
    assert lookup_render(task_id="t2", fid="abc", page=5) == b"PNG-T2-P5"
    assert lookup_render(task_id="t1", fid="abc", page=6) is None
    assert lookup_render(task_id="other", fid="abc", page=5) is None


def test_render_cache_reset_removes_entries():
    reset_task("t1")
    register_render(task_id="t1", fid="abc", page=5, png_bytes=b"X")
    assert lookup_render(task_id="t1", fid="abc", page=5) == b"X"
    reset_task("t1")
    assert lookup_render(task_id="t1", fid="abc", page=5) is None


# ─── auxiliary_tracer per-run, per-kind sequence ────────────────────────


def test_aux_tracer_seq_isolated_per_run_and_kind(tmp_path):
    from exaone.auxiliary_tracer import _next_seq
    from exaone.compaction_tracer import _CURRENT_RUN_DIR

    run1 = tmp_path / "run1"; run1.mkdir()
    run2 = tmp_path / "run2"; run2.mkdir()

    tok = _CURRENT_RUN_DIR.set(run1)
    try:
        assert _next_seq("vlm_get_visuals") == 1
        assert _next_seq("vlm_get_visuals") == 2
        # different kind → independent counter
        assert _next_seq("vlm_analyze") == 1
    finally:
        _CURRENT_RUN_DIR.reset(tok)

    tok = _CURRENT_RUN_DIR.set(run2)
    try:
        # different run → counter starts fresh
        assert _next_seq("vlm_get_visuals") == 1
    finally:
        _CURRENT_RUN_DIR.reset(tok)


def test_aux_tracer_seq_zero_when_unbound():
    # No run bound → returns 0 (signals handler to skip the write).
    from exaone.auxiliary_tracer import _next_seq
    from exaone.compaction_tracer import _CURRENT_RUN_DIR
    # Force-clear to be safe.
    tok = _CURRENT_RUN_DIR.set(None)
    try:
        assert _next_seq("any") == 0
    finally:
        _CURRENT_RUN_DIR.reset(tok)


# ─── mm_docqa style/identity drift detection ────────────────────────────


def _read_prompt(name: str, kind: str) -> str:
    # `kind` is the dir name; "style" and "identities" are the only two used here.
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "exaone" / "prompts" / kind / f"{name}.txt"
    return p.read_text(encoding="utf-8")


def test_mm_docqa_style_starts_with_docqa_style():
    """mm_docqa.txt style intentionally embeds the full docqa.txt as its
    prefix + a visual addendum. This test ensures the prefix stays in
    sync — any docqa.txt edit must be mirrored or this test fails loud.
    """
    docqa = _read_prompt("docqa", "style")
    mm = _read_prompt("mm_docqa", "style")
    assert mm.startswith(docqa.rstrip()), (
        "mm_docqa style must start with the exact docqa style text; "
        "they have drifted — re-sync the prefix."
    )


def test_mm_docqa_identity_only_diverges_at_visual_phrase():
    """mm_docqa identity = docqa identity with one visual phrase added.
    Verify the rest stays byte-identical, line-by-line after the first.
    """
    docqa = _read_prompt("docqa", "identities").splitlines()
    mm = _read_prompt("mm_docqa", "identities").splitlines()
    assert len(docqa) == len(mm), (
        f"mm_docqa identity line count drifted ({len(mm)} vs {len(docqa)})"
    )
    # First line allowed to diverge (visual phrase inserted there).
    assert docqa[1:] == mm[1:], "post-line-1 docqa↔mm_docqa identity diverged"
