"""HTTP client for docviz/agent's /v2/run endpoint.

The agent is the source-of-truth for the agentic Cross-doc Iterative Search
(CIS) pillar. This wrapper:
  - Posts RunRequestV2 to the agent's FastAPI server (default http://localhost:9024).
  - Locks paper-experiment defaults (web_search disabled, temperature=0,
    seed=42, language="en", DSL-only output).
  - Pins the reasoner backbone to Qwen3.5-397B-A17B-FP8 served by local vLLM.

The Qwen3.5-397B-A17B-FP8 endpoints currently serve max_model_len=131072. Three
instances at 10.1.211.163-170:8000 . For Week 0
the agent is given a single endpoint; load-balancing across the three
ports lives in any follow-up direct-call client (S1 baseline).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx


# ── Config ──────────────────────────────────────────────────────────────────

AGENT_BASE_URL = os.environ.get("DOCVIZ_AGENT_URL", "http://localhost:9024")

# ── On-premise Qwen3.5-397B-A17B-FP8 vLLM cluster ──────────────────────────
# 8 production hosts on the internal cluster, all serving the same model.
# Each entry is "host:port"; the orchestrator's round-robin picks one
# entry per pipeline instance, allowing parallel sample-level dispatch.
#
# Mode selection (env DOCVIZ_HOST_MODE, default "single"):
#   - "single" → only the first host is used (one URL for the whole batch);
#   - "multi"  → round-robin across all hosts in QWEN_HOSTS.
#
# Override by setting QWEN_HOSTS env to a comma-separated list.

_DEFAULT_QWEN_HOSTS = ",".join(f"10.1.211.{i}:8000" for i in range(163, 171))
QWEN_HOSTS = [
    h.strip() for h in os.environ.get("QWEN_HOSTS", _DEFAULT_QWEN_HOSTS).split(",")
    if h.strip()
]
DOCVIZ_HOST_MODE = os.environ.get("DOCVIZ_HOST_MODE", "single").lower()
QWEN_MODEL = os.environ.get("QWEN_MODEL", "Qwen3.5-397B-A17B-FP8")
QWEN_BASE_URL = os.environ.get(
    "QWEN_BASE_URL",
    f"http://{QWEN_HOSTS[0]}/v1" if QWEN_HOSTS else "http://10.1.211.163:8000/v1",
)

DEFAULT_REASONER_KEY = "EMPTY"   # vLLM ignores; set to non-empty to satisfy
                                  # the agent's Pydantic validator.

# Anti-hallucination defaults aligned with PAPER_MASTER_SPEC §3.5 / §19.
PAPER_DEFAULT_TEMPERATURE = 0
PAPER_DEFAULT_SEED = 42


# ── Request / Response wrappers ────────────────────────────────────────────

@dataclass
class StepReasoning:
    step_number: int
    step_type: str
    step_name: str
    action: Optional[Dict[str, Any]]
    duration: float


@dataclass
class AgentRunResponse:
    final_answer: str
    steps_reasoning: List[StepReasoning]
    inputs_used: int
    train_sample: Optional[Dict[str, Any]]
    trace: Optional[Dict[str, Any]]
    warnings: List[str]
    session_id: str
    total_tokens: int
    total_duration_seconds: float
    raw: Dict[str, Any] = field(default_factory=dict)   # full server payload


# ── Client ──────────────────────────────────────────────────────────────────


class AgentClient:
    """Thin httpx wrapper for the agent's /v2/run endpoint.

    Use as a context manager (or pass an existing httpx.Client). One
    AgentClient per process is sufficient for Week 0 prototype scale.
    """

    def __init__(
        self,
        base_url: str = AGENT_BASE_URL,
        timeout_seconds: float = 600.0,
        admin_secret: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._admin_secret = admin_secret or os.environ.get("DOCVIZ_AGENT_ADMIN_SECRET")
        self._client: Optional[httpx.Client] = None

    def __enter__(self) -> "AgentClient":
        self._client = httpx.Client(timeout=self._timeout)
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # ── Paper-experiment helper ────────────────────────────────────────────

    def run_paper_default(
        self,
        *,
        doc_json_path: str,
        user_query: str,
        custom_tools_path: Optional[str] = None,
        custom_rules: Optional[str] = None,
        n_steps_max: int = 8,
        session_id: Optional[str] = None,
        return_trace: bool = True,
        return_train_sample: bool = False,
        reasoner_model_name: str = QWEN_MODEL,
        reasoner_base_url: str = QWEN_BASE_URL,
        reasoner_api_key: str = DEFAULT_REASONER_KEY,
        reasoner_max_length: Optional[int] = 32768,
        extra_overrides: Optional[Dict[str, Any]] = None,
    ) -> AgentRunResponse:
        """Run /v2/run with PAPER_MASTER_SPEC defaults baked in.

        Locks: lang="en", DSL-only output (enforced via agent prompt config),
        temperature=0 / seed=42 (passed via custom_rules and reasoner default),
        web_search disabled (via custom_rules; see WEEK0 inventory for the
        verified disable mechanism).
        """
        # Encourage DSL-only output and forbid web search via custom_rules.
        # The agent compiles these into the system prompt verbatim.
        web_search_off_rule = (
            "- Do NOT invoke any web_search or external_search tool. "
            "All evidence must come from the supplied document."
        )
        deterministic_rule = (
            f"- Use temperature={PAPER_DEFAULT_TEMPERATURE} and "
            f"seed={PAPER_DEFAULT_SEED} for any internal LLM call."
        )
        # The downstream parser (viz_output_mapper._extract_dsl_block) keys on
        # exactly this JSON shape; matching it eliminates fenced-block heuristics
        # and the prose-fallback that was producing un-renderable viz_dsl.
        dsl_output_rule = (
            "- Your final_answer must be EXACTLY one JSON object and nothing "
            "else (no prose before or after, no markdown fences). The object "
            "has two keys: \"viz_type\" and \"viz_dsl\".\n"
            "  - viz_type ∈ {\"chartjs_bar\", \"chartjs_line\", "
            "\"chartjs_grouped_bar\", \"chartjs_pie\", \"chartjs_scatter\", "
            "\"mermaid_flowchart\", \"mermaid_timeline\", \"mermaid_mindmap\", "
            "\"mermaid_sequenceDiagram\", \"mermaid_classDiagram\"} "
            "(10-type enum; expanded 2026-05-10).\n"
            "  - viz_dsl is a single string holding the raw DSL: Mermaid "
            "markdown for the mermaid_* types, or a Chart.js JSON spec "
            "(serialized as a string) for the chartjs_* types.\n"
            "- Pick the viz_type that best fits the user's query type and "
            "the source structure (temporal → timeline, hierarchical → "
            "mindmap, relational/process → flowchart or sequenceDiagram, "
            "quantitative → chartjs_*, proportion → chartjs_pie, "
            "correlation → chartjs_scatter, schema → classDiagram).\n"
            "- Use only facts present in the supplied document; do not "
            "fabricate. If the document is insufficient, return a minimal but "
            "valid DSL covering what is present, not prose."
        )
        rules = [web_search_off_rule, deterministic_rule, dsl_output_rule]
        if custom_rules:
            rules.append(custom_rules.strip())
        merged_rules = "\n".join(rules)

        body: Dict[str, Any] = {
            "doc_json_path": doc_json_path,
            "user_query": user_query,
            "lang": "en",
            "single_doc": True,            # bundle is concat-serialized → one doc
            "n_steps_max": n_steps_max,
            "return_trace": return_trace,
            "return_train_sample": return_train_sample,
            "reasoner_type": "llm",
            "reasoner_model_name": reasoner_model_name,
            "reasoner_base_url": reasoner_base_url,
            "reasoner_api_key": reasoner_api_key,
            "custom_rules": merged_rules,
        }
        if reasoner_max_length is not None:
            body["reasoner_model_max_length"] = reasoner_max_length
        if custom_tools_path:
            body["custom_tools_path"] = custom_tools_path
        if session_id:
            body["session_id"] = session_id
        if extra_overrides:
            body.update(extra_overrides)

        return self._post_run(body)

    # ── Low-level POST ─────────────────────────────────────────────────────

    def _post_run(self, body: Dict[str, Any]) -> AgentRunResponse:
        if self._client is None:
            raise RuntimeError("AgentClient must be used as a context manager")

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._admin_secret:
            headers["X-Admin-Secret"] = self._admin_secret

        resp = self._client.post(
            f"{self.base_url}/v2/run", json=body, headers=headers
        )
        resp.raise_for_status()
        payload = resp.json()

        steps = [
            StepReasoning(
                step_number=s["step_number"],
                step_type=s["step_type"],
                step_name=s.get("step_name", ""),
                action=s.get("action"),
                duration=s.get("duration", 0.0),
            )
            for s in payload.get("steps_reasoning", [])
        ]

        return AgentRunResponse(
            final_answer=payload.get("final_answer", ""),
            steps_reasoning=steps,
            inputs_used=payload.get("inputs_used", 0),
            train_sample=payload.get("train_sample"),
            trace=payload.get("trace"),
            warnings=payload.get("warnings", []),
            session_id=payload.get("session_id", ""),
            total_tokens=payload.get("total_tokens", 0),
            total_duration_seconds=payload.get("total_duration_seconds", 0.0),
            raw=payload,
        )

    # ── Health probe ───────────────────────────────────────────────────────

    def health(self) -> bool:
        """Return True iff the agent server responds 200 to /health."""
        if self._client is None:
            with httpx.Client(timeout=5.0) as c:
                try:
                    return c.get(f"{self.base_url}/health").status_code == 200
                except httpx.HTTPError:
                    return False
        try:
            return self._client.get(f"{self.base_url}/health").status_code == 200
        except httpx.HTTPError:
            return False


# ── Direct-call helper for S1 (no agent loop) ──────────────────────────────


class QwenDirectClient:
    """OpenAI-compatible client targeting the Qwen3.5-397B-A17B-FP8 vLLM
    cluster (10.1.211.163-170:8000 by default). Used by S1 Direct and any
    other strategy that bypasses the agent loop.

    Host selection honors DOCVIZ_HOST_MODE:
      - "single" → only the first host in QWEN_HOSTS (sequential calls);
      - "multi"  → round-robin across all hosts.
    """

    def __init__(
        self,
        hosts: Optional[List[str]] = None,
        timeout_seconds: float = 600.0,
    ):
        chosen = hosts if hosts is not None else (
            QWEN_HOSTS if DOCVIZ_HOST_MODE == "multi" else QWEN_HOSTS[:1]
        )
        if not chosen:
            chosen = ["10.1.211.163:8000"]
        self._bases = [f"http://{h}/v1" for h in chosen]
        self._idx = 0
        self._timeout = timeout_seconds

    def _next_base(self) -> str:
        base = self._bases[self._idx % len(self._bases)]
        self._idx += 1
        return base

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: str = QWEN_MODEL,
        temperature: float = PAPER_DEFAULT_TEMPERATURE,
        seed: int = PAPER_DEFAULT_SEED,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Issue one chat.completion request. Returns the raw OpenAI-style payload."""
        base = self._next_base()
        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "seed": seed,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if response_format is not None:
            body["response_format"] = response_format
        if extra_body:
            body.update(extra_body)
        with httpx.Client(timeout=self._timeout) as c:
            resp = c.post(
                f"{base}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {DEFAULT_REASONER_KEY}"},
            )
            resp.raise_for_status()
            return resp.json()
