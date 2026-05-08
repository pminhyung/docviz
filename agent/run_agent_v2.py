#!/usr/bin/env python3
"""
Document Agent V2 - CLI Entrypoint

This is the main CLI entrypoint for the refactored document agent.
It wraps the original agent loop with:
- YAML-based prompt patching
- Role-based model routing
- Rich trace export
- Backward-compatible training JSONL export
- Clean language enforcement
- JSON document input
- Web search + ReadFullText support
- Tool output image auto-detection with VL model switching

Usage:
    python run_agent_v2.py \
        --doc_json_path /path/to/doc.json \
        --export_trace_path trace.json \
        --export_training_path train.jsonl \
        --lang ENGLISH \
        --single_doc true
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.config.runtime_prompts import get_runtime_prompt_blocks, assemble_runtime_prompt
from agent.config.training_prompts import (
    get_training_system_prompt,
    DOC_STEP_PROMPT,
    EXTRACTOR_PROMPT,
    EXTRACTOR_DOC_PROMPT,
)
from agent.core.prompt_compiler import PromptCompiler, CompiledPrompt
from agent.core.model_router import ModelRouter, ModelRole, ToolOutput, ImageRef
from agent.core.tool_output import (
    parse_tool_output,
    parse_images,
    build_multimodal_message,
)
from agent.core.trace_collector import TraceCollector, TraceSession
from agent.core.document_loader import DocumentLoader
from agent.core.tool_registry import ToolRegistry
from agent.core.tool_actions import ToolContext
from agent.core.selector_client import SelectorClient
from agent.core.web_search_client import WebSearchClient
from agent.core.sandbox import (
    is_sandbox_mode,
    set_sandbox_mode,
    get_sandbox_search_results,
    get_sandbox_document_extraction,
)
from agent.export.training_jsonl import (
    TrainingJSONLExporter,
    convert_base_train_sample,
    export_training_sample,
)
from agent.domain.reasoning.parser import parse_agent_response
from agent.domain.document.truncator import truncate_documents
from agent.domain.training.builder import TrainingSampleBuilder
from agent.domain.reasoning.events import DocSummaryCompleted, StepCompleted, ToolExtractionCompleted


def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Document Agent V2 - Refactored document analysis agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required arguments
    parser.add_argument(
        "--doc_json_path",
        type=str,
        required=True,
        help="Path to document JSON file",
    )

    parser.add_argument(
        "--export_trace_path",
        type=str,
        required=True,
        help="Output path for trace JSON/JSONL",
    )

    # Optional arguments
    parser.add_argument(
        "--doc_json_path_2",
        type=str,
        default=None,
        help="Optional second document for 2-doc mode",
    )

    parser.add_argument(
        "--lang",
        type=str,
        choices=["ENGLISH", "KOREAN"],
        default="ENGLISH",
        help="Language for agent output (default: ENGLISH)",
    )

    parser.add_argument(
        "--single_doc",
        type=str,
        choices=["true", "false"],
        default="true",
        help="Single document mode (default: true)",
    )

    parser.add_argument(
        "--override_patch",
        type=str,
        default=None,
        help="Path to YAML patch file for prompt overrides",
    )

    parser.add_argument(
        "--model_config",
        type=str,
        default=None,
        help="Path to model config YAML",
    )

    parser.add_argument(
        "--export_training_path",
        type=str,
        default=None,
        help="Output path for training JSONL",
    )

    parser.add_argument(
        "--n_steps_max",
        type=int,
        default=20,
        help="Maximum number of agent steps (default: 20)",
    )

    parser.add_argument(
        "--user_query",
        type=str,
        default=None,
        help="Single query to run (instead of generating queries)",
    )

    parser.add_argument(
        "--n_queries",
        type=int,
        default=5,
        help="Number of queries to generate if not using --user_query",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Enable sandbox mode (no external API calls, deterministic responses)",
    )

    return parser.parse_args()


class AgentV2Runner:
    """
    Main runner class for Document Agent V2.

    Wraps the original agent loop with enhanced functionality.
    """

    def __init__(
        self,
        language: str = "ENGLISH",
        single_doc: bool = True,
        n_steps_max: int = 20,
        override_patch: Optional[str] = None,
        model_config: Optional[str] = None,
        verbose: bool = False,
        custom_tools: Optional[List[Dict[str, Any]]] = None,
        custom_rules: Optional[str] = None,
        tool_registry: Optional[ToolRegistry] = None,
        tool_secrets: Optional[Dict[str, Any]] = None,
        reasoner_type: str = "llm",
        reasoner_model_name: Optional[str] = None,
        reasoner_api_key: Optional[str] = None,
        reasoner_base_url: Optional[str] = None,
        reasoner_model_max_length: Optional[int] = None,
        extraction_api_key: Optional[str] = None,
    ):
        """
        Initialize the runner.

        Args:
            language: Language for agent output
            single_doc: Whether to use single document mode
            n_steps_max: Maximum number of agent steps
            override_patch: Path to YAML patch file
            model_config: Path to model config YAML
            verbose: Enable verbose output
            custom_tools: Optional list of custom tool definitions for prompt injection
            custom_rules: Optional custom rules string to inject
            tool_registry: Optional pre-configured ToolRegistry for execution
            tool_secrets: Optional secrets dict for custom tools (e.g., API keys)
            reasoner_type: "llm" for text-only, "vl" for vision-language
            reasoner_model_name: Specific model name (default based on reasoner_type)
            reasoner_api_key: API key for reasoning model (required except in sandbox mode)
            reasoner_base_url: Explicit base URL override for reasoning model
            reasoner_model_max_length: Override max output tokens for reasoner model
            extraction_api_key: Separate API key for extraction/builtin models (e.g., Novita key when reasoner uses OpenAI)
        """
        self.language = language
        self.single_doc = single_doc
        self.n_steps_max = n_steps_max
        self.override_patch = override_patch
        self.model_config = model_config
        self.verbose = verbose
        self.custom_tools = custom_tools
        self.custom_rules = custom_rules
        # Create default registry with built-in tools if not provided
        self.tool_registry = tool_registry if tool_registry else ToolRegistry(include_builtin=True)
        self.tool_secrets = tool_secrets
        self.reasoner_type = reasoner_type
        self.reasoner_model_name = reasoner_model_name
        self.reasoner_api_key = reasoner_api_key or ""
        self.reasoner_base_url = reasoner_base_url
        self.reasoner_model_max_length = reasoner_model_max_length
        self.extraction_api_key = extraction_api_key or ""

        # Initialize components
        self.compiler = PromptCompiler(language=language)
        self.router = ModelRouter()
        self.trace_collector = TraceCollector()
        self.doc_loader = DocumentLoader()

        # Compiled prompt
        self.compiled_prompt: Optional[CompiledPrompt] = None

        # Image directory (set during load_documents)
        self.image_dir: Optional[str] = None

        # Selector and web search clients
        self.selector_client: Optional[SelectorClient] = None
        self.web_search_client: Optional[WebSearchClient] = None

        # Reasoning client
        self.reasoning_client = None

    def setup(self) -> None:
        """Set up the runner (compile prompts, init clients, etc.)"""
        if is_sandbox_mode():
            print("[Setup] *** SANDBOX MODE ENABLED - No external API calls ***")
        print(f"[Setup] Language: {self.language}, Single doc: {self.single_doc}")

        # Determine lang code
        lang = "en"
        if self.language.upper() == "KOREAN":
            lang = "ko"

        # Get all tools from registry (builtin + custom) for prompt injection
        all_tools = self.tool_registry.get_tools_for_prompt()

        # Compile prompts with all tools and rules
        self.compiled_prompt = self.compiler.compile(
            patch_file=self.override_patch,
            tools=all_tools,
            custom_rules=self.custom_rules,
            lang=lang
        )
        print(f"[Setup] Prompt compiled: pack_id={self.compiled_prompt.prompt_pack_id}")
        print(f"[Setup] Runtime prompt hash: {self.compiled_prompt.prompt_hash}")
        if self.compiled_prompt.override_hash:
            print(f"[Setup] Override hash: {self.compiled_prompt.override_hash}")

        # Log builtin/custom tool breakdown
        all_names = self.tool_registry.get_tool_names()
        custom_names = [n for n in all_names if n not in self.tool_registry.BUILTIN_NAMES]
        if custom_names:
            print(f"[Setup] Custom tools: {custom_names}")
        if self.custom_rules:
            print(f"[Setup] Custom rules injected")
            if not custom_names:
                print("[Setup] WARNING: custom_rules set but no custom_tools loaded")
        print(f"[Setup] All tools: {all_names}")

        # Load model config if provided
        if self.model_config:
            self.router.load_config(self.model_config)
            print(f"[Setup] Model config loaded from: {self.model_config}")

        # Create reasoning client based on reasoner_type
        self.reasoning_client = self.router.create_reasoning_client(
            reasoner_type=self.reasoner_type,
            model_name=self.reasoner_model_name,
            api_key=self.reasoner_api_key,
            base_url=self.reasoner_base_url,
            max_length=self.reasoner_model_max_length,
            extraction_api_key=self.extraction_api_key or None,
        )

        # Log reasoner configuration
        model_id = getattr(self.reasoning_client, 'model_config', None)
        if model_id:
            print(f"[Setup] Reasoner: type={self.reasoner_type}, model={model_id.model_id}")
        else:
            print(f"[Setup] Reasoner: type={self.reasoner_type} (sandbox mode)")

        # Initialize selector client (round-robin LB by default)
        from agent.core.selector_client import SELECTOR_URLS
        legacy_url = os.environ.get("GW_STG_SELECTOR_URL")
        self.selector_client = SelectorClient(url=legacy_url)
        print(f"[Setup] SelectorClient initialized: {legacy_url or SELECTOR_URLS}")

        # Initialize web search client (Brave primary + DDG fallback)
        brave_keys_raw = os.environ.get("BRAVE_KEYS", "[]").strip().strip("'\"")
        try:
            brave_keys = json.loads(brave_keys_raw)
        except Exception:
            brave_keys = []
        serpapi_key = os.environ.get("SERPAPI_KEY", "")
        self.web_search_client = WebSearchClient(
            brave_keys=brave_keys,
            serpapi_keys=[serpapi_key] if serpapi_key else [],
        )
        print(f"[Setup] WebSearchClient initialized: brave_keys={len(brave_keys)}, serpapi={'yes' if serpapi_key else 'no'}")

        print("[Setup] Setup completed successfully")

    def load_documents(
        self,
        doc_json_path: str,
        doc_json_path_2: Optional[str] = None,
        image_dir: Optional[str] = None,
    ) -> Tuple[List[List[Dict[str, Any]]], List[str], str]:
        """
        Load documents from JSON paths.

        Args:
            doc_json_path: Path to first document JSON
            doc_json_path_2: Optional path to second document JSON
            image_dir: Optional path to image directory (for docai format)

        Returns:
            Tuple of (multi_docs, filenames, doc_contexts)
        """
        doc_paths = [doc_json_path]
        if doc_json_path_2 and not self.single_doc:
            doc_paths.append(doc_json_path_2)

        # Build image_dirs list
        image_dirs = None
        if image_dir:
            image_dirs = [image_dir]

        multi_docs, filenames, loaded_image_dirs = self.doc_loader.load_documents(
            doc_paths,
            single_doc=self.single_doc,
            image_dirs=image_dirs
        )

        # Store first image dir for tool context
        if loaded_image_dirs:
            self.image_dir = loaded_image_dirs[0]
        elif image_dir:
            self.image_dir = image_dir

        # Generate document contexts for summary
        doc_contexts = ""
        for i, pages in enumerate(multi_docs, 1):
            if pages:
                filename = pages[0].get("filename", f"Document {i}")
                content_preview = "\n".join(
                    p.get("content", "")[:500] for p in pages[:3]
                )
                doc_contexts += f"\n\nFile {i}: {filename}\n{content_preview}..."

        print(f"[Load] Loaded {len(multi_docs)} document(s): {filenames}")
        for i, pages in enumerate(multi_docs, 1):
            print(f"  Document {i}: {len(pages)} pages")
        if self.image_dir:
            print(f"[Load] Image directory: {self.image_dir}")

        return multi_docs, filenames, doc_contexts

    def run_single_query(
        self,
        user_query: str,
        multi_docs: List[List[Dict[str, Any]]],
        filenames: List[str],
        doc_contexts: str,
    ) -> Tuple[TraceSession, Dict[str, Any]]:
        """
        Run the agent for a single query.

        Args:
            user_query: The user's query
            multi_docs: Loaded documents
            filenames: Document filenames
            doc_contexts: Document context string

        Returns:
            Tuple of (trace_session, train_sample)
        """
        print(f"\n{'='*80}")
        print(f"[Query] {user_query}")
        print(f"{'='*80}")

        # Start trace session
        session = self.trace_collector.start_session(
            user_query=user_query,
            filenames=filenames,
            language=self.language,
            prompt_pack_id=self.compiled_prompt.prompt_pack_id,
            prompt_hash=self.compiled_prompt.prompt_hash,
            override_hash=self.compiled_prompt.override_hash,
        )

        # Initialize builder (replaces inline train_sample dict)
        builder = TrainingSampleBuilder(user_query=user_query, filenames=filenames)
        train_sample = builder._sample  # shared reference — builtin_tools mutate directly

        try:
            # Run the agent loop
            train_sample = self._run_agent_loop(
                user_query=user_query,
                multi_docs=multi_docs,
                filenames=filenames,
                doc_contexts=doc_contexts,
                train_sample=train_sample,
                session=session,
                builder=builder,
            )

            self.trace_collector.finish_session(success=True)

        except Exception as e:
            print(f"[Error] Agent loop failed: {e}")
            import traceback
            traceback.print_exc()
            self.trace_collector.finish_session(success=False, error=str(e))

        return session, train_sample

    def _run_agent_loop(
        self,
        user_query: str,
        multi_docs: List[List[Dict[str, Any]]],
        filenames: List[str],
        doc_contexts: str,
        train_sample: Dict[str, Any],
        session: TraceSession,
        builder: TrainingSampleBuilder = None,
    ) -> Dict[str, Any]:
        """
        Run the main agent loop.

        Uses SelectorClient and WebSearchClient directly (no base_import dependency).
        """
        client = self.reasoning_client

        # Document summary truncation (domain module)
        docs_summary_input = truncate_documents(multi_docs, max_length=80000)

        # Step 1: Document summary
        print("\n[Step 1] Generating document summary...")
        self.trace_collector.start_step()

        doc_summ_prompt = DOC_STEP_PROMPT.format(user_query=user_query)
        doc_summ_prompt += doc_contexts

        doc_summ_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": doc_summ_prompt},
        ]

        summ_response = client.chat.completions.create(
            messages=doc_summ_messages,
            temperature=0.2,
            max_tokens=4000
        )
        msg = summ_response.choices[0].message
        doc_summary = msg.content or getattr(msg, 'reasoning_content', '') or ''

        if builder is not None:
            builder.record_doc_step(DocSummaryCompleted(prompt=doc_summ_prompt, summary=doc_summary))
        else:
            train_sample["doc_step"] = [
                {"role": "user", "content": doc_summ_prompt, "loss_masking": True},
                {"role": "assistant", "content": doc_summary, "loss_masking": False},
            ]

        self.trace_collector.record_step(
            step_type="doc_summary",
            step_name="Document Analysis",
            action="doc_summary",
            tokens_used=summ_response.usage.total_tokens if summ_response.usage else 0,
            model_used="qwen3",
        )

        print(f"[Step 1] Document summary generated ({len(doc_summary)} chars)")

        # Initialize agent state
        runtime_prompt = self.compiled_prompt.runtime_prompt

        action_start = [{"role": "system", "content": runtime_prompt}]

        filelist = ", ".join([f"Document{i+1}-{fn}" for i, fn in enumerate(filenames)])
        first_user_turn = f"""**Primary User Question** : {user_query}

**Internal Documents' list with their numbers: {filelist}

**Internal Documents' overview** : {doc_summary}

---

Using the above, respond fully follow the system instructions.
"""

        action_start.append({"role": "user", "content": first_user_turn})
        action_state = action_start.copy()
        searched_doc_indice = []
        search_pages = []  # Shared mutable list for global search result accumulation

        # Main agent loop
        step_num = 1
        while step_num < self.n_steps_max:
            step_num += 1
            print(f"\n[Step {step_num}] Processing...")
            self.trace_collector.start_step()

            # Call LLM (use model config max_tokens via client default)
            completion = client.chat.completions.create(
                messages=action_state,
                temperature=0.2,
            )

            full_response = completion.choices[0].message.content
            tokens_used = completion.usage.total_tokens if completion.usage else 0

            # Parse response (domain module)
            parsed = parse_agent_response(full_response)

            # Record for training via builder
            if builder is not None:
                builder.record_reasoning_turn(StepCompleted(
                    action_state=action_state, response=full_response, step_number=step_num,
                ))
            else:
                action_state_for_train = []
                for turn in action_state:
                    turn_copy = turn.copy()
                    turn_copy["loss_masking"] = True
                    action_state_for_train.append(turn_copy)

                train_sample["reasoning"].append(
                    action_state_for_train + [
                        {"role": "assistant", "content": full_response, "loss_masking": False},
                    ]
                )

            # Check if final answer
            if parsed.final_answer:
                print(f"[Step {step_num}] Final answer generated")

                self.trace_collector.record_step(
                    step_type="final_answer",
                    observation=parsed.observation,
                    reasoning=parsed.reasoning,
                    step_name=parsed.step_name,
                    final_answer=parsed.final_answer,
                    tokens_used=tokens_used,
                    model_used="qwen3",
                    raw_response=full_response,
                )

                action_state.append({"role": "assistant", "content": full_response})
                break

            # Handle tool invocation
            if not parsed.tool_invoke:
                print(f"[Step {step_num}] No tool invocation found, continuing...")
                action_state.append({"role": "assistant", "content": full_response})
                continue

            tool_name = parsed.tool_invoke.name
            tool_args = parsed.tool_invoke.arguments

            print(f"[Step {step_num}] Tool: {tool_name}")

            # Execute tool
            tool_response = self._execute_tool(
                tool_name=tool_name,
                tool_args=tool_args,
                multi_docs=multi_docs,
                filenames=filenames,
                searched_doc_indice=searched_doc_indice,
                search_pages=search_pages,
                user_query=user_query,
                train_sample=train_sample,
                reasoning=parsed.reasoning or "",
                current_step=step_num,
                builder=builder,
            )

            self.trace_collector.record_step(
                step_type="tool_invoke",
                observation=parsed.observation,
                reasoning=parsed.reasoning,
                step_name=parsed.step_name,
                action=tool_name,
                action_args=tool_args,
                action_result=str(tool_response)[:500],
                tokens_used=tokens_used,
                model_used="qwen3",
                raw_response=full_response,
            )

            # Process tool output for images (output_type policy)
            tool_output = self._process_tool_output(tool_response)

            # Update action state
            action_state.append({"role": "assistant", "content": full_response})

            # Build action result message (with images if detected)
            if tool_output.has_images:
                action_result_msg = self._build_multimodal_message(tool_output)
                # Auto-switch to VL model if images detected and not already VL
                if self.reasoner_type != "vl":
                    print(f"[Step {step_num}] Image detected in tool output, auto-switching to VL model")
            else:
                action_result_msg = {"role": "user", "content": f"<action_result> {tool_response} </action_result>"}

            action_state.append(action_result_msg)

        if builder is not None:
            return builder.build()
        return train_sample

    def _process_tool_output(self, tool_response: str) -> ToolOutput:
        """Delegate to core.tool_output.parse_tool_output."""
        return parse_tool_output(tool_response)

    def _parse_images(self, images_data: List[Dict]) -> List[ImageRef]:
        """Delegate to core.tool_output.parse_images."""
        return parse_images(images_data)

    def _build_multimodal_message(self, tool_output: ToolOutput) -> Dict[str, Any]:
        """Delegate to core.tool_output.build_multimodal_message."""
        return build_multimodal_message(tool_output)

    def _execute_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        multi_docs: List[List[Dict[str, Any]]],
        filenames: List[str],
        searched_doc_indice: List[int],
        search_pages: List[Dict[str, Any]],
        user_query: str,
        train_sample: Dict[str, Any],
        reasoning: str,
        current_step: int = 0,
        builder: Optional[TrainingSampleBuilder] = None,
    ) -> str:
        """Execute a tool through the registry.

        All tools (built-in and custom) are executed via ToolRegistry.
        Sandbox mode is handled separately for deterministic stub responses.

        Args:
            builder: If provided, extraction events from _extraction_sink
                     are converted to ToolExtractionCompleted and recorded.
        """

        # Sandbox mode: return deterministic stub results
        if is_sandbox_mode():
            if tool_name == "search":
                return get_sandbox_search_results()
            elif tool_name in ["ReadFullDocument", "ReadFullText"]:
                # Record stub via builder or direct mutation
                stub_content = get_sandbox_document_extraction()
                stub_messages = [{"role": "user", "content": f"[SANDBOX] {tool_name} extraction request"}]
                if builder is not None:
                    builder.record_extraction(ToolExtractionCompleted(
                        tool_name=tool_name,
                        messages=stub_messages,
                        result=stub_content,
                    ))
                else:
                    key = "readfulldocument" if tool_name == "ReadFullDocument" else "readfulltext"
                    if key not in train_sample:
                        train_sample[key] = []
                    train_sample[key].append([
                        {"role": "user", "content": stub_messages[0]["content"], "loss_masking": True},
                        {"role": "assistant", "content": stub_content, "loss_masking": False},
                    ])
                return stub_content
            elif tool_name == "GetPage":
                return get_sandbox_search_results()
            else:
                stub_result = json.dumps({"sandbox": True, "message": f"Stub response for {tool_name}"})
                # Auto-record custom tool in sandbox mode
                if builder is not None and self.tool_registry.is_custom_tool(tool_name):
                    builder.record_extraction(ToolExtractionCompleted(
                        tool_name=tool_name,
                        messages=[{"role": "user", "content": json.dumps(tool_args, ensure_ascii=False)}],
                        result=stub_result,
                    ))
                return stub_result

        # Fresh sink per call → thread-safe (no shared mutable state)
        extraction_sink: List[Dict[str, Any]] = []

        # Build context with all necessary fields for both built-in and custom tools
        context = ToolContext(
            user_query=user_query,
            filenames=filenames,
            multi_docs=multi_docs,
            image_dir=self.image_dir,
            language="ko" if self.language.upper() == "KOREAN" else "en",
            current_step=current_step,
            tool_secrets=self.tool_secrets,
            # Built-in tools context
            model_router=self.router,
            reasoning_client=self.reasoning_client,
            selector_fn=None,  # Legacy, use selector_client instead
            selector_client=self.selector_client,
            web_search_client=self.web_search_client,
            train_sample=train_sample,
            reasoning=reasoning,
            searched_indices=searched_doc_indice,
            search_pages=search_pages,
            _extraction_sink=extraction_sink,
        )

        # Execute through registry (handles both built-in and custom tools)
        if self.tool_registry.has_tool(tool_name):
            result = self.tool_registry.execute(tool_name, tool_args, context)

            # Auto-record custom tool execution into extraction_sink
            if self.tool_registry.is_custom_tool(tool_name):
                extraction_sink.append({
                    "tool_name": tool_name,
                    "messages": [{"role": "user", "content": json.dumps(tool_args, ensure_ascii=False)}],
                    "result": result,
                })
        else:
            result = json.dumps({"error": f"Unknown tool: {tool_name}"})

        # Harvest extraction events from sink → builder
        if builder is not None:
            for ext in extraction_sink:
                builder.record_extraction(ToolExtractionCompleted(
                    tool_name=ext["tool_name"],
                    messages=ext["messages"],
                    result=ext["result"],
                ))

        return result

    def export_trace(
        self,
        session: TraceSession,
        output_path: str,
    ) -> None:
        """Export trace to JSON file"""
        trace_data = self.trace_collector.export_session(session, redact=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, ensure_ascii=False, indent=2)

        print(f"[Export] Trace saved to: {output_path}")

    def export_training(
        self,
        train_sample: Dict[str, Any],
        session: TraceSession,
        output_path: str,
    ) -> None:
        """Export training sample to JSONL"""
        export_training_sample(
            output_path=output_path,
            train_sample=train_sample,
            train_system_prompt=get_training_system_prompt(
                language=self.language,
                cur_date=self.compiler.cur_date
            ),
            runtime_prompt_hash=self.compiled_prompt.prompt_hash,
            session=session,
            language=self.language,
            override_hash=self.compiled_prompt.override_hash,
            append=True,
        )

        print(f"[Export] Training sample saved to: {output_path}")


def main():
    """Main entry point"""
    args = parse_args()

    # Enable sandbox mode if requested
    if args.sandbox:
        set_sandbox_mode(True)

    # Parse single_doc as boolean
    single_doc = args.single_doc.lower() == "true"

    # Initialize runner
    runner = AgentV2Runner(
        language=args.lang,
        single_doc=single_doc,
        n_steps_max=args.n_steps_max,
        override_patch=args.override_patch,
        model_config=args.model_config,
        verbose=args.verbose,
    )

    # Setup
    runner.setup()

    # Load documents
    multi_docs, filenames, doc_contexts = runner.load_documents(
        doc_json_path=args.doc_json_path,
        doc_json_path_2=args.doc_json_path_2,
    )

    # Determine queries to run
    if args.user_query:
        queries = [args.user_query]
    else:
        # Generate queries (simplified - just use a default for now)
        print("[Info] No --user_query provided, using default query")
        queries = ["What are the main topics covered in this document?"]

    # Run each query
    all_traces = []
    for query in queries:
        session, train_sample = runner.run_single_query(
            user_query=query,
            multi_docs=multi_docs,
            filenames=filenames,
            doc_contexts=doc_contexts,
        )

        all_traces.append(session)

        # Export training if path provided
        if args.export_training_path:
            runner.export_training(
                train_sample=train_sample,
                session=session,
                output_path=args.export_training_path,
            )

    # Export traces
    if len(all_traces) == 1:
        runner.export_trace(all_traces[0], args.export_trace_path)
    else:
        # Export as JSONL for multiple traces
        trace_path = Path(args.export_trace_path)
        if trace_path.suffix == ".json":
            trace_path = trace_path.with_suffix(".jsonl")

        with open(trace_path, "w", encoding="utf-8") as f:
            for session in all_traces:
                trace_data = runner.trace_collector.export_session(session, redact=True)
                f.write(json.dumps(trace_data, ensure_ascii=False) + "\n")

        print(f"[Export] Traces saved to: {trace_path}")

    # Print usage summary
    usage = runner.router.get_all_usage()
    print("\n[Summary] Model usage:")
    for model, stats in usage.items():
        print(f"  {model}: {stats['calls']} calls, {stats['tokens']} tokens")


if __name__ == "__main__":
    main()
