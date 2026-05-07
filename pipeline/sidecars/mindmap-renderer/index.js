import express from "express";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app = express();
const PORT = parseInt(process.env.MINDMAP_PORT || "3004", 10);
const MAX_BODY = "10mb";

app.use(express.json({ limit: MAX_BODY }));

// ===== Load D3.js (bundled UMD file) =====
let D3_SCRIPT = "";
try {
  D3_SCRIPT = readFileSync(join(__dirname, "d3.min.js"), "utf-8");
} catch {
  console.warn("WARNING: d3.min.js not found. Download it: curl -sL https://d3js.org/d3.v7.min.js -o d3.min.js");
  D3_SCRIPT = `/* D3 not found */`;
}

// ===== Load HTML template =====
const TEMPLATE = readFileSync(
  join(__dirname, "templates", "mindmap.html"),
  "utf-8"
);

// ===== Themes list =====
const THEMES = ["corporate", "academic", "creative", "dark", "minimal", "nature"];
const LAYOUTS = ["radial", "tree_lr", "tree_td"];

// ===== Health =====
app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "mindmap-renderer", port: PORT });
});

// ===== Themes =====
app.get("/themes", (_req, res) => {
  res.json({ themes: THEMES, layouts: LAYOUTS });
});

// ===== Render HTML =====
app.post("/render", (req, res) => {
  try {
    const data = req.body;
    if (!data || !data.nodes || data.nodes.length === 0) {
      return res.status(400).json({ error: "Missing or empty nodes array" });
    }
    const html = generateHTML(data);
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.send(html);
  } catch (err) {
    console.error("Render error:", err);
    res.status(500).json({
      error: "Render failed",
      detail: err.message,
      hint: "Check that your MindmapData JSON is valid",
    });
  }
});

// ===== Render PNG =====
app.post("/render-png", async (req, res) => {
  let browser = null;
  try {
    const data = req.body;
    if (!data || !data.nodes || data.nodes.length === 0) {
      return res.status(400).json({ error: "Missing or empty nodes array" });
    }

    const w = data.options?.width || 1600;
    const h = data.options?.height || 1200;
    const html = generateHTML(data);

    // Dynamic import of puppeteer (heavy dep)
    const puppeteer = await import("puppeteer");
    browser = await puppeteer.default.launch({
      headless: "new",
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    });
    const page = await browser.newPage();
    await page.setViewport({ width: w, height: h, deviceScaleFactor: 2 });
    await page.setContent(html, { waitUntil: "networkidle0" });

    // Wait for render complete signal
    await page.waitForFunction("window.__RENDER_COMPLETE__ === true", {
      timeout: 15000,
    });
    // Small extra delay for animations
    await new Promise((r) => setTimeout(r, 500));

    const buffer = await page.screenshot({ type: "png", fullPage: false });
    await browser.close();
    browser = null;

    res.setHeader("Content-Type", "image/png");
    res.send(buffer);
  } catch (err) {
    if (browser) await browser.close().catch(() => {});
    console.error("PNG render error:", err);
    res.status(500).json({
      error: "PNG render failed",
      detail: err.message,
    });
  }
});

// ===== Render SVG =====
app.post("/render-svg", async (req, res) => {
  let browser = null;
  try {
    const data = req.body;
    if (!data || !data.nodes || data.nodes.length === 0) {
      return res.status(400).json({ error: "Missing or empty nodes array" });
    }

    const w = data.options?.width || 1600;
    const h = data.options?.height || 1200;
    const html = generateHTML(data);

    const puppeteer = await import("puppeteer");
    browser = await puppeteer.default.launch({
      headless: "new",
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    });
    const page = await browser.newPage();
    await page.setViewport({ width: w, height: h });
    await page.setContent(html, { waitUntil: "networkidle0" });
    await page.waitForFunction("window.__RENDER_COMPLETE__ === true", {
      timeout: 15000,
    });

    // Extract SVG element
    const svgContent = await page.evaluate(() => {
      const svg = document.getElementById("mindmap-svg");
      // Inject styles
      const styles = document.querySelector("style").textContent;
      const styleEl = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "style"
      );
      styleEl.textContent = styles;
      svg.insertBefore(styleEl, svg.firstChild);
      return new XMLSerializer().serializeToString(svg);
    });

    await browser.close();
    browser = null;

    res.setHeader("Content-Type", "image/svg+xml");
    res.send(svgContent);
  } catch (err) {
    if (browser) await browser.close().catch(() => {});
    console.error("SVG render error:", err);
    res.status(500).json({
      error: "SVG render failed",
      detail: err.message,
    });
  }
});

// ===== HTML Generation =====
function generateHTML(data) {
  const title = data.title || "Mindmap";
  const subtitle = data.subtitle || "";
  const theme = THEMES.includes(data.theme) ? data.theme : "corporate";

  // Sanitize data for JSON embedding
  const dataJson = JSON.stringify(data)
    .replace(/<\/script>/gi, "<\\/script>")
    .replace(/<!--/g, "<\\!--");

  let html = TEMPLATE;
  html = html.replace(/\{\{TITLE\}\}/g, escapeHtml(title));
  html = html.replace(/\{\{SUBTITLE\}\}/g, escapeHtml(subtitle));
  html = html.replace(/\{\{THEME\}\}/g, theme);
  // Use split/join to avoid $ replacement issues in JSON data
  const dataParts = html.split("{{DATA_JSON}}");
  if (dataParts.length === 2) {
    html = dataParts[0] + dataJson + dataParts[1];
  }
  // Use split/join to avoid $ replacement issues in D3 source code
  const D3_PLACEHOLDER = "// We use a bundled D3 from the server side: {{D3_SCRIPT}}";
  const parts = html.split(D3_PLACEHOLDER);
  if (parts.length === 2) {
    html = parts[0] + D3_SCRIPT + parts[1];
  }

  return html;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ===== Start =====
app.listen(PORT, () => {
  console.log(`mindmap-renderer listening on :${PORT}`);
  console.log(`  GET  /health`);
  console.log(`  GET  /themes`);
  console.log(`  POST /render      → HTML`);
  console.log(`  POST /render-png  → PNG`);
  console.log(`  POST /render-svg  → SVG`);
});
