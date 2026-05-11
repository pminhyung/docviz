# DocViz-Agent

> First generalist pipeline for query-grounded multi-document visualization.

## Overview

DocViz-Agent generates faithful visualizations (charts, diagrams, mindmaps) grounded in multiple long documents in response to user queries. It is the first unified pipeline addressing the combined setting of (multi-document + user query + multi-visualization-type), a gap not covered by existing specialized methods (DiagrammerGPT, MatPlotAgent, NVAGENT, CoDA, ViviDoc, Text2Vis).

The pipeline is built on three design pillars:
- **Cross-doc Iterative Search (CIS)** — agentic search-query-driven retrieval across all source documents
- **Type-aware Multi-Viz Generation (TMG)** — query-type classification routes to appropriate visualization type
- **Source-Attributed DSL Output (SAO)** — every visual element traces back to source documents for verifiability

## Repository contents

- `PAPER_MASTER_SPEC.md` — operational source of truth for the entire research project
- `QG-MDV_Week0_Action_Guide.md` — Week 0 prototype action guide for research agent
- (To be populated) — code, data, outputs, notebooks, weekly reports

## Target

EMNLP 2026 (main attempt → Findings auto-fallback). 11-12 week timeline.

## Workflow

The research agent works in a separate environment, pushes to this repository on feature branches, and opens PRs. The advisor pulls and provides codebase-grounded feedback. Each PR follows the template in `.github/pull_request_template.md`.

Each weekly milestone produces a `WEEK<N>_REPORT.md` in `docs/weekly_reports/` with all numbers, decisions, and open questions.

## Key Documents

Read in this order before starting work:
1. `AMENDMENT_v0.3_ACTION_SPEC.md` — **latest operational source of truth** (action-level, P0/P1/P2/P3 priority, supersedes conflicting v0.2 guidance)
2. `PAPER_MASTER_SPEC.md` — full strategic and experimental specification (v0.2 baseline)
3. `CHANGELOG.md` — version history with reasons for each change
4. `QG-MDV_Week0_Action_Guide.md` — concrete prototype-phase actions

## Status

Week 0: prototype validation phase. Decision gates and Go/No-Go criteria are in the Week 0 action guide.
