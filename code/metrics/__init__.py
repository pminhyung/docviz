"""Image-level + DSL-level metrics for viz evaluation.

Currently exposed:
  - clipscore: M5 deterministic image↔text alignment (CLIP)
"""
from code.metrics.clipscore import (
    CLIPScoreResult,
    compute_clipscore,
    compute_clipscore_batch,
)

__all__ = [
    "CLIPScoreResult",
    "compute_clipscore",
    "compute_clipscore_batch",
]
