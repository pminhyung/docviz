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
# 9 production hosts on the internal cluster, all serving the same model.
# Each entry is "host:port"; the orchestrator's round-robin picks one
# entry per pipeline instance, allowing parallel sample-level dispatch.
#
# Host policy:
#   - 10.1.211.148:8000 is the *single-host pinned* endpoint (head of list,
#     always used in single mode);
#   - 10.1.211.163..170:8000 are the additional pool members used in
#     multi mode for sample-level parallelism.
#
# Mode selection (env DOCVIZ_HOST_MODE, default "single"):
#   - "single" → only QWEN_HOSTS[0] (= 148) is used;
#   - "multi"  → round-robin across all QWEN_HOSTS (148 + 163-170).
#
# Override by setting QWEN_HOSTS env to a comma-separated list.

_DEFAULT_QWEN_HOSTS = ",".join(
    ["10.1.211.148:8000"] + [f"10.1.211.{i}:8000" for i in range(163, 171)]
)
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
# QWEN_SEED env override enables §13 three-seed reporting (42/43/44) without
# touching downstream pipelines — every PAPER_DEFAULT_SEED importer picks up
# the override transparently.
PAPER_DEFAULT_TEMPERATURE = 0
PAPER_DEFAULT_SEED = int(os.environ.get("QWEN_SEED", "42"))

# Qwen3.5-397B-A17B-FP8 recommended sampling per Alibaba/Qwen team:
#   - non-thinking mode: T=0.7, top_p=0.8, top_k=20, min_p=0
#   - thinking mode:     T=0.6, top_p=0.95, top_k=20, min_p=0
# We use non-thinking everywhere in Week 0 (chat_template_kwargs=
# {"enable_thinking": False}). seed=PAPER_DEFAULT_SEED preserved for
# within-run reproducibility (vLLM honors seed under sampling).
QWEN_NON_THINKING_SAMPLING = {
    "temperature": 0.7,
    "top_p": 0.8,
    "extra_body": {
        "top_k": 20,
        "min_p": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    },
}
QWEN_THINKING_SAMPLING = {
    "temperature": 0.6,
    "top_p": 0.95,
    "extra_body": {
        "top_k": 20,
        "min_p": 0,
        "chat_template_kwargs": {"enable_thinking": True},
    },
}


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
        doc_json_path: Optional[str] = None,
        doc_json_paths: Optional[List[str]] = None,
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
        omit_default_dsl_rule: bool = False,
    ) -> AgentRunResponse:
        """Run /v2/run with PAPER_MASTER_SPEC defaults baked in.

        Locks: lang="en", DSL-only output (enforced via agent prompt config),
        temperature=0 / seed=42 (passed via custom_rules and reasoner default),
        web_search disabled (via custom_rules; see WEEK0 inventory for the
        verified disable mechanism).

        `omit_default_dsl_rule` (V4 modes): when True, suppress the default
        "final_answer must be one JSON object {viz_type, viz_dsl}" rule
        because V4 strategies override the output contract via custom_rules
        (rule 17/18: invoke `generate_viz` tool → sidecar persists viz →
        agent's final_answer is a short ack). Keeping the default rule
        causes a conflict the model resolves in favor of the older default.
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
        # V4 strategies suppress this rule via omit_default_dsl_rule=True
        # because they own the output contract (sidecar persistence + ack
        # final_answer) and any "must emit JSON" instruction conflicts.
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
        rules = [web_search_off_rule, deterministic_rule]
        if not omit_default_dsl_rule:
            rules.append(dsl_output_rule)
        if custom_rules:
            rules.append(custom_rules.strip())
        merged_rules = "\n".join(rules)

        # N-way multi-doc takes precedence; falls back to legacy single-path.
        # When doc_json_paths is provided, the agent server forces
        # single_doc=False so each path is loaded as its own document,
        # preserving the per-doc title + snippet structure expected by
        # DOC_STEP_PROMPT and the action loop's filelist conventions.
        if doc_json_paths:
            primary_path = doc_json_paths[0]
            multi_doc_active = True
        elif doc_json_path:
            primary_path = doc_json_path
            multi_doc_active = False
        else:
            raise ValueError(
                "run_paper_default: either doc_json_paths (multi) or "
                "doc_json_path (single) must be provided"
            )

        body: Dict[str, Any] = {
            "doc_json_path": primary_path,
            "user_query": user_query,
            "lang": "en",
            # When multi_doc_active, the agent ignores single_doc and uses
            # doc_json_paths directly (handlers.py + run_agent_v2.py).
            "single_doc": not multi_doc_active,
            "n_steps_max": n_steps_max,
            "return_trace": return_trace,
            "return_train_sample": return_train_sample,
            "reasoner_type": "llm",
            "reasoner_model_name": reasoner_model_name,
            "reasoner_base_url": reasoner_base_url,
            "reasoner_api_key": reasoner_api_key,
            "custom_rules": merged_rules,
            # We are both producer and consumer of the trace (orchestrator →
            # viz_output_mapper → judge). Disable trace redaction so the
            # downstream judge can see the actual search.query array and
            # ReadFullDocument.goal text for the retrieval-query-quality axis.
            "redact_args": False,
        }
        if multi_doc_active:
            body["doc_json_paths"] = list(doc_json_paths)
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
    cluster (10.1.211.148/163-170:8000 by default). Used by S1 Direct, S7
    SelfRefine, judge scorer, and any other strategy that bypasses the
    agent loop.

    Host selection honors DOCVIZ_HOST_MODE:
      - "single" → only the first host in QWEN_HOSTS (sequential calls);
      - "multi"  → round-robin across all hosts.

    Multi-host queue + retry semantics (v0.3 amendment §16 / cost-efficiency):
      - ConnectionRefusedError / httpx.ConnectError on a host → that host
        is marked unhealthy for `_HOST_COOLDOWN_SECONDS` (30s) and the
        request immediately re-routes to the next healthy host. The retry
        counter does NOT increment for refused-connection failures, so
        cluster-wide outages are still surfaced.
      - Non-refused failure (httpx.ReadTimeout, 5xx, RemoteProtocolError,
        decode errors): wait 3s and retry the SAME host once (handles
        transient host overload). If still failing, fall through to the
        next healthy host with the retry counter incremented.
      - If all hosts are in cooldown simultaneously, raises after a brief
        wait for at least one to recover.

    This is the production client for ALL Qwen access points across the
    codebase except (a) the agent-server's own sticky reasoner URL and
    (b) generate_viz tool, which uses its own caller-supplied URL.
    """

    _HOST_COOLDOWN_SECONDS = 30.0
    _RETRY_SLEEP_SECONDS = 3.0
    _MAX_NON_REFUSED_RETRIES = 1  # per request, applied per host

    def __init__(
        self,
        hosts: Optional[List[str]] = None,
        timeout_seconds: float = 600.0,
    ):
        chosen = hosts if hosts is not None else (
            QWEN_HOSTS if DOCVIZ_HOST_MODE == "multi" else QWEN_HOSTS[:1]
        )
        if not chosen:
            chosen = ["10.1.211.148:8000"]
        self._bases = [f"http://{h}/v1" for h in chosen]
        # Round-robin cursor + per-host cooldown registry. The cursor is
        # protected by a lock so concurrent callers (ThreadPoolExecutor)
        # distribute evenly across hosts.
        import threading
        self._idx = 0
        self._idx_lock = threading.Lock()
        self._cooldown_until: Dict[str, float] = {b: 0.0 for b in self._bases}
        self._cooldown_lock = threading.Lock()
        self._timeout = timeout_seconds

    def _next_base(self) -> str:
        """Round-robin advance. Does NOT honor cooldown — that's the
        caller's job via `_next_healthy_base()`. Kept for back-compat
        with any external direct callers."""
        with self._idx_lock:
            base = self._bases[self._idx % len(self._bases)]
            self._idx += 1
            return base

    def _next_healthy_base(
        self,
        skip: Optional[set] = None,
    ) -> Optional[str]:
        """Round-robin advance that skips hosts in cooldown and any host
        in `skip`. Returns None if no healthy host is available right now.
        """
        import time as _t
        skip = skip or set()
        now = _t.time()
        with self._idx_lock:
            n = len(self._bases)
            for _ in range(n):
                base = self._bases[self._idx % n]
                self._idx += 1
                if base in skip:
                    continue
                if self._cooldown_until.get(base, 0.0) <= now:
                    return base
            return None

    def _mark_cooldown(self, base: str) -> None:
        import time as _t
        with self._cooldown_lock:
            self._cooldown_until[base] = _t.time() + self._HOST_COOLDOWN_SECONDS

    def _build_body(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        top_p: Optional[float],
        seed: int,
        max_tokens: Optional[int],
        response_format: Optional[Dict[str, Any]],
        extra_body: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "seed": seed,
        }
        if top_p is not None:
            body["top_p"] = top_p
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if response_format is not None:
            body["response_format"] = response_format
        if extra_body:
            body.update(extra_body)
        return body

    def _post_once(
        self,
        base: str,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Single POST, no retry. Raises any exception unchanged. Returns
        parsed JSON."""
        with httpx.Client(timeout=self._timeout) as c:
            resp = c.post(
                f"{base}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {DEFAULT_REASONER_KEY}"},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _is_connection_refused(exc: BaseException) -> bool:
        """Detect "host refused / unreachable" — i.e. transport could not
        be established. We treat these as host-level outages (cooldown +
        re-queue without consuming retry budget). Everything else is
        treated as a transient that the same host may recover from."""
        # httpx.ConnectError covers refused, name-resolution, etc.
        if isinstance(exc, httpx.ConnectError):
            return True
        # Belt-and-suspenders for non-httpx callers
        if isinstance(exc, ConnectionRefusedError):
            return True
        # Walk __cause__/__context__ chain for nested transport errors
        cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
        if cause is not None and cause is not exc:
            try:
                return QwenDirectClient._is_connection_refused(cause)
            except RecursionError:
                return False
        return False

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: str = QWEN_MODEL,
        temperature: float = PAPER_DEFAULT_TEMPERATURE,
        top_p: Optional[float] = None,
        seed: int = PAPER_DEFAULT_SEED,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Issue one chat.completion request with multi-host queue + retry.

        Returns the raw OpenAI-style payload. Raises on persistent
        failure across all healthy hosts (after retries).
        """
        import time as _t

        body = self._build_body(
            messages, model, temperature, top_p, seed, max_tokens,
            response_format, extra_body,
        )

        attempted: set = set()
        non_refused_retries = 0
        # The hard upper bound prevents an infinite loop if every host
        # repeatedly fails with non-refused errors. We try each host at
        # most twice (one same-host retry + one fallback attempt).
        max_total_attempts = 2 * len(self._bases) + 2

        for _attempt in range(max_total_attempts):
            base = self._next_healthy_base(skip=attempted)
            if base is None:
                # All hosts either tried or in cooldown — wait briefly
                # for soonest cooldown to expire, then retry.
                now = _t.time()
                with self._cooldown_lock:
                    soonest = min(
                        (t for b, t in self._cooldown_until.items()
                         if t > now and b not in attempted),
                        default=None,
                    )
                if soonest is None:
                    # No remaining hosts at all — surface the failure.
                    raise RuntimeError(
                        "QwenDirectClient: all hosts exhausted/cooldown; "
                        f"attempted={sorted(attempted)}"
                    )
                wait = max(soonest - now, 0.1)
                _t.sleep(min(wait, 5.0))
                continue

            try:
                return self._post_once(base, body)
            except Exception as e:
                refused = self._is_connection_refused(e)
                if refused:
                    # Cooldown the host + re-queue (don't count as retry)
                    self._mark_cooldown(base)
                    attempted.add(base)
                    continue
                # Non-refused error: retry same host once after a 3s
                # sleep to ride out transient load/timeout.
                if non_refused_retries < self._MAX_NON_REFUSED_RETRIES:
                    non_refused_retries += 1
                    _t.sleep(self._RETRY_SLEEP_SECONDS)
                    try:
                        return self._post_once(base, body)
                    except Exception as e2:
                        if self._is_connection_refused(e2):
                            self._mark_cooldown(base)
                        attempted.add(base)
                        continue
                # Already retried once — drop this host from this request
                attempted.add(base)
                continue

        raise RuntimeError(
            "QwenDirectClient: exhausted retries across all hosts; "
            f"attempted={sorted(attempted)}"
        )
