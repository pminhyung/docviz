"""
Core module for Document Agent V2

Contains:
- selector_client: gw-stg selector (Format B) for document page selection
- web_search_client: Manager + SerpAPI web search with cache
- prompt_compiler: Compile prompts from blocks + YAML patches
- patch_validator: Validate YAML patches
- model_router: Role-based model routing + ToolOutput/ImageRef
- trace_collector: Step-by-step trace with redaction
- document_loader: Load docs from JSON file paths
- output_validator: Validate agent output for format, policy, language
- tool_actions: Tool context and type definitions
- tool_registry: Dynamic tool loading and execution (with override support)
- session_manager: Session-based JSONL accumulation
- gcs_uploader: GCS upload functionality
- request_logger: Silent request/response logging to GCS
"""

from .prompt_compiler import PromptCompiler, CompiledPrompt
from .patch_validator import PatchValidator, PatchValidationError
from .model_router import ModelRole, ModelRouter, ProxyClient, ModelConfig, ToolOutput, ImageRef
from .trace_collector import TraceCollector, TraceSession, TraceStep
from .document_loader import DocumentLoader, DocumentFormat
from .output_validator import OutputValidator, ValidationResult
from .sandbox import (
    is_sandbox_mode,
    set_sandbox_mode,
    SandboxProxyClient,
    get_sandbox_search_results,
    get_sandbox_document_extraction,
)
from .tool_actions import ToolContext, TOOL_TYPE_SEARCH, TOOL_TYPE_INFERENCE
from .tool_registry import ToolRegistry, ToolValidationError, ToolExecutionError
from .builtin_tools import (
    SearchTool,
    ReadFullDocumentTool,
    GetPageTool,
    ReadFullTextTool,
    BUILTIN_TOOL_CLASSES,
)
from .base_tool import BaseTool
from .session_manager import SessionManager, get_session_manager, SessionNotFoundError
from .gcs_uploader import upload_to_gcs, GCSUploadError, check_gcs_available
from .request_logger import RequestLogger, get_request_logger, log_request
from .selector_client import SelectorClient
from .web_search_client import WebSearchClient, PageContent

__all__ = [
    # prompt_compiler
    "PromptCompiler",
    "CompiledPrompt",
    # patch_validator
    "PatchValidator",
    "PatchValidationError",
    # model_router
    "ModelRole",
    "ModelRouter",
    "ProxyClient",
    "ModelConfig",
    "ToolOutput",
    "ImageRef",
    # trace_collector
    "TraceCollector",
    "TraceSession",
    "TraceStep",
    # document_loader
    "DocumentLoader",
    "DocumentFormat",
    # output_validator
    "OutputValidator",
    "ValidationResult",
    # sandbox
    "is_sandbox_mode",
    "set_sandbox_mode",
    "SandboxProxyClient",
    "get_sandbox_search_results",
    "get_sandbox_document_extraction",
    # tool_actions
    "ToolContext",
    "TOOL_TYPE_SEARCH",
    "TOOL_TYPE_INFERENCE",
    # tool_registry
    "ToolRegistry",
    "ToolValidationError",
    "ToolExecutionError",
    # builtin_tools
    "SearchTool",
    "ReadFullDocumentTool",
    "GetPageTool",
    "ReadFullTextTool",
    "BUILTIN_TOOL_CLASSES",
    # base_tool
    "BaseTool",
    # session_manager
    "SessionManager",
    "get_session_manager",
    "SessionNotFoundError",
    # gcs_uploader
    "upload_to_gcs",
    "GCSUploadError",
    "check_gcs_available",
    # request_logger
    "RequestLogger",
    "get_request_logger",
    "log_request",
    # selector_client
    "SelectorClient",
    # web_search_client
    "WebSearchClient",
    "PageContent",
]
