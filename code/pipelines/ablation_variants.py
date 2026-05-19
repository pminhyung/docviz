"""Layer D pillar ablation variants (v0.3 amendment §10 Layer D).

Four variants of B6 V4_consolidated for the pillar ablation experiment:
  - Full = V4_consolidated (CIS + TMG + SAO active)            ← existing
  - −TMG = same agent loop, no V4 custom rule / no generate_viz tool
           → falls back to direct DSL emission from the agent
  - −SAO = same as Full but with source_attribution forced to empty in
           the mapped output (no attribution post-processing)
  - −CIS = doc-step bypassed (server-side flag; deferred to Week-1
           because it requires agent server modification — full
           implementation requires DOCVIZ_SKIP_DOC_STEP env support
           that the vendored agent doesn't currently honor)

Each variant exposes the same `run(query, bundle) -> VizOutput`
interface and is dispatched by `run_prototype.py --strategies
B6_FULL,B6_NO_TMG,B6_NO_SAO`.

The ablation cell names map to amendment §10 Layer D row:
  - B6_Full         → "Full"
  - B6_NoTMG        → "-TMG"
  - B6_NoSAO        → "-SAO"
  - B6_NoCIS        → "-CIS"  (deferred, Week-1)
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from pathlib import Path

from code.pipelines.base import Bundle, Pipeline, VizOutput
from code.pipelines.s4_agentic import S4Agentic
from code.pipelines.s4_agentic_tmg import S4AgenticTMG


class B6Full(S4AgenticTMG):
    """Full V4_consolidated baseline — CIS + TMG + SAO active."""

    name = "B6_Full"

    def __init__(self, **kwargs):
        super().__init__(mode="v4_consolidated", **kwargs)


class B6NoTMG(S4Agentic):
    """V4_consolidated minus TMG (Pillar 2): no per-type viz routing,
    no generate_viz tool. Falls back to direct DSL emission via the
    agent's default final_answer JSON-output rule.

    Inherits from S4Agentic which is the canonical "agent loop without
    TMG custom rule" implementation. Override `name` for clean reporting.
    """

    name = "B6_NoTMG"


class B6NoSAO(S4AgenticTMG):
    """V4_consolidated minus SAO (Pillar 3): same agent loop and TMG
    routing, but the source_attribution post-processing is suppressed
    (the field is set to empty in the returned VizOutput so downstream
    metrics treating attribution as a signal degrade to 0)."""

    name = "B6_NoSAO"

    def __init__(self, **kwargs):
        super().__init__(mode="v4_consolidated", **kwargs)

    def run(
        self,
        query: str,
        bundle: Bundle,
        *,
        query_type: Optional[str] = None,
        query_id: Optional[str] = None,
    ) -> VizOutput:
        vo = super().run(query=query, bundle=bundle,
                         query_type=query_type, query_id=query_id)
        # Suppress SAO output post-mapper
        vo.source_attribution = {}
        return vo


class B6NoCIS(S4AgenticTMG):
    """V4_consolidated minus CIS (Pillar 1): same agent loop, TMG routing,
    SAO post-processing, but the upfront doc-summary step (agent server's
    Step 1) is skipped via `skip_doc_step=True` in RunRequestV2.

    The agent's first user-turn carries an empty 'Internal Documents' overview'
    so retrieval/reasoning proceeds without the cross-doc summary that the
    CIS pillar contributes. Honest abstention rather than raw-concat
    substitution (which would confound long-context tolerance with the
    pillar's contribution)."""

    name = "B6_NoCIS"

    def __init__(self, **kwargs):
        super().__init__(mode="v4_consolidated", **kwargs)

    def _ablation_overrides(self) -> Dict[str, Any]:
        return {"skip_doc_step": True}
