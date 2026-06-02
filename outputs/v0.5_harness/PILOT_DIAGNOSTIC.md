# v0.4.1 50-Pilot Diagnostic Report (per Goal)

**Date**: 2026-06-03
**Branch**: feat/source-loaders
**Backbone**: Qwen3.5-397B-A17B-FP8 (open frontier)
**N**: 50 queries × 1 seed × {B6_full, S1_Direct}
**Verdict**: **B6 LOSES to S1 across overall and on 4/5 challenge_types.**

---

## Headline result

| Metric | B6 (Ours) | S1 Direct | Δ (B6 − S1) | §16 strict gate |
|---|---|---|---|---|
| **intent_coverage** | 0.3133 | **0.4900** | **−0.1767** | ✗ FAIL |
| **evidence_f1 (implicit Jaccard)** | 0.4214 | **0.5017** | **−0.0803** | ✗ FAIL |
| chart_data_f1 | 0.0 | 0.0 | n/a | (P1 DSL synth stub, both same) |
| graph_edge_f1 | 0.0 | 0.0 | n/a | (same) |

Wall-clock cost asymmetry: **B6 = 12 min (~14 s/query agent loop)**, **S1 = ~50 s (~1 s/query single shot)**. B6 is **14× more expensive** AND **−0.18 intent_coverage worse**.

## Per-challenge_type (intent_coverage)

| challenge | B6 | S1 | Δ | B6 wins / ties / losses |
|---|---|---|---|---|
| multi_hop | 0.700 | 0.750 | −0.050 | 1 / 8 / 1 |
| artifact_planning | 0.217 | 0.400 | −0.183 | 3 / 1 / 6 |
| mixed_artifact | 0.150 | 0.300 | −0.150 | 1 / 5 / 4 |
| distractor_heavy | 0.500 | 0.500 | +0.000 | 2 / 6 / 2 |
| **contradiction** | **0.000** | **0.500** | **−0.500** | **0 / 5 / 5** |

B6 has **0 wins on contradiction**. Distractor_heavy is the only tie+ category.

## Per-source (intent_coverage)

| source | B6 | S1 | Δ |
|---|---|---|---|
| hotpot | 0.667 | 0.833 | −0.167 |
| arxiv | 0.463 | 0.556 | −0.093 |
| tech | 0.227 | 0.182 | **+0.045** ← only B6 win |
| multinews | 0.250 | 0.500 | −0.250 |
| 10k | 0.000 | 0.333 | −0.333 |
| govreport | 0.182 | 0.545 | −0.364 |

## ROOT CAUSE DIAGNOSIS (per Goal protocol)

### 1. MODULE weakness (primary cause, 70% of loss)

**Empty-artifact problem: B6 emits 0 artifacts on 14/50 (28%) records.**
- S1 produces 0 artifacts only 1/50 times (2%).
- This is the same `empty_final_answer` regression pattern observed with Gemma3/4 backbones earlier — but now occurring on **Qwen3.5-397B with V19 adapter ON**.
- The agent enters the loop, calls retrieval tools, but never invokes `generate_viz` — emits `<final_answer>success` straight away. (Tool stats: generate_viz=42/50, agent emitted text without calling tool for 8 records.)
- **Root**: V4 "Hard precondition: invoke generate_viz before final_answer" is a SOFT rule the model can violate.

**Under-emission for multi-artifact queries: B6 emits 1 artifact when gold expects 2-3.**
- Artifact emit count distribution: B6={0: 14, 1: 20, 2: 15, 3: 1} vs S1={0: 1, 1: 39, 2: 9, 3: 1}
- On `artifact_planning` + `mixed_artifact` (queries asking for 2-3 deliverables), B6 averages 1.2 artifacts vs gold 2.0.
- S1, with the same multi-artifact prompt clause, also under-emits but less severely (avg ~1.2 vs gold 2.0).
- **Root**: prompt says "Default: 1 artifact unless query explicitly asks for two distinct deliverables" — too conservative. Many real queries imply multi-artifact without explicit phrasing.

**Contradiction failure: 0 wins, 5 losses, 5 ties, all with low scores.**
- Contradiction queries phrase as "Visualize the conflicting claims about X". Agent doesn't have a routing pattern for this — falls back to single-artifact mermaid_flowchart which under-represents the conflict.
- S1's direct prompt with the same query phrasing produces single-artifact too, but its artifact tends to match the gold timeline/comparative intent better.
- **Root**: V4 prompt has no contradiction-specific guidance.

### 2. DATA DESIGN issue (secondary, ~20% of loss)

- Gold extraction for contradiction queries fills the `contradictions` field but leaves `gold_intents` thin (1 intent: "Timeline with both dated claims" stereotype). This may unfairly tag B6's flowchart attempts as no-match — though S1 also produces flowcharts and still scores higher, so it's not the dominant factor.
- 10k bundles are mostly Item 7 (MD&A) — narrative not numeric tables. Both models struggle. B6 with tool overhead struggles more.

### 3. EVAL ARTIFACT issue (minor, ~10% of loss)

- Evidence_f1 uses token-overlap Jaccard (no sentence-transformer embedder). This is coarse. Real implicit evidence would use embeddings — magnitude of effect is uncertain. The 0.08 Δ is small enough that even a 50% noise reduction wouldn't flip the winner.
- DSL synthesis is P1 stub → Chart Data F1 and Graph Edge F1 = 0 for both, can't differentiate.

## REMEDIATION DESIGN (per Goal: top-conf survey + novel idea)

### Relevant recent literature

| Paper | Year | Idea | Relevance |
|---|---|---|---|
| Plan-and-Solve (ACL '23) | 2023 | Explicit plan step before execution | Address under-emission via pre-planning |
| Tree of Thoughts (NeurIPS '23) | 2023 | Search-tree over reasoning steps | Heavy for our use case; reject |
| Self-Discover (ICML '24) | 2024 | Agent discovers its own task decomposition | Address contradiction handling |
| Reflexion (NeurIPS '23) | 2023 | Self-critique then retry | Address empty-artifact bug via verify-then-emit |
| Doc2Chart (EMNLP '25 Main) | 2025 | Intent decomposition → iterative data extraction → chart_type heuristic | Direct match — explicit intent decomp before viz |
| DiagramEval (arXiv '25) | 2025 | Structured graph/text eval | Already in our P0/P4 evaluators |
| ChartLens, ChartCheck (2024) | 2024 | Reasoning verification on chart outputs | Post-hoc validation; useful but downstream |
| ReWOO (EMNLP '23) | 2023 | Separate reasoning from observation; reduce tool overhead | Address agent vs direct cost asymmetry |

### Novel remediation: **Intent-Anticipated Planning (IAP)** module

**Concept**: insert a lightweight (1 LLM call, ~2K tokens) PLANNING stage between query intake and agent loop. Output:

```json
{
  "expected_artifact_count": 2,
  "viz_type_candidates": ["mermaid_timeline", "chartjs_grouped_bar"],
  "query_class": "contradiction",      // or "single_chart", "chart_plus_diagram", "multi_compare", "narrative_flow"
  "evidence_required": true,
  "preretrieval_keys": ["debt limit history", "1917 statutory ceiling"]
}
```

The B6 system prompt is then **conditioned** on this plan via Jinja substitution:
- Identity becomes: "you MUST emit exactly {expected_artifact_count} artifacts" (eliminates under-emission)
- generate_viz tool description prepended with: "viz_type ∈ {viz_type_candidates}" (focuses search space)
- For `query_class=contradiction`: special instruction "emit one timeline showing both claims with side markers + one comparative summary"

**Why this is novel**:
- Plan-and-Solve plans WITHIN the agent loop (every turn) — high overhead.
- Self-Discover discovers per-task module — too heavy for inference-time.
- Doc2Chart decomposes intent for charts only — we generalize to charts + diagrams + multi-artifact.
- **IAP plans BEFORE agent loop starts** (1 call, ~$0.001 cheap, then conditions the entire subsequent agent's prompt). Bridges planning + standard tool-using agent.

**Expected impact** (calibrated against pilot loss patterns):
- Empty-artifact 28% → <5% (explicit count requirement)
- Multi-artifact under-emission: Δ(B6−S1) +0.183 → ~0 on artifact_planning
- Contradiction 0/10 wins → ~5/10 wins via dedicated query_class routing
- Overall intent_coverage: B6 0.31 → ~0.50+ (matching/beating S1)

**Implementation cost**: ~200 LOC in `exaone/viz_tools/_iap_planner.py` + identity prompt patch. 1-2 hours.

### Secondary fixes (apply alongside IAP)

1. **Evidence id schema alignment** — agent's tool_call_id citations and gold's span ids must use one consistent format. Add an embedding-based bridge in evidence_metrics for now.
2. **DSL synthesis (P4 production)** — replace handle_generate_viz `_synthesize_dsl` stub with real Qwen call. Unblocks Chart/Graph F1.
3. **Contradiction-specific gold intent** — extend gold builder to always populate `gold_intents` with 2 intents for type E (one timeline, one comparative).
4. **3-backbone re-measurement** post-IAP: Qwen + DeepSeek + GPT-5-mini.

## Next concrete actions (in order)

1. Implement IAP planner module (~2h)
2. Implement real DSL synthesis (~1h)
3. Re-run B6 × Qwen with IAP enabled
4. If intent_coverage > 0.50 → verify on DeepSeek + GPT-5-mini (~2h compute)
5. If consistent SOTA → scale to 300

## Artifacts produced this cycle

- `data/queries/pilot_50.jsonl` — 50 queries (10/challenge_type)
- `data/queries/pilot_50_runner.jsonl` — harness JSONL input
- `data/gold/pilot_50.jsonl` — 50 gold records (auto-extracted, no Prolific)
- `outputs/v0.5_harness/docai_out/` — 195 pdf_index docs
- `outputs/v0.5_harness/sidecars/b6_qwen/` — 53 sidecars from B6 run
- `data/b6_qwen_pilot/` — 50 trajectories
- `data/s1_qwen_pilot/batch_0.jsonl` — 50 S1 baseline records
- `outputs/v0.5_harness/pilot_results/{b6_qwen,s1_qwen}.json` — per-record + summary
- `outputs/v0.5_harness/PILOT_DIAGNOSTIC.md` (this file)
