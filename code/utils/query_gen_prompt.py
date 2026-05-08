"""Query-generation prompts and 5-type taxonomy.

Spec sources of truth:
  - 5-type taxonomy:        PAPER_MASTER_SPEC §4.2 (L195-203)
  - Source → type pairing:  PAPER_MASTER_SPEC §5.2 (L256-260)
  - Generation protocol:    PAPER_MASTER_SPEC §5.2 (L262-266)
  - Filters:                ≤25 words AND references ≥1 bundle entity (L265)
"""
from __future__ import annotations

from typing import Dict, List

# §5.2 L256-260 — source → 2 query types per bundle
TYPE_ASSIGNMENT: Dict[str, List[str]] = {
    "hotpotqa":  ["relational",   "comparative"],
    "multinews": ["temporal",     "comparative"],
    "arxiv":     ["hierarchical", "comparative"],
    "10k":       ["quantitative", "temporal"],
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
