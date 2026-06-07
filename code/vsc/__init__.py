"""VSC (Visual Specification Contract) — v0.4.3 DocViz-Agent axis §4.5.

Canonical visual spec → deterministic DSL → contract validator (R1–R5) →
one-shot repair. Used both as a B6 generation mechanism and as the tab:vsc
deterministic metric over every arm's output.
"""
from __future__ import annotations

from .spec import (
    ChartSpec, DiagramSpec, DataPoint, Node, Edge, parse_spec,
    VIZ_TYPE_POOL, CHART_TYPES, DIAGRAM_TYPES,
)
from .to_dsl import spec_to_dsl
from .validator import (
    check, validate_spec, validate_dsl, Violation, ValidationResult, RULES,
)
from .repair import run_vsc, build_repair_prompt, VSCOutput

__all__ = [
    "ChartSpec", "DiagramSpec", "DataPoint", "Node", "Edge", "parse_spec",
    "VIZ_TYPE_POOL", "CHART_TYPES", "DIAGRAM_TYPES",
    "spec_to_dsl", "check", "validate_spec", "validate_dsl",
    "Violation", "ValidationResult", "RULES",
    "run_vsc", "build_repair_prompt", "VSCOutput",
]
