"""S4 Agentic with Pillar 2 (TMG) enabled — full DocViz-Agent (B6) cell.

Differs from `S4Agentic` only in that we inject a query-type-aware
one-shot rule into the agent's `custom_rules`. Everything else (CIS loop
inside the agent, SAO mapping in viz_output_mapper) is identical.

Comparing this against S4Agentic (which keeps query_type=None and so
emits no TMG block) yields the §11.4 "Full DocViz-Agent" vs "−TMG"
ablation pair on the same 60 (query, bundle) pairs.
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
from code.pipelines.tmg import build_tmg_rule


class S4AgenticTMG(Pipeline):
    """DocViz-Agent with TMG (Pillar 2) active. Only behavioural difference
    from S4Agentic is the type-specific one-shot block injected into
    custom_rules at run() time.
    """

    name = "S4_AgenticTMG"

    def __init__(
        self,
        agent_base_url: Optional[str] = None,
        n_steps_max: int = 8,
        reasoner_max_length: int = 32768,
        work_dir: Optional[Path] = None,
    ):
        self._base_url = agent_base_url or os.environ.get(
            "DOCVIZ_AGENT_URL", "http://localhost:9024"
        )
        self._n_steps_max = n_steps_max
        self._reasoner_max_length = reasoner_max_length
        self._work_dir = Path(work_dir) if work_dir else (
            Path(tempfile.gettempdir()) / "docviz_s4_tmg"
        )
        self._work_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        query: str,
        bundle: Bundle,
        *,
        query_type: str | None = None,
    ) -> VizOutput:
        doc_path, page_to_doc_id = write_bundle_as_docai(bundle, out_dir=self._work_dir)
        bundle.metadata.setdefault("page_to_doc_id", page_to_doc_id)

        # TMG rule is appended via custom_rules; if query_type is unknown
        # (or None) build_tmg_rule returns "" → reverts to −TMG behaviour.
        tmg_rule = build_tmg_rule(query_type) if query_type else ""

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
                    errors=[f"S4_TMG: agent /health unreachable at {self._base_url}"],
                )

            response = client.run_paper_default(
                doc_json_path=doc_path,
                user_query=query,
                n_steps_max=self._n_steps_max,
                return_trace=True,
                return_train_sample=False,
                reasoner_max_length=self._reasoner_max_length,
                custom_rules=tmg_rule if tmg_rule else None,
            )

        return map_agent_response(response, bundle, concat_doc_path=doc_path)
