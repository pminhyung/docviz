"""
API module for Document Agent V2

Provides FastAPI-based HTTP API for:
- Running document agent queries
- Validating agent output
- Health checks
"""

from .schemas import (
    RunRequestV2,
    RunResponseV2,
    ValidateRequest,
    ValidateResponse,
    HealthResponse,
    StepReasoning,
    ValidationStats,
    ValidationConstraints,
)
from .handlers import AgentHandler, ValidationHandler
from .server import app

__all__ = [
    # FastAPI app
    "app",
    # Schemas
    "RunRequestV2",
    "RunResponseV2",
    "ValidateRequest",
    "ValidateResponse",
    "HealthResponse",
    "StepReasoning",
    "ValidationStats",
    "ValidationConstraints",
    # Handlers
    "AgentHandler",
    "ValidationHandler",
]
