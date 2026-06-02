"""docviz v0.4.1 §4.2 — source × challenge_type compatibility matrix.

Returns a per-bundle list of challenge_types to generate.
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from exaone.sft_gen.docviz.query_schema import ChallengeType


# Compatibility weights (per §4.2): primary=2, ok=1, low=0.3, "—"=0
SOURCE_CHALLENGE_WEIGHTS: dict[str, dict[ChallengeType, float]] = {
    "hotpotqa": {
        "multi_hop": 2.0,
        "artifact_planning": 1.0,
        "mixed_artifact": 0.3,
        "distractor_heavy": 1.0,
        "contradiction": 0.0,
    },
    "multinews": {
        "multi_hop": 1.0,
        "artifact_planning": 1.0,
        "mixed_artifact": 1.0,
        "distractor_heavy": 1.0,
        "contradiction": 2.0,
    },
    "arxiv": {
        "multi_hop": 1.0,
        "artifact_planning": 2.0,
        "mixed_artifact": 2.0,
        "distractor_heavy": 1.0,
        "contradiction": 0.3,
    },
    "10k": {
        "multi_hop": 1.0,
        "artifact_planning": 1.0,
        "mixed_artifact": 0.3,
        "distractor_heavy": 2.0,
        "contradiction": 1.0,
    },
    "govreport": {
        "multi_hop": 1.0,
        "artifact_planning": 1.0,
        "mixed_artifact": 1.0,
        "distractor_heavy": 0.3,
        "contradiction": 1.0,
    },
    "tech_docs": {
        "multi_hop": 0.3,
        "artifact_planning": 2.0,
        "mixed_artifact": 2.0,
        "distractor_heavy": 1.0,
        "contradiction": 0.3,
    },
}


CHALLENGE_TYPES: tuple[ChallengeType, ...] = (
    "multi_hop", "artifact_planning", "mixed_artifact",
    "distractor_heavy", "contradiction",
)


def compute_quota(
    bundles: list[dict],
    *,
    target_count: int,
    seed: int = 42,
) -> dict[str, list[ChallengeType]]:
    """Assign challenge_types to bundles aiming for balanced totals.

    Returns: {bundle_id: [challenge_type_1, ...]}. Length is normally 1 per
    bundle but may be 2 for large bundles or to fill underfilled types.

    Algorithm:
      1. Compute target per challenge_type = target_count / 5.
      2. Sort bundles by source × weight × random jitter.
      3. Greedy assign challenge_type that (a) is compatible (weight > 0) and
         (b) is most under-quota globally.
    """
    rng = random.Random(seed)
    per_type_target = target_count / len(CHALLENGE_TYPES)
    per_type_remaining: dict[ChallengeType, float] = {
        c: per_type_target for c in CHALLENGE_TYPES
    }

    bundle_order = list(bundles)
    rng.shuffle(bundle_order)

    assignments: dict[str, list[ChallengeType]] = defaultdict(list)
    assigned_count = 0

    for b in bundle_order:
        if assigned_count >= target_count:
            break
        source = b["source"]
        weights = SOURCE_CHALLENGE_WEIGHTS.get(source, {})
        # Build candidate challenges weighted by compatibility AND remaining quota.
        scored: list[tuple[float, ChallengeType]] = []
        for c in CHALLENGE_TYPES:
            w = weights.get(c, 0.0)
            if w <= 0:
                continue
            remaining = per_type_remaining[c]
            if remaining <= 0:
                continue
            scored.append((w * remaining * rng.random(), c))
        if not scored:
            continue
        scored.sort(reverse=True)
        chosen = scored[0][1]
        assignments[b["bundle_id"]].append(chosen)
        per_type_remaining[chosen] -= 1
        assigned_count += 1

    return dict(assignments)
