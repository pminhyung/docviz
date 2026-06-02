"""docviz v0.4.1 §4.1 — Query + Intent dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal


ChallengeType = Literal[
    "multi_hop",          # A — entity/relation across documents
    "artifact_planning",  # B — model decides artifact count + types
    "mixed_artifact",     # C — query implicitly needs chart + diagram
    "distractor_heavy",   # D — bundle has tempting wrong source segments
    "contradiction",      # E — bundle has conflicting claims, gold marks support
]

OutputType = Literal[
    "quantitative",   # numeric comparison primary
    "relational",     # entity-entity links
    "temporal",       # sequence of dated events
    "hierarchical",   # tree / taxonomy
    "comparative",    # side-by-side categorical
]


@dataclass
class Intent:
    """One gold sub-intent of a query (used for Hungarian matching)."""
    intent_id: str
    artifact_type_hint: str       # "chartjs_*" | "mermaid_*" | "any"
    content_summary: str          # 1-sentence summary of what this intent covers


@dataclass
class Query:
    """A QG-MDV query with v0.4.1 challenge axis + output axis."""
    qid: str
    text: str
    bundle_id: str
    source: str
    challenge_type: ChallengeType
    output_type: OutputType
    secondary_tags: list[ChallengeType] = field(default_factory=list)
    gold_intent_count: int = 1
    gold_intents: list[Intent] = field(default_factory=list)
    filter_signal: str = ""               # set by difficulty filter (P2 stage 2)
    filter_models_majority: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        # asdict already handles nested dataclasses via asdict recursion.
        return d
