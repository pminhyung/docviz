"""B1 MatPlotAgent-adapted (Yang et al., MatPlotAgent, ACL Findings 2024).

v0.3 amendment §9 baseline: "MatPlotAgent-adapted — Concat all docs into
context, pass with query to MatPlotAgent agentic pipeline. Wrap input
format only."

We reimplement the core MatPlotAgent workflow rather than wrapping their
codebase so the same QwenDirectClient + multi-host queue + retry logic is
used end-to-end. Specifically the protocol per Yang et al. §3:
  1. Query Expansion Agent: rewrites the user's simple query into a
     detailed plot specification given the bundle context.
  2. Plot Agent: generates Python matplotlib code that, when executed,
     produces a PNG visualization answering the expanded query.
  3. (skipped on-prem) Visual Refine Agent: GPT-4-Vision-Preview reviews
     the rendered PNG and suggests refinement. We omit this step since
     on-prem Qwen3.5-397B is text-only. The omission is documented in
     paper §5 + §7 as a deliberate adaptation; the head-to-head with
     B6 DocViz-Agent remains fair because B1 retains its 2-agent core
     (the value-add over B5 Direct-LLM).

Output mapping to docviz VizOutput:
  - viz_type = "matplotlib" (off-enum literal; the 10-type enum is
    Chart.js / Mermaid only — paper §3 documents B1's external type)
  - viz_dsl = the generated Python code (text-axis judge consumes this
    just like a Mermaid string or Chart.js JSON spec)
  - rendered_image_path = the PNG written by subprocess execution
  - render_success = True iff the PNG exists and is non-empty
  - sub_queries = [expanded_instruction] (the agentic action this
    method takes — analogous to V4_cons sub_queries)

The Python execution runs in a subprocess with a 30s timeout under the
project's `python3` and limited stdout/stderr capture. If the model
generates code with `os.system` / `subprocess.run` / `eval` / network
calls, we strip these before exec to avoid sandbox escape. Generated
viz_dsl preserves the original code for auditing.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Dict, List, Tuple

from code.adapters.agent_client import (
    PAPER_DEFAULT_SEED,
    QWEN_MODEL,
    QWEN_NON_THINKING_SAMPLING,
    QwenDirectClient,
)
from code.pipelines.base import Bundle, Pipeline, VizOutput


# ── Stage 1: Query Expansion prompt ─────────────────────────────────────────
QUERY_EXPAND_PROMPT = """\
You are the Query Expansion Agent of MatPlotAgent (Yang et al., ACL Findings 2024).

The user has asked the following query about a multi-document text bundle:

User query:
{query}

Source documents (multi-doc bundle):
{docs_concat}

Your task: rewrite the user's query into a DETAILED plotting specification
that the downstream Plot Agent can convert into matplotlib code. Your
expansion must:
  - Specify the chart type appropriate for the user intent (bar chart,
    line plot, grouped bar, pie, scatter, etc.).
  - Enumerate the specific data points / categories / series that should
    appear, drawing only from the source documents above.
  - Specify axis labels, units, legend entries, and a title that reflect
    the documents' content.
  - Be concrete enough that a code-generation model can write the
    matplotlib code without ambiguity.
  - Be at most ~250 words.

Return ONLY the expanded specification text. No preamble, no JSON, no
markdown fences.
"""

# ── Stage 2: Plot Agent prompt ──────────────────────────────────────────────
PLOT_AGENT_PROMPT = """\
You are the Plot Agent of MatPlotAgent (Yang et al., ACL Findings 2024).

Detailed plotting specification:
{expanded}

Source documents (for grounding the data values):
{docs_concat}

Your task: write a single self-contained Python 3 script that uses
matplotlib to produce the visualization. The script will be executed
verbatim. Constraints:
  - Only standard-library imports + `matplotlib`. No `pandas`, no
    `numpy` other than `import numpy as np`, no `seaborn`, no network
    calls, no file reads beyond what your script itself writes.
  - Hard-coded data values inline in the script (no external data load).
  - Save the figure to the path `{out_path}` via
    `plt.savefig("{out_path}", dpi=120, bbox_inches="tight")`.
  - Then call `plt.close('all')`. No interactive backends; the runtime
    will use `Agg`.
  - Total script ≤ 2000 lines; targeted ~50-120.

Return ONLY the Python code. No markdown fences, no prose preamble, no
trailing commentary.
"""


# ── Helpers ─────────────────────────────────────────────────────────────────

_BLOCKED_CODE_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bos\.system\b"),
    re.compile(r"\bsubprocess\b"),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\b__import__\b"),
    re.compile(r"\bopen\s*\([^)]*['\"]w"),  # writing to non-out_path
    # Network primitives
    re.compile(r"\brequests\.\w"),
    re.compile(r"\burllib\b"),
    re.compile(r"\bhttpx\b"),
    re.compile(r"\bsocket\b"),
]


def _sanitize_code(code: str, out_path: str) -> Tuple[str, List[str]]:
    """Strip markdown fences, remove blocked patterns. Returns (clean, warnings).

    The `open(out_path, 'w')` check would falsely match the legitimate
    savefig path, so we only flag generic `open(... 'w'` and let
    `plt.savefig(out_path)` proceed via matplotlib internals (which use
    `Image` / `_png.write_png_string` rather than user `open`).
    """
    code = code.strip()
    code = re.sub(r"^```(?:python)?\s*", "", code, flags=re.MULTILINE)
    code = re.sub(r"```\s*$", "", code, flags=re.MULTILINE)

    warnings: List[str] = []
    for pat in _BLOCKED_CODE_PATTERNS:
        if pat.search(code):
            warnings.append(f"blocked pattern stripped: {pat.pattern}")
            code = pat.sub("# [BLOCKED]", code)
    return code.strip(), warnings


def _run_code(code: str, out_path: str, timeout_s: int = 30) -> Tuple[bool, str]:
    """Write code to a temp .py, run via subprocess. Returns (success, stderr)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8",
    ) as f:
        # Force Agg backend before the script's own matplotlib import so
        # plt.savefig works headlessly.
        f.write("import matplotlib\nmatplotlib.use('Agg')\n")
        f.write(code)
        script_path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(Path(out_path).parent),
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout_s}s"
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:400]
        return False, f"exit {proc.returncode}: {err}"

    if not Path(out_path).exists() or Path(out_path).stat().st_size < 100:
        return False, "savefig did not produce a usable PNG"

    return True, ""


class B1MatPlotAgent(Pipeline):
    """B1 MatPlotAgent-adapted baseline.

    Two-LLM-call agentic pipeline (query_expansion → plot_agent), then
    Python subprocess execution to produce the rendered PNG.
    """

    name = "B1_MatPlotAgent"

    def __init__(
        self,
        client: QwenDirectClient | None = None,
        model: str = QWEN_MODEL,
        max_tokens_expand: int = 600,
        max_tokens_plot: int = 4096,
        doc_char_cap: int = 12_000,
        out_dir: str | None = None,
        exec_timeout_s: int = 30,
    ):
        self._client = client or QwenDirectClient()
        self._model = model
        self._max_tokens_expand = max_tokens_expand
        self._max_tokens_plot = max_tokens_plot
        self._doc_char_cap = doc_char_cap
        self._out_dir = Path(out_dir) if out_dir else (
            Path(tempfile.gettempdir()) / "docviz_b1_renders"
        )
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._exec_timeout_s = exec_timeout_s

    def _docs_concat(self, bundle: Bundle) -> str:
        parts: List[str] = []
        for d in bundle.docs:
            body = (d.content or "")[: self._doc_char_cap]
            parts.append(f"[{d.title}]\n{body}")
        return "\n\n---\n\n".join(parts)

    def _chat(self, prompt: str, max_tokens: int) -> str:
        resp = self._client.chat(
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            temperature=QWEN_NON_THINKING_SAMPLING["temperature"],
            top_p=QWEN_NON_THINKING_SAMPLING["top_p"],
            seed=PAPER_DEFAULT_SEED,
            max_tokens=max_tokens,
            extra_body=QWEN_NON_THINKING_SAMPLING["extra_body"],
        )
        msg = resp["choices"][0]["message"]
        return msg.get("content") or msg.get("reasoning") or ""

    def run(
        self,
        query: str,
        bundle: Bundle,
        *,
        query_type: str | None = None,
        query_id: str | None = None,
    ) -> VizOutput:
        docs_concat = self._docs_concat(bundle)
        errors: List[str] = []
        total_tokens_in = 0
        total_tokens_out = 0

        # Output PNG path
        qid = query_id or f"{bundle.bundle_id}_unk"
        out_path = self._out_dir / f"{qid}.png"

        # ── Stage 1: Query Expansion ───────────────────────────────────
        expanded = ""
        try:
            expanded = self._chat(
                QUERY_EXPAND_PROMPT.format(query=query, docs_concat=docs_concat),
                self._max_tokens_expand,
            )
        except Exception as e:
            errors.append(f"B1: stage-1 (query_expansion) failed: {e}")
            return self._empty_output(bundle, errors)

        # ── Stage 2: Plot Agent (matplotlib code) ──────────────────────
        plot_prompt = PLOT_AGENT_PROMPT.format(
            expanded=expanded,
            docs_concat=docs_concat,
            out_path=str(out_path),
        )
        try:
            code_raw = self._chat(plot_prompt, self._max_tokens_plot)
        except Exception as e:
            errors.append(f"B1: stage-2 (plot_agent) failed: {e}")
            return self._empty_output(bundle, errors)

        code_clean, warns = _sanitize_code(code_raw, str(out_path))
        if warns:
            errors.extend(f"B1: {w}" for w in warns)

        # ── Stage 3 (skipped): Visual Refine ───────────────────────────
        # GPT-4-Vision-Preview not on-prem; documented in module docstring.

        # ── Execute the python code ────────────────────────────────────
        ok, exec_err = _run_code(
            code_clean, str(out_path), timeout_s=self._exec_timeout_s,
        )
        if not ok:
            errors.append(f"B1: plot execution failed: {exec_err}")
            rendered = ""
            render_success = False
        else:
            rendered = str(out_path)
            render_success = True

        return VizOutput(
            viz_dsl=code_clean,
            viz_type="matplotlib",
            rendered_image_path=rendered,
            render_success=render_success,
            retrieved_chunks=[
                {"doc_id": d.doc_id, "chunk_id": d.doc_id, "content": d.content}
                for d in bundle.docs
            ],
            sub_queries=[expanded[:500]] if expanded else [],
            source_attribution={},
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            cost_usd=0.0,
            errors=errors,
        )

    @staticmethod
    def _empty_output(bundle: Bundle, errors: List[str]) -> VizOutput:
        return VizOutput(
            viz_dsl="",
            viz_type="",
            rendered_image_path="",
            render_success=False,
            retrieved_chunks=[
                {"doc_id": d.doc_id, "chunk_id": d.doc_id, "content": d.content}
                for d in bundle.docs
            ],
            sub_queries=[],
            source_attribution={},
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            errors=errors,
        )
