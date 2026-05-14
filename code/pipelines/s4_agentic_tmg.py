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

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from code.adapters.agent_client import AgentClient
from code.adapters.bundle_to_docai import write_bundle_as_docai
from code.adapters.viz_output_mapper import map_agent_response
from code.pipelines.base import Bundle, Pipeline, VizOutput
from code.pipelines.tmg import V4_POOL_EXPOSURE_RULE, build_tmg_rule


# generate_viz tool's viz output sidecar — written by the tool, read by
# this orchestrator after the agent returns. Path format:
# /{DOCVIZ_VIZ_SIDECAR_DIR}/{mode}_{query_id}.json
_DEFAULT_VIZ_SIDECAR_DIR = "/tmp/v4_viz_outputs"


def _read_viz_sidecar(mode: str, query_id: Optional[str]) -> Optional[dict]:
    """Read the viz output sidecar produced by generate_viz tool.

    Returns the parsed dict or None if missing / unparseable.
    Removes the file after a successful read to keep the dir clean
    and avoid stale-file races on subsequent runs.
    """
    if not query_id:
        return None
    sidecar_dir = Path(
        os.environ.get("DOCVIZ_VIZ_SIDECAR_DIR", _DEFAULT_VIZ_SIDECAR_DIR)
    )
    path = sidecar_dir / f"{mode}_{query_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        path.unlink()
    except OSError:
        pass
    return data


_GENERATE_VIZ_TOOL_PATH = (
    Path(__file__).resolve().parent.parent / "agent_tools" / "generate_viz.py"
)


# Module-level round-robin assignment of reasoner_base_url across the
# on-prem Qwen3.5-397B-A17B-FP8 vLLM cluster. Each pipeline INSTANCE
# gets a sticky URL at __init__ — combined with run_prototype's
# `pipeline_factory()` per-task creation under ThreadPoolExecutor, this
# distributes load across hosts when --s4-workers > 1.
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
        # Sticky reasoner URL per instance — round-robin across host pool.
        self._reasoner_base_url = _next_reasoner_url()

    def run(
        self,
        query: str,
        bundle: Bundle,
        *,
        query_type: str | None = None,
        query_id: str | None = None,
    ) -> VizOutput:
        doc_paths, page_to_doc_id = write_bundle_as_docai(bundle, out_dir=self._work_dir)
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
                    # Tool uses the SAME vLLM endpoint as the agent's
                    # reasoner so this pipeline instance's sticky host
                    # is honored end-to-end (per-sample parallel).
                    "vllm_base_url": self._reasoner_base_url,
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

            def _do_run(reasoner_url: str):
                return client.run_paper_default(
                    doc_json_paths=doc_paths,
                    user_query=query,
                    n_steps_max=self._n_steps_max,
                    return_trace=True,
                    return_train_sample=False,
                    reasoner_max_length=self._reasoner_max_length,
                    reasoner_base_url=reasoner_url,
                    custom_rules=tmg_rule if tmg_rule else None,
                    custom_tools_path=custom_tools_path,
                    extra_overrides=extra_overrides,
                    # V4 owns the output contract via rule 17/18 (sidecar +
                    # ack final_answer). Suppress the default JSON-only rule
                    # which conflicts with that contract.
                    omit_default_dsl_rule=(self.mode in ("v4_pool", "v4_consolidated")),
                )

            # Wrap in try/except so HTTP 400 (after the tool already wrote a
            # sidecar) doesn't bypass the sidecar-rescue path below.
            # Plot2Code/Text2Vis subagent analysis identified Mode D/I:
            # generate_viz writes valid sidecar → envelope-validation 400 →
            # raise_for_status throws → orchestrator never reads the sidecar.
            # See docs/analysis/{text2vis,plot2code}_v4_cons_fail_analysis.md.
            response = None
            http_error: Optional[Exception] = None
            try:
                response = _do_run(self._reasoner_base_url)
            except Exception as e:
                http_error = e

            # Mode A recovery: agent server silently masks upstream LLM
            # ConnectError / 401 as 200 OK with empty final_answer (see
            # agent/run_agent_v2.py:459 silent except). Empty final_answer
            # + 0 tokens is almost certainly a transient upstream failure on
            # the sticky reasoner host. Retry once on a different
            # round-robin host with 3s backoff.
            # Preflight (2026-05-13, n=5): 4/5 recovered.
            # Applies to ALL modes — Mode A is an agent-server symptom.
            # Note: <5s duration gate REMOVED (Fix 3) — server [Setup] time
            # can push duration past 5s even when the reasoner crashed
            # immediately. Tokens=0 + empty final_answer is the load-bearing
            # signal.
            # Root cause: docs/analysis/v4_cons_fail_root_cause.md.
            if response is not None and (
                not response.final_answer
                and response.total_tokens == 0
            ):
                time.sleep(3.0)
                retry_url = _next_reasoner_url()
                try:
                    response = _do_run(retry_url)
                except Exception as e:
                    http_error = e

            # If the call raised (HTTP 400 / ConnectError / etc.) build a
            # placeholder response so the sidecar-rescue path can run.
            if response is None:
                from code.adapters.agent_client import AgentRunResponse
                response = AgentRunResponse(
                    final_answer="",
                    steps_reasoning=[],
                    inputs_used=0,
                    train_sample=None,
                    trace=None,
                    warnings=[f"agent call raised: {type(http_error).__name__}: {http_error}"[:300]],
                    session_id="",
                    total_tokens=0,
                    total_duration_seconds=0.0,
                    raw=None,
                )

        vo = map_agent_response(response, bundle, concat_doc_path=doc_paths[0] if doc_paths else None)

        # V4 modes: the generate_viz tool persisted the viz to a sidecar
        # file. Override the (likely empty / ack-only) viz from the agent's
        # short final_answer with the sidecar payload. Falls back to the
        # mapped agent response if the sidecar is missing (e.g., the agent
        # never invoked the tool — a content failure we surface as-is).
        if self.mode in ("v4_pool", "v4_consolidated"):
            sidecar = _read_viz_sidecar(self.mode, query_id)
            if sidecar:
                vo.viz_type = sidecar.get("viz_type") or vo.viz_type
                vo.viz_dsl = sidecar.get("viz_dsl") or vo.viz_dsl
            else:
                vo.errors.append(
                    f"{self.name}: generate_viz sidecar missing for "
                    f"query_id={query_id!r}; agent likely did not invoke "
                    "the tool. Final_answer used as fallback."
                )

        return vo
