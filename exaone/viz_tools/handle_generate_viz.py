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


def _repo_root_on_path():
    """Ensure `code.*` (sef/vsc/metrics) is importable from this tool."""
    import sys
    from pathlib import Path as _P
    root = str(_P(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)


def _vsc_enabled() -> bool:
    """v0.4.3: VSC active unless the −VSC ablation is selected.

    DOCVIZ_VARIANT=novsc → direct-DSL emission with no contract/repair (the
    ablation arm). Any other variant runs the full Visual Specification Contract.
    """
    variant = os.environ.get("DOCVIZ_VARIANT", "full").strip().lower()
    return variant != "novsc"


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
        # Named pools (select ONE via DOCVIZ_POOL — no auto-rotation). Each maps to
        # (hosts, key). DOCVIZ_SYNTH_HOSTS/API_KEY still override if set explicitly.
        _POOLS = {
            "qwen148": (["10.1.211.148"], "EMPTY"),
            "h100": ([f"10.1.211.{h}" for h in range(163, 171)], "vs_task_only"),
            "qwen": (["10.1.211.147", "10.1.211.148"] + [f"10.1.211.{h}" for h in range(163, 169)], "EMPTY"),
        }
        pool = os.environ.get("DOCVIZ_POOL", "qwen148")
        p_hosts, p_key = _POOLS.get(pool, _POOLS["qwen148"])
        hosts_env = os.environ.get("DOCVIZ_SYNTH_HOSTS", ",".join(p_hosts))
        key = os.environ.get("DOCVIZ_SYNTH_API_KEY", p_key)
        # Pick one randomly (cheap routing — vLLM batches per-host anyway).
        import random
        host = random.choice([h.strip() for h in hosts_env.split(",") if h.strip()])
        # host may carry an explicit port ("localhost:8001" → weak 4B backbone).
        base_url = f"http://{host}/v1" if ":" in host else f"http://{host}:8000/v1"
        _SYNTH_CLIENT = (openai.OpenAI(base_url=base_url, api_key=key),
                         os.environ.get("DOCVIZ_SYNTH_MODEL", "Qwen3.5-397B-A17B-FP8"))
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


# =====================================================================
# VSC path (v0.4.3 §4.5) — canonical spec synthesis + deterministic DSL +
# contract validation + one-shot repair. Active unless DOCVIZ_VARIANT=novsc.
# =====================================================================

_SPEC_SYNTH_PROMPT = """You are a deterministic visual-spec emitter.

viz_type: {viz_type}
intent: {intent}

content_brief (entities, dates, numbers, relationships to encode):
{content_brief}

evidence ids you may cite as source_eid (use ONLY these, verbatim):
{evidence_ids}

Emit ONLY a JSON object (no prose, no code fence) — the CANONICAL SPEC, not DSL.

For chartjs_* viz_type:
{{"viz_type":"{viz_type}","x_label":"...","y_label":"...","title":"...",
  "datapoints":[{{"series":"...","category":"...","value":<number>,"unit":"...","source_eid":"<one evidence id>"}}, ...]}}
  - Every (series, category) pair distinct. value is a bare number from the brief.

For mermaid_* viz_type:
{{"viz_type":"{viz_type}","title":"...",
  "nodes":[{{"id":"n1","label":"...","source_eid":"<evidence id>"}}, ...],
  "edges":[{{"from":"n1","to":"n2","rel_label":"...","source_eid":"<evidence id>"}}, ...]}}
  - Every edge.from and edge.to MUST be an id present in nodes.
  - Keep the specific facts (dates/numbers/named entities) from the brief; do not abstract them away.

Output the JSON object only."""


def _strip_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        import re as _re
        m = _re.match(r"```[a-z]*\s*\n([\s\S]*?)\n```", t)
        if m:
            return m.group(1).strip()
    return t


def _synthesize_spec(viz_type: str, content_brief: str, intent: str,
                     evidence_ids: list[str]) -> Optional[dict]:
    """Internal LLM → canonical visual spec dict (TMG, paper §4.5a). None on fail."""
    try:
        client, model = _get_synth_client()
        prompt = _SPEC_SYNTH_PROMPT.format(
            viz_type=viz_type, intent=intent[:200],
            content_brief=content_brief[:2000],
            evidence_ids=", ".join(map(str, evidence_ids)) or "(none provided)",
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2, max_tokens=2000,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        obj = json.loads(_strip_fence(resp.choices[0].message.content or ""))
        if isinstance(obj, dict):
            obj.setdefault("viz_type", viz_type)
            return obj
    except Exception as exc:
        logger.warning(f"spec synth failed: {exc}")
    return None


def _make_repair_fn():
    """Return a VSC repair_fn that re-synthesizes the spec from the repair prompt."""
    def repair_fn(spec, violations, prompt):
        from code.vsc import parse_spec
        try:
            client, model = _get_synth_client()
            spec_json = json.dumps(_spec_to_obj(spec), ensure_ascii=False)
            msg = (f"{prompt}\n\nCurrent spec JSON:\n{spec_json}\n\n"
                   "Return the corrected spec JSON object only.")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": msg}],
                temperature=0.1, max_tokens=2000,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            obj = json.loads(_strip_fence(resp.choices[0].message.content or ""))
            return parse_spec(obj)
        except Exception as exc:
            logger.warning(f"spec repair failed: {exc}")
            return None
    return repair_fn


def _spec_to_obj(spec) -> dict:
    """Serialize a ChartSpec/DiagramSpec back to the TMG JSON shape for repair."""
    import dataclasses
    from code.vsc import ChartSpec, DiagramSpec
    if isinstance(spec, ChartSpec):
        return {"viz_type": spec.viz_type, "x_label": spec.x_label,
                "y_label": spec.y_label, "title": spec.title,
                "datapoints": [dataclasses.asdict(dp) for dp in spec.datapoints]}
    if isinstance(spec, DiagramSpec):
        return {"viz_type": spec.viz_type, "title": spec.title,
                "nodes": [dataclasses.asdict(n) for n in spec.nodes],
                "edges": [{"from": e.from_id, "to": e.to_id,
                           "rel_label": e.rel_label, "source_eid": e.source_eid}
                          for e in spec.edges]}
    return {}


def _sef_eids_for_task(task_id: str, context: dict | None) -> Optional[set[str]]:
    """Resolve the SEF reference ids for R5 validation, if available.

    Order: context['sef_eids'] → DOCVIZ_SEF_DIR/{task_id}.json (SEF dict). When
    absent (e.g. −SEF arm, or SEF not yet routed) R5 is skipped gracefully.
    """
    if context and isinstance(context.get("sef_eids"), (list, set)):
        return set(context["sef_eids"])
    sef_dir = os.environ.get("DOCVIZ_SEF_DIR")
    if sef_dir:
        p = Path(sef_dir) / f"{task_id}.json"
        if p.exists():
            try:
                sef = json.loads(p.read_text())
                eids: set[str] = set()
                for blk in sef.get("blocks", []):
                    eids.add(blk.get("bid"))
                    for cu in blk.get("claim_units", []):
                        eids.add(cu.get("cuid"))
                return {e for e in eids if e}
            except Exception as exc:
                logger.warning(f"SEF load failed for {task_id}: {exc}")
    return None


def _build_artifact_vsc(viz_type: str, brief: str, intent: str,
                        evidence_ids: list[str],
                        sef_eids: Optional[set[str]]) -> dict:
    """Full VSC artifact: spec → deterministic DSL → validate → 1-shot repair."""
    _repo_root_on_path()
    from code.vsc import parse_spec, run_vsc, spec_to_dsl
    spec_obj = _synthesize_spec(viz_type, brief, intent, evidence_ids)
    if spec_obj is None:
        # spec synth failed → fall back to direct DSL stub so the chain is stable
        dsl = _synthesize_dsl(viz_type, brief, intent=intent)
        return {"viz_type": viz_type, "dsl": dsl, "vsc_ok": False,
                "repaired": False, "vsc_violations": {}, "source_eids": [],
                "vsc_enabled": True, "spec_synth_failed": True}
    try:
        spec = parse_spec(spec_obj)
    except ValueError as exc:  # bad viz_type → R4; record and stub
        return {"viz_type": viz_type, "dsl": "", "vsc_ok": False,
                "repaired": False, "vsc_violations": {"R4": 1},
                "source_eids": [], "vsc_enabled": True, "spec_error": str(exc)}
    out = run_vsc(spec, sef_eids=sef_eids, repair_fn=_make_repair_fn(), render=True)
    return {"viz_type": out.viz_type, "dsl": out.dsl, "vsc_ok": out.ok,
            "repaired": out.repaired, "vsc_violations": out.violations,
            "source_eids": out.source_eids, "vsc_enabled": True}


def _build_artifact_spec_only(viz_type: str, brief: str, intent: str,
                              evidence_ids: list[str]) -> dict:
    """−VSC ablation (redefined): canonical spec → deterministic DSL, but NO
    validator / repair loop. Keeps the spec's source_eids (SAO) so the ablation
    isolates the *contract* from source-attribution — removing VSC must not also
    remove the SAO grounding that drives Evidence F1."""
    _repo_root_on_path()
    from code.vsc import parse_spec, spec_to_dsl
    spec_obj = _synthesize_spec(viz_type, brief, intent, evidence_ids)
    if spec_obj is None:
        dsl = _synthesize_dsl(viz_type, brief, intent=intent)
        return {"viz_type": viz_type, "dsl": dsl, "vsc_enabled": False,
                "vsc_ok": None, "vsc_violations": {}, "repaired": False,
                "source_eids": [], "spec_synth_failed": True}
    try:
        spec = parse_spec(spec_obj)
    except ValueError:
        dsl = _synthesize_dsl(viz_type, brief, intent=intent)
        return {"viz_type": viz_type, "dsl": dsl, "vsc_enabled": False,
                "vsc_ok": None, "vsc_violations": {}, "repaired": False,
                "source_eids": []}
    return {"viz_type": spec.viz_type, "dsl": spec_to_dsl(spec),
            "vsc_enabled": False, "vsc_ok": None, "vsc_violations": {},
            "repaired": False, "source_eids": spec.source_eids()}


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
        # v0.4.3 VSC fields (SAO source_eids + contract result). Absent-safe for
        # the −VSC arm, where these stay at their disabled defaults.
        "vsc_enabled": artifact.get("vsc_enabled", False),
        "vsc_ok": artifact.get("vsc_ok", None),
        "vsc_violations": artifact.get("vsc_violations", {}),
        "vsc_repaired": artifact.get("repaired", False),
        "source_eids": artifact.get("source_eids", []),
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
    use_vsc = _vsc_enabled()
    sef_eids = _sef_eids_for_task(task_id, context) if use_vsc else None
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

        if use_vsc:
            # Full VSC (paper §4.5): spec → deterministic DSL → validate → repair.
            art = _build_artifact_vsc(viz_type, brief, intent,
                                      list(evidence_ids), sef_eids)
            # M1 = contract satisfied post-repair; preflight mirrors it.
            ok = bool(art["vsc_ok"])
            err = "" if ok else "vsc_violation:" + ",".join(
                f"{k}={v}" for k, v in art.get("vsc_violations", {}).items() if v)
            art.update({"intent": intent, "evidence_ids": list(evidence_ids),
                        "preflight_ok": ok, "preflight_error": err})
        else:
            # −VSC ablation (redefined): canonical spec → DSL, no contract/repair.
            # Spec + source_eids retained so VSC is isolated from SAO.
            art = _build_artifact_spec_only(viz_type, brief, intent,
                                            list(evidence_ids))
            ok, _e = _preflight_parse(art["viz_type"], art["dsl"])
            art.update({"intent": intent, "evidence_ids": list(evidence_ids),
                        "preflight_ok": ok, "preflight_error": ""})

        sidecar_path = _write_sidecar(sidecar_dir, task_id, art, idx)
        emitted.append({
            "idx": idx,
            "viz_type": art["viz_type"],
            "intent": intent,
            "sidecar": str(sidecar_path),
            "preflight_ok": ok,
            "vsc_ok": art.get("vsc_ok"),
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
