# DocViz v0.4.1 Implementation Guide — for research agent

> **Status**: actionable implementation spec for the next prototype cycle.
> **Predecessors**: PAPER_MASTER_SPEC v0.2, AMENDMENT_v0.3_ACTION_SPEC.md, `docs/analysis/scope_v3_gate_pass_260523.md`, legacy code map (2026-05-30 including §6 image/bench/validation/aggregation additions).
> **Revision note**: Earlier draft contained four invented decisions (a fabricated weighted composite "FSOS", ViviBench as primary held-out, Plot2Code as primary held-out, `claude -p` CLI for the A5 judge). All four removed in this version. Gold construction §8 expanded with concrete extraction prompts, dedup, and Prolific task design.
> **Reading order**: §0 (research context) → §1 (how to read) → §2 (image eval) → §3 (eval paradigm) → §4-§10 (implementation) → §11-§13 (held-out + validation + aggregation) → §14 (migration phases) → §15 (risks).

---

## 0. Research context — why these experiments matter

Before writing a single line of code, the research agent must hold the paper's contribution structure in mind. **Every file change in this guide serves one of the four contributions below.** If a proposed change does not map to a contribution, do not implement it.

### 0.1 Four contributions (v0.4.1 refined from v0.3 five-contribution structure)

| # | Contribution | Evidence in paper | Implementation locus |
|---|---|---|---|
| **C1** | **QG-MDV task formalization + benchmark** — query-grounded × multi-document × 10-viz-primitive coverage. 300 queries, 6 source domains, 5 reasoning-challenge types × 5 output-structure types, 90 human-verified gold. | Table 2 (composition); Table 3 (per-challenge headline) | §4 query generation + §8 gold construction |
| **C2** | **DocViz-Agent method** — first generalist pipeline addressing QG-MDV. Three pillars (CIS / TMG / SAO). TMG is the *primary* contributor (ablation Δ −0.254 in scope-v3 prototype). | Table 4 (cross-backbone); Table 7 (pillar ablation) | §5 B6 generation pipeline |
| **C3** | **Deterministic structured evaluation framework with Hungarian intent matching** — Chart.js → table F1, Mermaid → graph F1, evidence F1, intent coverage. Replaces subjective judge as primary; 4-axis RocketEval kept as Tier 3 sanity. **Each metric reported separately; no weighted composite invented.** | Table 5 (per-axis); §6 paper "Evaluation Framework" | §3 paradigm + §7 parsers + §9 metrics |
| **C4** | **Multi-doc grounding gap finding** — cross-LLM cross-pipeline persistence of low Evidence F1 on multi-doc queries, including frontier (Opus 4.8) and budget (GPT-5-mini) closed models. **Evidence F1 is THE primary headline metric for this contribution.** | Table 4 cross-backbone column; headline figure (per-backbone Evidence F1 lag plot) | §11 held-out + §13 aggregation |

**Discarded from v0.3 structure**: the old C4 "setting-stratified comparison" is no longer a contribution — it is now evaluation methodology in §6. The old C5 "multi-doc grounding gap" was at §8 with 0.75 page; v0.4.1 promotes it to **headline finding** at the paper face with 1.5 page allocation.

### 0.2 Target experimental results

The implementation deliverable is a complete result set populating these paper tables (templates in `outputs/paper/blank_tables_reference.md`):

| Table | What it shows | Backbones | Size |
|---|---|---|---|
| T1 Headline (cross-task generalization) | **4 settings** × 7 baselines, **per-metric (no composite)**: QG-MDV + Text2Vis + Doc2Chart + SciDoc2DiagramBench | 4 (avg) | 7 rows × 16 cols (4 settings × 4 metrics) |
| T2 Composition | QG-MDV per-source bundle/query stats | — | 6 rows |
| T3 **Per-challenge-type (NEW headline-equivalent for C2)** | A/B/C/D/E × 7 baselines × 4 metrics | 4 (avg) | 5 rows × (7×4) cols |
| T4 **Cross-backbone QG-MDV (C4 finding evidence)** | 4 backbones × 7 baselines × Evidence F1 primary + others | 4 (all) | 4 rows × 7 cols |
| T5 Per-axis (Tier 3 RocketEval sanity) | 4 axes × 7 baselines | 4 (avg) | 7 rows × 5 cols |
| T6 Per-source | 6 sources × 7 baselines × 4 metrics | 4 (avg) | 6 rows × 7 cols |
| T7 Pillar ablation | 4 B6 variants × 4 metrics | 4 (avg) | 4 rows × 4 cols |
| T8 Image quality | M1 / M5 / A5 readability/layout/overall × 7 baselines | 4 (subset 100) | 7 rows × 5 cols |
| A1 Multi-doc scaling | 1/2/3/5 docs × 7 baselines, evidence_f1 (multi-doc primary) | 4 (avg) | 7 rows × 4 cols |
| A2 Long-context paradox | 8K/32K/128K × 7 baselines | 2 (Sonnet + Opus have full window) | 7 rows × 3 cols |
| A3 Validation | L2/L3/L4 anchors | — | 8 rows |

**Acceptance criteria for paper face** (must hold for main-track positioning; if any fails, reframe to Findings):

1. **C4 finding gate (primary)**: B6 leads on **Evidence F1** with Δ ≥ +0.020 vs strongest baseline on QG-MDV across **≥ 3 of 4 backbones**.
2. **C2 method gate**: B6 also leads on Chart Data F1 AND Graph Edge F1 with Δ ≥ +0.020 on **≥ 2 of 4 backbones**.
3. **Multi-criterion strict gate (replaces FSOS gate)**: on QG-MDV averaged over backbones, B6 leads on **≥ 3 of 4 primary metrics** (Chart Data F1, Graph Edge F1, Evidence F1, Intent Coverage), with at least Evidence F1 Δ ≥ +0.020.
4. **Per-challenge breadth**: B6 leads on **≥ 4 of 5 challenge types** in T3 by Evidence F1.
5. **Held-out (chart side)**: Text2Vis within −7 %p of B7 Text2Vis-orig specialist; Doc2Chart within −7 %p of B8 Doc2Chart-orig specialist (Table 1).
6. **Held-out (diagram side)**: SciDoc2DiagramBench within −7 %p of B9 SciDoc2Diagrammer-MAF specialist on CLIPScore + human readability (Table 1). **This criterion fills the diagram-side external-eval gap that single-bench Text2Vis-only could not address.**

### 0.3 Backbone pool (v0.3.1 amended)

| Slot | Model | Tier | Role |
|---|---|---|---|
| O1 | Qwen3.5-397B-A17B-FP8 | open frontier | primary measurement backbone (already gate-passed scope-v3) |
| O2 | DeepSeek-V4-Flash | open MoE | second-architecture supplementary (existing seed42 result) |
| C1 | GPT-5-mini | closed budget | cost-efficient closed evidence |
| C2 | Claude Opus 4.8 | closed frontier | top-tier closed evidence |

Filter models for difficulty filtering (§10): GPT-5 full + Claude Opus 4.7. Neither is in the eval pool — circularity blocked.

---

## 1. How to read this guide

### 1.1 Three categories of file change

- **[REUSE]** — file exists in legacy at `_legacy_v0.4_pre_harness/...`; port path/imports only.
- **[EXTEND]** — file exists; add fields / methods as specified.
- **[NEW]** — file does not exist; create from scratch.

### 1.2 Two orthogonal axes that drive everything

| Axis | Values | Drives |
|---|---|---|
| **Challenge type** (primary) | A multi_hop / B artifact_planning / C mixed_artifact / D distractor_heavy / E contradiction | difficulty filter; headline reporting (T3); capability claims |
| **Output structure** (secondary) | quantitative / relational / temporal / hierarchical / comparative | TMG soft-prior mapping; per-output-type breakdown |

Both axes required. Every query carries both labels.

### 1.3 Metric suite headline (NOT a weighted composite — replaces earlier fabricated "FSOS")

The earlier draft introduced "FSOS = 0.35×chart + 0.35×graph + 0.20×evidence + 0.10×intent" — those weights had no theoretical or empirical grounding. **Dropped**. Reviewer P4 attack: "where do these weights come from?" had no defense.

Instead, we report all four primary metrics in parallel and define a **multi-criterion strict gate** (§0.2 acceptance criteria #3):

| Metric | Designated primary for | Reporting |
|---|---|---|
| **Evidence F1** | C4 finding (multi-doc grounding gap) | headline figure + Table 4 primary column |
| **Chart Data F1** | C2 method quality on chart artifacts | T1, T3, T6, T7 columns |
| **Graph Edge F1** | C2 method quality on diagram artifacts | T1, T3, T6, T7 columns |
| **Intent Coverage** (Hungarian) | C2 multi-artifact planning quality | T3 Type-B column primary |

**Strict §16 gate replacement**: B6 must lead on ≥ 3 of 4 primary metrics with at least Evidence F1 Δ ≥ +0.020 vs strongest baseline. Per-metric Δ tabulated; no single composite reported as "the score".

This matches Doc2Chart / ChartEval / DiagramEval precedent — those papers all report metric suites without weighted composites. It also defangs the "where do weights come from" attack.

### 1.4 Mandatory rules

1. Test wrapper: `scripts/run_tests.sh` only.
2. No prompt cache breaking. Ablation variant selection at agent init only.
3. `get_hermes_home()` / `display_hermes_home()` for paths.
4. No change-detector tests; assert invariants ("every metric in [0,1]"), not snapshots ("len(metrics) == 8").
5. Deterministic: temperature=0, seed ∈ {42, 43, 44}, three-seed reporting for every Main Result row.
6. DSL-only model output (Chart.js JSON or Mermaid markdown).
7. Difficulty filter circularity ban: filter = GPT-5 full + Opus 4.7 (neither in eval pool).
8. No circular eval: checklist generator (Opus 4.8) ≠ scorer (GPT-5-mini).
9. `EXAONE_V19_ADAPTER=1` everywhere.
10. **A5 image judge uses Anthropic API** (Claude Sonnet 4.6 SDK), NOT `claude -p` CLI. CLI subscription has rate limits that block 2,800-call batch (§2.4).

---

## 2. Visual image evaluation — full coverage (user-emphasized priority)

Image-level eval is **secondary** to deterministic structured metrics, but **mandatory** for this paper. Every prior viz-generation benchmark (Plot2Code, MatPlotAgent, SciDoc2-MAF, ChartLlama, VisJudge-Bench) reports image-level metrics; removing it = certain reviewer attack.

### 2.1 Three layers and existing files

| Layer | Metric | File status | Scope | Cost |
|---|---|---|---|---|
| Deterministic | **M1 render_success** | `_legacy/code/render/renderer.py` (381 LOC) → `exaone/viz_tools/_renderer.py` **[REUSE]** | all 8,400 viz (300 × 7 × 4 backbones) | $0 |
| Deterministic | **M5 CLIPScore** | `_legacy/code/metrics/clipscore.py` (205 LOC) → `code/metrics/clipscore.py` **[REUSE]** | all 8,400 viz | $0 (local HF CLIPModel) |
| | M5 batch runner | `_legacy/code/scripts/clipscore_batch.py` (140 LOC) **[REUSE]** | applies M5 across viz set | $0 |
| LLM judge | **A5 readability / layout / overall** | `_legacy/code/judge/image_judge.py` (304 LOC) **[EXTEND]** | 100-record subset × 7 × 4 = 2,800 | ~$11 (Anthropic API, batch) |
| | Sonnet direct-call subset baseline (for B6 comparison) | `_legacy/code/scripts/run_sonnet_subset.py` (148 LOC) **[REUSE]** | ~50 records | API only — NOT subscription |
| Cross-judge | A5 cross-judge spot | extend `image_judge.py` **[EXTEND]** | 50 viz × GPT-5-mini vision | ~$0.5 |

### 2.2 Required changes to existing files

- **`code/metrics/clipscore.py`** [REUSE]: no behavior change. Add `_envelope.py` decorator (§3.3).
- **`code/judge/image_judge.py`** [EXTEND]: **switch transport from `claude -p` CLI to Anthropic API SDK**. Existing 304 LOC structure stays; replace CLI call with `anthropic.Anthropic().messages.create(model="claude-sonnet-4-6", ...)` with image content block. Reason: Sonnet `claude -p` CLI rate-limits halt 2,800-call batches. API has explicit per-minute quota that we can saturate up to.
- **`code/scripts/run_sonnet_subset.py`** [REUSE with same API switch]: Sonnet-as-baseline direct calls also via API.

### 2.3 A5 judge — API-mode prompt + cost model

```python
# code/judge/image_judge.py (extended)

import anthropic
import base64
from pathlib import Path

_CLIENT = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env

A5_PROMPT = """You are evaluating a visualization generated to answer the query below.
Query: {query}

Rate the rendered visualization on three axes, score 1-5 each.
Output ONLY a JSON object:
{{
  "readability": {{"score": <int 1-5>, "reason": "..."}},
  "layout":      {{"score": <int 1-5>, "reason": "..."}},
  "overall":     {{"score": <int 1-5>, "reason": "..."}}
}}

Rubrics:
  readability: axis labels visible, legend present, font readable, no text overlap
  layout: appropriate whitespace, visual hierarchy, no element collision
  overall: does this artifact help answer the query?
"""

def judge_image_api(
    image_path: str, query: str,
    model: str = "claude-sonnet-4-6",
    use_batch: bool = True,
) -> dict:
    image_b64 = base64.standard_b64encode(Path(image_path).read_bytes()).decode()
    message = _CLIENT.messages.create(
        model=model, max_tokens=500,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/png", "data": image_b64}},
            {"type": "text", "text": A5_PROMPT.format(query=query)},
        ]}],
        extra_headers={"anthropic-beta": "message-batches-2024-09-24"} if use_batch else {},
    )
    return _parse_json_strict(message.content[0].text)
```

Cost estimate (Sonnet 4.6 pricing $3/M input, $15/M output, batch −50%):
- Per judgment: ~1500 input tokens (image + prompt) + 200 output tokens
- Batch input: 1500 × $1.50/M = $0.00225
- Batch output: 200 × $7.50/M = $0.0015
- Per judgment ≈ $0.00375
- 2,800 judgments ≈ **$11**

Cross-judge spot (50 viz × GPT-5-mini-vision): 50 × $0.01 ≈ $0.5.

### 2.4 Sampling protocol

| Metric | Coverage | Allocation |
|---|---|---|
| M1 | all 8,400 viz | direct from renderer return |
| M5 CLIPScore | all 8,400 viz | `clipscore_batch.py` end-to-end |
| A5 readability/layout/overall | stratified 100-record sub × 7 × 4 = 2,800 | stratify by challenge_type only (20 per type), random within type, seed=42 |
| A5 cross-judge κ | 50 viz | random from the 2,800; G11 gate κ ≥ 0.6 |

### 2.5 Renderer failure taxonomy (M1)

In `RenderResult.error`:
- `parse_error_chartjs`, `parse_error_mermaid` — invalid DSL
- `render_timeout` — > 30 s
- `render_blank_image` — content < 1% of canvas (pixel variance check)
- `render_clipped` — overflow

`M1 = 1.0 if render_success else 0.0`.

---

## 3. Evaluation paradigm overview

### 3.1 Three-tier structure

```
Tier 1 PRIMARY (deterministic structured)
  chart_data_f1 + graph_edge_f1 + evidence_f1 + intent_coverage
  → all four reported separately (no weighted composite)
  → multi-criterion strict gate (§1.3)

Tier 2 SECONDARY (image-level — §2)
  M1 + M5 + A5 readability/layout/overall
  → reported as separate column, NOT mixed into Tier 1

Tier 3 SANITY (4-axis RocketEval judge)
  Faith / Coverage / Type-Appropriateness / Cross-Doc Integration
  → run on 100 subset, validate Spearman r ≥ 0.65 vs Tier 1 Evidence F1
  → existing scope-v3 framework, kept for backward compat
```

### 3.2 Per-challenge-type capability-specific signals

In addition to the 4 primary metrics, each query gets a type-specific signal. Reported in appendix per-type tables.

| Challenge | Signal | Used in |
|---|---|---|
| A multi_hop | `cross_doc_evidence_recall` = ︱{docs evidence pulls from} ∩ gold_docs︱ / ︱gold_docs︱ | T3 Type-A appendix col |
| B artifact_planning | `artifact_count_match` = 1 if ︱emitted︱ within ±1 of gold_intent_count else 0 | T3 Type-B |
| C mixed_artifact | `modality_coverage` = 1 if both chartjs and mermaid present else 0 | T3 Type-C |
| D distractor_heavy | `distractor_contamination` = ︱facts-in-viz ∩ gold_distractor_facts︱ / ︱facts-in-viz︱ (↓ better) | T3 Type-D |
| E contradiction | `contradiction_coverage` = 1 if both_claims_present ∧ correct_supported_side_marked else 0 | T3 Type-E |

These are reported but never folded into the primary metric set (would bias headline toward B6).

### 3.3 Reproducibility envelope

Every metric output JSON includes:

```json
{
  "metric_version": "0.4.1",
  "git_commit": "...",
  "seed": 42,
  "computed_at": "ISO-8601",
  "input_hashes": {"artifact": "sha256:...", "gold": "sha256:..."}
}
```

[NEW] `code/metrics/_envelope.py` decorator.

---

## 4. Query generation v0.4.1

### 4.1 Schema extension

Legacy `_legacy/code/utils/generate_queries.py` (331 LOC) had `{qid, text, bundle_id, query_type ∈ Quant/Rel/...}`. Extend with challenge axis + Hungarian intent fields.

[EXTEND] new home `exaone/sft_gen/docviz/query_schema.py`:

```python
from dataclasses import dataclass, field
from typing import Literal

ChallengeType = Literal["multi_hop", "artifact_planning", "mixed_artifact",
                        "distractor_heavy", "contradiction"]
OutputType = Literal["quantitative", "relational", "temporal",
                     "hierarchical", "comparative"]

@dataclass
class Intent:
    intent_id: str
    artifact_type_hint: str   # "chartjs_*" | "mermaid_flowchart" | "any"
    content_summary: str

@dataclass
class Query:
    qid: str
    text: str
    bundle_id: str
    source: str               # hotpotqa | multinews | arxiv | 10k | govreport | tech_docs
    challenge_type: ChallengeType         # NEW primary axis
    output_type: OutputType               # legacy axis, kept
    secondary_tags: list[ChallengeType] = field(default_factory=list)
    gold_intent_count: int = 1
    gold_intents: list[Intent] = field(default_factory=list)
    filter_signal: str = ""
    filter_models_majority: list[str] = field(default_factory=list)
```

### 4.2 Source × challenge compatibility matrix

[NEW] `exaone/sft_gen/docviz/quota.py`:

| Source | A multi_hop | B planning | C mixed | D distractor | E contradiction |
|---|---|---|---|---|---|
| HotpotQA | ✓ primary | ok | low | ok | — |
| MultiNews | ok | ok | ok | ok | ✓ primary |
| arXiv | ok | ✓ primary | ✓ primary | ok | low |
| 10-K | ok | ok | low | ✓ primary | ok |
| GovReport | ok | ok | ok | low | ok |
| Tech Docs | low | ✓ primary | ✓ primary | ok | low |

Target: ~60 per challenge_type, ~50 per source, 300 total.

### 4.3 1-shot demos per challenge type

[NEW] `exaone/sft_gen/docviz/prompts/query_gen/`:
```
base.txt
demo_multi_hop.txt
demo_artifact_planning.txt
demo_mixed_artifact.txt
demo_distractor_heavy.txt
demo_contradiction.txt
```

5 demos. Each MUST include full `Intent` decomposition. LLM emits JSON with `query_text`, `output_type`, `gold_intents[]`.

### 4.4 Generation entry point

[NEW] `exaone/sft_gen/docviz/generate_queries.py`:

```python
def generate_queries(
    bundles_dir: str, output_jsonl: str,
    target_count: int = 600, seed: int = 42,
) -> None:
    bundles = load_bundles(bundles_dir)
    quota_plan = compute_quota(bundles, SOURCE_CHALLENGE_COMPATIBILITY,
                               target_count=target_count, seed=seed)
    with open(output_jsonl, "w") as f:
        for bundle in bundles:
            for challenge in quota_plan[bundle.id]:
                demo = load_demo(challenge)
                candidate = call_gpt_4o_mini(...)
                f.write(json.dumps(asdict(Query(...))) + "\n")
```

### 4.5 Type-specific phrasing rules

**Mandatory** — violation = cherry-pick attack.

| Type | Allowed | Forbidden |
|---|---|---|
| A multi_hop | "Across the three reports…" / entity-based ref | naming docs by id |
| B planning | "Create the appropriate set…" (hidden gold count) | "Create N artifacts" |
| C mixed | **implicit need**: "Explain findings visually" (content forces chart + diagram) | **explicit "chart and diagram"** |
| D distractor | "Use only the final 2025 results, not preliminary" | "Ignore the irrelevant tables" |
| E contradiction | "Visualize the conflicting claims about X" | naming the correct doc |

Enforced via demo content + regex post-filter.

---

## 5. B6 generation pipeline

### 5.1 generate_viz tool — multi-artifact extension

Legacy `_legacy/code/agent_tools/generate_viz.py` (445 LOC) → `exaone/viz_tools/handle_generate_viz.py` (~250 LOC, drops bits ir-shim/v19 already cover).

```python
from typing import Literal
from pydantic import BaseModel, Field
from exaone.tool_formatting import format_tool_result, Index

VizType = Literal[
    "chartjs_bar", "chartjs_line", "chartjs_grouped_bar",
    "chartjs_pie", "chartjs_scatter",
    "mermaid_flowchart", "mermaid_timeline", "mermaid_mindmap",
    "mermaid_sequenceDiagram", "mermaid_classDiagram",
]

class ArtifactSpec(BaseModel):
    viz_type: VizType
    intent: str = Field(..., max_length=200)
    content_brief: str = Field(..., max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list,
        description="REQUIRED for B6 full. Format: '{doc_id}#{chunk_id}#{span}'.")

class GenerateVizInput(BaseModel):
    artifacts: list[ArtifactSpec] = Field(..., min_length=1, max_length=3,
        description="1-3 artifacts. Agent decides count from query's analytic intent.")

def handle_generate_viz(artifacts, *, context):
    emitted = []
    for spec in artifacts:
        dsl = _synthesize_dsl(spec.viz_type, spec.content_brief)
        if not (validation := preflight_validate(spec.viz_type, dsl)).ok:
            dsl = _synthesize_dsl(spec.viz_type, spec.content_brief,
                                  prior_error=validation.error)
        render_result = render(spec.viz_type, dsl, context.viz_dir)
        sidecar_path = write_sidecar(context.viz_dir, {
            "viz_type": spec.viz_type, "intent": spec.intent,
            "evidence_ids": spec.evidence_ids, "dsl_code": dsl,
            "render_success": render_result.render_success,
            "image_path": render_result.image_path,
        })
        emitted.append({...})
    return format_tool_result(
        text=f"Emitted {len(emitted)} artifact(s).",
        citations=[Index(...) for _ in emitted],
    )
```

`EXAONE_V19_ADAPTER=1` handles schema enforcement.

### 5.2 V4 prompt → harness 5-block

Legacy `_legacy/code/pipelines/tmg.py` (223 LOC) → split:
- `prompts/identities/docviz.txt` — V4 preamble
- `prompts/style/docviz.txt` — citation Index format, finalization
- `prompts/tools/generate_viz.txt` — tool description + 10-viz pool + SAO precondition

Required additions in `generate_viz.txt`:
1. 10-viz-type pool exposure
2. Multi-artifact instruction
3. evidence_ids precondition (SAO)
4. Soft-prior mapping

### 5.3 Ablation via identity-file swap

| Variant | Identity file | Selector |
|---|---|---|
| B6 full | `prompts/identities/docviz.txt` | `DOCVIZ_VARIANT=full` (default) |
| B6_NoCIS | `prompts/identities/docviz_nocis.txt` | `=nocis` |
| B6_NoSAO | `prompts/identities/docviz_nosao.txt` | `=nosao` |
| B6_NoTMG | `prompts/identities/docviz_notmg.txt` | `=notmg` |

`exaone/qa_modes.py` resolves at agent init. No agent-loop change.

### 5.4 1-shot exemplars per viz_type

10 exemplars at `exaone/prompts/tools/generate_viz_exemplars/{viz_type}.json`. Each: one valid DSL + evidence_ids format + intent/content_brief.

---

## 6. Baselines (B1-B5, B7)

### 6.1 Existing pipelines [REUSE with thin schema adapter]

`_legacy/code/pipelines/s1_direct.py` (B5), `s7_self_refine.py` (B7), `b1_matplotagent.py` … `b4_vividoc.py`.

### 6.2 Post-hoc adapter for baselines

[NEW] `code/adapters/baseline_to_artifact.py`:

```python
def adapt_baseline_output(raw_text: str, pipeline_id: str) -> list[ArtifactSpec]:
    """Extract chartjs / mermaid blocks from free-form baseline output.
    Returns one ArtifactSpec per detected block. evidence_ids always [].
    intent inferred via 1-line GPT-5-mini call on block content."""
```

### 6.3 Evidence F1 asymmetry — defended by design

B6 emits explicit `evidence_ids`; baselines emit none → implicit grounding via embedding similarity (§9.4). Defense: explicit/implicit modes reported as **separate columns**; ablation row `B6 -SAO` drops to implicit mode like baselines.

---

## 7. DSL parsers

Legacy `_legacy/code/judge/dsl_parser.py` (144 LOC) does syntax validation only. Extend with normalized extraction.

### 7.1 Chart.js parser [EXTEND]

```python
@dataclass
class NormalizedTable:
    chart_type: str
    columns: list[str]
    series: list[Series]
    cells: list[Cell]

def parse_chartjs_to_table(dsl_code: str) -> NormalizedTable | None:
    """Deterministic. None on syntax error."""
```

### 7.2 Mermaid parser [NEW vendor]

Vendor DiagramEval upstream parser (Apache-2). Location: `code/judge/_vendor/diagrameval_parser.py`. Pin mermaid-cli 10.x.

```python
def parse_mermaid_to_graph(dsl_code: str) -> NormalizedGraph | None:
    """Delegates to vendored DiagramEval parser."""
```

### 7.3 Parser failure rate gate

Pilot before commit: 30 prototype Qwen3.5-397B outputs. Gate: chartjs_success ≥ 0.85 AND mermaid_success ≥ 0.85.

[NEW] `scripts/parser_pilot.py`.

---

## 8. Gold construction — detailed protocol (expanded per user feedback)

Gold is the most failure-prone part of the pipeline. Bad gold → all metrics meaningless. This section gives the exact extraction prompts, dedup logic, Prolific task forms, and inter-rater protocol.

### 8.1 Schema [NEW]

`exaone/sft_gen/docviz/gold_schema.py`:

```python
@dataclass
class EvidenceSpan:
    id: str               # "{doc_id}#{chunk_id}#{start}-{end}"
    doc_id: str
    chunk_id: str
    text: str             # the verbatim span text (anchors for embedding match)
    span_start: int
    span_end: int

@dataclass
class GoldFact:
    id: str
    statement: str        # normalized declarative sentence
    supporting_evidence_ids: list[str]  # ≥ 1 required
    is_distractor: bool = False
    confidence: float = 1.0  # 1.0 after human verify, 0.5 LLM-only

@dataclass
class GoldTable:
    id: str
    intent_id: str
    chart_type: Literal["bar", "line", "grouped_bar", "pie", "scatter"]
    columns: list[str]
    series: list[Series]
    cells: list[Cell]
    evidence_ids: list[str]

@dataclass
class GoldGraph:
    id: str
    intent_id: str
    diagram_type: Literal["flowchart", "timeline", "mindmap",
                          "sequenceDiagram", "classDiagram"]
    nodes: list[Node]
    edges: list[Edge]
    evidence_ids: list[str]

@dataclass
class GoldContradiction:  # populated only for Type E queries
    id: str
    claim_a: str
    claim_b: str
    supported_side: Literal["a", "b"]
    evidence_ids_a: list[str]
    evidence_ids_b: list[str]

@dataclass
class Gold:
    qid: str
    evidence: list[EvidenceSpan]
    facts: list[GoldFact]
    tables: list[GoldTable]
    graphs: list[GoldGraph]
    contradictions: list[GoldContradiction]
    intents: list[Intent]
```

### 8.2 Multi-LLM union extraction [NEW]

`exaone/sft_gen/docviz/gold_builder.py`:

```python
EXTRACTORS = {
    "A": ("gpt-5-mini", _extract_with_openai),
    "B": ("claude-opus-4-8", _extract_with_anthropic),
}

def build_gold(query: Query, bundle: Bundle) -> Gold:
    """Two-extractor union with bidirectional human verification.
       - Two LLMs (GPT-5-mini + Opus 4.8) extract independently.
       - Union (not majority) on evidence/facts/tables/graphs.
       - Dedup on (statement_text, evidence_set).
       - 90-subset: human verifies bidirectionally:
           (a) source correctness (drop unsupported)
           (b) completeness (add missing)"""
    a = _extract_with_openai(query, bundle)
    b = _extract_with_anthropic(query, bundle)
    return Gold(
        qid=query.qid,
        evidence=_union_dedup(a.evidence, b.evidence,
                              key=lambda e: (e.doc_id, e.span_start)),
        facts=_union_dedup(a.facts, b.facts, key=lambda f: f.statement),
        tables=_union_dedup_by_intent(a.tables, b.tables),
        graphs=_union_dedup_by_intent(a.graphs, b.graphs),
        contradictions=a.contradictions if query.challenge_type == "contradiction" else [],
        intents=query.gold_intents,
    )
```

### 8.3 Extractor prompt template (challenge-type aware)

```python
# exaone/sft_gen/docviz/prompts/gold_extraction/base.txt

You are extracting gold ground-truth for a multi-document visualization
benchmark. You will see (a) a query, (b) multi-document bundle, (c) the
query's intent decomposition. Extract the following, all grounded in
SPECIFIC chunks of the bundle. Do NOT invent.

Query: {query_text}
Challenge type: {challenge_type}
Intent decomposition: {intents}

Documents:
{bundle_docs_with_chunk_ids}

Extract:
1. evidence_spans: text spans you reference. Each as
   {{"id": "doc_X#chunk_Y#start-end", "doc_id": ..., "chunk_id": ...,
     "text": "verbatim span text", "span_start": int, "span_end": int}}

2. facts: declarative sentences answering the query, each grounded
   in one or more evidence_spans. Format:
   {{"id": "f1", "statement": "...", "supporting_evidence_ids": [...]}}

3. tables: if the query's intent calls for chart artifacts, give the
   ideal table representation:
   {{"id": "t1", "intent_id": "i1", "chart_type": "bar",
     "columns": [...], "series": [...], "cells": [...],
     "evidence_ids": [...]}}

4. graphs: if the query's intent calls for diagram artifacts:
   {{"id": "g1", "intent_id": "i2", "diagram_type": "flowchart",
     "nodes": [...], "edges": [...], "evidence_ids": [...]}}

5. distractor_facts (Type D queries only): facts that appear in the
   bundle but are EXCLUDED by query phrasing (e.g., "preliminary
   numbers" when query asks for final). Mark with is_distractor=True.

6. contradictions (Type E queries only): pairs of conflicting claims
   with the side supported by audited evidence:
   {{"claim_a": "...", "claim_b": "...", "supported_side": "a",
     "evidence_ids_a": [...], "evidence_ids_b": [...]}}

CONSTRAINTS:
- Every fact MUST cite ≥ 1 evidence_span_id.
- evidence_span text must be verbatim (no paraphrasing).
- If a fact appears in multiple docs, list all supporting spans.
- For Type D queries: explicitly include the distractor facts you
  observed in the bundle (so we can later test contamination).

Output STRICT JSON conforming to the Gold schema.
```

Per-extractor difference: GPT-5-mini and Opus 4.8 are given the same prompt; we rely on extractor diversity to surface different facts in the union step.

### 8.4 Union / dedup algorithm

```python
def _union_dedup(extractor_a_items, extractor_b_items, key) -> list:
    """Union with conflict resolution.
       1. Build keyed dict from extractor A.
       2. For each B item, if key collision: merge supporting_evidence_ids,
          keep B's statement text (Opus 4.8 priors generally fluent).
       3. For B-only items: append.
       4. Mark provenance: each Gold item records {extractors: ["A"|"B"|"both"]}."""
```

For tables/graphs: dedup by (intent_id, chart_type/diagram_type). For evidence: dedup by (doc_id, span_start). For facts: dedup by normalized statement (lowercase, strip punctuation, sentence-transformer embedding ≥ 0.90 = duplicate).

### 8.5 Human verification — 90 subset Prolific protocol

**Subset selection**: 90 queries stratified by 5 challenge types × 6 sources (15 per type, target 18 per source — minor imbalance, accept). Seed=42.

**Per query, 3 raters perform 3 tasks**:

| Task | Question to rater | Aggregation rule |
|---|---|---|
| T1 source correctness | "For each fact, can you find this in the linked source span? yes/no" | Keep fact iff ≥ 2/3 say yes |
| T2 completeness | "Read the query + bundle. Is there an important fact the gold misses? Add it (free text)." | Each added fact re-verified by 1 additional rater (4th rater pool); accept if confirmed |
| T3 over-extraction | "Are any facts unsupported by the cited evidence? Mark them." | Drop fact iff ≥ 2/3 mark |

Each task is a separate Prolific HIT to avoid cognitive load:
- T1: $0.40 per HIT, 90 × 3 = 270 HITs → $108
- T2: $0.60 per HIT (longer task), 90 × 3 = 270 HITs → $162
- T3: $0.40 per HIT, 90 × 3 = 270 HITs → $108
- Completeness re-verify (4th rater): variable, budget $50 buffer

Total: ~$430.

**Inter-rater agreement gate**: Cohen's κ ≥ 0.6 on T1 and T3 (binary tasks). If below 0.6: rerun task with refined rubric. Computed per challenge_type to detect type-specific rubric failures.

**Rubric clarity**: each task prompt includes 3 worked examples (one easy yes, one easy no, one borderline with explained reasoning) — known to improve κ by 0.1-0.2 in chart-eval Prolific work.

### 8.6 Intent decomposition

- 90 gold subset: human-defined intents (count 1-3 per query), entered as separate Prolific task batched with T2.
- 210 silver: LLM-extracted from `generate_queries.py` output (§4.4). Spot-verify on 30 random; if accuracy < 80% on spot-check, expand human labeling to all 300.

### 8.7 Reuse of legacy infrastructure

`_legacy/code/judge/sample_for_human.py` (172 LOC) **[REUSE]** for stratified subset extraction. Extend output to the 3-task structure above.

### 8.8 Gold artifact pipeline output

Final gold artifact at `data/gold/qg_mdv_v0.4.1.jsonl`. Each line one `Gold` instance JSON-serialized. Build hash + extractor model versions in header.

---

## 9. Metric implementations

### 9.1 Module layout

```
code/metrics/
  __init__.py
  _envelope.py             [NEW]    reproducibility envelope (§3.3)
  chart_metrics.py         [NEW]    §9.2
  mermaid_metrics.py       [NEW]    §9.3
  evidence_metrics.py      [NEW]    §9.4
  hungarian_intent.py      [NEW]    §9.5
  challenge_specific.py    [NEW]    §3.2 type-specific signals
  clipscore.py             [REUSE]  legacy 205 LOC
```

**Note**: there is no `composite_fsos.py` — the earlier draft had one with invented weights; removed. The aggregator simply reports all 4 metrics in parallel (§13.1).

### 9.2 Chart.js metrics [NEW]

```python
def evaluate_chartjs(art: ArtifactSpec, gold_table: GoldTable) -> dict:
    table = parse_chartjs_to_table(art.dsl_code)
    if table is None:
        return {... all 0.0, "parse_failed": True}
    return {
        "chart_type_acc": float(table.chart_type == gold_table.chart_type),
        "chart_data_p":   _set_precision(table.cells, gold_table.cells, sim=_cell_sim),
        "chart_data_r":   _set_recall(...),
        "chart_data_f1":  _set_f1(...),
        "numeric_mae":    _numeric_mae(...),
        "hallucination_row_rate": _count_unmatched(...) / max(len(table.cells), 1),
        "parse_failed": False,
    }
```

`_cell_sim`: 0/1 categorical; numeric within 5% tolerance.

### 9.3 Mermaid metrics [NEW]

Same shape. `_node_sim` = SentenceTransformer cos ≥ 0.75. `_edge_sim` = min(src_sim, tgt_sim, label_sim). Returns `node_f1`, `edge_f1`, `path_alignment`, `relation_hallucination_rate`.

### 9.4 Evidence F1 (explicit + implicit) [NEW]

```python
def evaluate_evidence(art, gold, embedder) -> dict:
    if art.evidence_ids:  # explicit (B6 SAO)
        pred = set(art.evidence_ids)
        gold_ids = {e.id for e in gold.evidence}
        return {"evidence_p": ..., "evidence_r": ..., "evidence_f1": _f1(pred, gold_ids),
                "mode": "explicit"}
    else:                 # implicit fallback (baselines / -SAO ablation)
        viz_elements = _extract_textual_elements(art.dsl_code)
        matched = [gold.evidence[i].id for el in viz_elements
                   if (i, sim) := embedder.best_match(el, gold.evidence) and sim > 0.75]
        return {..., "mode": "implicit"}
```

Embedder: `sentence-transformers/all-mpnet-base-v2`.

### 9.5 Hungarian intent matching [NEW]

```python
from scipy.optimize import linear_sum_assignment

def hungarian_match(artifacts, gold_intents) -> dict:
    n_a, n_g = len(artifacts), len(gold_intents)
    C = np.full((max(n_a, n_g),)*2, 1.0)
    for i in range(n_a):
        for j in range(n_g):
            type_match = float(_type_matches(artifacts[i].viz_type,
                                             gold_intents[j].artifact_type_hint))
            content_sim = _rouge_l(artifacts[i].intent, gold_intents[j].content_summary)
            C[i, j] = 1.0 - (0.4 * type_match + 0.6 * content_sim)
    row, col = linear_sum_assignment(C)
    matched = [(i, j) for i, j in zip(row, col)
               if i < n_a and j < n_g and C[i, j] < 0.5]
    return {"intent_coverage": len(matched) / n_g,
            "redundancy_rate": max(0, n_a - len(matched)) / max(n_a, 1)}
```

### 9.6 Challenge-specific signals [NEW]

`code/metrics/challenge_specific.py` — see §3.2 table for per-type formulas.

---

## 10. Difficulty filter — Stage 2 of query pipeline

### 10.1 Type-specific filter signals [NEW]

`exaone/sft_gen/docviz/difficulty_filter.py`:

```python
FILTER_MODELS = ["gpt-5-full", "claude-opus-4-7"]  # neither in eval pool

def is_too_easy(query, bundle, filter_model_outputs) -> tuple[bool, str]:
    """Majority-of-2: keep iff ≥ 1 filter model fails the criterion."""
    success_a = _type_specific_success(query, filter_model_outputs[FILTER_MODELS[0]])
    success_b = _type_specific_success(query, filter_model_outputs[FILTER_MODELS[1]])
    if success_a and success_b:
        return True, "both_filter_models_solved"
    return False, f"{failed_model}_failed_on:{signal}"

def _type_specific_success(query, artifacts) -> bool:
    ct = query.challenge_type
    if ct == "multi_hop":         return _n_docs(artifacts) >= 2
    elif ct == "artifact_planning": return len(artifacts) == query.gold_intent_count
    elif ct == "mixed_artifact":  return _has_chart(artifacts) and _has_diagram(artifacts)
    elif ct == "distractor_heavy": return _distractor_contamination(...) < 0.05
    elif ct == "contradiction":   return _contradiction_correctly_handled(...)
```

### 10.2 Two-tier filter output

- Strict: both filter models fail. Cap 100 (hardest set).
- Soft: at least one fails. Cap extra 200.
- Total: 300.

Paper §7 reports twice — on strict-100 and on full-300.

### 10.3 Run

```bash
python -m exaone.sft_gen.docviz.difficulty_filter \
  --candidates data/queries/candidates_600.jsonl \
  --bundles_dir data/bundles \
  --filter_models gpt-5-full opus-4-7 \
  --strict_target 100 --soft_target 200 \
  --output data/queries/qg_mdv_300.jsonl
```

Cost: ~$132 one-time (600 × 2 calls).

---

## 11. Held-out cross-task generalization (Tier 1 face — 3 benches: Text2Vis + Doc2Chart + SciDoc2DiagramBench)

**Revised scope** (per held-out audit committed by user, 2026-06-02):

- **Text2Vis (chart-side general)** — primary held-out; general chart generation from text. Required.
- **Doc2Chart (chart-side intent-driven, EMNLP 2025 Main)** — primary held-out; intent-driven chart from documents — *sharpest specialist comparison* for our intent-driven setting. Required.
- **SciDoc2DiagramBench (diagram-side, EMNLP 2024 Findings)** — primary held-out; **diagram generation from scientific papers** — fills the diagram-side external-eval gap. Without this, our diagram capability (5 mermaid types) has *zero external evaluation*. Required.
- **Plot2Code** — optional appendix sensitivity. Unaligned with our setting; previously deemed optional in v0.3 §5.4 and confirmed optional here. Run only if Phase 7 budget allows.
- **ViviBench** — **dropped**: code unreleased; self-reimplementation is unaudited methodology → reviewer attack with no defense. Defer to v0.5.
- **VisDoM (multi-doc reverse-QA augmentation)** — **deferred**: optional sensitivity for v0.5; not in v0.4.1 implementation.

Three-bench Tier 1 face (chart × 2 + diagram × 1) is **substantially stronger** than the previous Text2Vis-only configuration:
- Universality concern addressed: chart + diagram both externally validated.
- Three specialist comparisons (B7, B8, B9) — single-bench dependency removed.
- EMNLP 2024 Findings + EMNLP 2025 Main venue precedent fully exploited.

### 11.1 Text2Vis — chart-side general held-out

| File | Status | Role |
|---|---|---|
| `_legacy/code/utils/load_text2vis.py` (155 LOC) | **[REUSE]** | loader |
| Text2Vis eval adapter | **[NEW]** | ~150 LOC; Text2Vis published 4-axis eval (answer correctness, chart correctness, chart readability, visual accuracy) |

Wiring: `DOCVIZ_BENCH=text2vis` → `data/bundles/text2vis.jsonl`. 100-sample subset (random seed=42 from Text2Vis dev), 6 baselines × 4 backbones = 2,400 cells.

Specialist: **B7 Text2Vis-orig** on same subset. Target: B6 within −7 %p of B7 on 4-axis avg.

### 11.2 Doc2Chart — chart-side intent-driven held-out (EMNLP 2025 Main precedent)

Reference: Jain, Ramu, Garimella, Saxena — "Doc2Chart: Intent-Driven Zero-Shot Chart Generation from Documents", EMNLP 2025 Main 1770. arXiv 2507.14819.

| File | Status | Role |
|---|---|---|
| `code/utils/load_doc2chart.py` | **[NEW]** ~120 LOC | Doc2Chart raw → docviz Bundle loader |
| `code/eval/doc2chart_eval.py` | **[NEW]** ~150 LOC | adapter applying Doc2Chart's chart accuracy + intent adherence + hallucination metrics |

Wiring: `DOCVIZ_BENCH=doc2chart` → `data/bundles/doc2chart.jsonl`. 100-sample subset, 6 baselines × 4 backbones = 2,400 cells.

Specialist: **B8 Doc2Chart-orig** on same subset (their multi-stage framework: intent decomp → iterative data extraction → chart type heuristic selection). Target: B6 within −7 %p of B8 on chart accuracy + intent adherence avg.

**Why this is the sharpest specialist comparison**: Doc2Chart's setting (intent + documents → chart) is closest to our QG-MDV single-doc sub-case. Their *one-shot heuristic* type selection is the direct comparison target for our *agent-inferred TMG* — head-to-head on the same dimension.

**Risk**: Doc2Chart-orig may genuinely beat B6 on single-doc intent-driven chart. Mitigation: frame Doc2Chart as *single-doc chart sub-case* of our QG-MDV; emphasize that B6's advantage lies in multi-doc + multi-viz where Doc2Chart cannot extend.

### 11.3 SciDoc2DiagramBench — diagram-side held-out (EMNLP 2024 Findings precedent) — *fills the gap*

Reference: Mondal, Pramanik, Sharma, Roy, Bhattacharya — "SciDoc2Diagrammer-MAF: Towards Generation of Scientific Diagrams from Documents guided by Multi-Aspect Feedback Refinement", Findings of EMNLP 2024. arXiv 2409.19242.

| File | Status | Role |
|---|---|---|
| `code/utils/load_scidoc2diagram.py` | **[NEW]** ~160 LOC | SciDoc2DiagramBench raw → docviz Bundle loader (89 ACL papers, 1,080 diagrams) |
| `code/eval/scidoc2diagram_eval.py` | **[NEW]** ~200 LOC | adapter: CLIPScore (reuse our M5) + completeness / faithfulness / layout Likert 1-5 via Anthropic API Sonnet vision (same path as A5) |

Wiring: `DOCVIZ_BENCH=scidoc2diagram` → `data/bundles/scidoc2diagram.jsonl`. 200-sample subset (their bench supports larger sample), 6 baselines × 4 backbones = 4,800 cells.

Specialist: **B9 SciDoc2Diagrammer-MAF** on same subset. Target: B6 within −7 %p of B9 on CLIPScore + completeness Likert avg.

**Important format mismatch (document honestly)**: SciDoc2DiagramBench's original eval uses ROUGE / BERTScore on TikZ code. **We emit Mermaid markdown** — TikZ/Mermaid are not character-comparable. Therefore:
- We **skip** their ROUGE/BERTScore metrics (paper note: "format mismatch; not applicable").
- We **apply** their CLIPScore + human Likert (image-level, format-agnostic).
- Paper §11 limitation note: "Comparison on SciDoc2DiagramBench restricted to image-level metrics due to DSL format mismatch (Mermaid ≠ TikZ)."

This is acceptable: image-level metrics ARE their two human-validated axes; we lose only the code-comparison axis.

**Why this fills the gap**: SciDoc2DiagramBench tests *exactly* the capability our diagram-side has zero external validation for — diagram generation from a long document. TMG's diagram-type selection (5 mermaid types) competes head-to-head with their MAF's specialized diagram synthesis. Without this bench: paper diagram claim is internal-only; with it: external anchor.

### 11.4 Plot2Code — optional appendix sensitivity

| File | Status | Role |
|---|---|---|
| `_legacy/code/utils/load_plot2code.py` (162 LOC) | **[REUSE if used]** | loader |
| `_legacy/code/eval/plot2code_eval.py` (193 LOC) | **[REUSE if used]** | adapter |

Specialist: **B10 MatPlotAgent-orig** (if Plot2Code path taken). Phase 7 gating: skip by default.

### 11.5 ViviBench / VisDoM — DROPPED / DEFERRED for v0.4.1

- ViviBench: code unreleased; reimplementation = unaudited methodology. Defer to v0.5.
- VisDoM (multi-doc reverse-QA augmentation): deferred to v0.5 as optional sensitivity. Not in v0.4.1 implementation.

### 11.6 Specialist baseline list (B7-B10) — updated

| ID | Specialist | For bench | Status |
|---|---|---|---|
| B7 | Text2Vis-orig | Text2Vis | required |
| **B8** | **Doc2Chart-orig** | **Doc2Chart** | **required (NEW for v0.4.1)** |
| **B9** | **SciDoc2Diagrammer-MAF** | **SciDoc2DiagramBench** | **required (NEW for v0.4.1)** |
| B10 | MatPlotAgent-orig | Plot2Code | optional |

(Note: in v0.3 spec B8 was ViviDoc-orig and B9 was MatPlotAgent. Renumbered here.)

### 11.7 Cost summary (held-out additions)

| Bench | Cells | Closed-API cost (Opus + GPT-5-mini batch) |
|---|---|---|
| Text2Vis 100 × 6 × 4 backbones | 2,400 | ~$80 |
| Doc2Chart 100 × 6 × 4 | 2,400 | ~$80 |
| SciDoc2DiagramBench 200 × 6 × 4 | 4,800 | ~$160 |
| (Plot2Code 50 × 6 × 4, optional) | 1,200 | ~$40 |
| **Total mandatory held-out** | **9,600** | **~$320** |

Plus SciDoc2DiagramBench image-judge (Sonnet vision): 200 × 7 × 4 = 5,600 judgments × $0.00375 = **~$21** for diagram-side human-replacement Likert. (Could downsample to 100 if budget tight.)

### 11.8 In-domain bench environment switching

| Env value | Dataset JSONL |
|---|---|
| `DOCVIZ_BENCH=full` | `data/bundles/qg_mdv_full_300.jsonl` |
| `DOCVIZ_BENCH=heldout` | `data/bundles/qg_mdv_heldout.jsonl` (if separate split exists) |
| `DOCVIZ_BENCH=text2vis` | §11.1 |
| `DOCVIZ_BENCH=doc2chart` | §11.2 |
| `DOCVIZ_BENCH=scidoc2diagram` | §11.3 |
| `DOCVIZ_BENCH=plot2code` | §11.4 (optional) |

---

## 12. Judge-validation pipeline (Table A3 Layer 2-4)

### 12.1 L2 human alignment

`_legacy/code/judge/sample_for_human.py` (172 LOC) **[REUSE]** for stratified subset extraction. Extend for the 4 Prolific task types (§8.5 T1/T2/T3 plus viz preference for FSOS-equivalent weight check — except we no longer have weights, so this task is replaced by simple per-metric reasonableness check on 50 viz).

Gate: rater agreement κ ≥ 0.6.

### 12.2 L3 cross-judge agreement

`_legacy/code/judge/analyze_correlation.py` (272 LOC) **[REUSE]**. Cohen's κ + Spearman ρ. Extend to compute Tier 1 ↔ Tier 3 correlation (per-metric vs 4-axis judge) for "structured eval consistent with judge" argument.

Gate: κ ≥ 0.70 on Tier 3 cross-judge; Spearman ρ ≥ 0.65 between Tier 1 metric ranking and Tier 3 ranking.

### 12.3 L4 reverse-QA [NEW]

`code/eval/reverse_qa.py`: GPT-5-mini answers query using ONLY generated viz (image attached), accuracy measured. B6 vs strongest baseline gap reported.

Subset: 100 queries × 7 baselines = 700 cells. Cost ~$3.

Gate: B6 − best baseline gap > 0 in direction (Layer 4 directional anchor per v0.3 §8.3).

---

## 13. Aggregation & paper tables

### 13.1 Existing aggregation [REUSE + EXTEND]

`_legacy/code/scripts/aggregate_v04_results.py` (187 LOC) **[EXTEND]**:
1. Replace 4-axis judge mean headline with **4 separate primary metrics** (no composite).
2. Add per-challenge-type breakdown (T3).
3. Add per-output-structure breakdown (T4 TMG evidence).
4. Add image-quality columns (T8 — M1/M5/A5).
5. Implement multi-criterion strict gate logic (§1.3): per-cell PASS/FAIL flag based on ≥ 3 of 4 primary metrics with Evidence F1 Δ ≥ +0.020.

`_legacy/code/scripts/run_v04_pipeline.sh` **[EXTEND]**:
1. P0 parser pilot gate.
2. `clipscore_batch.py` invocation (M5).
3. `image_judge.py` Anthropic-API invocation on 100 subset.
4. `reverse_qa.py` invocation.
5. **Held-out invocations**: Text2Vis (§11.1, mandatory) + **Doc2Chart (§11.2, mandatory)** + **SciDoc2DiagramBench (§11.3, mandatory)** + Plot2Code (§11.4, optional). ViviBench removed.
6. Specialist invocations: **B7 Text2Vis-orig + B8 Doc2Chart-orig + B9 SciDoc2Diagrammer-MAF** on respective benches.

### 13.2 Paper table builder [NEW]

`code/eval/build_paper_tables.py`:

```python
def build_all_tables(outputs_root, backbones, baselines, output_dir):
    """Emits LaTeX tables conforming to outputs/paper/blank_tables_reference.md."""
```

Outputs:
- `tables/T1_headline_cross_task.tex` — QG-MDV + Text2Vis + Doc2Chart + SciDoc2DiagramBench × 7 baselines × per-metric columns (+ optional Plot2Code)
- `tables/T2_composition.tex`
- `tables/T3_per_challenge_type.tex` — **headline-equivalent for C2 method**, 5 rows × 4 metrics × 7 baselines
- `tables/T4_cross_backbone.tex` — Evidence F1 primary, 4 backbones × 7 baselines
- `tables/T5_per_axis.tex` — Tier 3 judge sanity
- `tables/T6_per_source.tex`
- `tables/T7_pillar_ablation.tex` — 4 variants × 4 metrics
- `tables/T8_image_quality.tex` — M1 + M5 + A5
- `appendix/A1_multi_doc_scaling.tex` — Evidence F1 vs doc count
- `appendix/A2_long_context.tex`
- `appendix/A3_validation.tex`

### 13.3 Headline T3 — challenge-type axis (per-metric, no composite)

```
| Challenge | n  | metric              | B6              | strongest baseline | Δ B6 |
| A multi_hop      |80 | Evidence F1        | _ ± _ | _ ± _ | +_  |
|                  |   | Chart Data F1      | _ ± _ | _ ± _ | +_  |
|                  |   | Graph Edge F1      | _ ± _ | _ ± _ | +_  |
|                  |   | Intent Coverage    | _ ± _ | _ ± _ | +_  |
|                  |   | type-specific (cross_doc_evidence_recall) | _ | _ | +_ |
| B planning       |50 | (same 4+1 rows)
| C mixed          |70 | ...
| D distractor     |50 | ...
| E contradiction  |50 | ...
| Overall          |300| ...
```

Acceptance: B6 wins ≥ 4 of 5 challenge types on Evidence F1 with Δ ≥ +0.020 → C2 + C4 jointly validated.

---

## 14. Migration phases & validation gates

| Phase | Scope | Gate |
|---|---|---|
| **P0** Parser pilot | run §7 parsers on 30 prototype Qwen3.5-397B outputs | parser success ≥ 0.85 (chartjs AND mermaid) |
| **P1** Tool & prompt port | extend `generate_viz` to multi-artifact (§5.1); write 4 identity files (§5.3); `EXAONE_V19_ADAPTER=1` everywhere | 5 sample records pass tool→render→sidecar chain |
| **P2** Query regen (300) | run §4.4 generation → §10 filter → §4.5 phrasing audit | quota within ±10%; phrasing regex clean |
| **P3** Gold build | run §8.2 multi-LLM union → §8.5 Prolific 90 subset | inter-rater κ ≥ 0.6 per challenge_type |
| **P4** Metric impl | implement §9 modules (no FSOS — multi-metric reporting) | tests via `scripts/run_tests.sh`; invariants asserted |
| **P5** Pilot on prototype | run new metrics on existing scope-v3 outputs (Qwen + DeepSeek-V4) | per-metric Spearman r ≥ 0.7 vs scope-v3 judge ranking |
| **P6** Backbone full run | E0 pilot for GPT-5-mini and Opus 4.8 (30 records each); on pass commit Layer A 7 × 3 seeds × 4 backbones | E0 PASS = §1.3 multi-criterion gate on 30-record subset for at least one of two pilots |
| **P7** Held-out | Text2Vis 100 + **Doc2Chart 100 + SciDoc2DiagramBench 200** (all mandatory); Plot2Code 50 (optional, budget-gated). Includes specialists B7/B8/B9 invocations | rendering > 90% on each mandatory bench; B6 within −7 %p of each specialist on respective primary metric |
| **P8** Image eval | M5 all (clipscore_batch.py); A5 Anthropic-API on subset 100; cross-judge κ | G11 κ ≥ 0.6 |
| **P9** Validation | L2 Prolific 50 viz × 3 raters; L3 cross-judge; L4 reverse-QA | L2 Spearman ≥ 0.65; L3 κ ≥ 0.70; L4 direction positive |
| **P10** Reporting | run `build_paper_tables.py` | T1-T8 + A1-A3 populated; per-metric Δ tabulated |

### 14.1 Test policy

Invariant tests, not change-detector. Use `scripts/run_tests.sh`.

---

## 15. Risks & open questions

### 15.1 Implementation risks

| ID | Risk | Mitigation |
|---|---|---|
| R1 | Mermaid parser > 15% fail | P0 pilot first; vendor DiagramEval; pin mermaid-cli 10.x |
| R2 | GPT-5-mini fails V4 nested precondition | E0 30-record pilot; fallback = drop GPT-5-mini, reselect |
| R3 | Gold over-extraction → baselines look unfairly worse | bidirectional human verify (add + remove); multi-LLM union (§8.5) |
| R4 | Hungarian matching too lenient | cost threshold 0.5; validate on 30 prototype |
| R5 | Sonnet API rate-limited during 2,800-call A5 batch | use batch API (50% off + async over 24h); per-host quota monitor |
| R6 | Filter circularity — filter LLMs leak via training data overlap | GPT-5 full + Opus 4.7 (neither in pool) |
| R7 | Type C "designed to favor B6" attack | demo phrasing rules (§4.5) regex enforcement |
| R8 | Single-bench Tier 1 face insufficient (resolved by adding Doc2Chart + SciDoc2DiagramBench) | three-bench Tier 1 (chart × 2 + diagram × 1); per-challenge breadth (T3) supplements |
| R9 | Per-metric strict gate (§1.3) may fail on 1 of 4 even if other 3 strong | report all per-metric Δ; multi-criterion threshold ≥ 3 of 4 is permissive enough |
| R10 | **Doc2Chart-orig specialist beats B6 on single-doc intent-driven chart** (genuine setting overlap) | frame Doc2Chart as single-doc sub-case of QG-MDV; emphasize B6 advantage on multi-doc + multi-viz where Doc2Chart cannot extend; report Δ honestly even if negative |
| R11 | **SciDoc2DiagramBench format mismatch (TikZ vs our Mermaid)** prevents code-level metric comparison | restrict to image-level metrics (CLIPScore + Likert via Sonnet vision); document limitation in §11.3 and paper §11 |
| R12 | **Held-out work expands +8-10 days timeline** (Doc2Chart 1-2d + SciDoc2DiagramBench 2-3d adapters + specialist runs) | parallelize with Phase 1-2; expand P7 1 week → 2 weeks; total still within v0.3 timeline buffer |

### 15.2 Decisions deferred to user

- F1 — Gold extractor B model: Opus 4.8 (in eval pool, subtle bias) vs Opus 4.7 (not in pool, misses latest capability). Recommend **4.8 + document bias** since the union is bidirectionally human-verified on 90 subset.
- F2 — Whether to drop 4-axis RocketEval judge after P5 if Tier 1 ↔ Tier 3 Spearman ρ ≥ 0.85. Recommend **keep as Tier 3 sanity** — backward compat with scope-v3 readers.
- F3 — Plot2Code inclusion: optional, gated by Phase 6 budget remainder. Default skip; include only if explicitly cleared.
- F4 — Strict gate threshold permissiveness: 3-of-4 vs 4-of-4 metric pass. Recommend **3-of-4 with Evidence F1 mandatory** — 4-of-4 too strict given Intent Coverage's Hungarian noise.

### 15.3 v0.3 → v0.4.1 amendment summary (for CHANGELOG)

PAPER_MASTER_SPEC sections that change:
- §0.2 positioning paragraph → task-first framing
- §2.1 contributions C1-C5 → C1-C4 (drop "setting-stratified" as contribution)
- §3.6 VizOutput dataclass → ArtifactSpec list + Hungarian intent matching
- §4 task taxonomy → 5 challenge types primary + 5 output structures secondary
- §5.4 external benchmarks: ViviBench removed; **Doc2Chart (EMNLP 2025 Main) added as primary chart-side intent-driven held-out**; **SciDoc2DiagramBench (EMNLP 2024 Findings) added as primary diagram-side held-out — fills diagram external-eval gap**; Plot2Code optional only; Text2Vis chart-side general primary
- §7 baseline matrix: B7-B10 specialists redefined — B7 Text2Vis-orig, **B8 Doc2Chart-orig (NEW)**, **B9 SciDoc2Diagrammer-MAF (NEW, replaces ViviDoc-orig from v0.3)**, B10 MatPlotAgent-orig (optional, was B9 in v0.3)
- §6 model pool 5 → 4 (2 open + 2 closed, tier-spread)
- §8 evaluation framework → 3-tier (deterministic primary multi-metric + image secondary + judge Tier-3 sanity); **no weighted composite**
- §16 strict gate metric → multi-criterion per-metric gate (Evidence F1 primary)
- §19 inviolable rules → +4 entries (parser-first eval, difficulty filter circularity ban, multi-LLM gold union, Anthropic API for A5 judge)

---

## End of guide

Research agent starts from §14 P0 (parser pilot). Sections cross-reference but are independently parseable.

Escalation: any deviation from §1.4 mandatory rules, §10 difficulty filter design, §4.5 phrasing rules, §11 held-out scope, or §1.3 metric-suite gate definition requires human researcher approval.
