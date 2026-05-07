"""VisuBench viz redesign package (v3, 2026-04-09).

Content-aware subtype assignment + Vega-Lite/Mermaid generation pipeline.
Replaces legacy scripts/step2_generate_gold.py Chart DSL flow.

Modules (implemented incrementally per canonical plan D0-D17):
  - prompts.py          — 5 verbatim system/query prompts (D4)
  - context_builder.py  — prepare_full_context(doc) identity rule (D7)
  - subtype_assigner.py — LLM-based chart/diagram subtype + chart_spec (D5)
  - query_generator.py  — chart/diagram/mindmap query + QC (D6)
  - reference_generator.py — single-pass reference gen for 3 viz types (D8)
  - structure_extract_v2.py — Vega-Lite/Mermaid → structure.json (D11)
"""
