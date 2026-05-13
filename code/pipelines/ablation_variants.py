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

from typing import Optional
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


class B6NoCIS(Pipeline):
    """V0.3 PLACEHOLDER — deferred to Week-1.

    Full −CIS requires the agent server to bypass the doc-step
    (`agent/run_agent_v2.py:474` doc_summary generation). The cleanest
    way is to add a `skip_doc_step: bool` field to RunRequestV2; when
    True, the server uses an empty `doc_summary` and the agent's first
    user-turn omits the "Internal Documents' overview" line.

    Without this flag we cannot cleanly ablate CIS — substituting raw
    concat in the doc_summary slot would test "long context tolerance",
    not "Pillar 1 contribution". Honest abstention is better than a
    confounded ablation.

    For paper §7 Layer D table this row is reported as "deferred to
    Week-1; mechanism analysis in §8.4".
    """

    name = "B6_NoCIS"

    def run(
        self,
        query: str,
        bundle: Bundle,
        *,
        query_type: Optional[str] = None,
        query_id: Optional[str] = None,
    ) -> VizOutput:
        return VizOutput(
            viz_dsl="",
            viz_type="",
            rendered_image_path="",
            render_success=False,
            retrieved_chunks=[],
            sub_queries=[],
            source_attribution={},
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            errors=[
                "B6_NoCIS: deferred to Week-1 (requires agent server "
                "skip_doc_step flag; honest abstention vs confounded "
                "ablation per paper §7 Layer D notes)"
            ],
        )
