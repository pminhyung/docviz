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
import threading
from pathlib import Path
from typing import Optional

from code.adapters.agent_client import AgentClient
from code.adapters.bundle_to_docai import write_bundle_as_docai
from code.adapters.viz_output_mapper import map_agent_response
from code.pipelines.base import Bundle, Pipeline, VizOutput


# Module-level round-robin assignment of reasoner_base_url across the
# vLLM hosts listed in QWEN36_27B_PORTS env. Each pipeline INSTANCE
# gets a sticky URL at __init__ — distributes load across ports when
# --s4-workers > 1 (run_prototype creates a new instance per task).
_PORT_COUNTER_LOCK = threading.Lock()
_PORT_COUNTER = 0


def _next_reasoner_url() -> str:
    """Round-robin pick from QWEN36_27B_PORTS (default 9101,9102,9103)."""
    global _PORT_COUNTER
    ports_env = os.environ.get("QWEN36_27B_PORTS", "9101,9102,9103")
    ports = [p.strip() for p in ports_env.split(",") if p.strip()]
    if not ports:
        ports = ["9101"]
    with _PORT_COUNTER_LOCK:
        idx = _PORT_COUNTER % len(ports)
        _PORT_COUNTER += 1
    return f"http://localhost:{ports[idx]}/v1"


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
        # Sticky reasoner URL per instance — round-robin across host pool.
        self._reasoner_base_url = _next_reasoner_url()

    def run(
        self,
        query: str,
        bundle: Bundle,
        *,
        query_type: str | None = None,   # accepted for ABC parity, ignored
        query_id: str | None = None,     # accepted for ABC parity, ignored
    ) -> VizOutput:
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
                reasoner_base_url=self._reasoner_base_url,
            )

        return map_agent_response(response, bundle, concat_doc_path=doc_path)
