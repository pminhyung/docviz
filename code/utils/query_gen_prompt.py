"""Query-generation prompts — v0.4 multi-document taxonomy.

v0.4 redesign (2026-05-24):
  - Adds 8-type DEPENDENCY taxonomy (T1-T8) on top of the 5-type CONTENT shape.
  - Dependency types force the query to require ≥2 docs of the bundle to answer
    (vs v0.3 single-doc fallback risk). Source-survey:
    docs/active/tracks/feat-source-loaders/multi_doc_viz_survey.md
  - Per-source recommended dep-type sets are loose pools — the generator
    samples one per bundle.
  - 5-type content shape demoted to secondary chart-hint slot.

Spec sources:
  - 8-type dep taxonomy: multi_doc_viz_survey.md §2 (anchored on MultiChartQA,
    CodRED, HoVer, CiteVQA, DiverseSumm, Doc2Chart, MEBench, MultiHiertt)
  - per-source mapping:  multi_doc_viz_survey.md §5
  - prompt skeleton:     multi_doc_viz_survey.md §6
"""
from __future__ import annotations

from typing import Dict, List

# ── DEPENDENCY taxonomy (T1-T8) — primary, multi-doc-forcing ─────────────────
DEPENDENCY_TYPE_DEFS: Dict[str, Dict[str, str]] = {
    "CDC": {  # T1
        "name": "Cross-Document Comparison",
        "instruction": (
            "Ask to compare an attribute across the listed documents. "
            "The query MUST name at least one entity from [DOC_A] AND one from [DOC_B] "
            "(different documents)."
        ),
        "viz_hint": "grouped bar | side-by-side small multiples",
    },
    "CDA": {  # T2
        "name": "Cross-Document Aggregation / Set Operations",
        "instruction": (
            "Ask for a sum, count, union, or intersection that REQUIRES reading every "
            "listed document; a single-doc answer must be wrong or incomplete."
        ),
        "viz_hint": "stacked bar | venn | summary table",
    },
    "TAS": {  # T3
        "name": "Temporal Aggregation Across Sources",
        "instruction": (
            "Ask for a timeline / chronological sequence that interleaves events from "
            "≥2 documents. Each named event must come from a distinguishable doc."
        ),
        "viz_hint": "timeline | line over time | gantt",
    },
    "CCEM": {  # T4
        "name": "Cross-Document Claim-Evidence Mapping",
        "instruction": (
            "Pick a claim made in ONE doc and ask which OTHER docs support, refine, "
            "or contradict it. Name the claim entity AND ≥1 evidence-doc entity."
        ),
        "viz_hint": "bipartite mapping | claim-evidence table | mindmap",
    },
    "CDER": {  # T5
        "name": "Cross-Document Entity-Relationship Merge",
        "instruction": (
            "Ask for a graph/mindmap of entities and their relations that only emerges "
            "when ≥2 documents are merged via a bridge entity. Name the bridge entity."
        ),
        "viz_hint": "mermaid graph | mindmap",
    },
    "CIC": {  # T6
        "name": "Causal / Influence Chain Across Documents",
        "instruction": (
            "Ask for a cause→effect chain whose links are split across the documents. "
            "The query must reference the first cause AND the final effect."
        ),
        "viz_hint": "mermaid flowchart | sequence diagram",
    },
    "DCS": {  # T7
        "name": "Divergence / Contradiction Surfacing",
        "instruction": (
            "Identify a value/claim/framing where the documents DISAGREE and ask to "
            "surface the disagreement. The query must name the disputed attribute."
        ),
        "viz_hint": "side-by-side bar | annotated callout | radar",
    },
    "MSTS": {  # T8
        "name": "Multi-Source Trend Synthesis",
        "instruction": (
            "Each document supplies one slice of a longitudinal/categorical trend. "
            "Ask for the integrated trend; the query must name ≥2 of the slices."
        ),
        "viz_hint": "multi-series line | grouped bar over time",
    },
}

# Per-source recommended dependency-type pool (survey §5).
# Generator uniform-samples one per bundle (seed=42).
SOURCE_DEP_TYPES: Dict[str, List[str]] = {
    "hotpotqa":  ["CDER", "CCEM", "CDC"],
    "multinews": ["TAS", "DCS", "CCEM"],
    "arxiv":     ["CDC", "CIC", "DCS"],
    "10k":       ["CDA", "MSTS", "CDC"],
    "govreport": ["CCEM", "CIC", "TAS"],
    "tech_docs": ["CDER", "CDA", "MSTS"],
}

# ── CONTENT taxonomy (5-type, secondary chart-hint slot) ─────────────────────
# v0.3 amendment §3.5 — retained as chart-shape secondary hint.
TYPE_ASSIGNMENT: Dict[str, List[str]] = {
    "hotpotqa":  ["relational",   "comparative"],
    "multinews": ["temporal",     "comparative"],
    "arxiv":     ["hierarchical", "comparative"],
    "10k":       ["quantitative", "temporal"],
    "govreport": ["temporal",     "hierarchical"],
    "tech_docs": ["relational",   "hierarchical"],
}

# Legacy 5-type bundle→type split (kept for backward compat — used as
# secondary "content_shape" hint only by the new dep-aware generator).
SOURCE_TYPE_SPLIT: Dict[str, List[tuple]] = {
    "10k":       [("quantitative",  50)],
    "hotpotqa":  [("relational",    30), ("comparative",  20)],
    "multinews": [("temporal",      30), ("comparative",  20)],
    "arxiv":     [("hierarchical",  30), ("comparative",  20)],
    "govreport": [("temporal",      30), ("hierarchical", 20)],
    "tech_docs": [("relational",    30), ("hierarchical", 20)],
}

TYPE_DEFS: Dict[str, str] = {
    "quantitative": (
        "Numerical comparison or trend across measured values "
        "(e.g., 'How did segment revenue change year over year?'). "
        "The bundle must supply concrete numbers."
    ),
    "relational": (
        "Entity-entity dependency, link, or interaction "
        "(e.g., 'How are these two organizations connected?')."
    ),
    "temporal": (
        "Time-ordered events or progression "
        "(e.g., 'Show how this story unfolded over the past month.')."
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


# ── v0.4 prompt — explicit per-doc tags + dependency-type slot ───────────────
MULTIDOC_QUERY_GEN_PROMPT = """\
You are drafting a realistic user query for a multi-document visualization assistant.

BUNDLE — {n_docs} documents, each tagged [DOC_n]:
{docs_concat_with_tags}

PER-DOC ENTITY INVENTORY (you must reference at least one entity from ≥2 different docs):
{per_doc_entity_lines}

BRIDGE ENTITY (what ties these documents together): {bridge_entity}

DEPENDENCY TYPE: {dep_type} — {dep_name}
{dep_instruction}

CONTENT SHAPE (secondary, hints at the viz): {content_shape} — {content_def}
RECOMMENDED VIZ FORMAT: {viz_hint}

Hard constraints:
1. ≤25 words.
2. References ≥1 entity from doc [{doc_a_tag}] AND ≥1 entity from doc [{doc_b_tag}]
   (different documents — single-doc query is invalid).
3. Sounds like a real user — concrete, specific, no generic phrasing.
4. Answerable by a chart/diagram/timeline/mindmap, not prose.
5. The answer MUST require reading ≥2 documents — a single-doc answer must be wrong or incomplete.

Output ONLY the query text. No preamble, no quotes, no JSON.
"""

# Legacy prompt — retained for fallback / regression diff. Not used by v0.4 path.
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
