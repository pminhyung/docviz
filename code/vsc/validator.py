"""VSC violation validator — v0.4.3 paper §4.5(c) + Appendix B rules R1–R5.

Dual role (paper §5.1): a *generation mechanism* in B6 (validate the canonical
spec, drive one repair) and a *deterministic metric* in the scorer (the tab:vsc
violation rates, computed on every arm's raw DSL). Both go through `check()`.

  R1 render success — mermaid via mmdc (code.judge.render); chartjs via
                      structural parse (puppeteer hook for when charts enter the
                      corpus — Phase-4; current Phase-2 corpus is all mermaid).
  R2 dimension match (chartjs) — labels.length == datasets[i].data.length.
  R3 edge node refs (mermaid) — every edge endpoint is a declared node.
  R4 supported marker — viz_type ∈ 10 primitives.
  R5 source-ref validity (B6 only) — every source_eid ∈ SEF bids/cuids.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

from .spec import VIZ_TYPE_POOL, CHART_TYPES, ChartSpec, DiagramSpec, VisualSpec
from .to_dsl import spec_to_dsl

RULES = ("R1", "R2", "R3", "R4", "R5")
_RULE_NAME = {
    "R1": "render_fail", "R2": "dimension_mismatch", "R3": "broken_edge",
    "R4": "unsupported_marker", "R5": "invalid_source_ref",
}


@dataclass
class Violation:
    rule: str
    name: str
    element_id: str
    detail: str


@dataclass
class ValidationResult:
    ok: bool
    violations: list[Violation] = field(default_factory=list)

    def by_rule(self) -> dict[str, int]:
        d = {r: 0 for r in RULES}
        for v in self.violations:
            d[v.rule] += 1
        return d

    def summary(self) -> str:
        return "; ".join(f"{v.rule}:{v.name}@{v.element_id} ({v.detail})"
                         for v in self.violations) or "clean"


def _v(rule: str, element_id: str, detail: str) -> Violation:
    return Violation(rule, _RULE_NAME[rule], element_id, detail)


# --- R1 render ------------------------------------------------------------

def _mermaid_renders(dsl: str) -> tuple[bool, str]:
    from code.judge.render import render_mermaid
    r = render_mermaid(dsl, "/tmp/_vsc_render/probe.png")
    return bool(r.get("ok")), (r.get("error") or "")[:120]


def _chart_renders(dsl: str) -> tuple[bool, str]:
    # Structural render-proxy: a Chart.js object that parses to a non-empty
    # table is renderable. Real puppeteer render lands when charts enter the
    # corpus (set VSC_CHART_PUPPETEER=1 to require it).
    if os.environ.get("VSC_CHART_PUPPETEER") == "1":  # pragma: no cover
        from code.judge.render import render_chartjs  # type: ignore
        r = render_chartjs(dsl, "/tmp/_vsc_render/probe_chart.png")
        return bool(r.get("ok")), (r.get("error") or "")[:120]
    from code.metrics.chart_metrics import parse_chartjs_to_table
    tbl = parse_chartjs_to_table(dsl)
    if tbl is None or not tbl.chart_type:
        return False, "chartjs_unparseable"
    return True, ""


# --- core check -----------------------------------------------------------

def check(viz_type: str, dsl: str, *, spec: Optional[VisualSpec] = None,
          sef_eids: Optional[set[str]] = None,
          source_eids: Optional[list[str]] = None,
          render: bool = True) -> ValidationResult:
    """Validate a DSL (and optionally its spec) against R1–R5.

    For the metric path pass viz_type + dsl (+ source_eids if the arm emits
    them). For B6 generation pass spec as well so R3/R5 use declared structure.
    """
    vios: list[Violation] = []

    # R4 — supported marker
    if viz_type not in VIZ_TYPE_POOL:
        vios.append(_v("R4", viz_type or "?", "viz_type not in 10-primitive pool"))
        return ValidationResult(ok=False, violations=vios)  # other rules moot

    is_chart = viz_type in CHART_TYPES

    # R1 — render
    if render:
        ok, err = (_chart_renders(dsl) if is_chart else _mermaid_renders(dsl))
        if not ok:
            vios.append(_v("R1", viz_type, err or "render produced no output"))

    # R2 — dimension match (chartjs)
    if is_chart:
        vios.extend(_check_chart_dims(dsl))

    # R3 — edge node refs (mermaid)
    if not is_chart:
        vios.extend(_check_edges(dsl, spec))

    # R5 — source-ref validity (only when the arm declares sources + we have SEF)
    eids = source_eids
    if eids is None and spec is not None:
        eids = spec.source_eids()
    if eids and sef_eids is not None:
        for e in eids:
            if e not in sef_eids:
                vios.append(_v("R5", e, "source_eid absent from SEF"))

    return ValidationResult(ok=not vios, violations=vios)


def _check_chart_dims(dsl: str) -> list[Violation]:
    try:
        obj = json.loads(dsl)
        data = obj.get("data", {})
        labels = data.get("labels", [])
        out: list[Violation] = []
        for i, ds in enumerate(data.get("datasets", [])):
            d = ds.get("data", [])
            if len(d) != len(labels):
                out.append(_v("R2", ds.get("label", f"dataset{i}"),
                              f"len(data)={len(d)} != len(labels)={len(labels)}"))
        return out
    except (json.JSONDecodeError, AttributeError, TypeError):
        # unparseable JSON is an R1 render failure, not R2; don't double-count
        return []


def _check_edges(dsl: str, spec: Optional[VisualSpec]) -> list[Violation]:
    if isinstance(spec, DiagramSpec):
        node_ids = spec.node_ids()
        out: list[Violation] = []
        for e in spec.edges:
            if e.from_id not in node_ids:
                out.append(_v("R3", e.from_id, "edge source not a declared node"))
            if e.to_id not in node_ids:
                out.append(_v("R3", e.to_id, "edge target not a declared node"))
        return out
    # raw-DSL metric path: parse and flag malformed edge endpoints
    from code.metrics.mermaid_metrics import parse_mermaid_to_graph
    g = parse_mermaid_to_graph(dsl)
    if g is None:
        return []
    out = []
    for e in g.edges:
        if not (e.src and e.src.strip()) or not (e.dst and e.dst.strip()):
            out.append(_v("R3", f"{e.src}->{e.dst}", "edge with empty endpoint"))
    return out


# --- convenience wrappers -------------------------------------------------

def validate_spec(spec: VisualSpec, sef_eids: Optional[set[str]] = None,
                  *, render: bool = True) -> tuple[str, ValidationResult]:
    """B6 path: convert spec → DSL, validate. Returns (dsl, result)."""
    dsl = spec_to_dsl(spec)
    res = check(spec.viz_type, dsl, spec=spec, sef_eids=sef_eids, render=render)
    return dsl, res


def validate_dsl(viz_type: str, dsl: str, *,
                 source_eids: Optional[list[str]] = None,
                 sef_eids: Optional[set[str]] = None,
                 render: bool = True) -> ValidationResult:
    """Metric path: validate a raw DSL string from any arm."""
    return check(viz_type, dsl, source_eids=source_eids, sef_eids=sef_eids,
                 render=render)
