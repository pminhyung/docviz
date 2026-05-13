"""Viz rendering — DSL → PNG.

Dispatched by viz_type prefix:
  - mermaid_*: shell out to `mmdc` (Mermaid CLI, npm @mermaid-js/mermaid-cli)
  - chartjs_*: load Chart.js in a headless Chromium via Playwright, render
    on an off-screen canvas, screenshot.

Use `render(viz_type, viz_dsl, out_path)` for a single record, or
`render_record_paths(records, out_dir)` for a batch.
"""
from code.render.renderer import (
    RenderResult,
    render,
    render_mermaid,
    render_chartjs,
    render_record_paths,
)

__all__ = [
    "RenderResult",
    "render",
    "render_mermaid",
    "render_chartjs",
    "render_record_paths",
]
