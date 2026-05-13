"""DSL → PNG renderer for the 10-type viz enum.

Mermaid path: shells out to `mmdc` (Mermaid CLI) which uses puppeteer +
headless Chromium internally. Path resolution: $MMDC_BIN env var if set,
else `~/.npm-global/bin/mmdc`, else `mmdc` from $PATH.

Chart.js path: launches headless Chromium via Playwright, loads an
in-memory HTML page that imports Chart.js from CDN, instantiates the chart
on a canvas, then screenshots the chart element.

Both paths produce 800×600 PNGs by default (overridable per-render).
Failures (parse errors, CLI crashes, network problems) yield a
`RenderResult(success=False, error=...)` rather than raising.

A5 image-judge and M5 CLIPScore both consume the rendered PNGs.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Playwright is loaded lazily inside _render_chartjs_playwright so that
# `import code.render` doesn't require the binary to be installed.


# ── Public dataclass ────────────────────────────────────────────────────────


@dataclass
class RenderResult:
    """Outcome of a single render call."""
    success: bool
    image_path: str
    viz_type: str
    error: str = ""
    width: int = 0
    height: int = 0


# ── Helpers ─────────────────────────────────────────────────────────────────


def _resolve_mmdc_path() -> str:
    """Find mmdc binary. Checks $MMDC_BIN, ~/.npm-global/bin, then $PATH."""
    env_path = os.environ.get("MMDC_BIN")
    if env_path and Path(env_path).is_file():
        return env_path
    npm_global = Path.home() / ".npm-global" / "bin" / "mmdc"
    if npm_global.is_file():
        return str(npm_global)
    found = shutil.which("mmdc")
    if found:
        return found
    raise RuntimeError(
        "mmdc (Mermaid CLI) not found. Install with: "
        "npm install -g @mermaid-js/mermaid-cli (use "
        "`npm config set prefix ~/.npm-global` if you lack root permissions)."
    )


_ASSETS_DIR = Path(__file__).parent / "assets"
_CHART_JS_LIB = _ASSETS_DIR / "chart.umd.min.js"


def _repair_json_braces(text: str) -> str:
    """Best-effort fix for Qwen's two most common Chart.js JSON errors:
      - 1-3 trailing extra `}` (model "over-closes" the spec)
      - 1-3 missing trailing `}` (model "under-closes")
    Iteratively strip trailing `}` characters until the text parses; if
    that doesn't help, append missing `}` to balance opens.
    """
    text = text.strip()
    # First try trimming trailing extras
    candidate = text
    for _ in range(5):
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            if candidate.endswith("}"):
                candidate = candidate[:-1].rstrip()
                continue
            break
    # Next try appending missing closes based on brace count
    opens = text.count("{")
    closes = text.count("}")
    if opens > closes:
        return text + "}" * (opens - closes)
    return text

_CHARTJS_HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html, body {{ margin: 0; padding: 0; background: #ffffff; }}
  #wrap {{ width: {w}px; height: {h}px; padding: 16px; box-sizing: border-box; }}
  canvas {{ display: block; width: 100% !important; height: 100% !important; background: #ffffff; }}
</style>
<script>{chart_lib}</script>
</head>
<body>
<div id="wrap"><canvas id="c"></canvas></div>
<script id="payload" type="application/json">{payload}</script>
<script>
  (async () => {{
    try {{
      const spec = JSON.parse(document.getElementById('payload').textContent);
      // Disable animations so screenshot is taken on stable final frame
      spec.options = spec.options || {{}};
      spec.options.animation = false;
      spec.options.responsive = false;
      spec.options.maintainAspectRatio = false;
      // Strip JS callback strings — they won't eval as functions out of a JSON
      // string blob, and they'd otherwise prevent the chart from rendering.
      function strip(o) {{
        if (Array.isArray(o)) o.forEach(strip);
        else if (o && typeof o === 'object') {{
          for (const k of Object.keys(o)) {{
            if (typeof o[k] === 'string' && o[k].startsWith('function(')) delete o[k];
            else strip(o[k]);
          }}
        }}
      }}
      strip(spec.options);
      if (typeof window.Chart !== 'function') {{
        document.body.dataset.err = 'Chart.js global not found';
        return;
      }}
      const ctx = document.getElementById('c');
      window.__chart = new Chart(ctx, spec);
      document.body.dataset.ready = '1';
    }} catch (e) {{
      document.body.dataset.err = String(e);
    }}
  }})();
</script>
</body></html>
"""


# ── Mermaid renderer ────────────────────────────────────────────────────────


def render_mermaid(
    dsl: str,
    out_path: str | Path,
    *,
    width: int = 800,
    height: int = 600,
    background: str = "white",
    timeout_seconds: int = 60,
) -> RenderResult:
    """Render Mermaid DSL → PNG via mmdc CLI.

    Returns a RenderResult; on failure the PNG file is not written.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        mmdc = _resolve_mmdc_path()
    except RuntimeError as e:
        return RenderResult(False, "", "mermaid_*", error=str(e))

    if not dsl or not dsl.strip():
        return RenderResult(False, str(out_path), "mermaid_*", error="empty DSL")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mmd", delete=False, encoding="utf-8",
    ) as f:
        f.write(dsl)
        in_path = f.name

    try:
        cmd = [
            mmdc,
            "-i", in_path,
            "-o", str(out_path),
            "-w", str(width),
            "-H", str(height),
            "-b", background,
            "-p", str(_puppeteer_config_path()),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_seconds,
        )
        if proc.returncode != 0:
            return RenderResult(
                False, str(out_path), "mermaid_*",
                error=f"mmdc exit {proc.returncode}: "
                      f"{(proc.stderr or proc.stdout or '').strip()[:300]}",
            )
        if not out_path.exists() or out_path.stat().st_size < 100:
            return RenderResult(
                False, str(out_path), "mermaid_*",
                error="mmdc reported success but PNG missing/too small",
            )
        return RenderResult(True, str(out_path), "mermaid_*",
                            width=width, height=height)
    except subprocess.TimeoutExpired:
        return RenderResult(False, str(out_path), "mermaid_*",
                            error=f"mmdc timeout after {timeout_seconds}s")
    finally:
        try:
            Path(in_path).unlink()
        except OSError:
            pass


def _puppeteer_config_path() -> Path:
    """Write a puppeteer config that disables sandbox (required when running
    headless Chromium as non-root in many container/dev environments).
    Re-uses a stable file under /tmp so we don't recreate per call.
    """
    path = Path("/tmp/docviz_puppeteer.json")
    if not path.exists():
        path.write_text(
            json.dumps({"args": ["--no-sandbox", "--disable-dev-shm-usage"]}),
            encoding="utf-8",
        )
    return path


# ── Chart.js renderer ───────────────────────────────────────────────────────


def render_chartjs(
    dsl: str,
    out_path: str | Path,
    *,
    width: int = 800,
    height: int = 600,
    timeout_seconds: int = 30,
) -> RenderResult:
    """Render Chart.js JSON DSL → PNG via headless Chromium (Playwright).

    The DSL is parsed as JSON; if parsing fails, returns success=False.
    JS function strings inside options are stripped client-side before
    instantiation (see `_CHARTJS_HTML_TEMPLATE`).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not dsl or not dsl.strip():
        return RenderResult(False, str(out_path), "chartjs_*", error="empty DSL")

    try:
        spec = json.loads(dsl)
    except json.JSONDecodeError as e:
        # Best-effort JSON repair: Qwen sometimes emits 1-2 trailing extra
        # `}` or omits a closing brace. Try a brace-balance fix once.
        repaired = _repair_json_braces(dsl)
        try:
            spec = json.loads(repaired)
        except json.JSONDecodeError:
            return RenderResult(False, str(out_path), "chartjs_*",
                                error=f"DSL not valid JSON: {e}")

    try:
        from playwright.sync_api import sync_playwright  # lazy import
    except ImportError as e:
        return RenderResult(False, str(out_path), "chartjs_*",
                            error=f"playwright not installed: {e}")

    # Inline the chart.js library so we don't depend on CDN (corporate SSL
    # inspection sometimes breaks jsdelivr cert chain in this dev env).
    if not _CHART_JS_LIB.exists():
        return RenderResult(False, str(out_path), "chartjs_*",
                            error=f"bundled chart.js not found at {_CHART_JS_LIB}")
    chart_lib = _CHART_JS_LIB.read_text(encoding="utf-8")

    # JSON-encode the spec into the HTML; escape "</script>" defensively
    payload = json.dumps(spec, ensure_ascii=False).replace("</script", "<\\/script")
    html = _CHARTJS_HTML_TEMPLATE.format(
        w=width, h=height, payload=payload, chart_lib=chart_lib,
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                ctx = browser.new_context(
                    viewport={"width": width + 32, "height": height + 32},
                    ignore_https_errors=True,
                )
                page = ctx.new_page()
                page.set_content(html, wait_until="domcontentloaded")
                # Wait until the embedded script sets `data-ready=1` or
                # `data-err` after Chart construction completes/fails.
                page.wait_for_function(
                    "() => document.body.dataset.ready === '1' || "
                    "document.body.dataset.err",
                    timeout=timeout_seconds * 1000,
                )
                err = page.evaluate("() => document.body.dataset.err || ''")
                if err:
                    browser.close()
                    return RenderResult(False, str(out_path), "chartjs_*",
                                        error=f"chart construction failed: {err}")
                # Brief settle for paint
                page.wait_for_timeout(150)
                # Screenshot the wrap div, not the whole page
                wrap = page.locator("#wrap")
                wrap.screenshot(path=str(out_path), omit_background=False)
            finally:
                browser.close()
    except Exception as e:
        return RenderResult(False, str(out_path), "chartjs_*",
                            error=f"playwright render failed: {e}")

    if not out_path.exists() or out_path.stat().st_size < 100:
        return RenderResult(False, str(out_path), "chartjs_*",
                            error="screenshot missing/too small")
    return RenderResult(True, str(out_path), "chartjs_*",
                        width=width, height=height)


# ── Dispatcher ──────────────────────────────────────────────────────────────


def render(
    viz_type: str,
    viz_dsl: str,
    out_path: str | Path,
    *,
    width: int = 800,
    height: int = 600,
) -> RenderResult:
    """Dispatch by viz_type prefix to mermaid/chartjs path."""
    if not viz_type or not viz_dsl:
        return RenderResult(False, str(out_path), viz_type or "",
                            error="empty viz_type or viz_dsl")
    vt = viz_type.strip()
    if vt.startswith("mermaid_"):
        return render_mermaid(viz_dsl, out_path, width=width, height=height)
    if vt.startswith("chartjs_"):
        return render_chartjs(viz_dsl, out_path, width=width, height=height)
    return RenderResult(False, str(out_path), vt,
                        error=f"unsupported viz_type prefix: {vt!r}")


def render_record_paths(
    records: Iterable[Dict[str, Any]],
    out_dir: str | Path,
    *,
    width: int = 800,
    height: int = 600,
    skip_existing: bool = True,
) -> List[Tuple[Dict[str, Any], RenderResult]]:
    """Batch-render a sequence of viz records (each must have at least
    `query_id`, `strategy`, `viz_type`, `viz_dsl`). PNGs are written to
    `{out_dir}/{strategy}/{query_id}.png`.

    Returns a parallel list of (record, result) pairs.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out: List[Tuple[Dict[str, Any], RenderResult]] = []
    for r in records:
        qid = r.get("query_id", "unknown")
        strat = r.get("strategy", "unknown")
        viz_type = r.get("viz_type", "")
        viz_dsl = r.get("viz_dsl", "")
        sub = out_dir / strat
        sub.mkdir(parents=True, exist_ok=True)
        path = sub / f"{qid}.png"
        if skip_existing and path.exists() and path.stat().st_size > 100:
            res = RenderResult(True, str(path), viz_type, width=width, height=height)
        else:
            res = render(viz_type, viz_dsl, path, width=width, height=height)
        out.append((r, res))
    return out
