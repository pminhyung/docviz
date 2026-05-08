"""
Configuration module for Document Agent V2

Contains:
- runtime_prompts: Sealed runtime prompt blocks (internal)
- training_prompts: Public training system prompt (spec-like)
"""

from .runtime_prompts import RuntimePrompts, get_runtime_prompt_blocks
from .training_prompts import TRAINING_SYSTEM_PROMPT, get_training_system_prompt

__all__ = [
    "RuntimePrompts",
    "get_runtime_prompt_blocks",
    "TRAINING_SYSTEM_PROMPT",
    "get_training_system_prompt",
]
