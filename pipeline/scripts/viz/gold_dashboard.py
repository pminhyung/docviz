"""Gold-output viewer dashboard.

Browses every rendered PNG under data/gold/{chart,mindmap,diagram}/.
Supports keyboard nav (arrows), direct idx input, ±10 skip, viz-type filter.

Run:
    python -m scripts.viz.gold_dashboard            # default port 9039
    python -m scripts.viz.gold_dashboard --port N

Open: http://localhost:9039/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from flask import Flask, abort, redirect, render_template_string, request, send_file, url_for

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

GOLD_DIR = os.path.join(ROOT, "data", "gold")
CORPUS = os.path.join(ROOT, "data", "documents", "corpus.jsonl")
VIZ_TYPES = ["chart", "mindmap", "diagram"]


def _build_corpus_index() -> dict:
    out = {}
    with open(CORPUS, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            out[r["doc_id"]] = {
                "chart_subtype": r.get("chart_subtype", ""),
                "diagram_subtype": r.get("diagram_subtype", ""),
                "lang": r.get("lang", ""),
                "domain": r.get("domain", ""),
                "title": (r.get("title") or "")[:160],
            }
    return out


def _build_image_index() -> list[dict]:
    """Walk gold/{viz}/{doc}_rendered.png. One row per image."""
    rows = []
    for viz in VIZ_TYPES:
        d = os.path.join(GOLD_DIR, viz)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith("_rendered.png"):
                continue
            doc_id = f[: -len("_rendered.png")]
            rows.append({"viz": viz, "doc_id": doc_id})
    return rows


PAGE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>VisuBench gold dashboard ({{ viz_filter or 'all' }} {{ idx + 1 }}/{{ total }})</title>
  <style>
    body { margin:0; font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
           background:#0e1116; color:#e3e8ef; }
    header { padding:8px 14px; background:#1a1f29; border-bottom:1px solid #2a2f3a;
             display:flex; gap:14px; align-items:center; flex-wrap:wrap;}
    header form { display:flex; gap:6px; align-items:center;}
    header input[type=number]{ width:70px; padding:4px 6px; background:#0e1116;
        color:#e3e8ef; border:1px solid #444; border-radius:4px;}
    header select { padding:4px 6px; background:#0e1116; color:#e3e8ef;
        border:1px solid #444; border-radius:4px;}
    header a, header button { padding:4px 10px; border:1px solid #3a4250;
        background:#1f2632; color:#e3e8ef; border-radius:4px; text-decoration:none;
        cursor:pointer; font-size:13px; }
    header a:hover, header button:hover { background:#2a3140; }
    header a.disabled { opacity:0.35; pointer-events:none; }
    .meta { font-size:12px; color:#8e98a6; }
    .meta b { color:#cdd6e1; font-weight:600;}
    .pill { padding:2px 8px; border-radius:10px; background:#2a2f3a;
            font-size:11px; color:#9ab; }
    main { display:flex; flex-direction:row; padding:0; }
    .stage { flex:1; min-width:0; padding:18px; display:flex;
             flex-direction:column; align-items:center;}
    .stage img { max-width: 100%; max-height: 78vh; object-fit:contain;
                 background:#fff; border:1px solid #2a2f3a;}
    aside { width:360px; padding:14px; background:#15191f; border-left:1px solid #2a2f3a;
            font-size:12.5px; color:#cdd6e1; max-height:calc(100vh - 56px);
            overflow:auto;}
    aside h3 { margin:0 0 6px; font-size:12px; color:#9ab; text-transform:uppercase;
               letter-spacing:0.06em;}
    aside pre { white-space:pre-wrap; word-break:break-word; background:#0e1116;
                padding:10px; border-radius:6px; border:1px solid #222831;
                font-size:11.5px; line-height:1.45; color:#dde3ec;
                max-height:30vh; overflow:auto;}
    .toggle { cursor:pointer; user-select:none; color:#7aa7ff;}
    .small { color:#67707d; font-size:11px;}
    kbd { padding:1px 5px; border:1px solid #2f3540; border-radius:3px;
          background:#0e1116; font-family:monospace; font-size:11px; color:#9ab;}
  </style>
</head>
<body>
<header>
  <a href="{{ url_for('view', idx=prev10) }}" {% if idx==0 %}class="disabled"{% endif %}>« 10</a>
  <a href="{{ url_for('view', idx=prev1) }}"  {% if idx==0 %}class="disabled"{% endif %}>‹ 1</a>
  <span class="meta"><b>{{ idx + 1 }}</b> / {{ total }}</span>
  <a href="{{ url_for('view', idx=next1) }}"  {% if idx==total-1 %}class="disabled"{% endif %}>1 ›</a>
  <a href="{{ url_for('view', idx=next10) }}" {% if idx==total-1 %}class="disabled"{% endif %}>10 »</a>

  <form method="get" action="{{ url_for('view', idx=0) }}" onsubmit="this.action='/view/'+(parseInt(this.idx.value)-1);">
    <span class="small">jump to</span>
    <input type="number" name="idx" min="1" max="{{ total }}" value="{{ idx + 1 }}">
    <button type="submit">go</button>
  </form>

  <form method="get" action="{{ url_for('view', idx=0) }}">
    <span class="small">filter</span>
    <select name="viz" onchange="this.form.submit();">
      <option value="" {% if not viz_filter %}selected{% endif %}>all ({{ counts.all }})</option>
      <option value="chart"   {% if viz_filter=='chart' %}selected{% endif %}>chart ({{ counts.chart }})</option>
      <option value="mindmap" {% if viz_filter=='mindmap' %}selected{% endif %}>mindmap ({{ counts.mindmap }})</option>
      <option value="diagram" {% if viz_filter=='diagram' %}selected{% endif %}>diagram ({{ counts.diagram }})</option>
    </select>
  </form>

  {% if row %}
  <span class="pill">{{ row.viz }}{% if row.subtype %} • {{ row.subtype }}{% endif %}</span>
  <span class="meta"><b>{{ row.doc_id }}</b></span>
  <span class="meta">{{ row.lang or '?' }} · {{ row.domain or '?' }}</span>
  {% endif %}
</header>

<main>
  <div class="stage">
    {% if row %}
      <img src="{{ url_for('image', viz=row.viz, doc_id=row.doc_id) }}" alt="{{ row.doc_id }}">
      <div class="meta" style="margin-top:8px;">
        title: {{ row.title or '(no title)' }}
      </div>
    {% else %}
      <div class="meta">No image at this index.</div>
    {% endif %}
  </div>

  <aside>
    <h3>Source DSL</h3>
    {% if row %}
    <pre>{{ source_text }}</pre>
    {% else %}
    <pre>(no source)</pre>
    {% endif %}
    <h3 style="margin-top:14px;">Shortcuts</h3>
    <div class="small">
      <kbd>←</kbd> prev 1 &nbsp; <kbd>→</kbd> next 1<br>
      <kbd>Shift</kbd>+<kbd>←</kbd>/<kbd>→</kbd> ±10<br>
      <kbd>Home</kbd> first &nbsp; <kbd>End</kbd> last<br>
      type a number then <kbd>Enter</kbd> to jump
    </div>
  </aside>
</main>

<script>
const total = {{ total }};
const idx = {{ idx }};
const viz = "{{ viz_filter or '' }}";
function go(target){
  if (target<0) target=0;
  if (target>=total) target=total-1;
  let url = '/view/'+target;
  if (viz) url += '?viz='+encodeURIComponent(viz);
  window.location.href = url;
}
let buf="";
let bufTimer=null;
document.addEventListener('keydown', (e)=>{
  if (e.target.tagName==='INPUT' || e.target.tagName==='SELECT') return;
  const step = e.shiftKey ? 10 : 1;
  if (e.key==='ArrowLeft')  { e.preventDefault(); go(idx-step); }
  else if (e.key==='ArrowRight') { e.preventDefault(); go(idx+step); }
  else if (e.key==='Home') { e.preventDefault(); go(0); }
  else if (e.key==='End')  { e.preventDefault(); go(total-1); }
  else if (/^[0-9]$/.test(e.key)) {
    buf += e.key;
    clearTimeout(bufTimer);
    bufTimer = setTimeout(()=>{ buf=""; }, 1500);
  } else if (e.key==='Enter' && buf) {
    e.preventDefault();
    go(parseInt(buf,10)-1);
    buf="";
  }
});
</script>
</body></html>
"""


def _filter_index(images: list[dict], viz: Optional[str]) -> list[dict]:
    if not viz:
        return images
    return [r for r in images if r["viz"] == viz]


def _read_source(viz: str, doc_id: str, max_chars: int = 4000) -> str:
    p = os.path.join(GOLD_DIR, viz, f"{doc_id}_source.txt")
    if not os.path.exists(p):
        return ""
    try:
        with open(p, encoding="utf-8") as f:
            text = f.read()
        return text[:max_chars] + ("\n\n... (truncated)" if len(text) > max_chars else "")
    except OSError:
        return ""


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["IMAGE_INDEX"] = _build_image_index()
    app.config["CORPUS"] = _build_corpus_index()

    @app.route("/")
    def root():
        viz = request.args.get("viz") or ""
        return redirect(url_for("view", idx=0, viz=viz))

    @app.route("/view/<int:idx>")
    def view(idx: int):
        viz_filter = request.args.get("viz") or ""
        idx_full = app.config["IMAGE_INDEX"]
        filtered = _filter_index(idx_full, viz_filter or None)
        total = len(filtered)
        if total == 0:
            return f"<h1>No images for filter '{viz_filter}'</h1>", 404
        if idx < 0:
            idx = 0
        if idx >= total:
            idx = total - 1
        row = filtered[idx]
        meta = app.config["CORPUS"].get(row["doc_id"], {})
        subtype = ""
        if row["viz"] == "chart":
            subtype = meta.get("chart_subtype", "")
        elif row["viz"] == "diagram":
            subtype = meta.get("diagram_subtype", "")

        counts = {
            "all": len(idx_full),
            "chart": sum(1 for r in idx_full if r["viz"] == "chart"),
            "mindmap": sum(1 for r in idx_full if r["viz"] == "mindmap"),
            "diagram": sum(1 for r in idx_full if r["viz"] == "diagram"),
        }
        return render_template_string(
            PAGE,
            row={"viz": row["viz"], "doc_id": row["doc_id"], "subtype": subtype,
                  "title": meta.get("title", ""), "lang": meta.get("lang", ""),
                  "domain": meta.get("domain", "")},
            source_text=_read_source(row["viz"], row["doc_id"]),
            idx=idx, total=total, counts=counts,
            prev1=max(0, idx - 1), next1=min(total - 1, idx + 1),
            prev10=max(0, idx - 10), next10=min(total - 1, idx + 10),
            viz_filter=viz_filter,
        )

    @app.route("/img/<viz>/<doc_id>")
    def image(viz: str, doc_id: str):
        if viz not in VIZ_TYPES:
            abort(400)
        # Sanitise doc_id (no path separators)
        if "/" in doc_id or ".." in doc_id:
            abort(400)
        path = os.path.join(GOLD_DIR, viz, f"{doc_id}_rendered.png")
        if not os.path.exists(path):
            abort(404)
        return send_file(path, mimetype="image/png")

    @app.route("/healthz")
    def healthz():
        return {"ok": True, "n_images": len(app.config["IMAGE_INDEX"])}

    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9039)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    app = create_app()
    n = len(app.config["IMAGE_INDEX"])
    print(f"[gold-dashboard] indexed {n} PNGs across "
           f"chart/mindmap/diagram. Listening on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
