"""Mermaid DSL → PNG render with deterministic syntax auto-repair.

Model-synthesized Mermaid frequently puts special characters — ()=:;,<>%& — in
node/edge labels WITHOUT quotes, which Mermaid's flow parser rejects
(e.g. `C5[ReLU f(o)=max(0,o_i)]`). v0.4.1 handled this with a DSL auto-repair
pass; this re-implements a focused version: wrap any bracketed label that
contains special chars (and isn't already quoted) in double quotes.

Public API:
    repair_mermaid(dsl)  -> repaired dsl
    render_mermaid(dsl, out_png) -> {ok, png, error, repaired}
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

MMDC = os.environ.get("MMDC_BIN", "/home/poc/.npm-global/bin/mmdc")
_SPECIAL = set("()=:;,<>%&\"'`")

def _wrap(label: str) -> str:
    """Quote a label body if it needs it (has special chars, not already quoted)."""
    s = label.strip()
    if not s:
        return label
    if s[0] == '"' and s[-1] == '"':
        return label  # already quoted
    if any(c in _SPECIAL for c in s):
        inner = s.replace('"', "'")  # mermaid can't escape " inside "..."; downgrade
        return f'"{inner}"'
    return label


def repair_mermaid(dsl: str) -> str:
    """Quote the body of square `[...]` and curly `{...}` node labels when it
    holds special chars. The body is matched as 'anything up to the closing
    bracket of the same type', so inner parentheses (`f(o)=max(0,o_i)`) stay
    inside the quoted label instead of being mis-read as separate node shapes."""
    # Only flowchart/graph use [..]/{..}/(..) as NODE LABELS that need quoting.
    # In classDiagram these delimit class bodies; in sequenceDiagram/timeline/
    # mindmap the syntax is structural — quoting there corrupts the diagram.
    head = next((ln.strip() for ln in dsl.splitlines() if ln.strip()), "")
    if not re.match(r"(flowchart|graph)\b", head):
        return dsl
    out = dsl
    # square-bracket labels: ID[body]  (body may contain () but not [ ])
    out = re.sub(r"\[([^\[\]]+)\]", lambda m: "[" + _wrap(m.group(1)) + "]", out)
    # curly labels: ID{body}
    out = re.sub(r"\{([^{}]+)\}", lambda m: "{" + _wrap(m.group(1)) + "}", out)
    # edge labels  -->|label|  : quote if special chars present
    def _edge(m):
        body = m.group(1)
        if any(c in _SPECIAL for c in body) and not (body.strip().startswith('"')):
            return "|" + f'"{body.replace(chr(34), chr(39))}"' + "|"
        return m.group(0)
    out = re.sub(r"\|([^|]*)\|", _edge, out)
    return out


def render_mermaid(dsl: str, out_png: str | Path, *, repair: bool = True) -> dict:
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    used = repair_mermaid(dsl) if repair else dsl
    with tempfile.TemporaryDirectory() as td:
        mmd = Path(td) / "d.mmd"
        cfg = Path(td) / "p.json"
        mmd.write_text(used, encoding="utf-8")
        cfg.write_text('{"args":["--no-sandbox","--disable-gpu"]}', encoding="utf-8")
        try:
            r = subprocess.run([MMDC, "-i", str(mmd), "-o", str(out_png), "-p", str(cfg)],
                               capture_output=True, text=True, timeout=90)
        except Exception as e:
            return {"ok": False, "png": None, "error": f"{type(e).__name__}: {e}", "repaired": repair}
    ok = out_png.exists() and out_png.stat().st_size > 1000
    err = ""
    if not ok:
        m = re.search(r"(Parse error[\s\S]{0,160}|Error:[\s\S]{0,160})", r.stderr or r.stdout or "")
        err = (m.group(0) if m else (r.stderr or "")[:200]).replace("\n", " ")
    return {"ok": ok, "png": str(out_png) if ok else None, "error": err, "repaired": repair}


if __name__ == "__main__":
    import json, sys
    # self-test on the failing B6 sidecar if present
    import glob
    scs = sorted(glob.glob("/tmp/v4_viz_outputs/*.json"))
    if scs:
        d = json.loads(Path(scs[-1]).read_text())
        dsl = d.get("dsl_code", "")
        print("viz_type:", d.get("viz_type"))
        raw = render_mermaid(dsl, "/tmp/_render_raw.png", repair=False)
        fix = render_mermaid(dsl, "/tmp/_render_fix.png", repair=True)
        print("NO-repair:", raw["ok"], raw["error"][:120])
        print("repaired :", fix["ok"], fix["error"][:120])
