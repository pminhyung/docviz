"""
Exaone harness configuration — env vars, repo-local paths, gateway/agent defaults.

Load order (typical):
  1. ``bootstrap()`` or ``apply_project_path_defaults()`` after ``HERMES_EXAONE_AGENT=1``
  2. ``load_config()`` for a snapshot of settings
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAONE_REPO_ROOT = REPO_ROOT  # backward-compatible alias

_TRUTHY = frozenset({"1", "true", "yes"})
logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://10.1.211.148:8000/v1"
_DEFAULT_MODEL = "Qwen"
_DEFAULT_API_KEY = "EMPTY"
_SAFE_CHAT_COMPLETIONS_OVERRIDE_KEYS = frozenset(
    {
        "temperature",
        "top_p",
        "seed",
        "stream",
        "presence_penalty",
        "frequency_penalty",
        "logprobs",
        "top_logprobs",
        "response_format",
        "parallel_tool_calls",
        "tool_choice",
        "user",
        "stop",
        "n",
    }
)


def is_exaone_agent_enabled() -> bool:
    return os.getenv("HERMES_EXAONE_AGENT", "").lower() in _TRUTHY


def project_hermes_home() -> Path:
    return REPO_ROOT / ".hermes"


def project_trace_dir() -> Path:
    return REPO_ROOT / "logs" / "exaone_traces"


def apply_project_path_defaults() -> None:
    """Set HERMES_HOME and EXAONE_TRACE_DIR under the repo when Exaone mode is on."""
    if not is_exaone_agent_enabled():
        return
    # In Exaone harness mode, always pin state to the repo-local .hermes so
    # gateway/tool config is deterministic for this workspace.
    os.environ["HERMES_HOME"] = str(project_hermes_home())
    os.environ["EXAONE_TRACE_DIR"] = str(project_trace_dir())


def _load_vllm_params_from_env() -> dict[str, Any]:
    """Load default vLLM call params from env JSON.

    Supported env names (first non-empty wins):
      1) VLLM_PARAMS_K_EXAONE
      2) EXAONE_VLLM_PARAMS
    """
    raw = (
        os.getenv("VLLM_PARAMS_K_EXAONE", "").strip()
        or os.getenv("EXAONE_VLLM_PARAMS", "").strip()
    )
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in VLLM_PARAMS_K_EXAONE/EXAONE_VLLM_PARAMS; ignoring")
        return {}
    if not isinstance(parsed, dict):
        logger.warning("VLLM params env must be a JSON object; ignoring")
        return {}
    return parsed


# Vendor-recommended thinking-mode sampling, sourced from each model
# team's official guidance (verified in docviz/code/adapters/agent_client.py
# for Qwen3.5). Auto-merged at agent-init time by family-prefix match on
# the model id, underneath any explicit EXAONE_VLLM_PARAMS / constructor
# kwargs. Toggle off with EXAONE_AUTO_SAMPLING=0.
_VENDOR_THINKING_SAMPLING: dict[str, dict[str, Any]] = {
    "qwen": {
        "temperature": 0.6,
        "top_p": 0.95,
        "extra_body": {"top_k": 20, "min_p": 0},
    },
}


def _vendor_sampling_for_model(model: str) -> dict[str, Any]:
    """Return a copy of the vendor preset for ``model``'s family, or {}.

    Family is matched by case-insensitive prefix on the model id, so e.g.
    ``Qwen3.5-397B-A17B-FP8`` resolves to the ``qwen`` preset. extra_body
    is deep-copied so callers can mutate safely.
    """
    if not model:
        return {}
    m = model.lower()
    for family, preset in _VENDOR_THINKING_SAMPLING.items():
        if m.startswith(family):
            out = {k: v for k, v in preset.items() if k != "extra_body"}
            eb = preset.get("extra_body")
            if isinstance(eb, dict):
                out["extra_body"] = dict(eb)
            return out
    return {}


def _auto_sampling_enabled() -> bool:
    """``EXAONE_AUTO_SAMPLING`` gate. Default ON; set to "0" to disable."""
    return os.getenv("EXAONE_AUTO_SAMPLING", "1").strip().lower() in _TRUTHY


def _normalize_env_request_overrides(env_params: dict[str, Any]) -> dict[str, Any]:
    """Normalize env vLLM params into safe request_overrides.

    Unknown top-level keys are routed into extra_body so OpenAI SDK does not
    reject them as unexpected kwargs.
    """
    overrides: dict[str, Any] = {}
    extra_body: dict[str, Any] = {}
    for key, value in env_params.items():
        if key == "extra_body" and isinstance(value, dict):
            extra_body.update(value)
            continue
        if key in _SAFE_CHAT_COMPLETIONS_OVERRIDE_KEYS:
            overrides[key] = value
            continue
        extra_body[key] = value
    if extra_body:
        overrides["extra_body"] = extra_body
    return overrides


@dataclass(frozen=True)
class ExaoneConfig:
    enabled: bool
    hermes_home: Path
    trace_dir: Path
    base_url: str
    model: str
    api_key: str
    provider: str = "custom"
    api_mode: str = "chat_completions"
    save_raw_trace: bool = True
    save_trajectory: bool = True
    vllm_params: dict[str, Any] | None = None

    @classmethod
    def from_env(cls) -> ExaoneConfig:
        apply_project_path_defaults()
        trace = os.getenv("EXAONE_TRACE_DIR")
        return cls(
            enabled=is_exaone_agent_enabled(),
            hermes_home=Path(os.getenv("HERMES_HOME", str(project_hermes_home()))),
            trace_dir=Path(trace) if trace else project_trace_dir(),
            base_url=os.getenv("EXAONE_BASE_URL", _DEFAULT_BASE_URL),
            model=os.getenv("EXAONE_MODEL", _DEFAULT_MODEL),
            api_key=os.getenv("EXAONE_API_KEY", _DEFAULT_API_KEY),
            save_raw_trace=os.getenv("EXAONE_SAVE_RAW_TRACE", "1").lower() not in ("0", "false", "no"),
            save_trajectory=os.getenv("EXAONE_SAVE_TRAJECTORY", "1").lower() not in ("0", "false", "no"),
            vllm_params=_load_vllm_params_from_env(),
        )

    def trace_dir_resolved(self, override: str | Path | None = None) -> Path:
        if override is not None:
            return Path(override)
        return self.trace_dir

    def apply_agent_kwargs(self, kwargs: dict) -> dict:
        """Fill vLLM defaults on ExaoneAgent constructor kwargs (does not mutate input)."""
        out = dict(kwargs)
        out.setdefault("base_url", self.base_url)
        out.setdefault("model", self.model)
        out.setdefault("api_key", self.api_key)
        out.setdefault("api_mode", self.api_mode)
        out.setdefault("provider", self.provider)

        env_params = dict(self.vllm_params or {})
        if env_params:
            env_max_tokens = env_params.pop("max_tokens", None)
            if env_max_tokens is not None and ("max_tokens" not in out or out.get("max_tokens") is None):
                try:
                    parsed_max_tokens = int(env_max_tokens)
                    if parsed_max_tokens > 0:
                        out["max_tokens"] = parsed_max_tokens
                except (TypeError, ValueError):
                    logger.warning("Invalid max_tokens in VLLM params env; ignoring")

            env_overrides = _normalize_env_request_overrides(env_params)
            if env_overrides:
                existing_overrides = out.get("request_overrides")
                if not isinstance(existing_overrides, dict):
                    existing_overrides = {}
                # Env provides defaults; explicit request/constructor overrides win.
                merged_overrides = dict(env_overrides)
                env_extra_body = merged_overrides.get("extra_body")
                existing_extra_body = existing_overrides.get("extra_body")
                if isinstance(env_extra_body, dict) and isinstance(existing_extra_body, dict):
                    merged_extra_body = dict(env_extra_body)
                    merged_extra_body.update(existing_extra_body)
                    merged_overrides["extra_body"] = merged_extra_body
                merged_overrides.update({k: v for k, v in existing_overrides.items() if k != "extra_body"})
                out["request_overrides"] = merged_overrides

        # Vendor preset merge — sits underneath everything above so explicit
        # EXAONE_VLLM_PARAMS / constructor kwargs always win. Family is
        # detected from the (post-resolution) model id, so each batch_runner
        # worker auto-picks the right preset for the host it was bound to.
        if _auto_sampling_enabled():
            vendor = _vendor_sampling_for_model(out.get("model") or "")
            if vendor:
                vendor_overrides = _normalize_env_request_overrides(vendor)
                existing = out.get("request_overrides")
                if not isinstance(existing, dict):
                    existing = {}
                for k, v in vendor_overrides.items():
                    if k == "extra_body" and isinstance(v, dict):
                        existing_eb = existing.get("extra_body") or {}
                        merged_eb = dict(v)
                        if isinstance(existing_eb, dict):
                            merged_eb.update(existing_eb)
                        existing["extra_body"] = merged_eb
                    elif k not in existing:
                        existing[k] = v
                out["request_overrides"] = existing
        return out

    def runtime_kwargs(self) -> dict:
        """Kwargs for gateway ``resolve_runtime_provider`` bypass."""
        return {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "provider": self.provider,
            "api_mode": self.api_mode,
            "command": None,
            "args": [],
            "credential_pool": None,
        }


@lru_cache(maxsize=1)
def load_config() -> ExaoneConfig:
    return ExaoneConfig.from_env()


def resolve_exaone_runtime_kwargs() -> dict:
    return load_config().runtime_kwargs()


def resolve_exaone_model() -> str:
    return load_config().model


def bootstrap_gateway_env(*, load_dotenv: bool = True) -> Path:
    """Enable Exaone mode, apply path defaults, optionally load repo ``.env``."""
    os.environ.setdefault("HERMES_EXAONE_AGENT", "1")
    os.environ.setdefault("API_SERVER_ENABLED", "1")
    apply_project_path_defaults()
    if load_dotenv:
        from hermes_cli.env_loader import load_hermes_dotenv

        load_hermes_dotenv(project_env=REPO_ROOT / ".env")
        apply_project_path_defaults()
        load_config.cache_clear()
    return REPO_ROOT


def serve() -> int:
    """Start Exaone gateway (API :8642). Use: python exaone/serve.py"""
    import asyncio
    import sys

    root = bootstrap_gateway_env()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from gateway.run import start_gateway

    return 0 if asyncio.run(start_gateway()) else 1
