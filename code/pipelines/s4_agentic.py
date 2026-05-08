"""S4 Agentic pipeline (≡ §7 baseline B6: DocViz-Agent).

Wraps the existing /v2/run agent loop with the Pipeline interface. The agent
expects a docai-format JSON file as input, so we:

  1. Serialize the Bundle to a temp `{1: page1, ...}` JSON via bundle_to_docai.
  2. Call AgentClient.run_paper_default(...) (paper-locked defaults: en, no
     web search, temperature=0, seed=42).
  3. Map the trace + final_answer back into VizOutput via map_agent_response.

The temp file is created under `tempfile.gettempdir()/docviz_s4` and reused
per bundle on repeated runs (idempotent — bundle_to_docai overwrites).
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


class S4Agentic(Pipeline):
    """Doc-grounded agent loop. Multi-step search → reason → emit DSL."""

    name = "S4_Agentic"

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
            Path(tempfile.gettempdir()) / "docviz_s4"
        )
        self._work_dir.mkdir(parents=True, exist_ok=True)

    def run(self, query: str, bundle: Bundle) -> VizOutput:
        doc_path, page_to_doc_id = write_bundle_as_docai(bundle, out_dir=self._work_dir)

        # Stash the page→doc_id mapping on the Bundle so map_agent_response can
        # resolve agent page citations back to canonical doc_ids for SAO.
        bundle.metadata.setdefault("page_to_doc_id", page_to_doc_id)

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
                    errors=[f"S4: agent /health unreachable at {self._base_url}"],
                )

            response = client.run_paper_default(
                doc_json_path=doc_path,
                user_query=query,
                n_steps_max=self._n_steps_max,
                return_trace=True,
                return_train_sample=False,
                reasoner_max_length=self._reasoner_max_length,
            )

        return map_agent_response(response, bundle, concat_doc_path=doc_path)
