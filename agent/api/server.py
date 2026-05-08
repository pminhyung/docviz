"""
FastAPI Server for Document Agent V2

Production-oriented API for running the document agent.

Usage:
    uvicorn agent.api.server:app --host 0.0.0.0 --port 9024

Environment Variables (auto-loaded from .env via whitelist):
    BRAVE_KEYS: JSON array of Brave Search API keys (for web search)
    SERPAPI_KEY: SerpAPI key (for DuckDuckGo fallback)
    DOCVIZ_AGENT_ADMIN_SECRET: Admin secret for internal key auto-resolution
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Auto-load ONLY infrastructure env vars from .env (not model API keys).
# Model API keys (OPENAI_API_KEY, NOVITA_API_KEY, etc.) must come from
# client request body (reasoner_api_key), or via X-Admin-Secret header.
_SERVER_ENV_WHITELIST = {
    "BRAVE_KEYS",
    "SERPAPI_KEY",
    "GW_STG_SELECTOR_URL",
    "WEB_SEARCH_PROXY",
    "VLLM_BASE_URL",
    "DOCVIZ_AGENT_ADMIN_SECRET",
}

_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    try:
        from dotenv import dotenv_values
        _env_vals = dotenv_values(_env_path)
        for key, val in _env_vals.items():
            if key in _SERVER_ENV_WHITELIST and val is not None:
                os.environ.setdefault(key, val)
    except ImportError:
        pass  # python-dotenv not installed; rely on shell env

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.api.schemas import (
    HealthResponse,
    RunRequestV2,
    RunResponseV2,
    ValidateRequest,
    ValidateResponse,
    FinalizeSessionRequest,
    FinalizeSessionResponse,
)
from agent.api.handlers import AgentHandler, ValidationHandler, FinalizeSessionHandler
from agent.core.sandbox import is_sandbox_mode, set_sandbox_mode

# API version
API_VERSION = "2.0.0"

# Initialize FastAPI app
app = FastAPI(
    title="Document Agent V2 API",
    description="Production API for Document Agent V2 - Document analysis with reasoning",
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize handlers
agent_handler = AgentHandler()
validation_handler = ValidationHandler()
finalize_session_handler = FinalizeSessionHandler()


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.

    Returns server status, API version, model availability, and sandbox mode.
    """
    sandbox = is_sandbox_mode()

    # Model API keys are provided per-request by clients (not loaded server-side)
    models_available = True

    return HealthResponse(
        status="healthy",
        version=API_VERSION,
        models_available=models_available,
        sandbox_mode=sandbox,
    )


@app.post("/v2/run", response_model=RunResponseV2, tags=["Agent"])
async def run_agent(
    request: RunRequestV2,
    x_admin_secret: Optional[str] = Header(default=None),
):
    """
    Run the document agent for a single query.

    This endpoint executes the full agent loop:
    1. Loads documents from the specified path
    2. Generates document summary
    3. Runs reasoning loop with tool invocations
    4. Returns final answer with reasoning trace

    **Request Fields:**
    - `doc_json_path`: Path to document JSON file (required)
    - `doc_json_path_2`: Optional second document path
    - `single_doc`: Single document mode (default: true)
    - `lang`: Output language - ENGLISH or KOREAN (default: ENGLISH)
    - `user_query`: Question to answer (required)
    - `override_patch_path`: Optional YAML patch file path
    - `model_config_path`: Optional model config YAML path
    - `n_steps_max`: Maximum agent steps (default: 20)
    - `return_trace`: Include full trace in response
    - `return_train_sample`: Include training sample in response

    **Response Fields:**
    - `final_answer`: The agent's answer
    - `steps_reasoning`: List of reasoning steps
    - `inputs_used`: Count of documents used
    - `warnings`: Validation warnings
    - `session_id`: Unique session ID
    - `total_tokens`: Tokens used
    - `success`: Whether agent completed successfully

    **Security Note:**
    System prompts are never included in responses.
    """
    # Validate document path exists
    if not os.path.exists(request.doc_json_path):
        raise HTTPException(
            status_code=400,
            detail=f"Document path not found: {request.doc_json_path}"
        )

    if request.doc_json_path_2 and not os.path.exists(request.doc_json_path_2):
        raise HTTPException(
            status_code=400,
            detail=f"Second document path not found: {request.doc_json_path_2}"
        )

    if request.override_patch_path and not os.path.exists(request.override_patch_path):
        raise HTTPException(
            status_code=400,
            detail=f"Override patch path not found: {request.override_patch_path}"
        )

    if request.model_config_path and not os.path.exists(request.model_config_path):
        raise HTTPException(
            status_code=400,
            detail=f"Model config path not found: {request.model_config_path}"
        )

    if request.custom_tools_path and not os.path.exists(request.custom_tools_path):
        raise HTTPException(
            status_code=400,
            detail=f"Custom tools path not found: {request.custom_tools_path}"
        )

    if request.doc_image_dir and not os.path.isdir(request.doc_image_dir):
        raise HTTPException(
            status_code=400,
            detail=f"Image directory not found: {request.doc_image_dir}"
        )

    try:
        response = await agent_handler.run(request, admin_secret=x_admin_secret)
        return response

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        # Log the error (in production, use proper logging)
        import traceback
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {str(e)}"
        )


@app.post("/v2/validate", response_model=ValidateResponse, tags=["Validation"])
async def validate_output(request: ValidateRequest):
    """
    Validate a trace or raw LLM output.

    Checks for:
    - Format compliance (tool_invoke or final_answer tags)
    - Policy adherence (document actions before final answer)
    - Language consistency (Hangul ratio, polite endings)

    **Request Fields:**
    - `trace`: Trace object to validate (OR raw_output)
    - `raw_output`: Raw LLM text to validate (OR trace)
    - `constraints`: Optional validation constraints
    - `language`: Expected language (default: ENGLISH)
    - `has_documents`: Whether documents were provided (default: true)

    **Response Fields:**
    - `ok`: True if no errors (warnings may still exist)
    - `errors`: List of validation errors
    - `warnings`: List of validation warnings
    - `stats`: Validation statistics (steps_count, tool_invoke_count, citation_count)
    """
    if request.trace is None and request.raw_output is None:
        raise HTTPException(
            status_code=400,
            detail="Must provide either 'trace' or 'raw_output'"
        )

    try:
        response = validation_handler.validate(request)
        return response

    except Exception as e:
        import traceback
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Validation failed: {str(e)}"
        )


@app.post("/v2/finalize_session", response_model=FinalizeSessionResponse, tags=["Session"])
async def finalize_session(request: FinalizeSessionRequest):
    """
    Finalize a session and upload accumulated training samples to GCS.

    Use this after accumulating training samples via multiple /v2/run requests
    with the same session_id.

    **Request Fields:**
    - `session_id`: Session ID to finalize and upload

    **Response Fields:**
    - `session_id`: The finalized session ID
    - `sample_count`: Total number of training samples
    - `gcs_path`: GCS path where the JSONL was uploaded
    - `success`: Whether finalization succeeded
    - `error`: Error message if failed

    **Example Workflow:**
    1. Send multiple /v2/run requests with `session_id: "my_batch_123"`
    2. Call /v2/finalize_session with `session_id: "my_batch_123"`
    3. Receive GCS path with all accumulated training samples
    """
    try:
        response = finalize_session_handler.finalize(request)
        return response

    except Exception as e:
        import traceback
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Session finalization failed: {str(e)}"
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler to ensure clean error responses."""
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": type(exc).__name__,
        }
    )


# Entry point for direct execution
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9024)
