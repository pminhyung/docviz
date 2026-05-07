/**
 * Chart.js config generators — one function per chart type.
 * Each takes a parsed spec and theme, returns a Chart.js configuration object.
 */

export function buildChartConfig(spec, theme) {
  const builder = CHART_BUILDERS[spec.type];
  if (!builder) throw new Error(`Unknown chart type: ${spec.type}`);
  return builder(spec, theme);
}

// ── Bar (basic / grouped / stacked) ──────────────────────────

function barConfig(spec, theme) {
  const stacked = spec.type === "stacked-bar";
  return {
    type: "bar",
    data: {
      labels: spec.x,
      datasets: spec.series.map((s, i) => ({
        label: s.name,
        data: s.values,
        backgroundColor: theme.colors[i % theme.colors.length] + "CC",
        borderColor: theme.colors[i % theme.colors.length],
        borderWidth: 1,
      })),
    },
    options: {
      responsive: true,
      plugins: { title: titlePlugin(spec.title), legend: { position: "top" } },
      scales: {
        x: { stacked, grid: { color: theme.gridColor } },
        y: { stacked, beginAtZero: true, grid: { color: theme.gridColor } },
      },
    },
  };
}

// ── Line ─────────────────────────────────────────────────────

function lineConfig(spec, theme) {
  return {
    type: "line",
    data: {
      labels: spec.x,
      datasets: spec.series.map((s, i) => ({
        label: s.name,
        data: s.values,
        borderColor: theme.colors[i % theme.colors.length],
        backgroundColor: theme.colors[i % theme.colors.length] + "33",
        tension: 0.3,
        fill: false,
        pointRadius: 4,
      })),
    },
    options: {
      responsive: true,
      plugins: { title: titlePlugin(spec.title), legend: { position: "top" } },
      scales: {
        x: { grid: { color: theme.gridColor } },
        y: { beginAtZero: true, grid: { color: theme.gridColor } },
      },
    },
  };
}

// ── Area (line with fill) ───────────────────────────────────

function areaConfig(spec, theme) {
  return {
    type: "line",
    data: {
      labels: spec.x,
      datasets: spec.series.map((s, i) => ({
        label: s.name,
        data: s.values,
        borderColor: theme.colors[i % theme.colors.length],
        backgroundColor: theme.colors[i % theme.colors.length] + "55",
        tension: 0.3,
        fill: true,
        pointRadius: 3,
      })),
    },
    options: {
      responsive: true,
      plugins: { title: titlePlugin(spec.title), legend: { position: "top" } },
      scales: {
        x: { grid: { color: theme.gridColor } },
        y: { beginAtZero: true, stacked: spec.series.length > 1,
              grid: { color: theme.gridColor } },
      },
    },
  };
}

// ── Radar ───────────────────────────────────────────────────

function radarConfig(spec, theme) {
  return {
    type: "radar",
    data: {
      labels: spec.x,
      datasets: spec.series.map((s, i) => ({
        label: s.name,
        data: s.values,
        borderColor: theme.colors[i % theme.colors.length],
        backgroundColor: theme.colors[i % theme.colors.length] + "33",
        borderWidth: 2,
        pointRadius: 4,
      })),
    },
    options: {
      responsive: true,
      plugins: { title: titlePlugin(spec.title), legend: { position: "top" } },
      scales: {
        r: { beginAtZero: true, grid: { color: theme.gridColor },
              pointLabels: { color: theme.fontColor || "#333" } },
      },
    },
  };
}

// ── Combo (bar + line, dual Y-axis) ─────────────────────────

function comboConfig(spec, theme) {
  const datasets = spec.series.map((s, i) => {
    const isLine = s.type === "line";
    const yAxisID = s.axis === "right" ? "yRight" : "yLeft";
    return {
      label: s.name,
      data: s.values,
      type: isLine ? "line" : "bar",
      yAxisID,
      borderColor: theme.colors[i % theme.colors.length],
      backgroundColor: isLine
        ? theme.colors[i % theme.colors.length] + "33"
        : theme.colors[i % theme.colors.length] + "CC",
      tension: isLine ? 0.3 : undefined,
      fill: false,
      pointRadius: isLine ? 4 : undefined,
      borderWidth: isLine ? 2 : 1,
      order: isLine ? 0 : 1, // lines on top
    };
  });

  const scales = {
    x: { grid: { color: theme.gridColor } },
    yLeft: {
      type: "linear",
      position: "left",
      beginAtZero: true,
      title: { display: !!spec.yLeft?.label, text: spec.yLeft?.label || "" },
      grid: { color: theme.gridColor },
    },
    yRight: {
      type: "linear",
      position: "right",
      beginAtZero: true,
      title: { display: !!spec.yRight?.label, text: spec.yRight?.label || "" },
      grid: { drawOnChartArea: false },
    },
  };

  // Apply min/max if specified
  if (spec.yLeft?.min != null) scales.yLeft.min = spec.yLeft.min;
  if (spec.yLeft?.max != null) scales.yLeft.max = spec.yLeft.max;
  if (spec.yRight?.min != null) scales.yRight.min = spec.yRight.min;
  if (spec.yRight?.max != null) scales.yRight.max = spec.yRight.max;

  return {
    type: "bar", // base type, individual datasets override
    data: { labels: spec.x, datasets },
    options: {
      responsive: true,
      plugins: { title: titlePlugin(spec.title), legend: { position: "top" } },
      scales,
    },
  };
}

// ── Pie / Donut ─────────────────────────────────────────────

function pieConfig(spec, theme) {
  const isDonut = spec.type === "donut" || spec.type === "doughnut";
  return {
    type: "pie",
    data: {
      labels: spec.labels || spec.series.map(s => s.name),
      datasets: [{
        data: spec.values || spec.series.map(s => s.values[0]),
        backgroundColor: theme.colors.slice(0, (spec.labels || spec.series).length),
        borderWidth: 2,
        borderColor: theme.background,
      }],
    },
    options: {
      responsive: true,
      cutout: isDonut ? "50%" : 0,
      plugins: {
        title: titlePlugin(spec.title),
        legend: { position: "right" },
      },
    },
  };
}

// ── Scatter ──────────────────────────────────────────────────

function scatterConfig(spec, theme) {
  return {
    type: "scatter",
    data: {
      datasets: spec.series.map((s, i) => ({
        label: s.name,
        data: s.values.map(v => (Array.isArray(v) ? { x: v[0], y: v[1] } : v)),
        backgroundColor: theme.colors[i % theme.colors.length] + "AA",
        borderColor: theme.colors[i % theme.colors.length],
        pointRadius: 6,
      })),
    },
    options: {
      responsive: true,
      plugins: { title: titlePlugin(spec.title), legend: { position: "top" } },
      scales: {
        x: { title: { display: !!spec.xLabel, text: spec.xLabel || "" }, grid: { color: theme.gridColor } },
        y: { title: { display: !!spec.yLabel, text: spec.yLabel || "" }, grid: { color: theme.gridColor } },
      },
    },
  };
}

// ── Funnel ───────────────────────────────────────────────────

function funnelConfig(spec, theme) {
  // Funnel rendered as horizontal bar chart, sorted descending
  const sorted = [...spec.series].sort((a, b) => b.values[0] - a.values[0]);
  return {
    type: "bar",
    data: {
      labels: sorted.map(s => s.name),
      datasets: [{
        data: sorted.map(s => s.values[0]),
        backgroundColor: sorted.map((_, i) => theme.colors[i % theme.colors.length] + "CC"),
        borderWidth: 0,
        barPercentage: 0.9,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: {
        title: titlePlugin(spec.title),
        legend: { display: false },
      },
      scales: {
        x: { beginAtZero: true, grid: { color: theme.gridColor } },
        y: { grid: { display: false } },
      },
    },
  };
}

// ── Heatmap (using matrix plugin concept — grid of colored rects) ──

function heatmapConfig(spec, theme) {
  // Heatmap as bubble chart with fixed radius and color coding
  // (Chart.js doesn't have native heatmap — we simulate with a grid approach)
  const datasets = [];
  const data = spec.data || [];
  const yLabels = spec.yCategories || data.map((_, i) => `Row ${i + 1}`);

  // Flatten to data points
  const allValues = data.flat();
  const minVal = Math.min(...allValues);
  const maxVal = Math.max(...allValues);

  const points = [];
  for (let row = 0; row < data.length; row++) {
    for (let col = 0; col < (data[row] || []).length; col++) {
      const val = data[row][col];
      const intensity = maxVal > minVal ? (val - minVal) / (maxVal - minVal) : 0.5;
      points.push({ x: col, y: row, v: val, r: 20, intensity });
    }
  }

  // Heatmap needs runtime callbacks (tooltip, axis ticks) that can't survive JSON.stringify.
  // Store metadata as _heatmapMeta and inject callbacks via inline script in html-builder.
  const bgColors = points.map(p => {
    const c = theme.colors[0];
    const alpha = 0.2 + p.intensity * 0.8;
    return c + Math.round(alpha * 255).toString(16).padStart(2, "0");
  });

  return {
    type: "bubble",
    _heatmapMeta: { points, xLabels: spec.x || [], yLabels },
    data: {
      datasets: [{
        data: points.map(p => ({ x: p.x, y: p.y, r: p.r })),
        backgroundColor: bgColors,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        title: titlePlugin(spec.title),
        legend: { display: false },
        // tooltip callback injected at runtime in html-builder.js
      },
      scales: {
        x: {
          type: "linear",
          // tick callback injected at runtime in html-builder.js
          grid: { color: theme.gridColor },
        },
        y: {
          type: "linear",
          grid: { color: theme.gridColor },
          reverse: true,
        },
      },
    },
  };
}

// ── Waterfall ────────────────────────────────────────────────

function waterfallConfig(spec, theme) {
  // Waterfall: each bar starts where the previous ended
  const labels = spec.series.map(s => s.name);
  const values = spec.series.map(s => s.values[0]);
  let cumulative = 0;
  const bases = [];
  const heights = [];
  const colors = [];

  for (let i = 0; i < values.length; i++) {
    bases.push(cumulative);
    heights.push(values[i]);
    const posColor = theme.colors[0] || "#4A90D9";
    const negColor = theme.colors[Math.min(5, theme.colors.length - 1)] || "#FC8181";
    colors.push(values[i] >= 0 ? posColor + "CC" : negColor + "CC");
    cumulative += values[i];
  }

  return {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Base", data: bases, backgroundColor: "transparent", borderWidth: 0 },
        { label: "Value", data: heights, backgroundColor: colors, borderWidth: 0 },
      ],
    },
    options: {
      responsive: true,
      plugins: { title: titlePlugin(spec.title), legend: { display: false } },
      scales: {
        x: { stacked: true, grid: { color: theme.gridColor } },
        y: { stacked: true, grid: { color: theme.gridColor } },
      },
    },
  };
}

// ── Helpers ──────────────────────────────────────────────────

function titlePlugin(text) {
  return { display: !!text, text: text || "", font: { size: 16, weight: "bold" } };
}

// ── Builder registry ────────────────────────────────────────

const CHART_BUILDERS = {
  bar: barConfig,
  "grouped-bar": barConfig,     // same as bar with multiple series
  "stacked-bar": barConfig,     // same with stacked: true
  line: lineConfig,
  combo: comboConfig,
  pie: pieConfig,
  donut: pieConfig,
  doughnut: pieConfig,
  area: areaConfig,
  radar: radarConfig,
  scatter: scatterConfig,
  heatmap: heatmapConfig,
  funnel: funnelConfig,
  waterfall: waterfallConfig,
  // subplot is handled separately in html-builder
};
