"""S4 Agentic with Pillar 2 (TMG) — variant-aware (V0 / V1 / V4).

mode dispatch:
  v0 — rule routing via TYPE_TO_VIZ + placeholder one-shot from
       ONE_SHOT_BY_VIZ_TYPE (== current pre-pivot behaviour; backward
       compatible with the existing 60-record S4_AgenticTMG dataset).
  v1 — rule routing + NO one-shot. Mentor risk #1 baseline; isolates
       the value of the one-shot independently from the routing
       decision. Strategy name: S4_AgenticTMGv1noshot.
  v4_pool — agent-inference + tool-call. Agent picks viz_type from the
       10-enum pool exposed in custom_rules (V4_POOL_EXPOSURE_RULE),
       then calls the generate_viz tool which samples 1 exemplar from
       per-type pool via deterministic sha1(query_id) % len(pool).
       Strategy name: S4_AgenticTMGv4_pool.
  v4_consolidated — same as v4_pool but the generate_viz tool injects
       the single integrated exemplar (every sub-pattern of the type
       in one coherent example) instead of sampling from a pool.
       Strategy name: S4_AgenticTMGv4_consolidated.

Comparing on the same 60 (query, bundle) pairs:
  - Δ(V0 − S4) = §11.4 ablation row "−TMG vs Full (placeholder)" baseline
  - Δ(V1 − V0) = isolates one-shot value (rule routing held fixed)
  - Δ(V4_pool − V1) = mentor risk #1 — tool-call complexity justification
  - Δ(V4_consolidated − V4_pool) = NEW direction (one integrated example
    vs pool sampling)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from code.adapters.agent_client import AgentClient
from code.adapters.bundle_to_docai import write_bundle_as_docai
from code.adapters.viz_output_mapper import map_agent_response
from code.pipelines.base import Bundle, Pipeline, VizOutput
from code.pipelines.tmg import V4_POOL_EXPOSURE_RULE, build_tmg_rule


_GENERATE_VIZ_TOOL_PATH = (
    Path(__file__).resolve().parent.parent / "agent_tools" / "generate_viz.py"
)


_STRATEGY_NAMES = {
    "v0": "S4_AgenticTMG",                          # backward compat
    "v1": "S4_AgenticTMGv1noshot",
    "v4_pool": "S4_AgenticTMGv4_pool",
    "v4_consolidated": "S4_AgenticTMGv4_consolidated",
}


class S4AgenticTMG(Pipeline):
    """Variant-aware DocViz-Agent with Pillar 2 (TMG) active.

    See module docstring for mode semantics.
    """

    def __init__(
        self,
        mode: str = "v0",
        agent_base_url: Optional[str] = None,
        n_steps_max: int = 8,
        reasoner_max_length: int = 32768,
        work_dir: Optional[Path] = None,
    ):
        if mode not in _STRATEGY_NAMES:
            raise ValueError(
                f"mode must be one of {list(_STRATEGY_NAMES)}; got {mode!r}"
            )
        self.mode = mode
        self.name = _STRATEGY_NAMES[mode]
        self._base_url = agent_base_url or os.environ.get(
            "DOCVIZ_AGENT_URL", "http://localhost:9024"
        )
        self._n_steps_max = n_steps_max
        self._reasoner_max_length = reasoner_max_length
        self._work_dir = Path(work_dir) if work_dir else (
            Path(tempfile.gettempdir()) / f"docviz_s4tmg_{mode}"
        )
        self._work_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        query: str,
        bundle: Bundle,
        *,
        query_type: str | None = None,
        query_id: str | None = None,
    ) -> VizOutput:
        doc_path, page_to_doc_id = write_bundle_as_docai(bundle, out_dir=self._work_dir)
        bundle.metadata.setdefault("page_to_doc_id", page_to_doc_id)

        # Mode dispatch — V0/V1 inject custom_rules with rule routing;
        # V4 also passes custom_tools_path so the agent can call
        # generate_viz, and a tool_secrets payload so the tool can
        # deterministically pick the per-type exemplar.
        custom_tools_path: Optional[str] = None
        extra_overrides = None

        if self.mode == "v0":
            tmg_rule = build_tmg_rule(query_type, include_one_shot=True) if query_type else ""
        elif self.mode == "v1":
            tmg_rule = build_tmg_rule(query_type, include_one_shot=False) if query_type else ""
        elif self.mode in ("v4_pool", "v4_consolidated"):
            tmg_rule = V4_POOL_EXPOSURE_RULE
            custom_tools_path = str(_GENERATE_VIZ_TOOL_PATH)
            # tool_secrets is forwarded to the tool's execute() context
            # by the agent server (see agent/run_agent_v2.py).
            extra_overrides = {
                "tool_secrets": {
                    "query_id": query_id or "_unknown",
                    "tmg_mode": self.mode,
                }
            }
        else:
            tmg_rule = ""

        with AgentClient(base_url=self._base_url) as client:
            if not client.health():
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
                        f"{self.name}: agent /health unreachable at {self._base_url}"
                    ],
                )

            response = client.run_paper_default(
                doc_json_path=doc_path,
                user_query=query,
                n_steps_max=self._n_steps_max,
                return_trace=True,
                return_train_sample=False,
                reasoner_max_length=self._reasoner_max_length,
                custom_rules=tmg_rule if tmg_rule else None,
                custom_tools_path=custom_tools_path,
                extra_overrides=extra_overrides,
            )

        return map_agent_response(response, bundle, concat_doc_path=doc_path)
