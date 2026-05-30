"""
exaone/agent.py — ExaoneAgent, an AIAgent subclass for LGAI EXAONE models.
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from run_agent import AIAgent
from exaone.aliasing import RandomShortAliaser
from exaone.config import bootstrap_gateway_env, load_config
from exaone.qa_modes import (
    QA_MODES,
    validate_exclusive_modes,
    validate_qa_mode_prompt_files,
)
from exaone.system_prompt import (
    compose_system_prompt,
    compose_tool_list_for_tools,
    load_prompt_blocks,
)
from exaone.tool_formatting import (
    RunIndexStore,
    ToolResultFormatter,
    is_already_enveloped,
    new_run_formatting,
    parse_tool_result_content,
    resolve_result_format,
)
from exaone.tools import EXAONE_TOOLSET, EXAONE_TOOLSET_NAME, register_exaone_tools
from exaone.tracer import log_trace

logger = logging.getLogger(__name__)

_bootstrap_done = False


# sft_pipeline reasoning_system_prompt uses ``{cur_date}`` and ``{language}``
# placeholders that the upstream pipeline filled via str.format. We compose the
# system prompt at agent-init time and need the same substitution here, so the
# placeholders don't survive into the wire prompt. ``{language}`` defaults to a
# language-agnostic phrase because the agent supports multilingual sessions;
# per-question language is taken from the user's input by the model itself.
_PROMPT_PLACEHOLDER_DEFAULTS = {
    "cur_date": datetime.now(timezone.utc).date().isoformat(),
    "language": "the user's question language",
}


def _format_prompt_placeholders(text: str, overrides: dict | None = None) -> str:
    """Substitute {cur_date} / {current_date} / {language} placeholders.

    `overrides` lets a caller (ExaoneAgent) inject a concrete `language`
    value at agent-init time — used by the SFT batch path so the prompt
    pins to e.g. "Korean" instead of the generic fallback. Production
    serving passes no override and inherits the fallback, so the model
    matches the user-query language naturally at inference.
    """
    if not text:
        return text
    subs = overrides if overrides is not None else _PROMPT_PLACEHOLDER_DEFAULTS
    try:
        return text.format(**subs)
    except (KeyError, IndexError, ValueError):
        # Other prompt files may contain literal braces (e.g. code samples) —
        # leave them untouched if format() can't safely substitute.
        return text


class ExaoneAgent(AIAgent):
    """AIAgent subclass pre-configured for EXAONE on vLLM with trace logging."""

    def __init__(self, trace_log_path: str = None, **kwargs):
        global _bootstrap_done
        if not _bootstrap_done:
            bootstrap_gateway_env()
            _bootstrap_done = True

        cfg = load_config()
        qa_mode = kwargs.pop("qa_mode", None)
        requested_toolset = kwargs.pop("toolset", None)
        caller_enabled_toolsets = kwargs.pop("enabled_toolsets", None)
        reasoning = kwargs.pop("reasoning", True)
        # SFT batch pipelines pass `language` (e.g. "Korean") here so the
        # {language} placeholder in style/identity prompts gets pinned to
        # one concrete value — matches the original sft_pipeline's
        # `gen_include_language=True` behavior. Production serving omits
        # this kwarg and the placeholder falls back to the generic phrase
        # so the trained model adapts to the user-query language at
        # inference. Saved trajectory.json never carries the pin (the
        # Hermes hardcode template in _convert_to_trajectory_format does
        # not embed the style block), so distill input stays language-neutral.
        language_pin = kwargs.pop("language", None)
        validate_exclusive_modes(requested_toolset, qa_mode)
        self._trace_save_raw = kwargs.pop("save_raw_trace", cfg.save_raw_trace)
        self._trace_save_trajectory = kwargs.pop("save_trajectory", cfg.save_trajectory)

        register_exaone_tools()

        if caller_enabled_toolsets is not None:
            self._configured_toolset = caller_enabled_toolsets
            blocks = load_prompt_blocks()
            self._qa_mode = None
        elif qa_mode is not None:
            mode_config = validate_qa_mode_prompt_files(qa_mode)
            self._configured_toolset = mode_config.toolset
            blocks = load_prompt_blocks(
                identity_name=mode_config.identity_name,
                style_name=mode_config.style_name,
                strict=True,
            )
            self._qa_mode = mode_config.name
        else:
            self._configured_toolset = (
                QA_MODES["general"].toolset
                if requested_toolset is None
                else requested_toolset
            )
            blocks = load_prompt_blocks()
            self._qa_mode = None
        self._reasoning_enabled = True if reasoning is None else bool(reasoning)

        self._system_blocks = blocks
        # Per-instance placeholder dict — overridden only when `language`
        # kwarg was supplied. None means "use module-level defaults".
        # The actual `_system_blocks_text` is composed below after tool list
        # has been resolved, so we don't pre-compute it here.
        self._placeholder_overrides: dict | None = None
        if language_pin:
            self._placeholder_overrides = {
                **_PROMPT_PLACEHOLDER_DEFAULTS,
                "language": str(language_pin),
            }

        kwargs = cfg.apply_agent_kwargs(kwargs)
        if caller_enabled_toolsets is None:
            kwargs["enabled_toolsets"] = [EXAONE_TOOLSET_NAME]
        kwargs["session_db"] = None
        kwargs.setdefault("max_iterations", 10)
        kwargs.setdefault("skip_memory", True)
        kwargs.setdefault("skip_context_files", True)
        kwargs.setdefault("tool_delay", 0)

        self._trace_log_dir = cfg.trace_dir_resolved(trace_log_path)
        self._trace_log_dir.mkdir(parents=True, exist_ok=True)
        self._tool_aliaser: RandomShortAliaser | None = None
        self._index_store: RunIndexStore | None = None
        self._tool_formatter: ToolResultFormatter | None = None

        super().__init__(**kwargs)

        # NOTE: Wrap the primary OpenAI client immediately so the v19
        # adapter is active for every code path that reads self.client
        # (including run_agent.py:5957 where _ensure_primary_openai_client
        # short-circuits to the cached self.client without re-wrapping).
        # The _create_request_openai_client / _ensure_primary_openai_client
        # overrides below cover the request-scoped and re-created paths.
        try:
            from exaone.v19_completions_adapter import (
                wrap_openai_client as _v19_wrap, is_adapter_enabled as _v19_on,
            )
            if _v19_on() and getattr(self, "client", None) is not None:
                _v19_wrap(self.client)
                # NOTE: Force non-streaming. The agent's main loop
                # (run_agent.py:11602) prefers streaming for liveness
                # checking; that path calls chat.completions.create with
                # stream=True and iterates the result as a stream of
                # chunks. Our v19 adapter renders the prompt locally and
                # returns a one-shot ChatCompletion (SimpleNamespace), so
                # the streaming iteration crashes with "SimpleNamespace
                # object is not iterable". `_disable_streaming` is the
                # documented gate (line 11582) — setting it routes every
                # call through _interruptible_api_call (non-stream) and
                # keeps the adapter's response shape valid.
                self._disable_streaming = True
        except Exception:
            logger.exception("v19 adapter wrap of primary client failed")

        selected_tools = self._select_tools(self._configured_toolset)
        self.tools = selected_tools
        self.valid_tool_names = {t["function"]["name"] for t in self.tools}
        if not self.quiet_mode:
            names = ", ".join(t["function"]["name"] for t in self.tools) or "(none)"
            print(f"🛠️  ExaoneAgent active tools ({len(self.tools)}): {names}")

        # Pin enable_thinking explicitly — don't rely on the server's chat-template
        # default, which varies across vLLM deploys.
        overrides = self.request_overrides = dict(self.request_overrides or {})
        extra_body = overrides["extra_body"] = dict(overrides.get("extra_body") or {})
        extra_body["chat_template_kwargs"] = {
            **(extra_body.get("chat_template_kwargs") or {}),
            "enable_thinking": self._reasoning_enabled,
        }

        selected_names = [t["function"]["name"] for t in selected_tools]
        tool_list_text = compose_tool_list_for_tools(selected_names, strict=True)
        self._system_blocks["tool_list"] = tool_list_text.strip()
        self._system_blocks_text = _format_prompt_placeholders(
            compose_system_prompt(self._system_blocks),
            self._placeholder_overrides,
        )

    # NOTE: Override AIAgent's openai-client factory so we can wrap
    # chat.completions.create with the v19 chat-template adapter.
    # WHY: The Qwen3 chat_template on our self-hosted vLLM injects empty
    # <think>\n\n</think> blocks for past assistant turns and silently
    # drops their reasoning_content — which conditions the model to skip
    # thinking on later turns (froggeric Qwen-Fixed-Chat-Templates v19
    # diagnosis). The clean fix would be a per-request chat_template
    # override, but our vLLM was started without --trust-request-chat-template
    # so that path returns HTTP 400. Instead the adapter renders the wire
    # prompt locally via v19's jinja and POSTs to /v1/completions, then
    # reshapes the raw text into a ChatCompletion so the rest of the
    # agent loop is unchanged. Gated by EXAONE_V19_ADAPTER env (default ON).
    def _create_request_openai_client(self, *, reason, api_kwargs=None):
        client = super()._create_request_openai_client(reason=reason, api_kwargs=api_kwargs)
        try:
            from exaone.v19_completions_adapter import wrap_openai_client, is_adapter_enabled
            if is_adapter_enabled():
                wrap_openai_client(client)
        except Exception:
            logger.exception("v19 adapter wrap failed; falling back to native client")
        return client

    # NOTE: Also wrap the cached primary client. The finalizer path at
    # run_agent.py:10700 (iteration-limit summary) uses _ensure_primary_openai_client
    # directly instead of going through _create_request_openai_client, so
    # without this override the finalizer call would bypass the v19 adapter
    # and re-introduce the empty-think regression for the summary turn.
    def _ensure_primary_openai_client(self, *, reason):
        client = super()._ensure_primary_openai_client(reason=reason)
        try:
            from exaone.v19_completions_adapter import wrap_openai_client, is_adapter_enabled
            if is_adapter_enabled():
                wrap_openai_client(client)
        except Exception:
            logger.exception("v19 adapter wrap failed; falling back to native client")
        return client

    def _reset_run_formatting(self) -> None:
        self._tool_aliaser = RandomShortAliaser()
        self._index_store, self._tool_formatter = new_run_formatting()

    def _alias_tool_calls(self, assistant_message, messages: list) -> None:
        if self._tool_aliaser is None:
            return
        for tc in assistant_message.tool_calls or []:
            tc.id = self._tool_aliaser.alias(
                provider_id=tc.id, tool_name=tc.function.name
            )

        if messages and messages[-1].get("role") == "assistant":
            for tc in messages[-1].get("tool_calls") or []:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                pid = tc.get("id", "")
                tc["id"] = self._tool_aliaser.alias(provider_id=pid, tool_name=name)

    def _format_tool_message(self, msg: dict) -> None:
        if self._tool_formatter is None:
            return
        content = msg.get("content") or ""
        raw = parse_tool_result_content(content)
        if is_already_enveloped(raw):
            return
        tool_name = msg.get("name") or ""
        # Skip tools whose output is metadata / lifecycle plumbing, not citable
        # evidence: parse_web_and_doc builds the chunk pool and list_documents
        # enumerates registrations. Every other tool — web_search, web_extract,
        # doc_search, get_document_chunks, ReadFullDocument — flows through the
        # citation envelope so its rows get an Index that downstream answers
        # can cite.
        if tool_name in {"parse_web_and_doc", "list_documents"}:
            return
        tcid = msg.get("tool_call_id") or ""
        fmt = resolve_result_format(tool_name, raw)
        msg["content"] = self._tool_formatter.format(
            tool_call_id=tcid,
            tool_name=tool_name,
            raw_result=raw,
            result_format=fmt,
        )

    def _execute_tool_calls(
        self,
        assistant_message,
        messages: list,
        effective_task_id: str,
        api_call_count: int = 0,
    ) -> None:
        self._alias_tool_calls(assistant_message, messages)
        n_before = len(messages)
        super()._execute_tool_calls(
            assistant_message, messages, effective_task_id, api_call_count
        )
        for msg in messages[n_before:]:
            if msg.get("role") == "tool":
                self._format_tool_message(msg)

    def _build_system_prompt(self, system_message: str = None) -> str:
        prompt = system_message or self._system_blocks_text or ""
        self._cached_system_prompt = prompt
        return prompt

    def run_conversation(
        self,
        user_message: str,
        system_message: str = None,
        conversation_history: List[Dict[str, Any]] = None,
        task_id: str = None,
        stream_callback: Optional[callable] = None,
        persist_user_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = str(uuid.uuid4())
        self._current_run_dir = self._trace_log_dir / ts / run_id
        self._current_run_dir.mkdir(parents=True, exist_ok=True)
        self._compaction_count = 0
        self._forced_finish = False
        self._reset_run_formatting()
        from exaone.compaction_tracer import bind_run_dir, unbind_run_dir
        from exaone.auxiliary_tracer import bind_run as _bind_aux, unbind_run as _unbind_aux

        # Mirror the per-run RunIndexStore into the task-keyed registry so
        # handlers can resolve `<tcid>.<n>` Index strings the model echoes
        # from prior tool results. Removed at run end.
        from exaone.tool_formatting import (
            register_index_store_for_task, unregister_index_store_for_task,
        )

        tok_dir, tok_seq = bind_run_dir(self._current_run_dir)
        tok_aux = _bind_aux(self._current_run_dir)
        effective_task_id_for_store = task_id or "default"
        register_index_store_for_task(effective_task_id_for_store, self._index_store)

        selected_tools = self.tools
        try:
            result = super().run_conversation(
                user_message=user_message,
                system_message=system_message,
                conversation_history=conversation_history,
                task_id=task_id,
                stream_callback=stream_callback,
                persist_user_message=persist_user_message,
            )
            try:
                log_trace(
                    user_message=user_message,
                    result=result,
                    tools=selected_tools,
                    system_prompt=getattr(self, "_cached_system_prompt", "") or "",
                    system_blocks=self._system_blocks,
                    session_id=getattr(self, "session_id", None),
                    trace_log_dir=self._trace_log_dir,
                    agent=self,
                    run_dir=self._current_run_dir,
                    save_raw=self._trace_save_raw,
                    save_trajectory=self._trace_save_trajectory,
                )
            except Exception:
                logger.exception("ExaoneAgent: failed to write trace — ignoring")
            return result
        finally:
            unbind_run_dir(tok_dir, tok_seq)
            _unbind_aux(tok_aux)
            unregister_index_store_for_task(effective_task_id_for_store)

    def _compress_context(
        self,
        messages,
        system_message,
        *,
        approx_tokens=None,
        task_id="default",
        focus_topic=None,
    ):
        from exaone.compaction_tracer import write_compaction_triplet
        from exaone.auxiliary_tracer import _write_compression

        self._compaction_count += 1
        idx = self._compaction_count
        step_n = sum(1 for m in messages if m.get("role") == "assistant")
        pre_snapshot = [dict(m) for m in messages]

        _run_dir = self._current_run_dir
        if hasattr(self, "context_compressor") and self.context_compressor is not None:
            self.context_compressor.summary_log_callback = (
                lambda user_prompt, assistant, meta: _write_compression(
                    _run_dir, idx, user_prompt, assistant, meta
                ) if _run_dir else None
            )

        compressed, new_system = super()._compress_context(
            messages,
            system_message,
            approx_tokens=approx_tokens,
            task_id=task_id,
            focus_topic=focus_topic,
        )

        summary_text = getattr(self.context_compressor, "_previous_summary", None) or ""
        post_snapshot = [dict(m) for m in compressed]

        if getattr(self, "_current_run_dir", None):
            write_compaction_triplet(
                run_dir=self._current_run_dir,
                idx=idx,
                step_n=step_n,
                pre_messages=pre_snapshot,
                summary_text=summary_text,
                post_messages=post_snapshot,
            )
        return compressed, new_system

    def _handle_max_iterations(self, messages: list, api_call_count: int) -> str:
        self._forced_finish = True
        if getattr(self, "_current_run_dir", None) and self._compaction_count > 0:
            from exaone.compaction_tracer import (
                rename_last_post_compaction_force_finish,
            )

            rename_last_post_compaction_force_finish(
                self._current_run_dir, self._compaction_count
            )

        fin_dir = Path(__file__).parent / "prompts" / "finalization"

        system_path = fin_dir / "system.txt"
        fin_system = (
            system_path.read_text(encoding="utf-8").strip()
            if system_path.exists()
            else (
                "You are a finalization agent. The investigation phase has ended. "
                "Your only job is to output the final plain-text answer based on "
                "the context above. Do NOT call any tools. Do NOT emit any "
                "tool_calls. Respond with the final answer only."
            )
        )

        termination_path = fin_dir / "termination_user.txt"
        termination_msg = (
            termination_path.read_text(encoding="utf-8").strip()
            if termination_path.exists()
            else (
                "We've reached the iteration budget. Provide your final answer now "
                "based on the information gathered above. Do not call any more tools."
            )
        )

        non_system = [
            {
                k: v
                for k, v in m.items()
                if k not in ("reasoning", "finish_reason", "_thinking_prefill")
            }
            for m in messages
            if m.get("role") != "system"
        ]
        api_messages = (
            [{"role": "system", "content": fin_system}]
            + non_system
            + [{"role": "user", "content": termination_msg}]
        )

        summary_kwargs = {
            "model": self.model,
            "messages": api_messages,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }

        try:
            resp = self._ensure_primary_openai_client(
                reason="iteration_limit_summary"
            ).chat.completions.create(**summary_kwargs)
            result = self._get_transport().normalize_response(resp)
            text = (result.content or "").strip()
            if "<think>" in text:
                text = re.sub(
                    r"<think>.*?</think>\s*", "", text, flags=re.DOTALL
                ).strip()
            if text:
                from exaone.auxiliary_tracer import write_finalizer_log
                try:
                    write_finalizer_log(messages=api_messages, assistant=text)
                except Exception:
                    pass
                messages.append({"role": "assistant", "content": text})
                return text
        except Exception:
            logger.exception("ExaoneAgent: finalization API call failed")
        return "최대 반복 횟수에 도달했습니다."

    def _cleanup_dead_connections(self) -> bool:
        return False

    def _persist_session(self, messages, conversation_history=None):
        pass

    def _select_tools(self, toolset: "str | list[str] | None") -> list:
        if not self.tools:
            return []
        if toolset is None:
            return self.tools

        requested = [toolset] if isinstance(toolset, str) else list(toolset)
        expanded: list[str] = []
        for name in requested:
            if name in EXAONE_TOOLSET:
                expanded.extend(EXAONE_TOOLSET[name])
                continue
            from toolsets import get_toolset as _get_hermes_toolset
            hermes_ts = _get_hermes_toolset(name)
            if hermes_ts is not None:
                expanded.extend(hermes_ts.get("tools", []))
                continue
            expanded.append(name)

        available_map = {t["function"]["name"]: t for t in self.tools}
        available = set(available_map.keys())
        requested = set(expanded)
        missing = requested - available
        if missing:
            from tools.registry import registry

            registered = set(registry.get_all_tool_names())
            unknown = sorted(name for name in missing if name not in registered)
            unavailable = sorted(name for name in missing if name in registered)
            if unknown:
                known = ", ".join(sorted(available))
                raise ValueError(
                    f"Unknown tool name(s): {', '.join(unknown)}. "
                    f"Available tools: {known}"
                )
            if unavailable:
                hint = ""
                if {"web_search", "web_extract"} & set(unavailable):
                    hint = (
                        " | hint: set web.backend=brave with brave_search MCP "
                        "(or configure TAVILY_API_KEY/SEARXNG_URL)"
                    )
                logger.warning(
                    "ExaoneAgent: requested tool(s) unavailable (requirements not met): %s%s",
                    ", ".join(unavailable),
                    hint,
                )

        ordered: list[str] = []
        seen: set[str] = set()
        for name in expanded:
            if name in seen:
                continue
            seen.add(name)
            ordered.append(name)

        selected: list[dict] = [
            available_map[name] for name in ordered if name in available_map
        ]
        return selected
