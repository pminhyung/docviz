"""Common dataclasses + Pipeline ABC for the DocViz-Agent prototype.

Schema sources of truth:
  - VizOutput: PAPER_MASTER_SPEC §3.6
  - Bundle / Doc: PAPER_MASTER_SPEC §5.1
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Doc:
    doc_id: str                          # f"{source}_{bundle_idx}_{doc_idx}"
    title: str
    content: str                         # plain text, no HTML
    page_id: Optional[str] = None        # for paginated sources (e.g. 10-K)


@dataclass
class Bundle:
    bundle_id: str                       # unique, source-prefixed
    source: str                          # one of: hotpotqa | multinews | arxiv | 10k
    docs: List[Doc]                      # 2+ entries
    metadata: Dict[str, Any] = field(default_factory=dict)
    # metadata holds source-specific extras (original_question, cluster_id,
    # ticker, topic_seed, etc.) and the doc_id ↔ "Passage [N]" mapping after
    # bundle_to_docai concat.

    def total_chars(self) -> int:
        return sum(len(d.content) for d in self.docs)


@dataclass
class VizOutput:
    """Common output schema for all baselines (B1-B5) and DocViz-Agent (B6).

    Required fields are populated for every strategy.
    Agentic-only and SAO-only fields are empty for non-agentic baselines.
    """
    # ── Required for all baselines ─────────────────────────────────────────
    viz_dsl: str                         # raw DSL — Chart.js JSON or Mermaid markdown
    viz_type: str                        # enum (10-type, expanded 2026-05-10):
                                         #   chart   : chartjs_bar | chartjs_line | chartjs_grouped_bar
                                         #             | chartjs_pie | chartjs_scatter
                                         #   diagram : mermaid_flowchart | mermaid_timeline | mermaid_mindmap
                                         #             | mermaid_sequenceDiagram | mermaid_classDiagram
    rendered_image_path: str             # PNG file path (set after sidecar render); "" if not rendered
    render_success: bool                 # M1 metric
    retrieved_chunks: List[Dict[str, Any]]  # [{doc_id, chunk_id, content}, ...]

    # ── Agentic only (DocViz-Agent S4); empty for B1-B5 ───────────────────
    sub_queries: List[str] = field(default_factory=list)

    # ── Pillar 3 SAO (DocViz-Agent only); empty for B1-B5 ─────────────────
    source_attribution: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # {viz_element_id: {doc_id, chunk_id, evidence_span}}

    # ── Metadata (required for all baselines) ─────────────────────────────
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    errors: List[str] = field(default_factory=list)


class Pipeline(ABC):
    """Base class for all baseline strategies (B1-B5) and DocViz-Agent (B6)."""

    name: str

    @abstractmethod
    def run(
        self,
        query: str,
        bundle: Bundle,
        *,
        query_type: Optional[str] = None,
        query_id: Optional[str] = None,
    ) -> VizOutput:
        """Execute the strategy on a (query, bundle) pair and return VizOutput.

        `query_type` is the 5-type taxonomy label (§4.2) — passed by the
        runner so TMG-aware variants (DocViz-Agent Pillar 2, §3.2) can
        route the prompt. Bare-bones baselines (B5 Direct-LLM, our S1)
        accept and ignore it; that is the §11.4 "−TMG" ablation cell.

        `query_id` is the per-record identifier (e.g.,
        "hotpot_00_relational"). Used by V4 strategies to thread a
        deterministic key into the generate_viz tool's per-type pool
        sampler (sha1(query_id) % len(pool)). S1/S4/V0/V1 accept and
        ignore it.
        """
        raise NotImplementedError
