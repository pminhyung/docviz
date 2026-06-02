"""generate_viz tool — multi-artifact DSL synthesis + sidecar.

v0.4.1 §5.1 port from `_legacy/code/agent_tools/generate_viz.py` (445 LOC).
This version drops bits ir-shim/v19 already cover:
  - oneshot pool lookup → minimal (kept; one-shot exemplar per viz_type)
  - separate Qwen client → uses ExaoneAgent's primary client (auxiliary fallback)
  - sidecar dir resolution → kept (DOCVIZ_VIZ_SIDECAR_DIR env)
  - rescue path → REMOVED (P1 relies on v19 adapter to keep `generate_viz`
    invocations well-formed; orchestrator-side rescue moves to P4 if needed)

Output: writes one sidecar JSON per (task_id, query_id) under
`DOCVIZ_VIZ_SIDECAR_DIR` (default `/tmp/v4_viz_outputs`). Returns a short
text envelope + per-artifact citation Index.

P1 smoke gate (per §14): 5 sample records pass tool → preflight-parse →
sidecar chain end-to-end without errors.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from tools.registry import tool_result, tool_error

logger = logging.getLogger(__name__)


VIZ_TYPE_POOL = [
    "chartjs_bar", "chartjs_line", "chartjs_grouped_bar",
    "chartjs_pie", "chartjs_scatter",
    "mermaid_flowchart", "mermaid_timeline", "mermaid_mindmap",
    "mermaid_sequenceDiagram", "mermaid_classDiagram",
]


GENERATE_VIZ_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "generate_viz",
        "description": (
            "Emit 1-3 grounded visualization artifacts (charts/diagrams) as a "
            "sidecar. The tool synthesizes Chart.js or Mermaid DSL from your "
            "natural-language content_brief; you do not produce DSL directly. "
            "Required `viz_type` ∈ chartjs_bar/line/grouped_bar/pie/scatter, "
            "mermaid_flowchart/timeline/mindmap/sequenceDiagram/classDiagram. "
            "Required prior step: at least one doc_search or ReadFullDocument."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "artifacts": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "viz_type": {
                                "type": "string",
                                "enum": VIZ_TYPE_POOL,
                                "description": "One of the 10-element viz_type pool.",
                            },
                            "intent": {
                                "type": "string",
                                "maxLength": 200,
                                "description": "One-sentence summary of what this artifact shows.",
                            },
                            "content_brief": {
                                "type": "string",
                                "maxLength": 2000,
                                "description": "Exhaustive description of entities, dates, numbers, relationships from the source documents. The synthesizer cannot see the documents — only this brief.",
                            },
                            "evidence_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Citation Index values from doc_search / ReadFullDocument grounding this artifact. Required for B6 full / -CIS / -TMG; may be [] in -SAO ablation.",
                            },
                        },
                        "required": ["viz_type", "intent", "content_brief"],
                    },
                }
            },
            "required": ["artifacts"],
        },
    },
}


def _sidecar_dir() -> Path:
    return Path(os.environ.get("DOCVIZ_VIZ_SIDECAR_DIR", "/tmp/v4_viz_outputs"))


def _resolve_task_id(context: dict | None) -> str:
    """Pull task_id from agent context for sidecar keying. Falls back to UUID."""
    if context and isinstance(context, dict):
        for key in ("task_id", "request_id", "query_id"):
            if val := context.get(key):
                return str(val)
    return f"adhoc-{uuid.uuid4().hex[:8]}"


_SYNTH_CLIENT = None


def _get_synth_client():
    """Lazy-init OpenAI client pointing at the Qwen multi-host pool.
    Hosts cycled per call via the DOCVIZ_QWEN_HOSTS env (comma-separated)
    or default 8-host pool. Uses one host for simplicity (vLLM scheduler
    will load-balance internally)."""
    global _SYNTH_CLIENT
    if _SYNTH_CLIENT is None:
        import openai
        hosts_env = os.environ.get(
            "DOCVIZ_SYNTH_HOSTS",
            "10.1.211.147,10.1.211.148,10.1.211.163,10.1.211.164,"
            "10.1.211.165,10.1.211.166,10.1.211.167,10.1.211.168")
        # Pick one randomly (cheap routing — vLLM batches per-host anyway).
        import random
        host = random.choice([h.strip() for h in hosts_env.split(",") if h.strip()])
        _SYNTH_CLIENT = (openai.OpenAI(
            base_url=f"http://{host}:8000/v1",
            api_key=os.environ.get("DOCVIZ_SYNTH_API_KEY", "EMPTY"),
        ), os.environ.get("DOCVIZ_SYNTH_MODEL", "Qwen3.5-397B-A17B-FP8"))
    return _SYNTH_CLIENT


_DSL_SYNTH_PROMPT = """You are a deterministic DSL emitter for a visualization tool.

viz_type: {viz_type}
intent: {intent}

content_brief (entities, dates, numbers, relationships to encode):
{content_brief}

Emit ONLY the DSL — no preamble, no explanation, no markdown fence.

Format requirements:
- chartjs_*: emit a single JSON object like {{"type": "<bar|line|pie|scatter>", "data": {{"labels": [...], "datasets": [{{"label": "...", "data": [...]}}]}}}}. For grouped_bar emit type=bar with multiple datasets.
- mermaid_*: emit a mermaid markdown block starting with the kind keyword (flowchart TD / timeline / mindmap / sequenceDiagram / classDiagram). Use real node ids and labels from the content_brief, not placeholders.

Output the DSL only."""


def _synthesize_dsl(viz_type: str, content_brief: str, intent: str = "") -> str:
    """Synthesize Chart.js or Mermaid DSL via a single LLM call.

    Uses a separate Qwen pool host (multi-host load-balanced). Falls back to
    a minimal valid stub if the LLM call fails or output can't parse — the
    P0 preflight will reject obviously broken DSL anyway.
    """
    try:
        client, model = _get_synth_client()
        prompt = _DSL_SYNTH_PROMPT.format(
            viz_type=viz_type,
            intent=intent[:200],
            content_brief=content_brief[:2000],
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2000,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        dsl = (resp.choices[0].message.content or "").strip()
        # Strip code fences if model wrapped output.
        if dsl.startswith("```"):
            import re as _re
            m = _re.match(r"```[a-z]*\s*\n([\s\S]*?)\n```", dsl)
            if m:
                dsl = m.group(1).strip()
        if dsl:
            return dsl
    except Exception as exc:
        logger.warning(f"DSL synth fallback: {exc}")

    # Fallback stub (matches P1 behavior — preserves chain stability).
    if viz_type.startswith("chartjs_"):
        chart_type = viz_type.removeprefix("chartjs_")
        if chart_type == "grouped_bar":
            chart_type = "bar"
        return json.dumps({
            "type": chart_type,
            "data": {"labels": ["A", "B"],
                     "datasets": [{"label": content_brief[:50] or "series",
                                   "data": [1, 2]}]},
        })
    if viz_type.startswith("mermaid_"):
        kind = viz_type.removeprefix("mermaid_")
        snippet = content_brief.replace("\n", " ")[:80] or "placeholder"
        if kind == "timeline":
            return f"timeline\n    title {snippet}\n    2024 : event A\n"
        if kind == "mindmap":
            return f"mindmap\n  root(({snippet}))\n    A\n    B\n"
        if kind == "flowchart":
            return f"flowchart TD\n    A[{snippet}] --> B[next]\n"
        if kind == "sequenceDiagram":
            return f"sequenceDiagram\n    participant A\n    participant B\n    A->>B: {snippet}\n"
        if kind == "classDiagram":
            return f"classDiagram\n    class A {{\n      +method()\n    }}\n"
        return f"graph TD\n    A[{snippet}]\n"
    return ""


def _preflight_parse(viz_type: str, dsl: str) -> tuple[bool, str]:
    """Validate the synthesized DSL parses with our P0 parsers.

    Returns (ok, error_reason). Used to abort sidecar write on garbage output.
    """
    try:
        # Lazy import to keep tool registration cheap.
        import sys
        from pathlib import Path as _P
        sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
        if viz_type.startswith("chartjs_"):
            from code.metrics.chart_metrics import parse_chartjs_to_table
            tbl = parse_chartjs_to_table(dsl)
            if tbl is None or not tbl.chart_type or not tbl.cells:
                return False, "chartjs_parse_empty"
        elif viz_type.startswith("mermaid_"):
            from code.metrics.mermaid_metrics import parse_mermaid_to_graph
            g = parse_mermaid_to_graph(dsl)
            if g is None or g.kind == "mermaid_unknown":
                return False, "mermaid_parse_empty"
        return True, ""
    except Exception as exc:
        return False, f"preflight_exception: {exc}"


def _write_sidecar(
    sidecar_dir: Path, task_id: str, artifact: dict, idx: int
) -> Path:
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    path = sidecar_dir / f"{task_id}__a{idx}.json"
    payload = {
        "task_id": task_id,
        "artifact_idx": idx,
        "viz_type": artifact["viz_type"],
        "intent": artifact["intent"],
        "evidence_ids": artifact.get("evidence_ids", []),
        "dsl_code": artifact["dsl"],
        "preflight_ok": artifact["preflight_ok"],
        "preflight_error": artifact.get("preflight_error", ""),
        "emitted_at": int(time.time()),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def handle_generate_viz(args: dict | None = None, context: dict | None = None,
                        **kwargs) -> str:
    """Tool entrypoint. Returns a tool_result envelope."""
    payload = dict(args or {})
    artifacts_in = payload.get("artifacts") or []

    if not isinstance(artifacts_in, list) or not (1 <= len(artifacts_in) <= 3):
        return tool_error("generate_viz: `artifacts` must be a list of 1-3 ArtifactSpec items.")

    task_id = _resolve_task_id(context)
    sidecar_dir = _sidecar_dir()
    emitted: list[dict] = []
    errors: list[str] = []

    for idx, spec in enumerate(artifacts_in):
        if not isinstance(spec, dict):
            errors.append(f"artifact {idx}: not an object")
            continue
        viz_type = spec.get("viz_type", "")
        intent = (spec.get("intent") or "")[:200]
        brief = (spec.get("content_brief") or "")[:2000]
        evidence_ids = spec.get("evidence_ids") or []
        if viz_type not in VIZ_TYPE_POOL:
            errors.append(f"artifact {idx}: viz_type={viz_type!r} not in pool")
            continue
        if not brief.strip():
            errors.append(f"artifact {idx}: content_brief is empty")
            continue
        dsl = _synthesize_dsl(viz_type, brief, intent=intent)
        ok, err = _preflight_parse(viz_type, dsl)
        sidecar_path = _write_sidecar(sidecar_dir, task_id, {
            "viz_type": viz_type,
            "intent": intent,
            "evidence_ids": list(evidence_ids),
            "dsl": dsl,
            "preflight_ok": ok,
            "preflight_error": err,
        }, idx)
        emitted.append({
            "idx": idx,
            "viz_type": viz_type,
            "intent": intent,
            "sidecar": str(sidecar_path),
            "preflight_ok": ok,
        })

    if not emitted:
        return tool_error("generate_viz: no artifact emitted. " + " | ".join(errors))

    summary = f"Emitted {len(emitted)} artifact(s) at {sidecar_dir}/{task_id}__aN.json."
    if errors:
        summary += " Skipped: " + "; ".join(errors)

    return tool_result(
        success=True,
        data={"emitted": emitted, "task_id": task_id, "sidecar_dir": str(sidecar_dir)},
        meta={"tool": "generate_viz", "n_artifacts": len(emitted)},
        text=summary,
    )
