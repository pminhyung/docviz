"""Unified LLM client for VisuBench pipeline.

Supports:
- LLMPool (Qwen3.5-397B on-premise, existing infrastructure)
- vLLM local servers (Qwen9B, InternVL3) via OpenAI-compat API
- External APIs (OpenAI, Anthropic, Google) — disabled until user enables

All clients expose a common call interface.
"""
import asyncio
import json
import os
import time
from typing import Optional

import openai


def get_llmpool_client():
    """Get OpenAI-compat client for on-premise Qwen3.5-397B vLLM servers.

    Uses round-robin but ONLY adds endpoints that actually serve the Qwen3.5-
    397B model AND respond quickly. Remote hosts are sometimes swapped to
    other models (observed 2026-04-09: 169/170 flipped to glm-4.7-fp8) and
    local 9200/9201 may be saturated by another user — in both cases we
    skip the endpoint to avoid worker wedging.

    Env override: QWEN_POOL_HOSTS="148,9201" to force a specific subset.
    """
    import os as _os
    QWEN_MODEL = "Qwen3.5-397B-A17B-FP8"
    all_candidates = [
        ("http://10.1.211.148:8000/v1", "148"),
        ("http://10.1.211.169:8000/v1", "169"),
        ("http://10.1.211.170:8000/v1", "170"),
        ("http://localhost:9200/v1", "9200"),
        ("http://localhost:9201/v1", "9201"),
    ]
    env = _os.environ.get("QWEN_POOL_HOSTS", "").strip()
    if env:
        wanted = {h.strip() for h in env.split(",") if h.strip()}
        candidates = [c for c in all_candidates if c[1] in wanted]
    else:
        candidates = all_candidates

    import json as _json
    import urllib.request
    clients = []
    for base, label in candidates:
        try:
            resp = urllib.request.urlopen(f"{base}/models", timeout=2)
            payload = _json.loads(resp.read().decode("utf-8", errors="replace"))
            ids = [m.get("id", "") for m in payload.get("data", [])]
            if QWEN_MODEL in ids:
                # 120s timeout for VLM image inference (large mindmap PNGs)
                clients.append(
                    openai.OpenAI(base_url=base, api_key="EMPTY", timeout=120.0)
                )
                print(f"[llm_clients] endpoint {label} (serving Qwen3.5-397B) added")
            else:
                print(f"[llm_clients] endpoint {label} SKIPPED — serves {ids}")
        except Exception as e:
            print(f"[llm_clients] endpoint {label} unreachable ({type(e).__name__})")
    if not clients:
        raise RuntimeError(
            "No Qwen3.5-397B endpoints available. "
            "Check remote hosts and local 9200/9201."
        )
    return _RoundRobinClient(clients, QWEN_MODEL)


class _RoundRobinClient:
    """Simple round-robin wrapper over multiple OpenAI clients."""

    def __init__(self, clients: list, model: str):
        self.clients = clients
        self.model = model
        self._idx = 0

    def next_client(self) -> openai.OpenAI:
        client = self.clients[self._idx % len(self.clients)]
        self._idx += 1
        return client


def get_vllm_client(endpoint: str) -> openai.OpenAI:
    """Get OpenAI-compat client for local vLLM server."""
    return openai.OpenAI(base_url=endpoint, api_key="EMPTY")


def get_openai_client() -> openai.OpenAI:
    """Get OpenAI API client."""
    return openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


def call_llmpool(pool: _RoundRobinClient, system_prompt: str, user_content: str,
                  temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
    """Call Qwen3.5-397B via round-robin vLLM hosts. Returns generated text.

    max_tokens is accepted for backward compatibility but intentionally NOT
    forwarded to the server — local vLLM must use its max_model_len default
    to avoid silent truncation.
    """
    client = pool.next_client()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    # Retry with next host on failure
    last_error = None
    for attempt in range(len(pool.clients)):
        try:
            resp = client.chat.completions.create(
                model=pool.model,
                messages=messages,
                temperature=temperature,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            content = resp.choices[0].message.content
            # Strip <think>...</think> blocks if present
            import re
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            return content
        except Exception as e:
            last_error = e
            client = pool.next_client()

    raise last_error


def call_openai_compat(client: openai.OpenAI, model: str,
                        system_prompt: str, user_content: str,
                        temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
    """Call via OpenAI-compatible API (local vLLM).

    max_tokens is accepted but NOT forwarded — use server default to avoid
    truncation.
    """
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=temperature,
    )
    return resp.choices[0].message.content


def call_model(model_id: str, system_prompt: str, user_content: str,
               temperature: float = 0.2, max_tokens: Optional[int] = None,
               _clients: dict = {}) -> str:
    """Unified call interface. Caches clients.

    Args:
        model_id: Key from scripts.config.MODEL_CONFIGS
        system_prompt: System message
        user_content: User message
    Returns:
        Generated text
    """
    from scripts.config import MODEL_CONFIGS

    config = MODEL_CONFIGS[model_id]
    model_type = config["type"]

    if model_type == "llmpool":
        if "llmpool" not in _clients:
            _clients["llmpool"] = get_llmpool_client()
        return call_llmpool(_clients["llmpool"], system_prompt, user_content,
                            temperature, max_tokens)

    elif model_type == "vllm":
        key = f"vllm_{model_id}"
        if key not in _clients:
            _clients[key] = get_vllm_client(config["endpoint"])
        return call_openai_compat(_clients[key], config["model"],
                                   system_prompt, user_content,
                                   temperature, max_tokens)

    elif model_type == "vllm_multi":
        # Round-robin over the list of local ports. Hosts launched externally
        # by scripts/viz/start_vllm_model.sh (D14). Each port serves the same
        # model. First-call probe: only keep reachable ports.
        key = f"vllm_multi_{model_id}"
        if key not in _clients:
            import urllib.request
            ports = config.get("ports", [])
            live_clients = []
            for p in ports:
                url = f"http://localhost:{p}/v1"
                try:
                    urllib.request.urlopen(f"{url}/models", timeout=2)
                    live_clients.append(openai.OpenAI(base_url=url, api_key="EMPTY"))
                except Exception:
                    pass
            if not live_clients:
                raise RuntimeError(
                    f"No reachable vllm_multi ports for {model_id}: {ports}")
            _clients[key] = _RoundRobinClient(live_clients, config["model"])
        pool = _clients[key]
        extra = {}
        if config.get("thinking_toggle") is False:
            extra = {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
        client = pool.next_client()
        last_err = None
        for _ in range(len(pool.clients)):
            try:
                resp = client.chat.completions.create(
                    model=pool.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=temperature,
                    **extra,
                )
                msg = resp.choices[0].message
                content = msg.content
                if content is None:
                    # Reasoning models (gpt-oss-20b etc.) return the answer
                    # in reasoning_content while setting content=None.
                    content = (getattr(msg, "reasoning_content", None)
                               or getattr(msg, "thinking", None)
                               or "")
                import re
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                return content
            except Exception as e:
                last_err = e
                client = pool.next_client()
        raise last_err

    elif model_type == "openai":
        if "openai" not in _clients:
            _clients["openai"] = get_openai_client()
        return call_openai_compat(_clients["openai"], config["model"],
                                   system_prompt, user_content,
                                   temperature, max_tokens)

    else:
        raise ValueError(f"Unsupported model type: {model_type} for {model_id}")


def call_model_with_image(model_id: str, system_prompt: str,
                          user_text: str, image_base64: str,
                          temperature: float = 0.1, max_tokens: Optional[int] = None,
                          _clients: dict = {}) -> str:
    """Call a VLM with text + image via OpenAI vision API format.

    Args:
        model_id: Key from MODEL_CONFIGS (only llmpool supported for now)
        system_prompt: System message (can be empty string)
        user_text: Text portion of user message
        image_base64: Base64-encoded PNG image
    Returns:
        Generated text
    """
    from scripts.config import MODEL_CONFIGS

    config = MODEL_CONFIGS[model_id]
    model_type = config["type"]

    if model_type != "llmpool":
        raise ValueError(f"call_model_with_image only supports llmpool, got {model_type}")

    if "llmpool" not in _clients:
        _clients["llmpool"] = get_llmpool_client()

    pool = _clients["llmpool"]
    client = pool.next_client()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # Multimodal user message: text + image
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {
                "url": f"data:image/png;base64,{image_base64}",
            }},
        ],
    })

    # Retry with next host on failure
    import re
    last_error = None
    for attempt in range(len(pool.clients)):
        try:
            resp = client.chat.completions.create(
                model=pool.model,
                messages=messages,
                temperature=temperature,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            content = resp.choices[0].message.content
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            return content
        except Exception as e:
            last_error = e
            client = pool.next_client()

    raise last_error


async def call_model_async(model_id: str, system_prompt: str, user_content: str,
                            temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
    """Async wrapper around sync call_model (runs in thread pool)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, call_model, model_id, system_prompt, user_content,
        temperature, max_tokens
    )
