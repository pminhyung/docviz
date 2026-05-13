"""
API Handlers for Document Agent V2

Contains handler classes for processing API requests.
"""

import asyncio
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.api.schemas import (
    RunRequestV2,
    RunResponseV2,
    StepReasoning,
    ValidateRequest,
    ValidateResponse,
    ValidationStats,
    FinalizeSessionRequest,
    FinalizeSessionResponse,
)
from agent.core.output_validator import OutputValidator, ValidationResult
from agent.core.tool_registry import ToolRegistry
from agent.core.session_manager import get_session_manager, SessionNotFoundError
from agent.core.gcs_uploader import upload_to_gcs, GCSUploadError
from agent.core.request_logger import get_request_logger
from agent.export.training_jsonl import convert_base_train_sample, convert_base_train_sample_v1
from agent.run_agent_v2 import AgentV2Runner

# Redaction constant
SYSTEM_PROMPT_REDACTED = "__SYSTEM_PROMPT_REDACTED__"


class AgentHandler:
    """
    Handler for /v2/run endpoint.

    Wraps AgentV2Runner with async execution and response building.
    """

    def __init__(self, max_workers: int = 4):
        """
        Initialize the handler.

        Args:
            max_workers: Maximum thread pool workers for blocking operations
        """
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    async def run(self, request: RunRequestV2, admin_secret: Optional[str] = None) -> RunResponseV2:
        """
        Run the agent for a single query.

        Args:
            request: The run request

        Returns:
            RunResponseV2 with results
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._run_sync,
            request,
            admin_secret,
        )

    def _run_sync(self, request: RunRequestV2, admin_secret: Optional[str] = None) -> RunResponseV2:
        """
        Synchronous agent execution.

        Args:
            request: The run request
            admin_secret: Optional admin secret from X-Admin-Secret header

        Returns:
            RunResponseV2 with results
        """
        start_time = time.time()

        # Resolve API keys: client-provided or admin-mode auto-resolution
        reasoner_api_key = request.reasoner_api_key
        extraction_api_key = request.extraction_api_key

        if not reasoner_api_key:
            if not self._verify_admin_secret(admin_secret):
                raise ValueError(
                    "reasoner_api_key is required. Provide it in the request body, "
                    "or use X-Admin-Secret header for internal use."
                )
            reasoner_api_key, extraction_api_key = self._resolve_admin_keys(
                request.reasoner_model_name, request.reasoner_type, extraction_api_key
            )

        # Normalize language
        lang = request.lang
        if lang == "ko":
            lang = "KOREAN"
        elif lang == "en":
            lang = "ENGLISH"

        # Load custom tools if provided
        custom_tools = None
        tool_registry = None
        if request.custom_tools_path:
            tool_registry = ToolRegistry()
            loaded_names = tool_registry.load_from_file(request.custom_tools_path)
            custom_tools = tool_registry.get_tools_for_prompt()

        # Initialize runner
        runner = AgentV2Runner(
            language=lang,
            single_doc=request.single_doc,
            n_steps_max=request.n_steps_max,
            override_patch=request.override_patch_path,
            model_config=request.model_config_path,
            verbose=False,
            custom_tools=custom_tools,
            custom_rules=request.custom_rules,
            tool_registry=tool_registry,
            tool_secrets=request.tool_secrets,
            reasoner_type=request.reasoner_type,
            reasoner_model_name=request.reasoner_model_name,
            reasoner_api_key=reasoner_api_key,
            reasoner_base_url=getattr(request, 'reasoner_base_url', None),
            reasoner_model_max_length=request.reasoner_model_max_length,
            extraction_api_key=extraction_api_key,
        )

        # Setup
        runner.setup()

        # Build image_dirs list if provided
        image_dirs = None
        if request.doc_image_dir:
            image_dirs = [request.doc_image_dir]

        # Load documents — N-way multi-doc takes precedence over the legacy
        # single/dual-path fields.
        multi_docs, filenames, doc_contexts = runner.load_documents(
            doc_json_path=request.doc_json_path,
            doc_json_path_2=request.doc_json_path_2,
            image_dir=request.doc_image_dir,
            doc_json_paths=request.doc_json_paths,
        )

        # Run query
        session, train_sample = runner.run_single_query(
            user_query=request.user_query,
            multi_docs=multi_docs,
            filenames=filenames,
            doc_contexts=doc_contexts,
        )

        # Get trace data (redacted)
        trace_data = runner.trace_collector.export_session(session, redact=request.redact_args)

        # Validate output
        validator = OutputValidator(
            language=lang,
            has_documents=len(filenames) > 0
        )
        validation_result = validator.validate_trace(trace_data)

        # Handle session accumulation
        accumulation_session_id = None
        session_sample_count = None
        if request.session_id:
            train_version = getattr(request, 'train_sample_version', 'v1')

            if train_version == 'v2':
                # v2 admin format: full metadata
                v2_sample = convert_base_train_sample(
                    base_train_sample=train_sample,
                    train_system_prompt=runner.compiled_prompt.training_prompt,
                    runtime_prompt_hash=runner.compiled_prompt.prompt_hash,
                    session=session,
                    language=lang,
                    override_hash=runner.compiled_prompt.override_hash,
                    metadata={
                        "custom_tools": [t["name"] for t in custom_tools] if custom_tools else [],
                        "has_custom_rules": bool(request.custom_rules),
                    }
                )
                sample_dict = v2_sample.to_dict()
            else:
                # v1 default format: 7 keys + train_system_prompt + custom keys
                sample_dict = convert_base_train_sample_v1(
                    base_train_sample=train_sample,
                    train_system_prompt=runner.compiled_prompt.training_prompt,
                )

            session_manager = get_session_manager()
            session_sample_count = session_manager.append_sample(
                request.session_id,
                sample_dict,
            )
            accumulation_session_id = request.session_id

        # Calculate duration
        duration = time.time() - start_time

        # Silent logging to GCS (non-blocking)
        try:
            # Prepare train_sample for logging
            if request.session_id:
                log_train_sample = sample_dict
            else:
                # Convert to v2 format for logging (always use v2 for internal logs)
                v2_sample_for_log = convert_base_train_sample(
                    base_train_sample=train_sample,
                    train_system_prompt=runner.compiled_prompt.training_prompt,
                    runtime_prompt_hash=runner.compiled_prompt.prompt_hash,
                    session=session,
                    language=lang,
                    override_hash=runner.compiled_prompt.override_hash,
                    metadata={
                        "custom_tools": [t["name"] for t in custom_tools] if custom_tools else [],
                        "has_custom_rules": bool(request.custom_rules),
                    }
                )
                log_train_sample = v2_sample_for_log.to_dict()

            request_logger = get_request_logger()
            request_logger.log_request(
                request_payload=request.model_dump(),
                custom_tools_path=request.custom_tools_path,
                train_sample=log_train_sample,
                session_id=request.session_id,
                request_id=trace_data.get("session_id")
            )
        except Exception:
            pass  # Silent fail - logging should not affect main response

        # Build response
        return self._build_response(
            session=session,
            trace_data=trace_data,
            train_sample=train_sample,
            validation_result=validation_result,
            return_trace=request.return_trace,
            return_train_sample=request.return_train_sample,
            inputs_used=len(filenames),
            duration=duration,
            accumulation_session_id=accumulation_session_id,
            session_sample_count=session_sample_count,
        )

    def _build_response(
        self,
        session,
        trace_data: Dict[str, Any],
        train_sample: Dict[str, Any],
        validation_result: ValidationResult,
        return_trace: bool,
        return_train_sample: bool,
        inputs_used: int,
        duration: float = 0.0,
        accumulation_session_id: Optional[str] = None,
        session_sample_count: Optional[int] = None,
    ) -> RunResponseV2:
        """
        Build the API response from agent results.

        Args:
            session: TraceSession object
            trace_data: Exported trace dict
            train_sample: Training sample dict
            validation_result: Validation result
            return_trace: Whether to include trace
            return_train_sample: Whether to include train_sample
            inputs_used: Count of document inputs
            duration: Total execution time in seconds
            accumulation_session_id: Session ID if accumulating samples
            session_sample_count: Current sample count in session

        Returns:
            RunResponseV2
        """
        # Extract final answer
        final_answer = ""
        for step in reversed(trace_data.get("steps", [])):
            if step.get("final_answer"):
                final_answer = step["final_answer"]
                break

        # Build steps reasoning
        steps_reasoning = []
        for step in trace_data.get("steps", []):
            action = None
            if step.get("action"):
                action = {
                    "name": step["action"],
                    "arguments": step.get("action_args", {})
                }

            steps_reasoning.append(StepReasoning(
                step_number=step.get("step_number", 0),
                step_type=step.get("step_type", "unknown"),
                step_name=step.get("step_name", ""),
                action=action,
                duration=step.get("duration_seconds", 0.0),
            ))

        # Prepare optional fields
        trace_out = None
        if return_trace:
            trace_out = self._redact_system_content(trace_data)

        train_sample_out = None
        if return_train_sample:
            train_sample_out = self._redact_train_sample(train_sample)

        return RunResponseV2(
            final_answer=final_answer,
            steps_reasoning=steps_reasoning,
            inputs_used=inputs_used,
            train_sample=train_sample_out,
            trace=trace_out,
            warnings=validation_result.warnings,
            session_id=trace_data.get("session_id", ""),
            total_tokens=trace_data.get("total_tokens", 0),
            total_duration_seconds=duration,
            num_steps=len(steps_reasoning),
            success=trace_data.get("success", False),
            error=trace_data.get("error"),
            accumulation_session_id=accumulation_session_id,
            session_sample_count=session_sample_count,
        )

    @staticmethod
    def _verify_admin_secret(secret: Optional[str]) -> bool:
        """Verify the admin secret against server-side env."""
        expected = os.environ.get("DOCVIZ_AGENT_ADMIN_SECRET")
        if not expected or not secret:
            return False
        return secret == expected

    @staticmethod
    def _resolve_admin_keys(model_name, reasoner_type, extraction_api_key):
        """
        Admin mode: resolve model API keys from .env file.

        Same pattern as e2e_helpers.py:67-83. Reads .env directly
        (not os.environ) since model keys are not loaded at startup.
        """
        try:
            from dotenv import dotenv_values
        except ImportError:
            return "", extraction_api_key

        env_path = Path(__file__).parent.parent.parent / ".env"
        env_vals = dotenv_values(env_path) if env_path.exists() else {}

        effective_model = model_name or (
            "qwen/qwen2.5-vl-72b-instruct" if reasoner_type == "vl" else "gpt-5.2"
        )
        if effective_model == "qwen_onpremise":
            reasoner_key = "EMPTY"
        elif effective_model.startswith("gpt-"):
            reasoner_key = env_vals.get("OPENAI_API_KEY", "")
        else:
            reasoner_key = env_vals.get("NOVITA_API_KEY", "")

        # GPT reasoner → extraction models (qwen3) need Novita key
        if not extraction_api_key and effective_model.startswith("gpt-"):
            extraction_api_key = env_vals.get("NOVITA_API_KEY", "")

        return reasoner_key, extraction_api_key

    @staticmethod
    def _redact_system_content(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Redact system prompts from trace data.

        Args:
            data: Trace data dict

        Returns:
            Redacted copy
        """
        redacted = data.copy()

        # Redact raw_response fields that might contain system prompts
        if "steps" in redacted:
            for step in redacted["steps"]:
                if "raw_response" in step:
                    step["raw_response"] = SYSTEM_PROMPT_REDACTED

        # Redact any prompt-related fields
        for key in ["runtime_prompt", "system_prompt", "prompt"]:
            if key in redacted:
                redacted[key] = SYSTEM_PROMPT_REDACTED

        return redacted

    @staticmethod
    def _redact_train_sample(train_sample: Dict[str, Any]) -> Dict[str, Any]:
        """
        Redact system content from train_sample.

        Preserves original field structure but removes runtime prompt content.

        Args:
            train_sample: Training sample dict

        Returns:
            Redacted copy
        """
        redacted = train_sample.copy()

        # Redact system messages in reasoning turns
        if "reasoning" in redacted:
            for step_turns in redacted.get("reasoning", []):
                for turn in step_turns:
                    if turn.get("role") == "system":
                        turn["content"] = SYSTEM_PROMPT_REDACTED

        # Preserve required fields
        required_fields = [
            "df_idx", "user_query", "filenames", "reasoning",
            "readfulldocument", "readfulltext", "doc_step"
        ]

        # Ensure all required fields exist
        for field in required_fields:
            if field not in redacted:
                if field in ["reasoning", "readfulldocument", "readfulltext", "doc_step"]:
                    redacted[field] = []
                elif field == "filenames":
                    redacted[field] = []
                elif field == "df_idx":
                    redacted[field] = 0
                elif field == "user_query":
                    redacted[field] = ""

        return redacted


class ValidationHandler:
    """
    Handler for /v2/validate endpoint.

    Validates traces or raw output.
    """

    def validate(self, request: ValidateRequest) -> ValidateResponse:
        """
        Validate a trace or raw output.

        Args:
            request: Validation request

        Returns:
            ValidateResponse with results
        """
        validator = OutputValidator(
            language=request.language,
            has_documents=request.has_documents
        )

        if request.trace is not None:
            # Validate trace
            constraints_dict = None
            if request.constraints:
                constraints_dict = request.constraints.model_dump(exclude_none=True)

            result = validator.validate_trace(
                trace=request.trace,
                constraints=constraints_dict
            )
        elif request.raw_output is not None:
            # Validate raw output
            result = validator.validate_response(
                response=request.raw_output,
                step_history=None
            )
        else:
            # Neither provided - error
            return ValidateResponse(
                ok=False,
                errors=["Must provide either 'trace' or 'raw_output'"],
                warnings=[],
                stats=ValidationStats(
                    steps_count=0,
                    tool_invoke_count=0,
                    citation_count=0
                )
            )

        return ValidateResponse(
            ok=result.ok,
            errors=result.errors,
            warnings=result.warnings,
            stats=ValidationStats(
                steps_count=result.stats.get("steps_count", 0),
                tool_invoke_count=result.stats.get("tool_invoke_count", 0),
                citation_count=result.stats.get("citation_count", 0)
            )
        )


class FinalizeSessionHandler:
    """
    Handler for /v2/finalize_session endpoint.

    Finalizes a session and uploads the accumulated JSONL to GCS.
    """

    def finalize(self, request: FinalizeSessionRequest) -> FinalizeSessionResponse:
        """
        Finalize a session and upload to GCS.

        Args:
            request: Finalization request with session_id

        Returns:
            FinalizeSessionResponse with upload results
        """
        session_manager = get_session_manager()

        try:
            # Get sample count before finalization
            sample_count = session_manager.get_sample_count(request.session_id)

            if sample_count == 0:
                return FinalizeSessionResponse(
                    session_id=request.session_id,
                    sample_count=0,
                    gcs_path="",
                    success=False,
                    error="Session not found or empty"
                )

            # Get local JSONL path
            local_path = session_manager.finalize(request.session_id)

            # Upload to GCS
            gcs_path = upload_to_gcs(
                local_path=local_path,
                session_id=request.session_id
            )

            # Clean up local files
            session_manager.cleanup(request.session_id)

            return FinalizeSessionResponse(
                session_id=request.session_id,
                sample_count=sample_count,
                gcs_path=gcs_path,
                success=True
            )

        except SessionNotFoundError as e:
            return FinalizeSessionResponse(
                session_id=request.session_id,
                sample_count=0,
                gcs_path="",
                success=False,
                error=str(e)
            )

        except GCSUploadError as e:
            return FinalizeSessionResponse(
                session_id=request.session_id,
                sample_count=session_manager.get_sample_count(request.session_id),
                gcs_path="",
                success=False,
                error=f"GCS upload failed: {e}"
            )

        except Exception as e:
            return FinalizeSessionResponse(
                session_id=request.session_id,
                sample_count=0,
                gcs_path="",
                success=False,
                error=f"Finalization failed: {e}"
            )
