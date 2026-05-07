"""Standalone rendering wrappers for sidecar services.

Reuses existing functions from diagram_tools.py but provides
a context-free interface for batch processing.
"""
import json
import os
import time

# Import existing helpers from diagram_tools
from examples.diagram.diagram_tools import (
    _extract_chart_dsl,
    _extract_mermaid_source,
    _http_post,
    _parse_markdown_to_nodes,
    _postprocess_mindmap_markdown,
    _strip_llm_wrapper,
)

import re

from scripts.config import SIDECAR_MERMAID_URL, SIDECAR_MINDMAP_URL


def _is_mermaid_mindmap(text: str) -> bool:
    """Detect Mermaid `mindmap` syntax vs Markdown `## Theme / - Topic` form."""
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if re.match(r'^\s*mindmap\b', stripped, re.MULTILINE):
        return True
    if re.search(r'\broot\(\(.+?\)\)', stripped):
        return True
    return False


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


# ── Mindmap Rendering ──────────────────────────────────────────────────────

MERMAID_MINDMAP_MODELS = {"mistral_small_3_24b", "claude_sonnet_4_6"}


def render_mindmap(markdown_text: str, output_dir: str,
                   doc_id: str = "", api_url: str = SIDECAR_MINDMAP_URL,
                   model_id: str = "", theme: str = "corporate") -> dict:
    """Process mindmap markdown → render via D3.js sidecar.

    For models in MERMAID_MINDMAP_MODELS that emit Mermaid `mindmap` syntax,
    route to the Mermaid.js sidecar (:3005) which natively supports the
    `mindmap` diagram type. All other models keep the existing D3 path to
    preserve pre-computed renders and VLM scores.

    Args:
        theme: sidecar theme preset. mindmap-renderer (:3004) supports
            corporate / academic / creative / dark / minimal / nature.

    Returns: {
        "success": bool,
        "source_text": str,        # post-processed markdown
        "nodes_edges": (list, list),  # parsed nodes and edges
        "rendered_path": str,      # path to PNG/HTML
        "error": str or None,
    }
    """
    if model_id in MERMAID_MINDMAP_MODELS and _is_mermaid_mindmap(markdown_text):
        mm = render_mermaid(markdown_text, "mindmap", output_dir,
                            doc_id=doc_id, fmt="png", theme=theme)
        return {
            "success": mm.get("success", False),
            "source_text": mm.get("source_text", markdown_text),
            "nodes_edges": ([], []),
            "rendered_path": mm.get("rendered_path", ""),
            "error": mm.get("error"),
        }

    result = {"success": False, "source_text": markdown_text,
              "nodes_edges": ([], []), "rendered_path": "", "error": None}

    try:
        # Post-process
        processed = _postprocess_mindmap_markdown(markdown_text)
        result["source_text"] = processed

        # Parse to nodes/edges
        nodes, edges = _parse_markdown_to_nodes(processed)
        result["nodes_edges"] = (nodes, edges)

        if not nodes:
            result["error"] = "No nodes parsed from markdown"
            return result

        # Auto layout
        total = len(nodes)
        layout = "radial" if total <= 60 else "tree_lr"
        collapse_depth = 4 if total <= 30 else (3 if total <= 60 else 2)

        mindmap_data = {
            "title": nodes[0]["label"] if nodes else "Mindmap",
            "subtitle": "",
            "theme": theme,
            "layout": layout,
            "options": {
                "width": 1600, "height": 1200,
                "show_citations": False,
                "show_cross_links": len(edges) > 0,
                "collapse_depth": collapse_depth,
                "animation": False,
            },
            "nodes": nodes,
            "edges": edges,
            "metadata": {},
        }

        # Render via sidecar
        ts = _timestamp()
        prefix = doc_id or ts

        # Try PNG first
        try:
            resp = _http_post(f"{api_url}/render-png", mindmap_data, timeout=60)
            if resp["type"] == "binary":
                png_path = os.path.join(output_dir, f"{prefix}_rendered.png")
                with open(png_path, "wb") as f:
                    f.write(resp["data"])
                result["rendered_path"] = png_path
                result["success"] = True
                return result
        except Exception:
            pass

        # Fallback to HTML
        resp = _http_post(f"{api_url}/render", mindmap_data, timeout=60)
        if resp["type"] != "json":
            html_path = os.path.join(output_dir, f"{prefix}_rendered.html")
            data_bytes = resp["data"]
            if isinstance(data_bytes, str):
                data_bytes = data_bytes.encode("utf-8")
            with open(html_path, "wb") as f:
                f.write(data_bytes)
            result["rendered_path"] = html_path
            result["success"] = True
        elif "error" in resp.get("data", {}):
            result["error"] = str(resp["data"]["error"])
        else:
            html = resp.get("data", {}).get("html", "")
            if html:
                html_path = os.path.join(output_dir, f"{prefix}_rendered.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)
                result["rendered_path"] = html_path
                result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


# ── Mermaid Diagram Rendering ──────────────────────────────────────────────

def render_mermaid(raw_source: str, diagram_type: str, output_dir: str,
                   doc_id: str = "", fmt: str = "svg",
                   api_url: str = SIDECAR_MERMAID_URL,
                   theme: str = "corporate") -> dict:
    """Process mermaid source → render via sidecar.

    Args:
        theme: mermaid-renderer (:3005) preset. Supported:
            corporate / modern / warm / dark / minimal.

    Returns: {
        "success": bool,
        "source_text": str,
        "rendered_path": str,
        "error": str or None,
    }
    """
    result = {"success": False, "source_text": raw_source,
              "rendered_path": "", "error": None}

    try:
        source = _extract_mermaid_source(raw_source, diagram_type)
        result["source_text"] = source

        ts = _timestamp()
        prefix = doc_id or ts

        resp = _http_post(f"{api_url}/render", {
            "mermaid_source": source,
            "format": fmt,
            "theme": theme,
        }, timeout=30)

        ext = "png" if fmt == "png" else "svg"
        filepath = os.path.join(output_dir, f"{prefix}_rendered.{ext}")

        if resp["type"] == "binary":
            with open(filepath, "wb") as f:
                f.write(resp["data"])
            result["rendered_path"] = filepath
            result["success"] = True
        elif resp["type"] == "json":
            data = resp.get("data", {})
            if "error" in data:
                result["error"] = str(data["error"])
            elif "svg" in data:
                svg_path = os.path.join(output_dir, f"{prefix}_rendered.svg")
                with open(svg_path, "w", encoding="utf-8") as f:
                    f.write(data["svg"])
                result["rendered_path"] = svg_path
                result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


# ── Vega-Lite Rendering (vl-convert-python, no sidecar) ───────────────────

def render_vegalite(vega_json, output_dir: str, doc_id: str = "",
                    fmt: str = "png", scale: float = 2.0) -> dict:
    """Render a Vega-Lite JSON spec to PNG via vl-convert-python.

    Accepts either a dict or a JSON string. Writes {doc_id}_rendered.png
    into output_dir. Returns {success, source_text, rendered_path, error}
    to match the render_mermaid / render_chart interface.
    """
    result = {"success": False, "source_text": "",
              "rendered_path": "", "error": None}
    try:
        import vl_convert as vlc
    except ImportError as e:
        result["error"] = f"vl-convert-python not installed: {e}"
        return result

    # Register system font directories once (vl-convert ships its own font
    # cache and silently drops text when it can't resolve the spec's font).
    global _VL_FONTS_REGISTERED
    try:
        _VL_FONTS_REGISTERED  # type: ignore[name-defined]
    except NameError:
        for d in (
            "/usr/share/fonts/opentype/noto",
            "/usr/share/fonts/truetype/noto",
            "/usr/share/fonts/truetype/dejavu",
            "/usr/share/fonts/truetype",
        ):
            if os.path.isdir(d):
                try:
                    vlc.register_font_directory(d)
                except Exception:
                    pass
        _VL_FONTS_REGISTERED = True  # type: ignore[name-defined]

    try:
        if isinstance(vega_json, str):
            result["source_text"] = vega_json
            spec = json.loads(vega_json)
        else:
            spec = vega_json
            result["source_text"] = json.dumps(spec, ensure_ascii=False, indent=2)
        # Coerce unresolvable spec-level font (e.g. "Arial") to a generic
        # family that vl-convert can map to the registered Noto/DejaVu fonts.
        if isinstance(spec, dict):
            cfg = spec.get("config", {})
            if isinstance(cfg, dict):
                font = cfg.get("font")
                if isinstance(font, str) and font.lower() in (
                    "arial", "helvetica", "helvetica neue", "segoe ui",
                    "pretendard",
                ):
                    cfg["font"] = "sans-serif"
                    spec["config"] = cfg

        if not isinstance(spec, dict):
            result["error"] = "vega_json must resolve to a dict"
            return result
        if "mark" not in spec and "layer" not in spec and "vconcat" not in spec \
           and "hconcat" not in spec and "repeat" not in spec and "facet" not in spec:
            result["error"] = "vega_json missing 'mark' (or layer/concat/repeat/facet)"
            return result

        ts = _timestamp()
        prefix = doc_id or ts
        os.makedirs(output_dir, exist_ok=True)

        if fmt == "svg":
            svg = vlc.vegalite_to_svg(vl_spec=spec)
            out = os.path.join(output_dir, f"{prefix}_rendered.svg")
            with open(out, "w", encoding="utf-8") as f:
                f.write(svg)
        else:
            png_bytes = vlc.vegalite_to_png(vl_spec=spec, scale=scale)
            out = os.path.join(output_dir, f"{prefix}_rendered.png")
            with open(out, "wb") as f:
                f.write(png_bytes)

        result["rendered_path"] = out
        result["success"] = True
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result


# ── Chart Rendering ────────────────────────────────────────────────────────

def render_chart(raw_source: str, chart_type: str, output_dir: str,
                 doc_id: str = "", api_url: str = SIDECAR_MERMAID_URL,
                 theme: str = "corporate") -> dict:
    """Process Chart DSL → render via Chart.js sidecar.

    Args:
        theme: passthrough to chart sidecar (currently corporate hardcoded
            in sidecar implementation; kept here for API symmetry and
            future support).

    Returns: {
        "success": bool,
        "source_text": str,
        "rendered_path": str,
        "error": str or None,
    }
    """
    result = {"success": False, "source_text": raw_source,
              "rendered_path": "", "error": None}

    try:
        dsl = _extract_chart_dsl(raw_source, chart_type)
        result["source_text"] = dsl

        ts = _timestamp()
        prefix = doc_id or ts

        resp = _http_post(f"{api_url}/render-chart", {
            "chart_source": dsl,
            "theme": theme,
        }, timeout=30)

        filepath = os.path.join(output_dir, f"{prefix}_rendered.html")

        if resp["type"] == "binary":
            # Sidecar returns HTML directly as binary
            data_bytes = resp["data"]
            if isinstance(data_bytes, str):
                data_bytes = data_bytes.encode("utf-8")
            with open(filepath, "wb") as f:
                f.write(data_bytes)
            result["rendered_path"] = filepath
            result["success"] = True
        elif resp["type"] == "json":
            data = resp.get("data", {})
            if "error" in data:
                result["error"] = str(data["error"])
            else:
                html = data.get("html", "")
                if html:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(html)
                    result["rendered_path"] = filepath
                    result["success"] = True

    except Exception as e:
        result["error"] = str(e)

    return result
