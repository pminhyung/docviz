"""
Role-Based Model Routing

Provides flexible model routing based on the role of the task.
API keys are passed directly by clients (NOT from environment variables).

Sandbox Mode:
    Set DOC_AGENT_V2_SANDBOX=1 to use stub responses instead of real API calls.
    This allows running the full pipeline without API keys.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List, Union
from pathlib import Path

import yaml

from agent.core.sandbox import is_sandbox_mode, SandboxProxyClient


# ── Tool Output Data Models ──────────────────────────────────

@dataclass
class ImageRef:
    """Reference to an image in tool output."""
    source: str          # "base64" | "path" | "url"
    data: str = ""       # base64 encoded data (when source=base64)
    path: str = ""       # file path (when source=path)
    url: str = ""        # image URL (when source=url)
    mime_type: str = "image/png"
    caption: str = ""


@dataclass
class ToolOutput:
    """Parsed tool output with optional images."""
    text: str
    images: List[ImageRef] = field(default_factory=list)
    has_images: bool = False


class ModelRole(Enum):
    """Roles for model routing"""
    REASONING = "reasoning"           # Main agent loop
    EXTRACTION = "extraction"         # Document/web extraction
    SUMMARIZATION = "summarization"   # Doc summary
    QUERY_GENERATION = "query_generation"  # Query generation


@dataclass
class ModelConfig:
    """Configuration for a single model"""
    model_id: str
    base_url: str
    max_tokens: int = 20480
    temperature: float = 0.2
    api_key: str = ""  # API key passed directly by client
    supports_vision: bool = False     # Image input support
    supports_tools: bool = False      # Function calling support
    use_max_completion_tokens: bool = False  # gpt-* LLM mode: use max_completion_tokens param

    def get_api_key(self) -> str:
        """Get the API key"""
        if not self.api_key:
            raise ValueError("API key not provided")
        return self.api_key


# Default model configurations (api_key must be provided at runtime)
DEFAULT_MODELS: Dict[str, ModelConfig] = {
    "qwen3": ModelConfig(
        model_id="qwen/qwen3-235b-a22b-instruct-2507",
        base_url="https://api.novita.ai/v3/openai",
        max_tokens=16384,
        temperature=0.2,
    ),
    "gemini": ModelConfig(
        model_id="gemini-2.5-pro",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        max_tokens=32768,
        temperature=0.2,
    ),
    "gpt4o": ModelConfig(
        model_id="gpt-4o",
        base_url="https://api.openai.com/v1",
        max_tokens=16384,
        temperature=0.7,
    ),
    "gpt5": ModelConfig(
        model_id="gpt-5.2",
        base_url="https://api.openai.com/v1",
        max_tokens=32768,
        temperature=0.2,
    ),
}


# Default routing (all to Qwen3)
DEFAULT_ROUTING: Dict[ModelRole, str] = {
    ModelRole.REASONING: "qwen3",
    ModelRole.EXTRACTION: "qwen3",
    ModelRole.SUMMARIZATION: "qwen3",
    ModelRole.QUERY_GENERATION: "qwen3",
}


class ProxyClient:
    """
    Proxy client that mimics the OpenAI client interface.

    This allows patching base.client_qwen with a custom client
    that routes to the appropriate model.
    """

    def __init__(
        self,
        model_config: ModelConfig,
        track_usage: bool = True
    ):
        """
        Initialize the proxy client.

        Args:
            model_config: The model configuration to use
            track_usage: Whether to track token usage
        """
        self.model_config = model_config
        self.track_usage = track_usage
        self._total_tokens = 0
        self._total_calls = 0

        # Initialize the actual OpenAI client
        import openai
        self._client = openai.OpenAI(
            api_key=model_config.get_api_key(),
            base_url=model_config.base_url,
        )

        # Create chat completions interface
        self.chat = _ChatCompletions(self)

    def _complete(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Any:
        """
        Make a completion request.

        Args:
            messages: The messages to send
            **kwargs: Additional arguments

        Returns:
            The completion response
        """
        # Merge with model defaults
        max_tok = kwargs.get("max_tokens", self.model_config.max_tokens)

        # gpt-* LLM mode requires max_completion_tokens instead of max_tokens
        tok_key = "max_completion_tokens" if self.model_config.use_max_completion_tokens else "max_tokens"

        params = {
            "model": self.model_config.model_id,
            "temperature": kwargs.get("temperature", self.model_config.temperature),
            tok_key: max_tok,
            "messages": messages,
        }

        # Remove our custom params before passing to API
        for key in ["temperature", "max_tokens", "messages"]:
            kwargs.pop(key, None)

        # Add any remaining kwargs
        params.update(kwargs)

        response = self._client.chat.completions.create(**params)

        # Track usage
        if self.track_usage and hasattr(response, "usage") and response.usage:
            self._total_tokens += response.usage.total_tokens
            self._total_calls += 1

        return response

    @property
    def total_tokens(self) -> int:
        """Get total tokens used"""
        return self._total_tokens

    @property
    def total_calls(self) -> int:
        """Get total API calls made"""
        return self._total_calls

    def reset_tracking(self) -> None:
        """Reset usage tracking"""
        self._total_tokens = 0
        self._total_calls = 0


class _ChatCompletions:
    """Chat completions interface wrapper"""

    def __init__(self, proxy: ProxyClient):
        self._proxy = proxy
        self.completions = self

    def create(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Any:
        """Create a chat completion"""
        return self._proxy._complete(messages, **kwargs)


class ModelRouter:
    """
    Routes model requests based on role.

    Usage:
        router = ModelRouter()
        router.load_config("model_config.yaml")
        client = router.get_proxy_client(ModelRole.REASONING)
    """

    def __init__(self):
        """Initialize the router with defaults"""
        self.models: Dict[str, ModelConfig] = DEFAULT_MODELS.copy()
        self.routing: Dict[ModelRole, str] = DEFAULT_ROUTING.copy()
        self._clients: Dict[str, ProxyClient] = {}

    def load_config(self, config_file: str) -> None:
        """
        Load configuration from a YAML file.

        Args:
            config_file: Path to the YAML config file
        """
        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Load model configs (api_key must be provided at runtime)
        if "models" in config:
            for name, model_config in config["models"].items():
                self.models[name] = ModelConfig(
                    model_id=model_config.get("model_id", ""),
                    base_url=model_config.get("base_url", ""),
                    max_tokens=model_config.get("max_tokens", 20480),
                    temperature=model_config.get("temperature", 0.2),
                )

        # Load routing config
        if "routing" in config:
            for role_name, model_name in config["routing"].items():
                try:
                    role = ModelRole(role_name)
                    if model_name in self.models:
                        self.routing[role] = model_name
                except ValueError:
                    pass  # Ignore unknown roles

        # Clear cached clients when config changes
        self._clients.clear()

    def get_model_for_role(self, role: ModelRole) -> ModelConfig:
        """
        Get the model configuration for a role.

        Args:
            role: The model role

        Returns:
            The model configuration
        """
        model_name = self.routing.get(role, "qwen3")
        if model_name not in self.models:
            raise ValueError(
                f"Model '{model_name}' not found for role '{role.value}'"
            )
        return self.models[model_name]

    def get_proxy_client(self, role: ModelRole) -> Union[ProxyClient, SandboxProxyClient]:
        """
        Get a proxy client for a role.

        In sandbox mode, returns a SandboxProxyClient that provides
        deterministic stub responses without external API calls.

        Args:
            role: The model role

        Returns:
            A ProxyClient (or SandboxProxyClient in sandbox mode)
        """
        # Check for sandbox mode
        if is_sandbox_mode():
            if "sandbox" not in self._clients:
                self._clients["sandbox"] = SandboxProxyClient()
            return self._clients["sandbox"]

        model_name = self.routing.get(role, "qwen3")

        if model_name not in self._clients:
            model_config = self.get_model_for_role(role)
            self._clients[model_name] = ProxyClient(model_config)

        return self._clients[model_name]

    def get_all_usage(self) -> Dict[str, Dict[str, int]]:
        """
        Get usage statistics for all clients.

        Returns:
            Dictionary of model_name -> {tokens, calls}
        """
        return {
            name: {
                "tokens": client.total_tokens,
                "calls": client.total_calls,
            }
            for name, client in self._clients.items()
        }

    def reset_all_tracking(self) -> None:
        """Reset usage tracking for all clients"""
        for client in self._clients.values():
            client.reset_tracking()

    def _resolve_base_url(
        self,
        model_name: str,
        base_url: Optional[str] = None,
    ) -> str:
        """Provider auto-detection (with override).

        Args:
            model_name: Model identifier
            base_url: Explicit override (highest priority)

        Returns:
            Resolved base URL
        """
        if base_url:
            return base_url
        if model_name == "qwen_onpremise":
            host = os.environ.get("QWEN_ONPREMISE_HOST", "10.1.17.178")
            port = os.environ.get("QWEN_ONPREMISE_PORT", "8000")
            return f"http://{host}:{port}/v1"
        if model_name.startswith("gpt-"):
            return "https://api.openai.com/v1"
        if "local/" in model_name:
            return os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
        return "https://api.novita.ai/v3/openai"

    @staticmethod
    def _resolve_max_tokens(model_name: str, is_local: bool) -> int:
        """Return max_tokens appropriate for the provider/model."""
        if model_name == "qwen_onpremise":
            return 131072
        if is_local:
            return 20480
        if model_name.startswith("gpt-5"):
            return 32768
        # Novita qwen, gpt-4o, and most hosted models cap at 16384
        return 16384

    def create_reasoning_client(
        self,
        reasoner_type: str = "llm",
        model_name: Optional[str] = None,
        api_key: str = "",
        base_url: Optional[str] = None,
        max_length: Optional[int] = None,
        extraction_api_key: Optional[str] = None,
    ) -> Union[ProxyClient, SandboxProxyClient]:
        """
        Create a reasoning client based on reasoner type and model name.

        Args:
            reasoner_type: "llm" for text-only, "vl" for vision-language
            model_name: Specific model name. If None, uses default for the type.
                       Prefix "gpt-" uses OpenAI API, "local/" uses vLLM, otherwise Novita API.
            api_key: API key for the model (required, except in sandbox and local modes)
            base_url: Explicit base URL override (highest priority)
            max_length: Override max output tokens. None uses model/provider default.
            extraction_api_key: Separate API key for extraction/builtin models.
                               When reasoner and extraction use different providers
                               (e.g., GPT reasoner + Novita extraction), set this to the
                               extraction provider's key. If None, falls back to api_key.

        Returns:
            ProxyClient configured for the specified model

        Default models:
            - llm: gpt-5.2 (OpenAI)
            - vl: qwen/qwen2.5-vl-72b-instruct (Novita)
        """
        # Check for sandbox mode
        if is_sandbox_mode():
            if "sandbox" not in self._clients:
                self._clients["sandbox"] = SandboxProxyClient()
            return self._clients["sandbox"]

        # Determine model name if not specified
        if model_name is None:
            if reasoner_type == "vl":
                model_name = "qwen/qwen2.5-vl-72b-instruct"
            else:
                model_name = "gpt-5.2"

        # API key: required for non-local / non-onpremise models
        is_local = "local/" in model_name
        is_onpremise = model_name == "qwen_onpremise"
        if not api_key and not is_local and not is_onpremise:
            raise ValueError(
                "API key is required. Pass 'reasoner_api_key' in the request."
            )
        if (is_local or is_onpremise) and not api_key:
            api_key = "EMPTY"

        # Resolve base URL
        resolved_url = self._resolve_base_url(model_name, base_url)

        # Create cache key (include api_key hash for multi-tenant support)
        cache_key = f"reasoning_{reasoner_type}_{model_name}_{hash(api_key) % 100000}"

        if cache_key not in self._clients:
            is_vl = reasoner_type == "vl"
            is_gpt = model_name.startswith("gpt-")
            # Resolve max_tokens: explicit override > per-provider default
            max_tok = max_length if max_length else self._resolve_max_tokens(model_name, is_local)
            # Resolve model_id: local/ prefix strip, onpremise env var
            if is_local:
                resolved_model_id = model_name.replace("local/", "")
            elif is_onpremise:
                resolved_model_id = os.environ.get("QWEN_ONPREMISE_MODEL", "Qwen3.5-397B-A17B-FP8")
            else:
                resolved_model_id = model_name
            config = ModelConfig(
                model_id=resolved_model_id,
                base_url=resolved_url,
                max_tokens=max_tok,
                temperature=0.2,
                api_key=api_key,
                supports_vision=is_vl,
                use_max_completion_tokens=(is_gpt and not is_vl),
            )

            self._clients[cache_key] = ProxyClient(config)

        # Store current reasoning info for VL fallback
        self._current_reasoning_type = reasoner_type
        self._current_api_key = api_key

        # Propagate API key to default model configs so get_proxy_client
        # (used by call_llm in ToolContext) can also create valid clients.
        # When reasoner and extraction use different providers, use the
        # extraction_api_key for models on a different base_url.
        for cfg in self.models.values():
            if not cfg.api_key:
                if extraction_api_key and cfg.base_url and cfg.base_url != resolved_url:
                    cfg.api_key = extraction_api_key
                else:
                    cfg.api_key = api_key

        return self._clients[cache_key]

    def get_proxy_client_for_vl(self) -> Union[ProxyClient, SandboxProxyClient]:
        """Get a VL-capable client for image input.

        If current reasoning client supports vision, returns it.
        Otherwise creates a VL-specific client.
        """
        if is_sandbox_mode():
            if "sandbox" not in self._clients:
                self._clients["sandbox"] = SandboxProxyClient()
            return self._clients["sandbox"]

        # Check if current reasoning client supports vision
        current_type = getattr(self, "_current_reasoning_type", "llm")
        if current_type == "vl":
            # Already a VL client, find and return it
            for key, client in self._clients.items():
                if key.startswith("reasoning_vl_"):
                    return client

        # Create a VL client
        api_key = getattr(self, "_current_api_key", "")
        return self.create_reasoning_client(
            reasoner_type="vl",
            api_key=api_key,
        )
