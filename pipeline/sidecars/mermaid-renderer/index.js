import express from "express";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
const PORT = parseInt(process.env.PORT || "3005", 10);
const MAX_BODY = "5mb";

app.use(express.json({ limit: MAX_BODY }));

// ===== Load bundled mermaid.min.js =====
let MERMAID_SCRIPT = "";
try {
  MERMAID_SCRIPT = readFileSync(join(__dirname, "mermaid.min.js"), "utf-8");
} catch {
  console.warn(
    "WARNING: mermaid.min.js not found. Download it:\n" +
    '  curl -sL "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js" -o mermaid.min.js'
  );
  MERMAID_SCRIPT = "/* mermaid not found */";
}

// ===== Theme presets =====
// Each preset defines themeVariables for mermaid.initialize()
// These give full control over colors, fonts, node shapes, etc.
const THEME_PRESETS = {
  corporate: {
    theme: "base",
    themeVariables: {
      primaryColor: "#4A90D9",
      primaryTextColor: "#FFFFFF",
      primaryBorderColor: "#2E6BB0",
      secondaryColor: "#7EC8E3",
      secondaryTextColor: "#1A3550",
      secondaryBorderColor: "#5AAFC7",
      tertiaryColor: "#F0F4F8",
      tertiaryTextColor: "#333333",
      tertiaryBorderColor: "#D0D8E0",
      lineColor: "#5A6A7A",
      textColor: "#2C3E50",
      mainBkg: "#4A90D9",
      nodeBorder: "#2E6BB0",
      clusterBkg: "#EBF2FA",
      clusterBorder: "#A8C8E8",
      titleColor: "#1A365D",
      edgeLabelBackground: "#FFFFFF",
      nodeTextColor: "#FFFFFF",
      // Pie chart colors
      pie1: "#4A90D9",
      pie2: "#7EC8E3",
      pie3: "#48BB78",
      pie4: "#ED8936",
      pie5: "#9F7AEA",
      pie6: "#FC8181",
      pie7: "#76E4F7",
      pie8: "#F6E05E",
      pieTitleTextColor: "#1A365D",
      pieSectionTextColor: "#FFFFFF",
      pieLegendTextColor: "#2C3E50",
      // Fonts
      fontFamily: '"Pretendard", "Noto Sans KR", "Segoe UI", sans-serif',
    },
  },
  modern: {
    theme: "base",
    themeVariables: {
      primaryColor: "#6C5CE7",
      primaryTextColor: "#FFFFFF",
      primaryBorderColor: "#5A4BD1",
      secondaryColor: "#A29BFE",
      secondaryTextColor: "#FFFFFF",
      secondaryBorderColor: "#8B83F0",
      tertiaryColor: "#F8F7FF",
      tertiaryTextColor: "#2D3436",
      tertiaryBorderColor: "#DDD6FE",
      lineColor: "#636E72",
      textColor: "#2D3436",
      mainBkg: "#6C5CE7",
      nodeBorder: "#5A4BD1",
      clusterBkg: "#F3F0FF",
      clusterBorder: "#C4B5FD",
      titleColor: "#2D3436",
      edgeLabelBackground: "#FFFFFF",
      nodeTextColor: "#FFFFFF",
      pie1: "#6C5CE7",
      pie2: "#00CEC9",
      pie3: "#FD79A8",
      pie4: "#FDCB6E",
      pie5: "#55EFC4",
      pie6: "#E17055",
      pie7: "#74B9FF",
      pie8: "#A29BFE",
      pieTitleTextColor: "#2D3436",
      pieSectionTextColor: "#FFFFFF",
      pieLegendTextColor: "#2D3436",
      fontFamily: '"Pretendard", "Inter", "Segoe UI", sans-serif',
    },
  },
  warm: {
    theme: "base",
    themeVariables: {
      primaryColor: "#E8725C",
      primaryTextColor: "#FFFFFF",
      primaryBorderColor: "#D4533D",
      secondaryColor: "#F0A868",
      secondaryTextColor: "#3D2B1F",
      secondaryBorderColor: "#D89050",
      tertiaryColor: "#FFF8F0",
      tertiaryTextColor: "#3D2B1F",
      tertiaryBorderColor: "#F0D0B0",
      lineColor: "#8B7355",
      textColor: "#3D2B1F",
      mainBkg: "#E8725C",
      nodeBorder: "#D4533D",
      clusterBkg: "#FFF0E6",
      clusterBorder: "#F0C8A8",
      titleColor: "#3D2B1F",
      edgeLabelBackground: "#FFFFFF",
      nodeTextColor: "#FFFFFF",
      pie1: "#E8725C",
      pie2: "#F0A868",
      pie3: "#6BBF7B",
      pie4: "#5B9BD5",
      pie5: "#C77DBA",
      pie6: "#F7DC6F",
      pie7: "#85C1E9",
      pie8: "#EB984E",
      pieTitleTextColor: "#3D2B1F",
      pieSectionTextColor: "#FFFFFF",
      pieLegendTextColor: "#3D2B1F",
      fontFamily: '"Pretendard", "Noto Sans KR", "Georgia", serif',
    },
  },
  dark: {
    theme: "dark",
    themeVariables: {
      primaryColor: "#6C5CE7",
      primaryTextColor: "#E8E8E8",
      primaryBorderColor: "#A29BFE",
      secondaryColor: "#2D3748",
      secondaryTextColor: "#E8E8E8",
      secondaryBorderColor: "#4A5568",
      tertiaryColor: "#1A202C",
      tertiaryTextColor: "#CBD5E0",
      tertiaryBorderColor: "#4A5568",
      lineColor: "#A0AEC0",
      textColor: "#E2E8F0",
      mainBkg: "#2D3748",
      nodeBorder: "#4A5568",
      clusterBkg: "#1A202C",
      clusterBorder: "#4A5568",
      titleColor: "#F7FAFC",
      edgeLabelBackground: "#2D3748",
      nodeTextColor: "#E2E8F0",
      pie1: "#6C5CE7",
      pie2: "#00CEC9",
      pie3: "#FD79A8",
      pie4: "#FDCB6E",
      pie5: "#55EFC4",
      pie6: "#E17055",
      pie7: "#74B9FF",
      pie8: "#A29BFE",
      pieTitleTextColor: "#F7FAFC",
      pieSectionTextColor: "#FFFFFF",
      pieLegendTextColor: "#E2E8F0",
      fontFamily: '"Pretendard", "Inter", "Segoe UI", sans-serif',
    },
  },
  minimal: {
    theme: "base",
    themeVariables: {
      primaryColor: "#E2E8F0",
      primaryTextColor: "#1A202C",
      primaryBorderColor: "#CBD5E0",
      secondaryColor: "#F7FAFC",
      secondaryTextColor: "#2D3748",
      secondaryBorderColor: "#E2E8F0",
      tertiaryColor: "#FFFFFF",
      tertiaryTextColor: "#4A5568",
      tertiaryBorderColor: "#E2E8F0",
      lineColor: "#A0AEC0",
      textColor: "#2D3748",
      mainBkg: "#F7FAFC",
      nodeBorder: "#CBD5E0",
      clusterBkg: "#FFFFFF",
      clusterBorder: "#E2E8F0",
      titleColor: "#1A202C",
      edgeLabelBackground: "#FFFFFF",
      nodeTextColor: "#1A202C",
      pie1: "#718096",
      pie2: "#A0AEC0",
      pie3: "#CBD5E0",
      pie4: "#E2E8F0",
      pie5: "#4A5568",
      pie6: "#2D3748",
      pie7: "#1A202C",
      pie8: "#F7FAFC",
      pieTitleTextColor: "#1A202C",
      pieSectionTextColor: "#1A202C",
      pieLegendTextColor: "#2D3748",
      fontFamily: '"Pretendard", "Helvetica Neue", "Arial", sans-serif',
    },
  },
};

const DEFAULT_THEME = "corporate";

// ===== Build HTML with embedded mermaid.js =====
function buildHTML(mermaidSource, themeConfig, bgColor) {
  const config = JSON.stringify({
    startOnLoad: false,
    theme: themeConfig.theme,
    themeVariables: themeConfig.themeVariables,
    securityLevel: "strict",
    fontFamily: themeConfig.themeVariables.fontFamily,
  });

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: ${bgColor};
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      padding: 40px;
    }
    #diagram-container {
      max-width: 95vw;
    }
    #diagram-container svg {
      max-width: 100%;
      height: auto;
    }
  </style>
</head>
<body>
  <div id="diagram-container">
    <pre class="mermaid">${escapeHTML(mermaidSource)}</pre>
  </div>
  <script>${MERMAID_SCRIPT}</script>
  <script>
    (async () => {
      try {
        mermaid.initialize(${config});
        await mermaid.run({ querySelector: '.mermaid' });
        window.__RENDER_COMPLETE__ = true;
      } catch (e) {
        document.body.innerHTML = '<pre style="color:red;">' + e.message + '</pre>';
        window.__RENDER_ERROR__ = e.message;
        window.__RENDER_COMPLETE__ = true;
      }
    })();
  </script>
</body>
</html>`;
}

function escapeHTML(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ===== Lazy puppeteer singleton =====
let _browser = null;
async function getBrowser() {
  if (!_browser || !_browser.isConnected()) {
    const puppeteer = await import("puppeteer");
    _browser = await puppeteer.default.launch({
      headless: "new",
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    });
    console.log("[mermaid-renderer] Puppeteer browser launched");
  }
  return _browser;
}

// ===== Health =====
app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    service: "mermaid-renderer",
    port: PORT,
    themes: Object.keys(THEME_PRESETS),
    hasMermaidJS: MERMAID_SCRIPT.length > 100,
    chartTypes: ["bar", "grouped-bar", "stacked-bar", "line", "area", "radar",
                 "combo", "pie", "donut", "doughnut",
                 "scatter", "heatmap", "funnel", "waterfall", "subplot"],
  });
});

// ===== List themes =====
app.get("/themes", (_req, res) => {
  const summaries = {};
  for (const [name, cfg] of Object.entries(THEME_PRESETS)) {
    summaries[name] = {
      base: cfg.theme,
      primaryColor: cfg.themeVariables.primaryColor,
      fontFamily: cfg.themeVariables.fontFamily,
    };
  }
  res.json({ themes: summaries, default: DEFAULT_THEME });
});

// ===== Render =====
app.post("/render", async (req, res) => {
  const {
    mermaid_source,
    format = "svg",
    theme = DEFAULT_THEME,
    theme_override = null,  // custom themeVariables to merge
    width = 1200,
    height = 800,
    background = "#FFFFFF",
    scale = 2,
  } = req.body || {};

  if (!mermaid_source || typeof mermaid_source !== "string") {
    return res.status(400).json({ error: "Missing or invalid mermaid_source" });
  }

  // Resolve theme: preset + optional override
  const preset = THEME_PRESETS[theme] || THEME_PRESETS[DEFAULT_THEME];
  const themeConfig = theme_override
    ? {
        theme: preset.theme,
        themeVariables: { ...preset.themeVariables, ...theme_override },
      }
    : preset;

  const bgColor = theme === "dark" ? "#1A202C" : background;
  const html = buildHTML(mermaid_source, themeConfig, bgColor);

  let page = null;
  try {
    const browser = await getBrowser();
    page = await browser.newPage();
    await page.setViewport({
      width: Math.min(width, 3000),
      height: Math.min(height, 3000),
      deviceScaleFactor: scale,
    });
    await page.setContent(html, { waitUntil: "networkidle0" });

    // Wait for mermaid render
    await page.waitForFunction("window.__RENDER_COMPLETE__ === true", {
      timeout: 15000,
    });

    // Check for render error
    const renderError = await page.evaluate(() => window.__RENDER_ERROR__);
    if (renderError) {
      await page.close();
      return res.status(422).json({
        error: "Mermaid syntax error",
        detail: renderError,
        hint: "Check that your mermaid source is valid syntax.",
      });
    }

    // Small delay for animations/fonts
    await new Promise((r) => setTimeout(r, 300));

    if (format === "png") {
      const buffer = await page.screenshot({ type: "png", fullPage: true });
      await page.close();
      res.setHeader("Content-Type", "image/png");
      return res.send(buffer);
    }

    if (format === "html") {
      const content = await page.content();
      await page.close();
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      return res.send(content);
    }

    // Default: SVG extraction
    const svgContent = await page.evaluate(() => {
      const container = document.getElementById("diagram-container");
      const svg = container?.querySelector("svg");
      if (!svg) return null;
      // Add xmlns for standalone SVG
      if (!svg.getAttribute("xmlns")) {
        svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      }
      return svg.outerHTML;
    });
    await page.close();

    if (!svgContent) {
      return res.status(500).json({ error: "No SVG element found after render" });
    }

    res.setHeader("Content-Type", "image/svg+xml");
    res.send(svgContent);
  } catch (err) {
    if (page) await page.close().catch(() => {});
    console.error("[mermaid-renderer] Render error:", err.message);
    res.status(500).json({
      error: "Render failed",
      detail: err.message,
    });
  }
});

// ===== Render Chart (Chart.js interactive HTML) =====
import { parseChartDSL } from "./chart/parser.js";
import { buildChartHTML } from "./chart/html-builder.js";

app.post("/render-chart", (req, res) => {
  const {
    chart_source,
    theme = "corporate",
    width = 900,
    height = 500,
  } = req.body || {};

  if (!chart_source || typeof chart_source !== "string") {
    return res.status(400).json({ error: "Missing or invalid chart_source" });
  }

  try {
    const spec = parseChartDSL(chart_source);
    const html = buildChartHTML(spec, theme, { width, height });
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.send(html);
  } catch (err) {
    console.error("[chart-renderer] Error:", err.message);
    res.status(422).json({
      error: "Chart render failed",
      detail: err.message,
      hint: "Check that your chart DSL syntax is valid.",
    });
  }
});

// ===== Graceful shutdown =====
process.on("SIGTERM", async () => {
  if (_browser) await _browser.close().catch(() => {});
  process.exit(0);
});
process.on("SIGINT", async () => {
  if (_browser) await _browser.close().catch(() => {});
  process.exit(0);
});

// ===== Start =====
app.listen(PORT, () => {
  console.log(`[mermaid-renderer] Listening on http://localhost:${PORT}`);
  console.log(`[mermaid-renderer] Themes: ${Object.keys(THEME_PRESETS).join(", ")}`);
  console.log(`[mermaid-renderer] Mermaid.js: ${(MERMAID_SCRIPT.length / 1024 / 1024).toFixed(1)}MB bundled`);
  console.log(`[mermaid-renderer] Chart.js: /render-chart endpoint (12 chart types)`);
});
