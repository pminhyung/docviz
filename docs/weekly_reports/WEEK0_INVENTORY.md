# Week 0 Inventory — Codebase ↔ Spec Mapping

> Source: PR1 `feat/week0-bootstrap`, 2026-05-08

## 1. Backbone (vLLM endpoints)

| | |
|---|---|
| Model | `Qwen3.6-27B` (`/ex_disk2/mhpark/poc/chartvr/models/qwen3.6-27b`) |
| Endpoints | `http://localhost:{9101, 9102, 9103}/v1` (OpenAI-compatible) |
| Layout | TP=4 × 3 instances, GPU 4-15 |
| `max_model_len` | **131072** (128K) |
| `enforce-eager` | true |
| `reasoning-parser` | qwen3 |
| Probed status | 3 / 3 ports return HTTP 200 |
| End-to-end agent /v2/run smoke (4-step) | 303 s wall, 12,944 output tokens |

This single backbone serves S1 Direct (`QwenDirectClient` round-robin), S4 Agentic
(via agent reasoner), query generation, and the **homo-judge** for Week 0.
Closed APIs (GPT-5 / Claude / Gemini) are deferred to the final validation
stage per user direction.

## 2. Agent (vendored at `agent/`) — pillar coverage

| Pillar | What the agent already provides | Day-N obligation |
|---|---|---|
| **CIS** (Pillar 1) | `core/tool_actions.ToolContext.multi_docs: List[List[Dict]]`, `core/selector_client.py`, `core/web_search_client.py` (we disable), `searched_indices` / `search_pages` accumulators, `RunResponseV2.steps_reasoning` carries the multi-step trace | Verify `web_search=off` actually disables (rules-based for Week 0); refine page → doc_id citation extraction (`viz_output_mapper._extract_source_attribution` stub) |
| **TMG** (Pillar 2) | `core/tool_registry.py` accepts a `custom_tools_path` per request; `agent/examples/diagram/diagram_tools.py` (vendored from visubench) holds Mermaid + Chart.js + Mermaid-mindmap system prompts | Add a 5-class query-type classifier in `code/classifiers/query_type.py` and route to the right custom tool path (PR4) |
| **SAO** (Pillar 3) | Step trace exposes `action.page` / `action.snippet` for any page-citing tool calls; `Bundle.metadata["page_to_doc_id"]` is populated by `bundle_to_docai.write_bundle_as_docai` | Promote the heuristic stub in `viz_output_mapper._extract_source_attribution` to a per-viz-element mapper once viz tools are wired (PR4) |

Pre-existing carry-overs (not blocking PR1):
- `agent/examples/diagram/diagram_tools.py:1360` — `from agent.core.llm_pool import get_default_pool` references a missing module. Lazy import; only triggers on the inline DSL helper. Replace with `core.model_router` when PR4 wires custom tools.
- `agent/examples/{client_example, vl_client}.py` ship pre-existing Python `global`-after-use SyntaxErrors. Not on the prototype path; leave for now.

## 3. Sidecars

| Sidecar | Path | Default port | Status |
|---|---|---|---|
| Mermaid + Chart.js renderer | `agent/sidecars/mermaid-renderer/` | 3005 | `npm ci` done (168 pkgs) |
| Mindmap (D3.js) renderer | `agent/sidecars/mindmap-renderer/` | 3004 | `npm install` done (168 pkgs) |

PR6 will provide a launcher script and a wrapper that calls them after the
agent emits a DSL block.

## 4. Spec ↔ schema mapping

| Spec section | Code artefact (PR1) |
|---|---|
| §3.6 `VizOutput` | `code/pipelines/base.VizOutput` |
| §5.1 `Bundle` / `Doc` | `code/pipelines/base.{Bundle,Doc}` |
| §5.1 raw → bundle conversion (4 sources) | scaffold in `data/prototype/sources/`, loaders in PR2 |
| §3.5 web_search disabled | `AgentClient.run_paper_default` injects rules forbidding web_search |
| §3.5 deterministic (T=0, seed=42) | `agent_client.PAPER_DEFAULT_TEMPERATURE/SEED`, `QwenDirectClient` defaults |
| §4.3 DSL-only output | enforced via `viz_output_mapper._extract_dsl_block` (returns the raw text under a fallback type if no block parses; PR4's S4 will tighten via system prompt) |
| §6.1 cross-judge | **Relaxed for Week 0** — homo-judge with Qwen3.6-27B (caveat noted in `WEEK0_REPORT.md` template). Cross-judge becomes JUDGE-FIX path if r < 0.5. |

## 5. Repo layout after PR1

```
docviz/
├── agent/                       (vendored — unchanged in this PR)
├── code/
│   ├── adapters/{agent_client, bundle_to_docai, viz_output_mapper}.py
│   ├── pipelines/base.py        (VizOutput, Bundle, Doc, Pipeline ABC)
│   ├── utils/cost_tracker.py
│   ├── classifiers/             (empty, fills in PR4)
│   ├── judge/                   (empty, fills in PR7)
│   └── scripts/smoke_test_pr1.py
├── data/prototype/{bundles,queries,sources}/   (empty — PR2/PR5 fill)
├── outputs/prototype/{viz,judge_scores,human_ratings}/   (empty)
├── notebooks/                   (empty — PR9)
├── docs/weekly_reports/{WEEK0_LOG, WEEK0_INVENTORY}.md
└── OPEN_QUESTIONS.md
```
