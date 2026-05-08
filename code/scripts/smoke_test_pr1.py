#!/usr/bin/env python3
"""PR1 smoke test.

End-to-end sanity check for the bootstrap layer:

  1. Build a tiny synthetic Bundle (2 Docs).
  2. Convert to docai dict-of-pages JSON via bundle_to_docai.
  3. Verify Qwen3.6-27B vLLM endpoint health (3 ports).
  4. POST to the agent /v2/run endpoint (must already be running).
  5. Map RunResponseV2 → VizOutput, print summary.

This script does NOT spawn the agent server — it expects it on
DOCVIZ_AGENT_URL (default http://localhost:9024). Use:

    bash agent/run_server.sh --port 9024 &
    python -m code.scripts.smoke_test_pr1
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Make `code.*` importable when invoked from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx

from code.adapters.agent_client import (
    AgentClient,
    QwenDirectClient,
    QWEN_36_27B_PORTS,
    QWEN_36_27B_BASE_URL,
)
from code.adapters.bundle_to_docai import write_bundle_as_docai
from code.adapters.viz_output_mapper import map_agent_response
from code.pipelines.base import Bundle, Doc
from code.utils.cost_tracker import CostTracker


SAMPLE_QUERY = (
    "Compare the document agent's reasoning loop and its API endpoints, "
    "and visualize the relationship between them."
)


def _check_vllm_endpoints() -> None:
    print("[1/5] Checking Qwen3.6-27B vLLM endpoints…")
    bad = []
    with httpx.Client(timeout=5.0) as c:
        for p in QWEN_36_27B_PORTS:
            try:
                r = c.get(f"http://localhost:{p}/v1/models")
                if r.status_code != 200:
                    bad.append((p, f"status={r.status_code}"))
                    continue
                model = r.json()["data"][0]
                print(f"      port {p}: 200  model={model['id']}  "
                      f"max_model_len={model['max_model_len']}")
            except Exception as e:
                bad.append((p, f"error={type(e).__name__}: {e}"))
    if bad:
        print(f"      [WARN] unhealthy ports: {bad}")
    else:
        print("      OK — all 3 ports healthy")


def _build_synthetic_bundle() -> Bundle:
    print("[2/5] Building synthetic bundle (2 docs)…")
    docs = [
        Doc(
            doc_id="smoke_0_0",
            title="Document Agent V2 Overview",
            content=(
                "The Document Agent V2 is a FastAPI server that runs a "
                "multi-step reasoning loop over input documents. It exposes "
                "a /v2/run endpoint accepting RunRequestV2 and returning "
                "RunResponseV2 with the agent's final answer plus a step trace."
            ),
        ),
        Doc(
            doc_id="smoke_0_1",
            title="Reasoning and Tools",
            content=(
                "Each step in the reasoning loop may emit a tool invocation. "
                "Built-in tools include Search, ReadFullDocument, and GetPage. "
                "The loop terminates when the agent decides it has enough "
                "information to answer the user's query."
            ),
        ),
    ]
    bundle = Bundle(
        bundle_id="smoke_pr1_001",
        source="synthetic",
        docs=docs,
        metadata={"note": "PR1 smoke test bundle"},
    )
    print(f"      bundle_id={bundle.bundle_id}  docs={len(bundle.docs)}  "
          f"chars={bundle.total_chars()}")
    return bundle


def _serialize_bundle(bundle: Bundle) -> str:
    print("[3/5] Serializing bundle → docai JSON…")
    out_dir = Path(tempfile.gettempdir()) / "docviz_smoke"
    path, page_to_doc_id = write_bundle_as_docai(bundle, out_dir=out_dir)
    print(f"      path: {path}")
    print(f"      page_to_doc_id: {page_to_doc_id}")
    return path


def _run_agent(doc_path: str) -> object:
    print("[4/5] POST /v2/run …")
    base_url = os.environ.get("DOCVIZ_AGENT_URL", "http://localhost:9024")
    print(f"      agent base_url: {base_url}")
    with AgentClient(base_url=base_url) as client:
        if not client.health():
            print("      [ABORT] agent /health not reachable")
            print("      start it with: bash agent/run_server.sh --port 9024 &")
            sys.exit(2)
        resp = client.run_paper_default(
            doc_json_path=doc_path,
            user_query=SAMPLE_QUERY,
            n_steps_max=4,           # smoke
            return_trace=True,
            return_train_sample=False,
            reasoner_max_length=4096,
        )
    print(f"      session_id={resp.session_id}  steps={len(resp.steps_reasoning)}  "
          f"total_tokens={resp.total_tokens}  duration={resp.total_duration_seconds:.2f}s")
    print(f"      final_answer head: {resp.final_answer[:200]!r}")
    return resp


def _map_and_summarize(resp: object, bundle: Bundle, doc_path: str) -> None:
    print("[5/5] Mapping RunResponseV2 → VizOutput…")
    vo = map_agent_response(resp, bundle, concat_doc_path=doc_path)
    summary = {
        "viz_type": vo.viz_type,
        "viz_dsl_chars": len(vo.viz_dsl),
        "sub_queries": len(vo.sub_queries),
        "source_attribution_keys": list(vo.source_attribution.keys()),
        "retrieved_chunks": len(vo.retrieved_chunks),
        "tokens_out": vo.tokens_out,
        "errors": vo.errors,
    }
    print(json.dumps(summary, indent=2))


def main() -> int:
    _check_vllm_endpoints()
    bundle = _build_synthetic_bundle()
    doc_path = _serialize_bundle(bundle)
    resp = _run_agent(doc_path)
    _map_and_summarize(resp, bundle, doc_path)

    # CostTracker is exercised here for sanity even though cost is $0.
    t = CostTracker()
    t.add(provider="vllm-qwen36", model="Qwen3.6-27B",
          tokens_in=0, tokens_out=getattr(resp, "total_tokens", 0),
          tag="smoke")
    print("CostTracker summary:", t.summary())
    print("\nPR1 smoke test PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
