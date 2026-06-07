"""VSC one-shot repair loop — v0.4.3 paper §4.5(c) + Appendix B.

On a contract violation, a repair prompt naming the violation type and location
is handed to TMG exactly once; the returned spec is re-validated. If it still
violates, M1 is scored 0 (paper: "보수 후 재검증. 재검증 실패 시 M1=0").

The LLM call itself is injected via `repair_fn` (lives in the generate_viz
wiring, task 3) so this module stays deterministic and unit-testable. The
canonical repair-prompt text is built here from the violation set.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .spec import VisualSpec
from .validator import ValidationResult, Violation, validate_spec

# repair_fn(spec, violations, prompt) -> repaired spec, or None to give up.
RepairFn = Callable[[VisualSpec, list[Violation], str], Optional[VisualSpec]]


@dataclass
class VSCOutput:
    viz_type: str
    dsl: str
    ok: bool                       # M1: contract satisfied (post-repair)
    repaired: bool
    violations: dict[str, int]     # rule -> count (final state)
    source_eids: list[str] = field(default_factory=list)
    spec: Optional[VisualSpec] = None


def build_repair_prompt(spec: VisualSpec, violations: list[Violation]) -> str:
    """Appendix-B repair prompt: state each violation's type + location, demand
    a one-shot fix using only SEF evidence facts."""
    lines = [
        f"The {spec.viz_type} visual spec has contract violations:",
    ]
    for v in violations:
        lines.append(f"  - {v.name} (rule {v.rule}) at {v.element_id}: {v.detail}")
    lines.append(
        "Repair the spec ONCE. Use only evidence facts already present in the "
        "SEF; do not invent new entities, numbers, or source ids. For "
        "dimension_mismatch ensure every series covers the same categories; for "
        "broken_edge ensure every edge endpoint is a declared node; for "
        "invalid_source_ref replace the id with a valid SEF bid/cuid."
    )
    return "\n".join(lines)


def run_vsc(spec: VisualSpec, sef_eids: Optional[set[str]] = None, *,
            repair_fn: Optional[RepairFn] = None,
            render: bool = True) -> VSCOutput:
    """Convert → validate → (repair once) → re-validate."""
    dsl, res = validate_spec(spec, sef_eids=sef_eids, render=render)
    if res.ok:
        return VSCOutput(spec.viz_type, dsl, ok=True, repaired=False,
                         violations=res.by_rule(), source_eids=spec.source_eids(),
                         spec=spec)

    if repair_fn is None:
        return VSCOutput(spec.viz_type, dsl, ok=False, repaired=False,
                         violations=res.by_rule(), source_eids=spec.source_eids(),
                         spec=spec)

    prompt = build_repair_prompt(spec, res.violations)
    repaired_spec = None
    try:
        repaired_spec = repair_fn(spec, res.violations, prompt)
    except Exception:
        repaired_spec = None

    if repaired_spec is None:
        return VSCOutput(spec.viz_type, dsl, ok=False, repaired=True,
                         violations=res.by_rule(), source_eids=spec.source_eids(),
                         spec=spec)

    dsl2, res2 = validate_spec(repaired_spec, sef_eids=sef_eids, render=render)
    return VSCOutput(repaired_spec.viz_type, dsl2, ok=res2.ok, repaired=True,
                     violations=res2.by_rule(),
                     source_eids=repaired_spec.source_eids(), spec=repaired_spec)
