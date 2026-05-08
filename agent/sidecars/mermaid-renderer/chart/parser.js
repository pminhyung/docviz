/**
 * Chart DSL parser — converts source text to chart spec JSON.
 *
 * DSL format:
 *   chart:<type>
 *   title: <text>
 *   x: [cat1, cat2, ...]
 *   y-left: "label" min --> max       (optional, for combo)
 *   y-right: "label" min --> max      (optional, for combo)
 *   bar [y-left|y-right] <name>: [v1, v2, ...]
 *   line [y-left|y-right] <name>: [v1, v2, ...]
 *   series:                           (for grouped/stacked/pie)
 *     <name>: [v1, v2, ...]
 *   data:                             (for heatmap)
 *     [v1, v2, ...]
 *   stages:                           (for funnel)
 *     <name>: <value>
 *
 * Subplot:
 *   chart:subplot <rows>x<cols>
 *   ---
 *   type: <chartType>
 *   title: ...
 *   ...
 *   ---
 *   ...
 */

/**
 * Parse chart DSL source text into a structured spec object.
 * @param {string} source - Chart DSL text
 * @returns {object} Chart spec
 */
export function parseChartDSL(source) {
  const lines = source.trim().split("\n");
  if (!lines.length) throw new Error("Empty chart source");

  // First line: chart:<type> [options]
  const headerMatch = lines[0].match(/^chart:(\S+)\s*(.*)?$/i);
  if (!headerMatch) throw new Error(`Invalid chart header: ${lines[0]}`);

  const chartType = headerMatch[1].toLowerCase();
  const headerOpts = (headerMatch[2] || "").trim();

  // Subplot: split by --- and parse each panel
  if (chartType === "subplot") {
    return parseSubplot(lines, headerOpts);
  }

  return parseSingleChart(chartType, lines.slice(1));
}

function parseSingleChart(type, lines) {
  const spec = { type, title: "", x: [], series: [], yLeft: null, yRight: null };
  let mode = null; // "series" | "data" | "stages"
  let currentData = [];

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith("%%")) continue;

    // title
    if (line.startsWith("title:")) {
      spec.title = line.slice(6).trim().replace(/^["']|["']$/g, "");
      continue;
    }

    // x-axis
    if (line.startsWith("x:")) {
      spec.x = parseArray(line.slice(2));
      continue;
    }

    // y-axis labels (for single axis charts)
    if (line.startsWith("y:") && !line.startsWith("y-")) {
      const arr = parseArray(line.slice(2));
      if (arr.length) {
        // Could be y-axis categories (heatmap) or simple data
        if (type === "heatmap") {
          spec.yCategories = arr;
        } else {
          spec.series.push({ name: "data", values: arr.map(Number), axis: "left" });
        }
      }
      continue;
    }

    // y-left / y-right axis config (combo charts)
    const yAxisMatch = line.match(/^y-(left|right):\s*"?([^"]*)"?\s*(\d+)?\s*(?:-->)?\s*(\d+)?/);
    if (yAxisMatch) {
      const side = yAxisMatch[1];
      const label = yAxisMatch[2].trim();
      const min = yAxisMatch[3] ? Number(yAxisMatch[3]) : null;
      const max = yAxisMatch[4] ? Number(yAxisMatch[4]) : null;
      spec[side === "left" ? "yLeft" : "yRight"] = { label, min, max };
      continue;
    }

    // bar/line with optional axis binding
    const seriesLineMatch = line.match(/^(bar|line)\s+(?:y-(left|right)\s+)?(.+?):\s*\[(.+)\]/);
    if (seriesLineMatch) {
      const seriesType = seriesLineMatch[1];
      const axis = seriesLineMatch[2] || "left";
      const name = seriesLineMatch[3].trim();
      const values = seriesLineMatch[4].split(",").map(v => Number(v.trim()));
      spec.series.push({ name, values, type: seriesType, axis });
      continue;
    }

    // series: block start
    if (line === "series:") {
      mode = "series";
      continue;
    }

    // data: block start (heatmap)
    if (line === "data:") {
      mode = "data";
      currentData = [];
      continue;
    }

    // stages: block start (funnel)
    if (line === "stages:") {
      mode = "stages";
      continue;
    }

    // colorScale (heatmap)
    if (line.startsWith("colorScale:")) {
      spec.colorScale = line.slice(11).trim();
      continue;
    }

    // Indented lines (mode-dependent)
    if (mode === "series") {
      const m = line.match(/^(.+?):\s*\[(.+)\]/);
      if (m) {
        spec.series.push({
          name: m[1].trim(),
          values: m[2].split(",").map(v => Number(v.trim())),
        });
      } else {
        // Scalar form `name: <number>` (single-value series, e.g. pie/donut/doughnut)
        const ms = line.match(/^(.+?):\s*([-+0-9.eE_,]+)\s*$/);
        if (ms) {
          const raw = ms[2].replace(/[_,]/g, "");
          const v = Number(raw);
          if (!Number.isNaN(v)) {
            spec.series.push({ name: ms[1].trim(), values: [v] });
          }
        }
      }
    } else if (mode === "data") {
      const m = line.match(/^\[(.+)\]/);
      if (m) {
        currentData.push(m[1].split(",").map(v => Number(v.trim())));
      }
      spec.data = currentData;
    } else if (mode === "stages") {
      const m = line.match(/^(.+?):\s*(\d+)/);
      if (m) {
        spec.series.push({ name: m[1].trim(), values: [Number(m[2])] });
      }
    }
  }

  // Pie/donut/doughnut: convert series to labels+values format
  if ((type === "pie" || type === "donut" || type === "doughnut")
      && spec.series.length) {
    spec.labels = spec.series.map(s => s.name);
    spec.values = spec.series.map(s => s.values[0]);
  }

  return spec;
}

function parseSubplot(lines, headerOpts) {
  const layoutMatch = headerOpts.match(/(\d+)x(\d+)/);
  const rows = layoutMatch ? Number(layoutMatch[1]) : 1;
  const cols = layoutMatch ? Number(layoutMatch[2]) : 2;

  // Split panels by ---
  const panels = [];
  let currentLines = [];

  for (const line of lines.slice(1)) {
    if (line.trim() === "---") {
      if (currentLines.length) {
        panels.push(currentLines);
      }
      currentLines = [];
    } else {
      currentLines.push(line);
    }
  }
  if (currentLines.length) panels.push(currentLines);

  const specs = panels.map(panelLines => {
    // Find type line
    const typeLine = panelLines.find(l => l.trim().startsWith("type:"));
    const type = typeLine ? typeLine.trim().slice(5).trim() : "bar";
    const remaining = panelLines.filter(l => !l.trim().startsWith("type:"));
    return parseSingleChart(type, remaining);
  });

  return { type: "subplot", rows, cols, panels: specs };
}

function parseArray(str) {
  const m = str.match(/\[(.+)\]/);
  if (!m) return [];
  return m[1].split(",").map(v => v.trim().replace(/^["']|["']$/g, ""));
}
