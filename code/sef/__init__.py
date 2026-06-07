"""SEF (Strategic Evidence Format) — v0.4.3 DocViz-Agent axis.

Deterministic structured representation of source documents, consumed by the
B6 arm only (baselines receive plain markdown). No LLM calls.
"""
from __future__ import annotations

from .schema import SEF, Block, ClaimUnit, CrossRef
from .build import (
    build_sef_from_markdown,
    build_sef_for_bundle,
)

__all__ = [
    "SEF", "Block", "ClaimUnit", "CrossRef",
    "build_sef_from_markdown", "build_sef_for_bundle",
]
