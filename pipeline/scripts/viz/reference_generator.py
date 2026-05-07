"""D8 — Reference visualization generator (single-pass real-world flow).

For each (doc, viz_type) pair:
  - load query from queries.jsonl
  - load full document context via prepare_full_context(doc)
  - call qwen397b with the viz_type-specific SYSTEM_PROMPT
  - parse output (Vega-Lite JSON / Mermaid / Mermaid mindmap)
  - render to PNG (vl-convert-python for chart, mermaid sidecar for diagram/mindmap)
  - write source.txt + rendered.png + structure stubs to data/gold/{viz_type}/

Failure handling:
  - any exception → append to data/gold/failures.jsonl with {doc_id, viz_type, error, raw_output}
  - Type A (generation failure) is NOT hidden; Render% reflects true success ratio

Resume support: skips (doc_id, viz_type) pairs that already have a source file.

Usage:
    python -m scripts.viz.reference_generator [--limit N] [--workers 8] [--viz chart,diagram,mindmap]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.viz.prompts import (
    SYSTEM_PROMPT_CHART,
    SYSTEM_PROMPT_DIAGRAM,
    SYSTEM_PROMPT_MINDMAP,
)
from scripts.viz.context_builder import prepare_full_context
from scripts.utils.llm_clients import call_model
from scripts.utils.rendering import render_vegalite, render_mermaid

CORPUS_PATH = "/ex_disk2/mhpark/poc/visubench/data/documents/corpus.jsonl"
QUERIES_PATH = "/ex_disk2/mhpark/poc/visubench/data/viz/queries.jsonl"
GOLD_DIR = "/ex_disk2/mhpark/poc/visubench/data/gold"
FAIL_PATH = os.path.join(GOLD_DIR, "failures.jsonl")

# Label language invariance — corpus lang → full language name for explicit
# directive injection (system prompts stay verbatim; explicitness is added to
# the USER message preamble only).
LANG_NAMES = {
    "en": "English", "ko": "Korean", "ja": "Japanese", "zh": "Chinese",
    "fr": "French", "de": "German", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "ru": "Russian",
}
# CJK block for leakage detection (Han, Hiragana, Katakana, Hangul)
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]")


def _contains_foreign_script(text: str, doc_lang: str) -> bool:
    """Return True if text contains a script that does not match doc_lang.

    Corpus is currently 100% en; we detect any CJK in the output as violation.
    For ko/ja/zh docs, no violation is flagged (script matches).
    """
    if doc_lang in ("zh", "ko", "ja"):
        return False
    return bool(_CJK_RE.search(text))

SYSTEM_PROMPTS = {
    "chart": SYSTEM_PROMPT_CHART,
    "diagram": SYSTEM_PROMPT_DIAGRAM,
    "mindmap": SYSTEM_PROMPT_MINDMAP,
}


# ── Output parsing helpers ───────────────────────────────────────────────────

_FENCE_RE = re.compile(r"^```(?:json|mermaid)?\s*", re.IGNORECASE)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        m = _FENCE_RE.match(t)
        if m:
            t = t[m.end():]
    if t.endswith("```"):
        t = t[: t.rfind("```")].rstrip()
    return t.strip()


def extract_vegalite(text: str) -> dict:
    """Parse Vega-Lite JSON from a model response. Raises on failure."""
    t = _strip_fences(text)
    # try direct parse
    try:
        d = json.loads(t)
    except Exception:
        # find the largest JSON object
        depth = 0
        start = -1
        best = None
        for i, ch in enumerate(t):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    candidate = t[start : i + 1]
                    if best is None or len(candidate) > len(best):
                        best = candidate
        if best is None:
            raise ValueError("no JSON object found in chart output")
        d = json.loads(best)
    if not isinstance(d, dict):
        raise ValueError("chart JSON is not an object")
    if "mark" not in d and "layer" not in d and "vconcat" not in d \
       and "hconcat" not in d and "repeat" not in d and "facet" not in d:
        raise ValueError("Vega-Lite spec missing 'mark' (or composite key)")
    return d


_MERMAID_SPECIAL = re.compile(r"[()&<>+,#@$%!?|=*{}\\/:;'.]")


def sanitize_mermaid(src: str, is_mindmap: bool) -> str:
    """Conservative fix-ups for mermaid 11.x parser strictness.

    v3 (2026-04-09): extended for rhombus/circle flowchart nodes, split
    `root((...))` trailing siblings, inject newline after `sankey-beta`.
    System prompts stay verbatim; sanitizer is post-process only.
    """
    # Bug I — sankey-beta with no newline after header:
    # `sankey-betasource["..."] --> target[...]` → `sankey-beta\nsource[...]`
    src = re.sub(r"^(sankey-beta)([a-zA-Z])", r"\1\n\2", src, count=1, flags=re.M)

    if is_mindmap:
        lines = src.split("\n")
        out = []
        for ln in lines:
            stripped = ln.lstrip()
            indent = ln[: len(ln) - len(stripped)]
            if not stripped or stripped.startswith("mindmap") or stripped.startswith("%%"):
                out.append(ln)
                continue
            # Bug F — root((label))  trailing_text   — split trailing text
            # into a child line one indent deeper. Must handle nested parens
            # inside the root label (e.g., `root((RCCAs (Alloys)))`).
            if stripped.startswith("root"):
                rm = re.match(r"^root\s*\(\(", stripped)
                if rm:
                    # Scan for the matching `))` of the root node.
                    start = rm.end()
                    depth = 2  # we've already consumed two `(`
                    end = None
                    i = start
                    while i < len(stripped):
                        ch = stripped[i]
                        if ch == "(":
                            depth += 1
                        elif ch == ")":
                            depth -= 1
                            if depth == 0:
                                end = i + 1
                                break
                        i += 1
                    if end is not None and end < len(stripped):
                        head = stripped[:end]
                        tail = stripped[end:].strip()
                        if tail:
                            out.append(f"{indent}{head}")
                            child_indent = indent + "  "
                            if _MERMAID_SPECIAL.search(tail):
                                tail_safe = tail.replace('"', "'")
                                out.append(f'{child_indent}["{tail_safe}"]')
                            else:
                                out.append(f"{child_indent}{tail}")
                            continue
            # Plain root((label)) — wrap label in quotes if it contains
            # nested parens or other specials (mermaid mindmap root grammar
            # cannot parse `root((Complex (RCCAs)))`).
            rm2 = re.match(r"^(root\s*\(\()(.*)(\)\))\s*$", stripped)
            if rm2:
                label = rm2.group(2)
                if ("(" in label or ")" in label or '"' in label) and \
                        not (label.startswith('"') and label.endswith('"')):
                    label_safe = label.replace('"', "'")
                    out.append(f'{indent}root(("{label_safe}"))')
                else:
                    out.append(ln)
                continue
            if re.match(r"^root\s*[\(\[]", stripped):
                out.append(ln)
                continue
            # already bracketed/quoted? Only `[...]` or `"..."` or backtick
            if re.match(r'^[\["`]', stripped):
                out.append(ln)
                continue
            if _MERMAID_SPECIAL.search(stripped):
                label = stripped.replace('"', "'")
                out.append(f'{indent}["{label}"]')
            else:
                out.append(ln)
        return "\n".join(out)

    # flowchart / other graphs
    def repl_square(m):
        inner = m.group(1)
        if inner.startswith('"') and inner.endswith('"'):
            return m.group(0)
        if _MERMAID_SPECIAL.search(inner):
            inner_esc = inner.replace('"', "'")
            return f'["{inner_esc}"]'
        return m.group(0)
    # `[Label(stuff)]` → `["Label(stuff)"]`
    src = re.sub(r"\[([^\[\]\n]+?)\]", repl_square, src)

    # Bug E — rhombus/decision `{Label with (stuff)}` and stadium `([Label])`
    # also need wrapping. Mermaid decision node grammar parses bare text with
    # special chars as a sub-node, breaking on `(11)`, `[Name]`, etc.
    def repl_rhombus(m):
        inner = m.group(1)
        if inner.startswith('"') and inner.endswith('"'):
            return m.group(0)
        if _MERMAID_SPECIAL.search(inner):
            inner_esc = inner.replace('"', "'")
            return "{" + f'"{inner_esc}"' + "}"
        return m.group(0)
    src = re.sub(r"\{([^{}\n]+?)\}", repl_rhombus, src)

    # Circle node `((Label (x)))` → `(("Label (x)"))` — leave single `(..)`
    # nodes alone since they can be link labels; only wrap double `((..))`.
    def repl_circle(m):
        inner = m.group(1)
        if inner.startswith('"') and inner.endswith('"'):
            return m.group(0)
        if _MERMAID_SPECIAL.search(inner):
            inner_esc = inner.replace('"', "'")
            return "((" + f'"{inner_esc}"' + "))"
        return m.group(0)
    src = re.sub(r"\(\(([^()\n]+?)\)\)", repl_circle, src)

    return src


def extract_mermaid(text: str, expect_mindmap: bool = False) -> str:
    """Return the mermaid source (without fences). Raises on obvious failure."""
    t = _strip_fences(text)
    # some models prepend a short header; drop leading lines until a known token
    lines = t.split("\n")
    valid_starts = ("mindmap", "flowchart", "sequenceDiagram", "classDiagram",
                    "stateDiagram", "erDiagram", "gantt", "sankey", "graph",
                    "pie", "journey", "gitGraph", "requirementDiagram")
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if any(stripped.startswith(v) for v in valid_starts):
            lines = lines[i:]
            break
    out = "\n".join(lines).strip()
    if not out:
        raise ValueError("empty mermaid source")
    if expect_mindmap and not out.lstrip().lower().startswith("mindmap"):
        raise ValueError("expected mindmap but got: " + out[:60])
    return out


# ── Per-viz generators ──────────────────────────────────────────────────────

def generate_chart(row: dict, query: str, context: str, output_dir: str) -> dict:
    user = f"{query}\n\nDocument:\n{context}"
    raw = call_model("qwen397b", SYSTEM_PROMPT_CHART, user,
                     temperature=0.2)
    spec = extract_vegalite(raw)
    # write source before rendering so we can inspect if render fails
    src_path = os.path.join(output_dir, f"{row['doc_id']}_source.txt")
    with open(src_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(spec, ensure_ascii=False, indent=2))
    r = render_vegalite(spec, output_dir, doc_id=row["doc_id"], fmt="png")
    if not r["success"]:
        raise RuntimeError(f"render_vegalite failed: {r['error']}")
    return {"source_path": src_path, "rendered_path": r["rendered_path"],
            "spec": spec, "raw_output": raw}


def generate_diagram(row: dict, query: str, context: str, output_dir: str,
                     diagram_subtype: str) -> dict:
    user = f"{query}\n\nDocument:\n{context}"
    raw = call_model("qwen397b", SYSTEM_PROMPT_DIAGRAM, user,
                     temperature=0.2)
    mermaid_src = extract_mermaid(raw, expect_mindmap=False)
    mermaid_src = sanitize_mermaid(mermaid_src, is_mindmap=False)
    src_path = os.path.join(output_dir, f"{row['doc_id']}_source.txt")
    with open(src_path, "w", encoding="utf-8") as f:
        f.write(mermaid_src)
    r = render_mermaid(mermaid_src, diagram_subtype, output_dir,
                       doc_id=row["doc_id"], fmt="png")
    if not r["success"]:
        raise RuntimeError(f"render_mermaid failed: {r['error']}")
    return {"source_path": src_path, "rendered_path": r["rendered_path"],
            "mermaid": mermaid_src, "raw_output": raw}


def generate_mindmap(row: dict, query: str, context: str, output_dir: str) -> dict:
    doc_lang = row.get("lang", "en")
    lang_name = LANG_NAMES.get(doc_lang, doc_lang)
    # Explicit language directive prepended to USER message (system prompt
    # stays verbatim per invariant). Retries with increasingly strong
    # phrasing when CJK leakage is detected in a non-CJK doc.
    base_user = f"{query}\n\nDocument:\n{context}"
    preambles = [
        f"LANGUAGE REQUIREMENT: Write ALL labels in {lang_name}. "
        f"The input document is in {lang_name}. Do not translate any text.\n\n",
        f"CRITICAL LANGUAGE RULE: You MUST write every single label, "
        f"node, and branch of the mindmap in {lang_name} ONLY. "
        f"DO NOT use Chinese, Korean, Japanese, or any script other than "
        f"{lang_name}. The source document is in {lang_name}; keep the "
        f"output in {lang_name}.\n\n",
        f"FINAL WARNING: Output must be in {lang_name}. Any Chinese, "
        f"Korean, or Japanese characters will be rejected. Use only "
        f"{lang_name} words and Latin script.\n\n",
    ]
    raw = None
    mermaid_src = None
    last_error = None
    for attempt, preamble in enumerate(preambles):
        try:
            raw = call_model("qwen397b", SYSTEM_PROMPT_MINDMAP,
                             preamble + base_user,
                             temperature=0.2 if attempt == 0 else 0.0)
            mermaid_src = extract_mermaid(raw, expect_mindmap=True)
            mermaid_src = sanitize_mermaid(mermaid_src, is_mindmap=True)
            if _contains_foreign_script(mermaid_src, doc_lang):
                last_error = f"CJK leakage on attempt {attempt + 1}"
                continue
            break
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            continue
    if mermaid_src is None or (
        _contains_foreign_script(mermaid_src, doc_lang)
    ):
        raise RuntimeError(
            f"mindmap generation failed after {len(preambles)} attempts "
            f"(last_error={last_error})"
        )
    src_path = os.path.join(output_dir, f"{row['doc_id']}_source.txt")
    with open(src_path, "w", encoding="utf-8") as f:
        f.write(mermaid_src)
    r = render_mermaid(mermaid_src, "mindmap", output_dir,
                       doc_id=row["doc_id"], fmt="png")
    if not r["success"]:
        raise RuntimeError(f"render_mermaid failed: {r['error']}")
    return {"source_path": src_path, "rendered_path": r["rendered_path"],
            "mermaid": mermaid_src, "raw_output": raw}


# ── Orchestration ────────────────────────────────────────────────────────────

def _already_done(doc_id: str, viz_type: str) -> bool:
    src = os.path.join(GOLD_DIR, viz_type, f"{doc_id}_source.txt")
    png = os.path.join(GOLD_DIR, viz_type, f"{doc_id}_rendered.png")
    return os.path.exists(src) and os.path.exists(png)


def process_one(row: dict, viz_type: str, query: str, diagram_subtype: str) -> dict:
    doc_id = row["doc_id"]
    out_dir = os.path.join(GOLD_DIR, viz_type)
    os.makedirs(out_dir, exist_ok=True)
    if _already_done(doc_id, viz_type):
        return {"doc_id": doc_id, "viz_type": viz_type, "skipped": True, "ok": True}
    try:
        context = prepare_full_context(row)
        if viz_type == "chart":
            r = generate_chart(row, query, context, out_dir)
        elif viz_type == "diagram":
            r = generate_diagram(row, query, context, out_dir, diagram_subtype)
        else:
            r = generate_mindmap(row, query, context, out_dir)
        return {"doc_id": doc_id, "viz_type": viz_type, "ok": True, **r}
    except Exception as e:
        tb = traceback.format_exc()[:2000]
        return {"doc_id": doc_id, "viz_type": viz_type, "ok": False,
                "error": f"{type(e).__name__}: {e}", "traceback": tb}


def append_failure(rec: dict):
    os.makedirs(GOLD_DIR, exist_ok=True)
    with open(FAIL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "doc_id": rec["doc_id"],
            "viz_type": rec["viz_type"],
            "error": rec.get("error", ""),
            "traceback": rec.get("traceback", ""),
        }, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="limit number of DOCS (not tasks)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--viz", type=str, default="chart,diagram,mindmap")
    args = ap.parse_args()

    viz_types = [v.strip() for v in args.viz.split(",") if v.strip()]
    for v in viz_types:
        if v not in SYSTEM_PROMPTS:
            raise SystemExit(f"unknown viz_type: {v}")

    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
    rows_by_id = {r["doc_id"]: r for r in rows}

    # load queries
    queries = {}  # (doc_id, viz_type) -> query_row
    with open(QUERIES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            q = json.loads(line)
            if q["doc_id"] in rows_by_id and q["viz_type"] in viz_types:
                queries[(q["doc_id"], q["viz_type"])] = q

    tasks = []
    for r in rows:
        for v in viz_types:
            if (r["doc_id"], v) not in queries:
                continue
            tasks.append((r, v, queries[(r["doc_id"], v)]["query"]))

    print(f"[tasks] {len(tasks)} ({len(rows)} docs × {len(viz_types)} viz_types)")
    t0 = time.time()
    done = 0
    ok = 0
    skip = 0
    fail = 0
    fail_by_viz: Dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {}
        for row, viz_type, query in tasks:
            diagram_subtype = row.get("diagram_subtype", "flowchart")
            futs[ex.submit(process_one, row, viz_type, query, diagram_subtype)] = (row["doc_id"], viz_type)
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            if r.get("skipped"):
                skip += 1
                ok += 1
            elif r["ok"]:
                ok += 1
            else:
                fail += 1
                fail_by_viz[r["viz_type"]] = fail_by_viz.get(r["viz_type"], 0) + 1
                append_failure(r)
            if done % 20 == 0 or done == len(tasks):
                elapsed = time.time() - t0
                print(f"  [{done}/{len(tasks)}]  ok={ok} (skip={skip})  fail={fail}  "
                      f"by_viz={fail_by_viz}  elapsed={elapsed:.0f}s  rate={done/max(elapsed,1e-6):.2f}/s")

    # per viz_type render% summary
    print("\n== render% summary ==")
    for v in viz_types:
        total = sum(1 for (_, vv) in queries.keys() if vv == v
                    and any(r["doc_id"] == _ for r in rows))
        # count successful sources on disk
        dirp = os.path.join(GOLD_DIR, v)
        if os.path.isdir(dirp):
            pngs = len([f for f in os.listdir(dirp) if f.endswith("_rendered.png")])
            srcs = len([f for f in os.listdir(dirp) if f.endswith("_source.txt")])
        else:
            pngs = srcs = 0
        print(f"  {v:8s} source={srcs}  rendered_png={pngs}")


if __name__ == "__main__":
    main()
