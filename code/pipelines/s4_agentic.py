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
# on-prem Qwen3.5-397B-A17B-FP8 vLLM cluster. Each pipeline INSTANCE
# gets a sticky URL at __init__ — distributes load across hosts when
# --s4-workers > 1 (run_prototype creates a new instance per task).
#
# Host pool source of truth: code.adapters.agent_client.QWEN_HOSTS
# (env QWEN_HOSTS, default 10.1.211.163-170:8000).
# Mode: env DOCVIZ_HOST_MODE = "single" (first host only) | "multi"
# (round-robin across all hosts).
_PORT_COUNTER_LOCK = threading.Lock()
_PORT_COUNTER = 0


def _next_reasoner_url() -> str:
    """Round-robin pick from QWEN_HOSTS honoring DOCVIZ_HOST_MODE."""
    global _PORT_COUNTER
    from code.adapters.agent_client import QWEN_HOSTS, DOCVIZ_HOST_MODE
    hosts = QWEN_HOSTS or ["10.1.211.148:8000"]
    if DOCVIZ_HOST_MODE != "multi":
        return f"http://{hosts[0]}/v1"
    with _PORT_COUNTER_LOCK:
        idx = _PORT_COUNTER % len(hosts)
        _PORT_COUNTER += 1
    return f"http://{hosts[idx]}/v1"


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
        doc_paths, page_to_doc_id = write_bundle_as_docai(bundle, out_dir=self._work_dir)

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
                doc_json_paths=doc_paths,
                user_query=query,
                n_steps_max=self._n_steps_max,
                return_trace=True,
                return_train_sample=False,
                reasoner_max_length=self._reasoner_max_length,
                reasoner_base_url=self._reasoner_base_url,
            )

        return map_agent_response(response, bundle, concat_doc_path=doc_paths[0] if doc_paths else None)
