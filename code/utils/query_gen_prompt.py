"""Query-generation prompts and 5-type taxonomy.

Spec sources of truth:
  - 5-type taxonomy:        PAPER_MASTER_SPEC §4.2 (L195-203)
  - Source → type pairing:  PAPER_MASTER_SPEC §5.2 (L256-260)
  - Generation protocol:    PAPER_MASTER_SPEC §5.2 (L262-266)
  - Filters:                ≤25 words AND references ≥1 bundle entity (L265)
"""
from __future__ import annotations

from typing import Dict, List

# v0.3 amendment §3.5 — 6-source type-assignment table.
# Each source gets primary + secondary query types based on natural content
# fit. The generator emits 1 query per bundle (300 total = 6 sources × 50
# bundles), using the per-source split below.
#
# tech_docs primary swapped to "relational" (amendment §3.5 had
# Hierarchical|Relational) so the 5-type distribution lands at the
# amendment §3.5-footnote target: Q=50 / R=60 / T=60 / H=70 / C=60.
#
# TYPE_ASSIGNMENT order: [primary, secondary]. Used for legacy code
# paths that still take 2 types per bundle; the new generator consumes
# SOURCE_TYPE_SPLIT directly.
TYPE_ASSIGNMENT: Dict[str, List[str]] = {
    "hotpotqa":  ["relational",   "comparative"],
    "multinews": ["temporal",     "comparative"],
    "arxiv":     ["hierarchical", "comparative"],
    "10k":       ["quantitative", "temporal"],
    "govreport": ["temporal",     "hierarchical"],
    "tech_docs": ["relational",   "hierarchical"],
}

# v0.3 amendment §3.5 footnote — per-source bundle→type split for the
# 1-query-per-bundle generator. Numbers sum to N_BUNDLES per source.
# 10k uses 15 (cached EDGAR tech-sector subset; see load_10k.py docstring).
# Resulting 5-type distribution (total 265, ~88% of amendment 300 target):
#   Q = 15 (10k — short of 50 target; documented in paper §5.1 caveat)
#   R = 30 (hotpotqa) + 30 (tech_docs)                    = 60
#   T = 30 (multinews) + 30 (govreport)                    = 60
#   H = 30 (arxiv)     + 20 (govreport) + 20 (tech_docs)   = 70
#   C = 20 (hotpotqa)  + 20 (multinews) + 20 (arxiv)       = 60
SOURCE_TYPE_SPLIT: Dict[str, List[tuple]] = {
    "10k":       [("quantitative",  15)],
    "hotpotqa":  [("relational",    30), ("comparative",  20)],
    "multinews": [("temporal",      30), ("comparative",  20)],
    "arxiv":     [("hierarchical",  30), ("comparative",  20)],
    "govreport": [("temporal",      30), ("hierarchical", 20)],
    "tech_docs": [("relational",    30), ("hierarchical", 20)],
}

# §4.2 L195-202 — operational definitions used in the generation prompt
TYPE_DEFS: Dict[str, str] = {
    "quantitative": (
        "Numerical comparison or trend across measured values "
        "(e.g., 'How did segment revenue change year over year?'). "
        "The bundle must supply concrete numbers."
    ),
    "relational": (
        "Entity-entity dependency, link, or interaction "
        "(e.g., 'How are these two organizations connected?'). "
        "The bundle must mention at least two named entities."
    ),
    "temporal": (
        "Time-ordered events or progression "
        "(e.g., 'Show how this story unfolded over the past month.'). "
        "The bundle must contain dates or temporal cues."
    ),
    "hierarchical": (
        "Categorization, taxonomy, or compositional structure "
        "(e.g., 'Group these papers by methodological approach.')."
    ),
    "comparative": (
        "Multi-entity feature comparison "
        "(e.g., 'Compare the architectural choices of these three systems.')."
    ),
}


QUERY_GEN_PROMPT = """\
You are drafting a realistic user query for a document-visualization assistant.

Bundle documents (you may reference any or all of them):
{docs_concat}

Generate ONE natural user query that:
1. Falls under the query type **{query_type}**.
2. Type definition: {type_def}
3. Can be answered by visualizing information present in the bundle above.
4. Sounds like something a real user would ask — concrete, specific, not generic.
5. References at least one named entity, term, ticker, or title from the bundle.
6. Implies a chart, diagram, timeline, or mindmap is the right answer format.
7. Is at most 25 words.

Output ONLY the query text. No preamble, no quotes, no JSON, no trailing notes.
"""
