"""Convert rendered visualization files (HTML/SVG/PNG) to PNG base64.

For mindmap HTML: re-renders via sidecar /render-png (D3.js not embedded in HTML).
For SVG/HTML (diagram, chart): uses Selenium headless Chrome screenshot.
"""
import base64
import json
import os
import time
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


MAX_RETRIES = 3


def rendered_to_png_base64(rendered_path: str) -> Optional[str]:
    """Convert a rendered file to base64-encoded PNG string.

    - .png: direct read
    - mindmap .html: re-render via sidecar /render-png (D3.js not in HTML)
    - other .html/.svg: Selenium headless Chrome screenshot
    Retries up to MAX_RETRIES times with driver recreation on failure.
    Returns None on failure.
    """
    if not os.path.exists(rendered_path):
        return None

    ext = os.path.splitext(rendered_path)[1].lower()

    if ext == ".png":
        with open(rendered_path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")

    # Mindmap HTML: inject D3.js and screenshot (HTML lacks D3.js bundle)
    if ext == ".html" and _is_mindmap_html(rendered_path):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                png_bytes = _render_mindmap_png(rendered_path)
                if png_bytes:
                    return base64.b64encode(png_bytes).decode("ascii")
            except Exception as e:
                print(f"[image_utils] Mindmap render attempt {attempt}/{MAX_RETRIES} "
                      f"failed: {e}")
                _reset_driver()
        return None

    # SVG or non-mindmap HTML: Selenium screenshot
    if ext in (".html", ".svg"):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                png_bytes = _screenshot_with_selenium(rendered_path)
                if png_bytes:
                    return base64.b64encode(png_bytes).decode("ascii")
            except Exception as e:
                print(f"[image_utils] Screenshot attempt {attempt}/{MAX_RETRIES} "
                      f"failed for {rendered_path}: {e}")
                _reset_driver()
        return None

    return None


# ── Mindmap: sidecar re-render ────────────────────────────────────────────

def _is_mindmap_html(file_path: str) -> bool:
    """Detect if an HTML file is a D3.js mindmap."""
    return "/mindmap/" in file_path or "mindmap" in os.path.basename(os.path.dirname(file_path)).lower()


_D3_JS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "sidecars", "mindmap-renderer", "d3.min.js",
)
_D3_JS_CACHE: Optional[str] = None


def _get_d3_js() -> str:
    """Load D3.js source (cached)."""
    global _D3_JS_CACHE
    if _D3_JS_CACHE is None:
        with open(_D3_JS_PATH, "r", encoding="utf-8") as f:
            _D3_JS_CACHE = f.read()
    return _D3_JS_CACHE


def _render_mindmap_png(html_path: str) -> Optional[bytes]:
    """Inject D3.js into mindmap HTML and capture via Selenium.

    The saved HTML has `/* D3 not found */` placeholder where D3.js should be.
    We inject the actual D3.js bundle, write a temp file, and screenshot it.
    """
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Inject D3.js where the placeholder is
    d3_js = _get_d3_js()
    content = content.replace("/* D3 not found */", d3_js)

    # Write temp file
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w",
                                      encoding="utf-8")
    tmp.write(content)
    tmp.close()

    try:
        driver = _get_driver()
        driver.get(f"file://{tmp.name}")
        time.sleep(10)  # D3 needs time to render tree layout

        # Click Expand All + Fit View
        driver.execute_script("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                if (b.textContent.trim() === 'Expand All') { b.click(); break; }
            }
        """)
        time.sleep(1)
        driver.execute_script("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                if (b.textContent.trim() === 'Fit View') { b.click(); break; }
            }
        """)
        time.sleep(1)
        # Hide control panel for clean screenshot
        driver.execute_script("""
            var panels = document.querySelectorAll('.toolbar, [class*="toolbar"], [class*="control"]');
            panels.forEach(function(p) { p.style.display = 'none'; });
        """)
        time.sleep(0.5)

        return driver.get_screenshot_as_png()
    finally:
        os.unlink(tmp.name)


# ── Selenium driver pool (for SVG and chart HTML) ────────────────────────

_driver: Optional[webdriver.Chrome] = None


def _get_driver(width: int = 1600, height: int = 1200) -> webdriver.Chrome:
    """Get or create a reusable headless Chrome driver."""
    global _driver
    if _driver is not None:
        try:
            _driver.title  # connectivity check
            return _driver
        except Exception:
            _driver = None

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument(f"--window-size={width},{height}")
    opts.add_argument("--hide-scrollbars")
    opts.add_argument("--force-device-scale-factor=1")

    _driver = webdriver.Chrome(options=opts)
    return _driver


def _screenshot_with_selenium(file_path: str,
                               width: int = 1600,
                               height: int = 1200) -> Optional[bytes]:
    """Take a PNG screenshot of a local HTML/SVG file via headless Chrome."""
    abs_path = os.path.abspath(file_path)
    file_url = f"file://{abs_path}"

    driver = _get_driver(width, height)
    driver.get(file_url)

    # Wait for JS rendering (Chart.js charts, complex SVGs)
    time.sleep(10)

    return driver.get_screenshot_as_png()


def _reset_driver():
    """Force-close and recreate driver on next use."""
    global _driver
    if _driver is not None:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None


def cleanup_driver():
    """Close the Selenium driver. Call at program exit."""
    _reset_driver()
