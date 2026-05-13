# §3. Task Formalization (v0.3 draft)

> Draft for paper §3. v0.3 amendment compliance:
>   - 5-query-type taxonomy (D1.3 base, unchanged from v0.2)
>   - 10-viz-subtype enum (D5: pie, scatter, sequenceDiagram, classDiagram added)
>   - VizOutput schema with `visual_quality_score` field (D7.1)

## 3.1 Query-Grounded Multi-Document Visualization (QG-MDV)

We define **Query-Grounded Multi-Document Visualization** (QG-MDV) as the
task of generating, from a user query `q` and a *bundle* of 2-N source
documents `{d_1, ..., d_n}`, a single visualization `v` that:

1. answers `q` using only facts present in the bundle,
2. binds factual elements of `v` to specific source documents (Pillar 3
   SAO), and
3. emits as a renderable DSL (no free-form prose answer).

A bundle is *source-internal*: all documents in `{d_i}` are drawn from
the same content domain (e.g., a news cluster, a 10-K's MD&A + Risk
sections). Bundles span 6 content domains (§5.1).

## 3.2 Query Type Taxonomy (5 types)

Each query in QG-MDV is labeled with one of five query types:

| Type | Definition | Visualization affinity |
|---|---|---|
| Quantitative   | Numerical comparison or trend over measured values | chartjs_bar / line / grouped_bar |
| Relational     | Entity-entity dependency / link / interaction | mermaid_flowchart / sequenceDiagram |
| Temporal       | Time-ordered events or progression | mermaid_timeline / chartjs_line |
| Hierarchical   | Categorization / taxonomy / compositional structure | mermaid_mindmap / classDiagram |
| Comparative    | Multi-entity feature comparison | chartjs_grouped_bar / pie |

The 5-type set is the unchanged base from PAPER_MASTER_SPEC v0.2 §4.2.
Amendment §3.5 binds 2 types per source domain so the 300-record dataset
covers the 5×5×6 grid with target [55, 65] queries per type.

## 3.3 Visualization Subtype Enumeration (10 types)

We support 10 visualization subtypes across two DSLs:

**Chart.js** (5 quantitative subtypes):
- `chartjs_bar` — single-series quantitative comparison
- `chartjs_line` — trend over an ordered axis
- `chartjs_grouped_bar` — multi-series quantitative comparison
- `chartjs_pie` — proportional / part-of-whole (D5 NEW)
- `chartjs_scatter` — bivariate correlation (D5 NEW)

**Mermaid** (5 relational/structural subtypes):
- `mermaid_flowchart` — relational / process
- `mermaid_timeline` — chronologically ordered events
- `mermaid_mindmap` — hierarchical taxonomy
- `mermaid_sequenceDiagram` — interaction protocol (D5 NEW)
- `mermaid_classDiagram` — typed structural schema (D5 NEW)

This 10-type coverage matches or exceeds peer benchmarks (ChartQA 4
chart types, VisJudge-Bench 6, MindBench 1, current visualization-
generation benchmarks 4-8). Extension beyond 10 (e.g., heatmap, gantt,
ER) is straightforward via renderer plugin and viz-type addition; we
cap at 10 for one-shot pool curation tractability.

## 3.4 VizOutput Schema

The output of any baseline / our method is a `VizOutput` dataclass with:

```python
@dataclass
class VizOutput:
    viz_dsl: str                          # raw DSL — Mermaid markdown or
                                          # Chart.js JSON spec
    viz_type: str                         # one of the 10 enum values
    rendered_image_path: str              # PNG file path
    render_success: bool                  # M1 deterministic metric
    retrieved_chunks: List[Dict]          # CIS retrieval (Pillar 1)
    sub_queries: List[str]                # agent retrieval queries
                                          # (search.query[] or RFD.goal)
    source_attribution: Dict[str, Dict]   # SAO mapping (Pillar 3)
    tokens_in: int
    tokens_out: int
    cost_usd: float
    errors: List[str]
    visual_quality_score: Dict[str, Any]  # D7.1 NEW — populated by
                                          # the A5 image judge + M5
                                          # CLIPScore downstream
```

The schema is uniform across all 7 baselines (B1-B5, B7, B6). External
baselines that produce non-enum outputs (e.g., B1 MatPlotAgent's
matplotlib python code) carry `viz_type="matplotlib"` and `viz_dsl`
holds the python code — text-axis judging consumes the code as DSL;
image-axis judging consumes the rendered PNG.

## 3.5 Pipeline Pillars (Pillar 1 / 2 / 3)

Our method (B6 DocViz-Agent, internally V4_consolidated) is built on
three pillars:

1. **CIS — Contextual Input Selection** (Pillar 1). The doc-step LLM
   summarizes the bundle into a coarse overview, which then drives the
   agent's retrieval (`search` / `ReadFullDocument`) over the bundle's
   per-document JSON files. Implementation in `agent/run_agent_v2.py`
   doc_step pass.

2. **TMG — Type-Mapped Generation** (Pillar 2). Custom rule 17 in the
   compiled agent prompt forces a `generate_viz` tool invocation
   before any `<final_answer>`. The tool, given `(viz_type,
   content_brief)`, emits a structurally-valid DSL using one of the 10
   exemplars in `code/agent_tools/oneshot_pool.json` as a syntax
   reference. Implementation in `code/agent_tools/generate_viz.py` and
   `code/pipelines/s4_agentic_tmg.py` (mode='v4_consolidated').

3. **SAO — Source-Attributed Output** (Pillar 3). The pipeline records,
   per visualization element, which source document the element was
   grounded in. Stored as `VizOutput.source_attribution`. In v0.3 this
   is a stub; full SAO is Week-1 work.

Layer D ablation (§7) measures the contribution of each pillar by
removing one at a time (−CIS / −TMG / −SAO / Full).
