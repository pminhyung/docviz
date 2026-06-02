# docviz legacy code map (pre-harness migration reference)

When porting docviz's B6 agent into the harness top-level structure, these
are the source files to consult. All paths are under
`_legacy_v0.4_pre_harness/` (gitignored on disk; frozen for reference).

## 1. Query generation

| File | Lines | Role |
|---|---|---|
| `code/utils/generate_queries.py` | 331 | Per-bundle generator producing 5 query types (Quantitative / Relational / Temporal / Hierarchical / Comparative) via LLM |
| `code/utils/query_gen_prompt.py` | 195 | Prompt templates for query generation (per-source variants) |

Output: `data/prototype/queries/all.json` (300 queries used in v0.4 measurements; was at `_legacy_v0.4_pre_harness/data/prototype/queries/`).

## 2. Diagram / chart generation tool (`generate_viz`)

| File | Lines | Role |
|---|---|---|
| **`code/agent_tools/generate_viz.py`** | **445** | **Core tool the agent invokes.** Inputs (`viz_type`, `content_brief`) → DSL output (mermaid / chartjs). Writes sidecar JSON to disk. |
| `code/adapters/viz_output_mapper.py` | 292 | Maps agent output → standard viz record format |
| `code/render/renderer.py` | 381 | DSL → PNG image rendering (mermaid CLI, chart.js via puppeteer, etc.) |
| `code/judge/dsl_parser.py` | 144 | DSL syntax validation + structure extraction (used by judge) |

## 3. Diagram-generation prompt + agent orchestration

| File | Lines | Role |
|---|---|---|
| **`code/pipelines/tmg.py`** | **223** | **V4 system prompt source** (`V4_POOL_EXPOSURE_RULE`, TMG / SAO / CIS 3-pillar definitions) |
| `code/pipelines/s4_agentic.py` | 118 | Agentic base — agent loop preparation |
| **`code/pipelines/s4_agentic_tmg.py`** | **429** | **Full B6 pipeline** — TMG/SAO step + retry / rescue / sidecar integration |
| `code/pipelines/ablation_variants.py` | 107 | Defines `B6_NoCIS`, `B6_NoSAO`, `B6_NoTMG` (which pillars to disable) |

## 4. Baselines (comparison group)

| File | Role |
|---|---|
| `code/pipelines/s1_direct.py` | B5 / S1: single-shot LLM call producing DSL |
| `code/pipelines/s7_self_refine.py` | B7 / S7: self-refine loop (the §16 strict-gate comparison target) |
| `code/pipelines/b1_matplotagent.py` … `b4_vividoc.py` | B1-B4 external-baseline adapters |

## 5. Pre-dumped reference (already readable)

- **`.harness/active/tracks/feat-source-loaders/v4_compiled_prompt.md`** (20 KB)
  - Compiled V4 prompt as actually sent to the model (markdown-dumped for tuning).
  - Mirrors `code/pipelines/tmg.py` in a human-readable form.
  - Recommended first stop for fast comprehension.

## 6. Image-level evaluation, external benches, and held-out validation

These cover paper Table A3 (image-quality metrics), the cross-task generalization
benches (Table 3), and the judge-validation layers (Table A4 L2-L4).

### 6A. Image-level metrics (M1 render success, M5 CLIPScore, A5 image-quality)

| File | Lines | Role |
|---|---|---|
| `code/render/renderer.py` | 381 | DSL → PNG renderer (input to M1 render success rate) |
| `code/metrics/clipscore.py` | 205 | **M5 CLIPScore** — query↔image cosine similarity via HuggingFace `CLIPModel` |
| `code/scripts/clipscore_batch.py` | 140 | Batch runner applying M5 across an entire viz output set |
| `code/judge/image_judge.py` | 304 | **A5 image-quality judge** — Claude Sonnet vision via `claude -p` headless CLI; outputs `readability` / `layout` / `overall` ∈ [0,1] |
| `code/scripts/run_sonnet_subset.py` | 148 | Runs direct-call baselines under Claude Sonnet on a stratified subset (~50 records, ~25-40 s/call ⇒ subset only) |

### 6B. External benches (cross-task generalization, paper Table 3)

| File | Lines | Role |
|---|---|---|
| `code/eval/plot2code_eval.py` | 193 | **Plot2Code** bench adapter (held-out cross-task gen) |
| `code/utils/load_plot2code.py` | 162 | Plot2Code raw → docviz bundle loader |
| `code/utils/load_text2vis.py` | 155 | **Text2Vis** bench loader (Table 3) |

ViviBench (B9 home-turf comparison) has no dedicated adapter in legacy — only the
dataset; the evaluation harness for it remains to be written.

### 6C. Judge-validation pipeline (paper §A4 Layer 2-4)

| File | Lines | Role |
|---|---|---|
| `code/judge/analyze_correlation.py` | 272 | **L3 cross-judge agreement** — Cohen's κ + Spearman ρ between judge runs |
| `code/judge/sample_for_human.py` | 172 | **L2 human alignment** — extracts the 90-record gold subset for Prolific raters |

### 6D. Aggregation and final-table assembly

| File | Lines | Role |
|---|---|---|
| `code/scripts/aggregate_v04_results.py` | 187 | Per-source / per-axis roll-up; §16 strict-gate verdict; backbone-comparison table |
| `code/scripts/run_v04_pipeline.sh` | (shell) | End-to-end orchestrator: baselines → judge → aggregate |

These feed the paper tables:
- M1, M5, A5 → **Table A3** (image-quality + render success)
- Plot2Code, Text2Vis → **Table 3** (cross-task generalization headline)
- L2/L3 metrics → **Table A4** (validation layer anchors)

## Recommended reading order when porting

1. **`v4_compiled_prompt.md`** — what the agent is asked to do, at a glance.
2. **`tmg.py`** — where the prompt is defined in code (which variables substitute where).
3. **`agent_tools/generate_viz.py`** — the tool I/O contract.
4. **`s4_agentic_tmg.py`** — the agent loop + rescue / sidecar logic.
   *In the harness port, the retry / rescue layer will likely be subsumed by the v19 adapter — re-evaluate after Phase 6.*
5. **`generate_queries.py` + `query_gen_prompt.py`** — only when regenerating the query dataset.
6. **`metrics/clipscore.py` + `judge/image_judge.py`** — only when re-running paper Table A3 image-level metrics; `eval/plot2code_eval.py` for Table 3 cross-task benches.

---

# Target structure — new docviz B6 in the harness layout

The harness already supplies most of what docviz used to hand-roll. This
section maps each legacy concern to its new home, then lists the small
set of **new** files we add for the docviz B6 mode.

## Harness modules we adopt as-is (no porting)

| Concern | Harness module | Notes |
|---|---|---|
| Agent loop / tool dispatch | `run_agent.py` (`AIAgent`) + `exaone/agent.py` (`ExaoneAgent`) | Replaces `_legacy/.../s4_agentic_tmg.py` orchestration |
| Tool registry | `exaone/tools.py` + `model_tools.TOOL_TO_TOOLSET_MAP` | Plug `generate_viz` here |
| Tool result envelope | `exaone/tool_formatting.py` | Standardized citation `Index` schema |
| Multi-host pool | `exaone/batch_runner_pool.py` + `configs/hosts.yaml` | 32 process-pinned workers (8 hosts × 4) on the same Qwen pool we already use |
| Qwen tool-call parsing | **`exaone/v19_completions_adapter.py`** | Local jinja render → `/v1/completions` → parse `<think>` / `<tool_call>` tags. Eliminates the "empty final_answer" class of failures via gating `EXAONE_V19_ADAPTER=1`. Replaces our custom `code/adapters/agent_client.py` parsing. |
| Document loading (Mode A) | `exaone/docqa_tools/`, `exaone/sft_gen/shim/pdf_index.py`, `exaone/parsing_tools/handle_parse_web_and_doc.py` | idx-only attachment model; `EXAONE_PARSED_ROOT` points at our converted bundle dir |
| Prompt composition | `exaone/system_prompt.py` 5-block (identity / tool_list / style / custom / memory) + `exaone/prompts/{identities,style,tools}/` | Replaces V4 monolithic prompt in `tmg.py` |
| QA mode dispatch | `exaone/qa_modes.py` | Add `"docviz"` entry pointing at our identity + toolset |
| Batch / checkpoint / resume | `batch_runner.py` + `exaone/batch_runner_pool.py` | Replaces `_legacy/.../run_prototype.py` `_run_strategy_pool` |
| Trajectory recording | `batch_runner.py` (OpenAI-format messages JSONL) | Replaces our scattered `raw.jsonl` writes |

## New files we add (the docviz B6 layer)

| Path | Purpose | Maps from |
|---|---|---|
| `exaone/qa_modes.py` (edit) | Register `"docviz"` mode: toolset `["docqa_tools", "viz_tools"]`, identity `docviz`, style `docviz` | (new wiring, not a 1:1 port) |
| `exaone/prompts/identities/docviz.txt` | Agent identity + task framing ("You generate visualizations from documents…") | Extract from `_legacy/code/pipelines/tmg.py` (V4 identity preamble) |
| `exaone/prompts/style/docviz.txt` | Response style: citation `Index` format, finalization rules | Extract from V4 style block |
| `exaone/prompts/tools/generate_viz.txt` | `generate_viz` tool description + viz-type catalog + hard precondition | Extract from `_legacy/code/pipelines/tmg.py` generate_viz section |
| **`exaone/viz_tools/handle_generate_viz.py`** | The actual tool handler — DSL synthesis + sidecar write | Port of `_legacy/code/agent_tools/generate_viz.py` (445 LOC → ~250 LOC, dropping the bits ir-shim/v19 already cover) |
| `exaone/viz_tools/__init__.py` | Tool registration into `register_exaone_tools()` | (new wiring) |
| `exaone/viz_tools/_renderer.py` | DSL → PNG renderer (mermaid CLI, chart.js+puppeteer, matplotlib) | Port of `_legacy/code/render/renderer.py` |
| `exaone/viz_tools/_dsl_parser.py` | DSL syntax validation for tool-side preflight | Port of `_legacy/code/judge/dsl_parser.py` (judge also reuses this) |
| `scripts/bundles_to_pdf_index.py` | One-off converter: `data/bundles/*.json` → `EXAONE_PARSED_ROOT` Mode A directory | (new) — drafted, lives at top-level scripts/ |
| `scripts/bundles_to_jsonl.py` | One-off converter: queries + per-bundle attachments → harness JSONL (`{prompt, attachments[]}`) | (new) — needed for `batch_runner_pool.py --dataset_file=...` |
| `configs/qa_modes/docviz.yaml` *(optional)* | Externalize docviz mode config if we want env-overridable toolsets | (new) |

## Ablation handling (B6 pillars)

The B6 pillars (CIS, TMG, SAO) were defined in `_legacy/code/pipelines/ablation_variants.py`
as a Python config object. In the new structure we map them to **separate identity files**
selected by env var:

| Variant | Identity file | Toolset | Selector |
|---|---|---|---|
| B6 (full) | `prompts/identities/docviz.txt` | `[docqa_tools, viz_tools]` | `DOCVIZ_VARIANT=full` (default) |
| B6_NoCIS | `prompts/identities/docviz_nocis.txt` | same | `DOCVIZ_VARIANT=nocis` |
| B6_NoSAO | `prompts/identities/docviz_nosao.txt` | same | `DOCVIZ_VARIANT=nosao` |
| B6_NoTMG | `prompts/identities/docviz_notmg.txt` | same | `DOCVIZ_VARIANT=notmg` |

`exaone/qa_modes.py` will resolve `DOCVIZ_VARIANT` at agent init to pick the right identity.
The ablation switch costs only an identity-file swap — no agent loop change.

## Bench / dataset switching

Aligned with the plan in
`.harness/active/tracks/feat-source-loaders/port_to_harness_plan.md` Phase 5:

| Env value | Dataset JSONL fed to `batch_runner_pool --dataset_file=` |
|---|---|
| `DOCVIZ_BENCH=full` | `data/bundles/qg_mdv_full_300.jsonl` (regenerated by `bundles_to_jsonl.py`) |
| `DOCVIZ_BENCH=heldout` | `data/bundles/qg_mdv_heldout.jsonl` |
| `DOCVIZ_BENCH=plot2code` | `data/bundles/plot2code.jsonl` |
| `DOCVIZ_BENCH=text2vis` | `data/bundles/text2vis.jsonl` |

A thin wrapper script `scripts/run_docviz.sh` will compose
`DOCVIZ_BENCH` + `DOCVIZ_VARIANT` + Qwen pool host config and dispatch
to `batch_runner_pool.py`.

## Decision: what gets *deleted* once new B6 hits Qwen parity

After Phase 7 (3-seed Qwen parity validated):
- `_legacy_v0.4_pre_harness/code/{agent_tools,pipelines,adapters,render}` → no longer needed at runtime; kept for paper reference + ablation comparison.
- Custom multi-host `QwenDirectClient` round-robin → already replaced; do NOT port.
- Custom `_RETRIABLE_ERROR_PATTERNS` requeue loop → re-evaluate if v19 + rescue eliminate the pattern; likely drop.

## Snapshot info

- Captured: 2026-05-30 (during harness migration, post-commit `e3d3d0c`)
- v0.4 measurement reference scores: see `outputs/paper/blank_tables_reference.md`
  (and `_legacy_v0.4_pre_harness/outputs/v0.4_backbone_compare/reports/backbone_results.md`)
