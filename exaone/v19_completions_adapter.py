"""V19 chat-template adapter — local render + /v1/completions backend.

Background
----------
The Qwen3 chat_template loaded on our vLLM hosts injects an empty
`<think>\\n\\n</think>` block for every PAST assistant turn while
silently dropping the `reasoning_content` field carried on those
turns. This conditions the model to mimic the empty-think pattern on
subsequent turns and causes thinking to disappear from late tool-call
turns and the final synthesis. froggeric's "Qwen-Fixed-Chat-Templates"
v19 fixes this by preserving past `<think>real_text</think>` blocks
chronologically; that template is shipped under
``configs/chat_templates/qwen3_fixed_v19.jinja``.

The vLLM server rejects per-request ``chat_template`` overrides
("--trust-request-chat-template not set"), so the only way to apply
v19 without restarting the server is:

  1. Render the wire prompt locally via the v19 jinja template.
  2. POST the rendered prompt to ``/v1/completions``.
  3. Re-shape the raw completion text into an OpenAI ChatCompletion
     so upstream Hermes code reads it the same as if it had been
     produced by ``/v1/chat/completions``.

This module provides that pipeline. ``wrap_client(client)`` returns a
shim whose ``chat.completions.create()`` behaves exactly like the
original for non-Qwen / opted-out paths and routes to our local
render + ``/v1/completions`` path for Qwen models. The decision is
explicit, model-prefix based, and gated by ``EXAONE_V19_ADAPTER`` env
(default ON).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from jinja2.sandbox import ImmutableSandboxedEnvironment

logger = logging.getLogger(__name__)

# Resolve the v19 template once at import time. Path is relative to the
# repo root so the resolution survives running from worktrees/subdirs.
_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "configs" / "chat_templates" / "qwen3_fixed_v19.jinja"
)


def _build_jinja_env() -> ImmutableSandboxedEnvironment:
    env = ImmutableSandboxedEnvironment(
        trim_blocks=True, lstrip_blocks=True,
        extensions=["jinja2.ext.loopcontrols"],
    )
    def _raise(msg: str):
        raise RuntimeError(msg)
    env.globals["raise_exception"] = _raise
    env.globals["strftime_now"] = lambda fmt: time.strftime(fmt)
    return env


_ENV = _build_jinja_env()
_TEMPLATE = None


def _load_template():
    global _TEMPLATE
    if _TEMPLATE is None:
        if not _TEMPLATE_PATH.exists():
            raise FileNotFoundError(f"v19 template not found: {_TEMPLATE_PATH}")
        _TEMPLATE = _ENV.from_string(_TEMPLATE_PATH.read_text())
    return _TEMPLATE


def _normalize_messages_for_template(messages: list[dict]) -> list[dict]:
    """Coerce assistant tool_calls[].function.arguments to dict for v19 render.

    The OpenAI API uses JSON-string arguments; v19's template iterates them
    as a mapping and needs dict shape. Reasoning fields are passed through.
    """
    out = []
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            mm = dict(m)
            tcs = mm.get("tool_calls") or []
            if tcs:
                mm["tool_calls"] = []
                for tc in tcs:
                    if hasattr(tc, "model_dump"):
                        tc = tc.model_dump()
                    elif hasattr(tc, "__dict__"):
                        tc = {k: getattr(tc, k) for k in ("id", "type", "function")}
                    fn = (tc.get("function") if isinstance(tc, dict) else None) or {}
                    args = fn.get("arguments") if isinstance(fn, dict) else None
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    mm["tool_calls"].append({
                        "id": (tc.get("id") if isinstance(tc, dict) else "") or "",
                        "type": (tc.get("type") if isinstance(tc, dict) else "function") or "function",
                        "function": {
                            "name": (fn.get("name") if isinstance(fn, dict) else "") or "",
                            "arguments": args if isinstance(args, dict) else {},
                        },
                    })
            # Ensure content is a string (template iterates content as iterable
            # for vision parts; plain string short-circuits to verbatim render).
            if mm.get("content") is None:
                mm["content"] = ""
            out.append(mm)
        else:
            out.append(m)
    return out


def render_prompt(
    *, messages: list[dict], tools: list[dict] | None,
    enable_thinking: bool = True, preserve_thinking: bool = True,
) -> str:
    """Render messages+tools to a Qwen3 wire prompt using v19."""
    tmpl = _load_template()
    msgs = _normalize_messages_for_template(messages)
    return tmpl.render(
        messages=msgs,
        tools=tools or [],
        add_generation_prompt=True,
        enable_thinking=enable_thinking,
        preserve_thinking=preserve_thinking,
    )


# ── completion-text → ChatCompletion shape ──────────────────────────────────

_THINK_END = "</think>"
_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<function=([^>]+)>(.*?)</function>\s*</tool_call>",
    re.DOTALL,
)
_PARAM_RE = re.compile(r"<parameter=([^>]+)>(.*?)</parameter>", re.DOTALL)


def _parse_completion_text(text: str) -> tuple[str, str, list[dict]]:
    """Split into (reasoning, content, tool_calls).

    v19 + add_generation_prompt=True opens a `<think>\\n` at the assistant
    prefix. The model continues inside `<think>` and emits `</think>` to
    close, then either tool_calls (`<tool_call>...</tool_call>`) or final
    answer prose. We split on the FIRST `</think>` and treat the head as
    reasoning. Tool calls are decoded from the XML form Qwen3-Coder uses.
    """
    if _THINK_END in text:
        reasoning, rest = text.split(_THINK_END, 1)
    else:
        reasoning, rest = "", text
    tcs: list[dict] = []
    for m in _TOOL_CALL_RE.finditer(rest):
        fn_name = m.group(1).strip()
        body = m.group(2)
        args: dict[str, Any] = {}
        for pm in _PARAM_RE.finditer(body):
            key = pm.group(1).strip()
            raw = pm.group(2).strip()
            # Prefer JSON parse so list/dict/number args survive. Fall back
            # to literal string when the parameter wasn't JSON-encoded.
            try:
                args[key] = json.loads(raw)
            except Exception:
                args[key] = raw
        tcs.append({"name": fn_name, "arguments": args})
    # Content = post-think text minus the tool_call XML blocks
    content = _TOOL_CALL_RE.sub("", rest).strip()
    return reasoning.strip("\n"), content, tcs


def _make_chat_completion(
    *, model: str, reasoning: str, content: str, tool_calls: list[dict],
    finish_reason: str, prompt_tokens: int | None, completion_tokens: int | None,
) -> Any:
    """Build a ChatCompletion-shaped SimpleNamespace.

    Upstream Hermes reads `.choices[0].message` with attribute access for
    content/tool_calls/reasoning_content. SimpleNamespace satisfies both
    attribute and getattr(default=None) idioms used at run_agent.py:9015-9066.
    For `model_extra`-style fallbacks the SDK uses, expose an empty dict so
    `_copy_reasoning_content_for_api`'s nested check is safe.
    """
    # Map our tool_calls to the OpenAI shape. Generate a stable-looking id
    # so the agent's later message bookkeeping has something to alias.
    api_tool_calls: list[Any] = []
    for tc in tool_calls:
        api_tool_calls.append(SimpleNamespace(
            id="chatcmpl-tool-" + uuid.uuid4().hex[:16],
            type="function",
            function=SimpleNamespace(
                name=tc["name"],
                # OpenAI passes arguments as JSON string on the wire
                arguments=json.dumps(tc["arguments"], ensure_ascii=False),
            ),
        ))
    # Choose finish_reason. If tool_calls present and parent told us "stop"
    # because we matched <|im_end|>, label it "tool_calls" so upstream's
    # tool dispatcher fires correctly.
    if api_tool_calls and finish_reason in ("stop", None):
        finish_reason = "tool_calls"

    msg = SimpleNamespace(
        role="assistant",
        content=content if content else None,
        tool_calls=api_tool_calls or None,
        # Surface reasoning under both attribute names. Upstream reads either
        # at run_agent.py:3351 (reasoning) and :9022 (reasoning_content).
        reasoning=reasoning or None,
        reasoning_content=reasoning or None,
        reasoning_details=None,
        codex_reasoning_items=None,
        # Empty model_extra dict — upstream checks hasattr + falls back to {}
        model_extra={"reasoning_content": reasoning} if reasoning else {},
    )
    choice = SimpleNamespace(
        index=0,
        message=msg,
        finish_reason=finish_reason or "stop",
    )
    return SimpleNamespace(
        id="chatcmpl-" + uuid.uuid4().hex[:16],
        object="chat.completion",
        created=int(time.time()),
        model=model,
        choices=[choice],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
            total_tokens=(prompt_tokens or 0) + (completion_tokens or 0),
            prompt_tokens_details=None,
        ),
        service_tier=None,
        system_fingerprint=None,
    )


# ── completions HTTP call ───────────────────────────────────────────────────

def _completions_call(
    *, base_url: str, api_key: str, model: str, prompt: str,
    max_tokens: int | None, temperature: float | None, top_p: float | None,
    extra_body: dict | None, timeout: float | None,
) -> dict:
    """POST /v1/completions with the rendered prompt. Returns response JSON."""
    import httpx
    eb = dict(extra_body or {})
    # chat_template_kwargs is meaningless on /v1/completions (no template)
    eb.pop("chat_template_kwargs", None)
    # vLLM /v1/completions defaults max_tokens=16 when omitted, which
    # truncates mid-thinking. Default to a large cap so the model can
    # finish <think>...</think> + content / tool_call XML. EXAONE_V19_MAX_TOKENS
    # lets the caller override this floor (e.g., for very short answers).
    if max_tokens is None:
        max_tokens = int(os.getenv("EXAONE_V19_MAX_TOKENS", "8192"))
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stop": ["<|im_end|>"],
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    # vLLM accepts top_k / min_p / repetition_penalty etc. at top level
    for k in ("top_k", "min_p", "repetition_penalty", "seed",
              "presence_penalty", "frequency_penalty"):
        if k in eb:
            payload[k] = eb.pop(k)
    # Anything left in eb gets dropped silently — /v1/completions doesn't
    # accept arbitrary unknown keys (returns 422). Log what we drop in case
    # someone added a knob expecting it to flow through.
    if eb:
        logger.debug("v19 adapter dropped extra_body keys: %s", list(eb.keys()))
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    with httpx.Client(timeout=timeout or 600.0) as c:
        r = c.post(f"{base_url.rstrip('/')}/completions", json=payload, headers=headers)
        r.raise_for_status()
        return r.json()


# ── public entry: dispatch_via_completions ───────────────────────────────────

def dispatch_via_completions(
    *, base_url: str, api_key: str, model: str,
    messages: list[dict], tools: list[dict] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None, top_p: float | None = None,
    extra_body: dict | None = None,
    timeout: float | None = None,
    **_ignored,
) -> Any:
    """One-shot: render v19 prompt → POST /v1/completions → ChatCompletion shape."""
    eb = dict(extra_body or {})
    ct_kwargs = eb.get("chat_template_kwargs") or {}
    enable_thinking = bool(ct_kwargs.get("enable_thinking", True))
    preserve_thinking = bool(ct_kwargs.get("preserve_thinking", True))

    prompt = render_prompt(
        messages=messages, tools=tools,
        enable_thinking=enable_thinking,
        preserve_thinking=preserve_thinking,
    )
    raw = _completions_call(
        base_url=base_url, api_key=api_key, model=model, prompt=prompt,
        max_tokens=max_tokens, temperature=temperature, top_p=top_p,
        extra_body=eb, timeout=timeout,
    )
    choice = raw["choices"][0]
    text = choice.get("text") or ""
    reasoning, content, tcs = _parse_completion_text(text)
    usage = raw.get("usage") or {}
    return _make_chat_completion(
        model=model, reasoning=reasoning, content=content, tool_calls=tcs,
        finish_reason=choice.get("finish_reason") or "stop",
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
    )


# ── client wrapper ──────────────────────────────────────────────────────────

def is_adapter_enabled() -> bool:
    """``EXAONE_V19_ADAPTER`` env gate. Default ON; set to "0" to disable."""
    return os.getenv("EXAONE_V19_ADAPTER", "1").strip().lower() in (
        "1", "true", "yes", "on"
    )


def should_route(model: str) -> bool:
    """Only route Qwen-family models. Others fall through to the SDK path."""
    if not is_adapter_enabled():
        return False
    if not model:
        return False
    return model.lower().startswith("qwen")


def wrap_client_create(original_create, base_url: str, api_key: str):
    """Return a wrapped chat.completions.create that routes Qwen → v19 path."""
    def _create(**kwargs):
        model = kwargs.get("model") or ""
        if not should_route(model):
            return original_create(**kwargs)
        # Strip kwargs that /v1/completions doesn't take. We forward only
        # what the v19 path needs; rest is logged-dropped by adapter.
        return dispatch_via_completions(
            base_url=base_url, api_key=api_key,
            model=model,
            messages=kwargs.get("messages") or [],
            tools=kwargs.get("tools"),
            max_tokens=kwargs.get("max_tokens"),
            temperature=kwargs.get("temperature"),
            top_p=kwargs.get("top_p"),
            extra_body=kwargs.get("extra_body"),
            timeout=kwargs.get("timeout"),
        )
    return _create


def wrap_openai_client(client) -> Any:
    """Patch chat.completions.create on an OpenAI client in-place. Idempotent."""
    if getattr(client, "_v19_wrapped", False):
        return client
    try:
        base_url = str(client.base_url).rstrip("/")
        api_key = getattr(client, "api_key", "") or ""
    except Exception:
        base_url = ""
        api_key = ""
    original = client.chat.completions.create
    client.chat.completions.create = wrap_client_create(original, base_url, api_key)
    client._v19_wrapped = True
    return client
