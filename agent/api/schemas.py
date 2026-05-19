"""
API Schemas for Document Agent V2

Pydantic models for request/response validation.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class StepReasoning(BaseModel):
    """Single reasoning step in the agent trace"""
    step_number: int = Field(description="Sequential step number")
    step_type: str = Field(description="Type of step (reasoning, tool_call, etc.)")
    step_name: str = Field(default="", description="Name/description of the step")
    action: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Action taken (tool name and arguments)"
    )
    duration: float = Field(description="Duration in seconds")


class ValidationStats(BaseModel):
    """Statistics from output validation"""
    steps_count: int = Field(description="Total number of steps in trace")
    tool_invoke_count: int = Field(description="Number of tool invocations")
    citation_count: int = Field(description="Number of [N] citation patterns in final_answer")


class ValidationConstraints(BaseModel):
    """Optional constraints for validation"""
    max_steps: Optional[int] = Field(
        default=None,
        description="Maximum allowed steps"
    )
    required_tools: Optional[List[str]] = Field(
        default=None,
        description="List of tools that must be used"
    )
    min_citations: Optional[int] = Field(
        default=None,
        description="Minimum required citations"
    )


# ============================================================================
# Run Endpoint Schemas
# ============================================================================


class RunRequestV2(BaseModel):
    """Request body for /v2/run endpoint"""

    doc_json_path: str = Field(
        description="Path to document JSON file (required)"
    )
    doc_json_path_2: Optional[str] = Field(
        default=None,
        description="Path to second document JSON file (for multi-doc)"
    )
    doc_json_paths: Optional[List[str]] = Field(
        default=None,
        description="Paths to N document JSON files (for N-way multi-doc). "
                    "If provided, takes precedence over doc_json_path / doc_json_path_2 "
                    "and forces single_doc=False so each path is loaded as its own document. "
                    "Use this for bundle workflows where the input is a collection of "
                    "distinct source documents (e.g., arXiv papers, 10-K sections) and "
                    "the agent should see each as a separate document with its own "
                    "title, snippet, and document_number for search/RFD."
    )
    doc_image_dir: Optional[str] = Field(
        default=None,
        description="Path to image directory for docai format documents"
    )
    single_doc: bool = Field(
        default=True,
        description="Whether to process as single document mode"
    )
    lang: Literal["ko", "en"] = Field(
        default="en",
        description="Output language ('ko' for Korean, 'en' for English)"
    )
    user_query: str = Field(
        description="User query to answer (required)"
    )
    override_patch_path: Optional[str] = Field(
        default=None,
        description="Path to YAML override patch file"
    )
    model_config_path: Optional[str] = Field(
        default=None,
        description="Path to model configuration YAML file"
    )
    n_steps_max: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of agent steps"
    )
    export_training_jsonl: bool = Field(
        default=False,
        description="Whether to export training JSONL file"
    )
    return_trace: bool = Field(
        default=False,
        description="Whether to include full trace in response"
    )
    return_train_sample: bool = Field(
        default=False,
        description="Whether to include train_sample in response"
    )

    # Custom tool extension
    custom_tools_path: Optional[str] = Field(
        default=None,
        description="Path to .py file containing custom tool classes"
    )

    # Custom rules extension
    custom_rules: Optional[str] = Field(
        default=None,
        description="Additional rules to inject (format: '- rule1\\n- rule2...')"
    )

    # Session-based accumulation
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for accumulating training samples"
    )

    # Tool secrets (generic key-value pairs for custom tools)
    tool_secrets: Optional[Dict[str, str]] = Field(
        default=None,
        description="Secret values for custom tools (e.g., API keys). Passed to tools via context['tool_secrets']"
    )

    # Reasoner configuration
    reasoner_type: Literal["llm", "vl"] = Field(
        default="llm",
        description="Reasoner type: 'llm' for text-only, 'vl' for vision-language (supports image input)"
    )
    reasoner_model_name: str = Field(
        default="gpt-5.2",
        description="Model name for reasoning. Default: gpt-5.2 (OpenAI). Prefix 'gpt-' uses OpenAI API, 'local/' uses vLLM, 'qwen_onpremise' uses on-premise Qwen 3.5, otherwise Novita API."
    )
    reasoner_api_key: Optional[str] = Field(
        default=None,
        description="API key for reasoning model. Required for external clients. "
                    "Can be omitted when using X-Admin-Secret header for internal use."
    )
    extraction_api_key: Optional[str] = Field(
        default=None,
        description="API key for extraction/builtin models (e.g., Novita key). Required when reasoner uses a different provider (e.g., GPT reasoner + Novita extraction). If None, uses reasoner_api_key."
    )
    reasoner_base_url: Optional[str] = Field(
        default=None,
        description="Explicit base URL for reasoning model. Overrides auto-detection. Use for local vLLM (e.g., 'http://localhost:8000/v1')."
    )
    reasoner_model_max_length: Optional[int] = Field(
        default=None,
        description="Override max output tokens for reasoner model. None uses model default (gpt-5.2: 32768, Novita: 16384)."
    )

    # Training sample format version (hidden, admin-only for v2)
    train_sample_version: Literal["v1", "v2"] = Field(
        default="v1",
        description="Training sample format: 'v1' (default, 7 keys + train_system_prompt + custom keys) or 'v2' (admin, adds metadata fields)"
    )

    # Trace redaction control — default-on for external API safety; orchestrators
    # that are both producer and consumer of the trace (e.g., this repo's
    # pipeline → judge chain) can opt-out to see actual tool arguments,
    # specifically the `search.query` array and `ReadFullDocument.goal` text,
    # which the downstream judge needs for the retrieval-query-quality axis.
    redact_args: bool = Field(
        default=True,
        description="Whether to redact tool `action_args` and truncate `action_result` in the returned trace. "
                    "Default True (backward compat / external API safety). Set False for internal pipelines that "
                    "need the actual search queries and RFD goals downstream (e.g., judge scoring)."
    )

    skip_doc_step: bool = Field(
        default=False,
        description="When True, skip the doc-summary LLM call (Step 1) and set the agent's first user-turn "
                    "'Internal Documents' overview' to an empty string. Used by the v0.3 Layer D −CIS pillar "
                    "ablation to ablate the Cross-doc Iterative Search (CIS) pillar without confounding "
                    "long-context tolerance with retrieval contribution. Honest abstention vs raw-concat "
                    "substitution per paper §7 Layer D notes."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "doc_json_path": "/path/to/document.json",
                    "user_query": "Summarize this document",
                    "lang": "en",
                    "n_steps_max": 20,
                    "reasoner_api_key": "your-openai-api-key-here",
                    "return_trace": False
                },
                {
                    "doc_json_path": "/path/to/docai/out/category/hash.json",
                    "doc_image_dir": "/path/to/docai/out/img/category/hash/",
                    "user_query": "Analyze the chart on page 4",
                    "custom_tools_path": "/path/to/vl_tools.py",
                    "custom_rules": "- When analyzing charts, use analyze_chart tool first",
                    "session_id": "batch_20240223",
                    "reasoner_type": "vl",
                    "reasoner_model_name": "qwen/qwen2.5-vl-72b-instruct",
                    "reasoner_api_key": "your-novita-api-key-here",
                    "reasoner_model_max_length": 16384
                }
            ]
        }
    }


class RunResponseV2(BaseModel):
    """Response body for /v2/run endpoint"""

    final_answer: str = Field(
        description="The agent's final answer"
    )
    steps_reasoning: List[StepReasoning] = Field(
        description="List of reasoning steps (step_number, step_type, step_name, action, duration)"
    )
    inputs_used: int = Field(
        description="Count of document inputs used (not content)"
    )
    train_sample: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Training sample if return_train_sample=true"
    )
    trace: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Full trace if return_trace=true"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Validation warnings from output validator"
    )
    session_id: str = Field(
        description="Unique request session identifier"
    )
    total_tokens: int = Field(
        description="Total tokens used in session"
    )
    total_duration_seconds: float = Field(
        default=0.0,
        description="Total execution time in seconds"
    )
    num_steps: int = Field(
        default=0,
        description="Number of agent steps taken"
    )
    success: bool = Field(
        description="Whether the agent completed successfully"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if success=false"
    )

    # Session accumulation info (when session_id is specified in request)
    accumulation_session_id: Optional[str] = Field(
        default=None,
        description="Accumulation session ID if specified in request"
    )
    session_sample_count: Optional[int] = Field(
        default=None,
        description="Current sample count in accumulation session"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "final_answer": "The document discusses...",
                    "steps_reasoning": [
                        {
                            "step_number": 1,
                            "step_type": "reasoning",
                            "step_name": "Reading document",
                            "action": {"name": "ReadFullDocument", "arguments": {"filename": "doc.pdf"}},
                            "duration": 1.5
                        }
                    ],
                    "inputs_used": 1,
                    "warnings": [],
                    "session_id": "abc-123-def",
                    "total_tokens": 1500,
                    "total_duration_seconds": 45.2,
                    "num_steps": 4,
                    "success": True,
                    "accumulation_session_id": "batch_20240223",
                    "session_sample_count": 3
                }
            ]
        }
    }


# ============================================================================
# Validate Endpoint Schemas
# ============================================================================


class ValidateRequest(BaseModel):
    """Request body for /v2/validate endpoint"""

    trace: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Trace object to validate (mutually exclusive with raw_output)"
    )
    raw_output: Optional[str] = Field(
        default=None,
        description="Raw LLM text to validate (mutually exclusive with trace)"
    )
    constraints: Optional[ValidationConstraints] = Field(
        default=None,
        description="Optional validation constraints"
    )
    language: Literal["ENGLISH", "KOREAN"] = Field(
        default="ENGLISH",
        description="Expected language for validation"
    )
    has_documents: bool = Field(
        default=True,
        description="Whether documents were provided (affects policy checks)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "raw_output": "<reasoning>test</reasoning><final_answer>answer</final_answer>",
                    "language": "ENGLISH"
                },
                {
                    "trace": {"steps": [], "success": True},
                    "constraints": {"min_citations": 1}
                }
            ]
        }
    }


class ValidateResponse(BaseModel):
    """Response body for /v2/validate endpoint"""

    ok: bool = Field(
        description="Whether validation passed (no errors)"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="List of validation errors"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="List of validation warnings"
    )
    stats: ValidationStats = Field(
        description="Validation statistics"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ok": True,
                    "errors": [],
                    "warnings": ["No document action found before final_answer"],
                    "stats": {
                        "steps_count": 3,
                        "tool_invoke_count": 2,
                        "citation_count": 1
                    }
                }
            ]
        }
    }


# ============================================================================
# Health Endpoint Schemas
# ============================================================================


class HealthResponse(BaseModel):
    """Response body for /health endpoint"""

    status: str = Field(description="Health status")
    version: str = Field(description="API version")
    models_available: bool = Field(description="Whether model clients are configured")
    sandbox_mode: bool = Field(
        default=False,
        description="Whether sandbox mode is enabled (no external API calls)"
    )


# ============================================================================
# Session Finalization Schemas
# ============================================================================


class FinalizeSessionRequest(BaseModel):
    """Request body for /v2/finalize_session endpoint"""

    session_id: str = Field(
        description="Session ID to finalize and upload"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "batch_20240223"
                }
            ]
        }
    }


class FinalizeSessionResponse(BaseModel):
    """Response body for /v2/finalize_session endpoint"""

    session_id: str = Field(
        description="Session ID that was finalized"
    )
    sample_count: int = Field(
        description="Total number of samples in the session"
    )
    gcs_path: str = Field(
        description="GCS path where the JSONL was uploaded"
    )
    success: bool = Field(
        description="Whether finalization succeeded"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if success=false"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "batch_20240223",
                    "sample_count": 50,
                    "gcs_path": "gs://mhpark_bucket/reasoning_api_output/batch_20240223/train.jsonl",
                    "success": True
                }
            ]
        }
    }
