/**
 * Build self-contained interactive HTML with Chart.js embedded.
 */

import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { buildChartConfig } from "./templates.js";
import { CHART_THEMES, DEFAULT_THEME } from "./themes.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Load Chart.js UMD bundle once
let CHART_JS = "";
try {
  CHART_JS = readFileSync(join(__dirname, "..", "chart.min.js"), "utf-8");
} catch {
  console.warn("[chart] chart.min.js not found — download from CDN");
}

/**
 * Build a self-contained HTML page with an interactive Chart.js chart.
 * @param {object} spec - Parsed chart spec from parser.js
 * @param {string} themeName - Theme preset name
 * @param {object} options - { width, height }
 * @returns {string} Complete HTML string
 */
export function buildChartHTML(spec, themeName = DEFAULT_THEME, options = {}) {
  const theme = CHART_THEMES[themeName] || CHART_THEMES[DEFAULT_THEME];
  const width = options.width || 900;
  const height = options.height || 500;

  // Subplot: multiple charts in grid
  if (spec.type === "subplot") {
    return buildSubplotHTML(spec, theme, options);
  }

  const config = buildChartConfig(spec, theme);

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: ${theme.background};
      color: ${theme.textColor};
      font-family: ${theme.fontFamily};
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      padding: 24px;
    }
    .chart-container {
      position: relative;
      width: ${width}px;
      max-width: 95vw;
    }
  </style>
</head>
<body>
  <div class="chart-container">
    <canvas id="chart"></canvas>
  </div>
  <script>${CHART_JS}</script>
  <script>
    Chart.defaults.color = '${theme.textColor}';
    Chart.defaults.font.family = ${JSON.stringify(theme.fontFamily)};
    ${buildChartInitScript(config)}
  </script>
</body>
</html>`;
}

/**
 * Build Chart.js init script. Handles heatmap callbacks that can't survive JSON.stringify.
 */
function buildChartInitScript(config) {
  // Heatmap: inject tooltip + axis callbacks as runtime code
  if (config._heatmapMeta) {
    const meta = config._heatmapMeta;
    const cleanConfig = { ...config };
    delete cleanConfig._heatmapMeta;
    return `
    var _hm = ${JSON.stringify(meta)};
    var _cfg = ${JSON.stringify(cleanConfig)};
    _cfg.options.plugins.tooltip = {
      callbacks: {
        label: function(ctx) {
          var p = _hm.points[ctx.dataIndex];
          var xl = _hm.xLabels[p.x] || p.x;
          var yl = _hm.yLabels[p.y] || p.y;
          return yl + ' × ' + xl + ': ' + p.v;
        }
      }
    };
    _cfg.options.scales.x.ticks = { callback: function(v) { return _hm.xLabels[v] || v; }, stepSize: 1 };
    _cfg.options.scales.y.ticks = { callback: function(v) { return _hm.yLabels[v] || v; }, stepSize: 1 };
    new Chart(document.getElementById('chart'), _cfg);`;
  }
  // Default: plain JSON config (no functions needed)
  return `new Chart(document.getElementById('chart'), ${JSON.stringify(config)});`;
}

/**
 * Build subplot init scripts — delegates to buildChartInitScript per panel.
 */
function buildSubplotInitScripts(canvases) {
  return canvases.map(c => {
    const script = buildChartInitScript(c.config);
    return script.replace(/getElementById\('chart'\)/, `getElementById('${c.id}')`);
  }).join("\n    ");
}

/**
 * Build subplot (NxM grid of charts) HTML.
 */
function buildSubplotHTML(spec, theme, options) {
  const { rows, cols, panels } = spec;
  const cellWidth = Math.floor((options.width || 900) / cols);
  const cellHeight = Math.floor((options.height || 500) / rows);

  const canvases = panels.map((panelSpec, i) => {
    const config = buildChartConfig(panelSpec, theme);
    return {
      id: `chart-${i}`,
      config,
    };
  });

  const gridHTML = canvases.map(c =>
    `<div class="cell"><canvas id="${c.id}"></canvas></div>`
  ).join("\n");

  const initScripts = buildSubplotInitScripts(canvases);

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: ${theme.background};
      color: ${theme.textColor};
      font-family: ${theme.fontFamily};
      padding: 24px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(${cols}, 1fr);
      grid-template-rows: repeat(${rows}, 1fr);
      gap: 16px;
      max-width: 95vw;
      margin: 0 auto;
    }
    .cell {
      position: relative;
      min-height: ${cellHeight}px;
    }
  </style>
</head>
<body>
  <div class="grid">
    ${gridHTML}
  </div>
  <script>${CHART_JS}</script>
  <script>
    Chart.defaults.color = '${theme.textColor}';
    Chart.defaults.font.family = ${JSON.stringify(theme.fontFamily)};
    ${initScripts}
  </script>
</body>
</html>`;
}
