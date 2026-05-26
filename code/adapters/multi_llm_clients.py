"""Multi-LLM client factory for cross-model robustness experiments.

Per PAPER_MASTER_SPEC priority 2 (5-model extension): the same direct-call
pipelines (S1_Direct, S7_SelfRefine, B2_NVAGENT, B3_CoDA, B4_ViviDoc, etc.)
should be runnable under multiple LLM backbones to show the method's
gains are model-agnostic, not Qwen-specific.

Backbones supported here:
  - "qwen"    : Qwen3.5-397B-A17B-FP8 on 10.1.211.148/163-166:8000
                (167-170 retasked to DeepSeek as of 2026-05-24)
  - "deepseek": DeepSeek V4-Flash on 10.1.211.167-170:8000 (sglang)
  - "gemma3"  : google/gemma-3-27b-it on a vLLM server (default
                localhost:9401); see scripts/launch_gemma3.sh for setup
  - "sonnet"  : Claude Sonnet via `claude -p` CLI (session credits, no API
                cost). Sequential, rate-limit aware (time.sleep + retry).

All backbones expose a `.chat(messages, model=..., temperature, top_p,
seed, max_tokens, response_format, extra_body)` method matching the
existing `QwenDirectClient` contract — direct-call pipelines do not need
modification. The factory `get_client(backbone)` picks the right
implementation; pipelines accept it via their `client=` kwarg.

For agent-server-backed pipelines (B6, also some baselines that hit
http://localhost:9024), the LLM is configured on the agent server side
(env vars QWEN3_BASE_URL / MODEL_ID / API_KEY). To swap LLM there, a
separate agent server instance is required — out of scope for this
client module.
"""
from __future__ import annotations

import os
import time
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from code.adapters.agent_client import QwenDirectClient


# ── Hosts / model registry ─────────────────────────────────────────────────

_QWEN_HOSTS_DEFAULT = (
    ["10.1.211.148:8000"]
    + [f"10.1.211.{i}:8000" for i in range(163, 167)]   # 167-170 now DeepSeek
)
_DEEPSEEK_HOSTS_DEFAULT = [f"10.1.211.{i}:8000" for i in range(167, 171)]
_GEMMA3_HOSTS_DEFAULT = ["localhost:9401"]


BACKBONE_REGISTRY = {
    "qwen": {
        "hosts_env": "QWEN_HOSTS",
        "hosts_default": _QWEN_HOSTS_DEFAULT,
        "model_env": "QWEN_MODEL",
        "model_default": "Qwen3.5-397B-A17B-FP8",
    },
    "deepseek": {
        "hosts_env": "DEEPSEEK_HOSTS",
        "hosts_default": _DEEPSEEK_HOSTS_DEFAULT,
        "model_env": "DEEPSEEK_MODEL",
        "model_default": "deepseek-v4-flash",
    },
    "gemma3": {
        "hosts_env": "GEMMA3_HOSTS",
        "hosts_default": _GEMMA3_HOSTS_DEFAULT,
        "model_env": "GEMMA3_MODEL",
        "model_default": "gemma-3-27b-it",
    },
}


def _resolve_hosts(backbone: str) -> List[str]:
    cfg = BACKBONE_REGISTRY[backbone]
    raw = os.environ.get(cfg["hosts_env"], "").strip()
    if raw:
        return [h.strip() for h in raw.split(",") if h.strip()]
    return list(cfg["hosts_default"])


def _resolve_model(backbone: str) -> str:
    cfg = BACKBONE_REGISTRY[backbone]
    return os.environ.get(cfg["model_env"], cfg["model_default"])


# ── vLLM-style clients (Qwen / DeepSeek / Gemma3) ──────────────────────────


def get_vllm_client(backbone: str) -> QwenDirectClient:
    """Return a QwenDirectClient configured for the given backbone.

    The QwenDirectClient is OpenAI-compatible and works against any
    vLLM/sglang server that exposes the same endpoint shape — the host
    list and (optional) per-call `model=` string is all that varies.
    """
    if backbone not in {"qwen", "deepseek", "gemma3"}:
        raise ValueError(f"backbone={backbone!r} is not a vLLM-style backbone")
    hosts = _resolve_hosts(backbone)
    return QwenDirectClient(hosts=hosts)


# ── Claude Sonnet CLI client ───────────────────────────────────────────────


@dataclass
class SonnetResponse:
    content: str
    usage: Dict[str, Any]
    duration_seconds: float
    raw: Dict[str, Any]


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class ClaudeSonnetClient:
    """OpenAI-compatible (.chat) wrapper around `claude -p` CLI.

    Uses the user's Claude Code session credits — avoids per-call API
    cost — but is sequential and rate-limited. The wrapper enforces:
      - explicit `time.sleep` between successful calls (default 3s)
      - exponential backoff on transient errors
      - longer backoff if the error message mentions rate / limit
      - JSON output parsing (--output-format json gives the wrapped
        envelope; the inner `result` is the assistant text, which may
        itself be a ```json {...}``` block if the prompt asked for JSON)

    NOT thread-safe — instantiate one client and call sequentially.
    For concurrent runs, instantiate multiple clients (each enforces
    its own pacing).
    """

    def __init__(
        self,
        model: str = "sonnet",
        sleep_seconds: float = 3.0,
        max_retries: int = 4,
        timeout_seconds: int = 120,
    ):
        self._model = model
        self._sleep_seconds = sleep_seconds
        self._max_retries = max_retries
        self._timeout_seconds = timeout_seconds
        self._claude_bin = self._resolve_bin()

    @staticmethod
    def _resolve_bin() -> str:
        c = shutil.which("claude")
        if not c:
            for cand in ("/home/poc/.local/bin/claude", "/usr/local/bin/claude"):
                if os.path.exists(cand):
                    c = cand
                    break
        if not c:
            raise RuntimeError("`claude` CLI not found on PATH")
        return c

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.0,            # unused — claude -p has no temp arg in headless mode
        top_p: Optional[float] = None,        # unused
        seed: Optional[int] = None,           # unused
        max_tokens: Optional[int] = None,     # unused — Sonnet uses its default
        response_format: Optional[Dict[str, Any]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send messages, return OpenAI-style response dict.

        Returns a dict shaped like:
          {"choices":[{"message":{"content": "..."}}],
           "usage": {...}}

        Compatible with code paths that read `resp["choices"][0]["message"]["content"]`.
        """
        # Collapse messages → single prompt. System message goes first as
        # framing; user messages concatenated.
        sys_msgs = [m["content"] for m in messages if m.get("role") == "system"]
        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        assistant_msgs = [m["content"] for m in messages if m.get("role") == "assistant"]
        # For our use case, messages are typically [{"role":"user","content":...}].
        prompt_parts = []
        if sys_msgs:
            prompt_parts.append("\n\n".join(sys_msgs))
        if assistant_msgs:
            # Treat prior assistant turns as context — uncommon in our calls.
            for a in assistant_msgs:
                prompt_parts.append(f"[prior-assistant]\n{a}")
        prompt_parts.append("\n\n".join(user_msgs))
        # If a JSON response was requested, append a soft directive.
        if response_format and response_format.get("type") == "json_object":
            prompt_parts.append(
                "\nReturn ONLY a single JSON object — no surrounding prose, "
                "no markdown fences."
            )
        prompt = "\n\n".join(p for p in prompt_parts if p)

        cmd = [
            self._claude_bin, "-p", prompt,
            "--model", self._model,
            "--output-format", "json",
        ]

        backoff = 4.0
        last_err = ""
        start = time.time()
        for attempt in range(1, self._max_retries + 1):
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=self._timeout_seconds,
                )
            except subprocess.TimeoutExpired as e:
                last_err = f"timeout: {e}"
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 60.0)
                continue
            if proc.returncode != 0:
                last_err = (proc.stderr or proc.stdout or "").strip()[:300]
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 60.0)
                continue
            try:
                envelope = json.loads(proc.stdout)
            except json.JSONDecodeError as e:
                last_err = f"non-JSON stdout: {e}; head={proc.stdout[:200]!r}"
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 60.0)
                continue
            if envelope.get("is_error"):
                last_err = (envelope.get("result") or "")[:300]
                # Honor rate-limit framing
                if any(s in last_err.lower() for s in ("rate", "limit", "throttle")):
                    time.sleep(max(backoff, 15.0))
                    backoff = min(backoff * 2.0, 120.0)
                else:
                    time.sleep(backoff)
                    backoff = min(backoff * 2.0, 60.0)
                continue

            inner_text = envelope.get("result", "")
            # If caller wants JSON, try to unwrap a fenced block
            content = inner_text
            if response_format and response_format.get("type") == "json_object":
                m = _FENCED_JSON_RE.search(inner_text)
                if m:
                    content = m.group(1)

            # Pace next call
            time.sleep(self._sleep_seconds)

            usage = envelope.get("usage") or {}
            return {
                "choices": [{"message": {"content": content, "role": "assistant"}}],
                "usage": usage,
                "model": model or self._model,
                "_raw": envelope,
                "_duration_seconds": time.time() - start,
            }

        raise RuntimeError(
            f"ClaudeSonnetClient.chat failed after {self._max_retries} attempts: {last_err}"
        )

    # Optional context-manager support (no-op; kept for parity with httpx clients)
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def get_client(backbone: str):
    """Top-level factory."""
    if backbone in {"qwen", "deepseek", "gemma3"}:
        return get_vllm_client(backbone)
    if backbone in {"sonnet", "claude"}:
        return ClaudeSonnetClient()
    raise ValueError(f"unknown backbone: {backbone!r}")


# ── Default per-backbone model name (for the `model=` arg in .chat) ────────


def default_model(backbone: str) -> str:
    if backbone in BACKBONE_REGISTRY:
        return _resolve_model(backbone)
    if backbone in {"sonnet", "claude"}:
        return "sonnet"
    raise ValueError(f"unknown backbone: {backbone!r}")
