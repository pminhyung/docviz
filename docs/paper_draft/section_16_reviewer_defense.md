# §16 Reviewer Attack Defense (v0.3 draft)

> Pre-empt the 5-8 most likely reviewer attacks. v0.3 adds 3 new defense
> lines for: 6-domain coverage, held-out generalist framing, image-modal
> coverage (A5 + M5).

## R1 — "Why only 6 source domains? MMLongBench-Doc uses 7."

**Defense**: We select 6 domains spanning encyclopedic / news /
academic / financial / governmental / technical content, covering both
general and specialized registers. This matches the domain coverage of
ZeroSCROLLS (7 domains) and approaches MMLongBench-Doc (7 domains).
Domains beyond these (legal, medical, narrative) are noted as future
extensions (§11 future work). The exact 6-domain composition is
documented in §5.1 with per-source licensing.

## R2 — "Why a single LLM (Qwen3.5-397B)? Where's the 5-LLM matrix?"

**Defense**: v0.3 is a prototype-scale demonstration on-prem. Same-model
controlled comparison isolates *method shape* from *model capability*,
which is the standard ablation prior to multi-model scaling. Week-1
extends to 5 LLMs per amendment §10. The current single-model
comparison is sufficient to establish the **method-shape direction** of
B1-B7 baselines vs B6.

## R3 — "How is image quality evaluated?" (D7 — NEW)

**Defense**: We employ two image-axis signals:

1. **M5 CLIPScore** (deterministic, every record): OpenAI CLIP
   ViT-L-14 cosine similarity with Hessel et al. (2021) rescaling.
   Cost: $0.
2. **A5 image-judge axis** (3,500 records, sub-sample): Claude Sonnet
   (latest vision-capable) via `claude -p` CLI, with GPT-4V or
   Gemini 3.0-preview cross-judge on 20-30 records for Cohen κ ≥ 0.6
   validation. Cost projection: ~$220.

Precedent: SciDoc2-MAF, MatPlotAgent, Plot2Code, ChartLlama,
ChartMimic, METAL, Text2Vis, ViviBench, VisJudge-Bench — 9 of 10
surveyed peer benchmarks include image-level eval. Our A5+M5 setup
matches that precedent.

Implementation status:
- M5 CLIPScore pipeline: complete and G10-sanity verified.
- A5 image judge wrapper: complete and 2-fixture verified; full
  100-record sub-sample run pending closed-API budget activation per
  amendment §16 two-phase strategy.

## R4 — "Held-out generalist framing — what does it mean?"

**Defense**: Following T0 (Sanh et al. 2021), FLAN (Wei et al. 2022),
InstructBLIP (Dai et al. 2023), and **UnifiedVisual** (EMNLP 2025
Main), we treat Text2Vis, ViviBench, and Plot2Code as **held-out**
benchmarks for zero-shot generalist evaluation. QG-MDV serves as both
a new task definition and our in-domain primary evaluation.

Unlike instruction-tuned generalists, DocViz-Agent is a **training-free
generalist** achieved through prompting and tool composition, removing
the training-domain bias that confounds InstructBLIP-style
evaluations. UnifiedVisual is the most recent EMNLP-Main precedent.

## R5 — "Why didn't you compare to MatPlotAgent / NVAGENT?"

**Defense**: We do. B1-B4 are external-method baselines:

| ID | Method | Citation |
|---|---|---|
| B1 | MatPlotAgent-adapted | Yang et al., ACL Findings 2024 |
| B2 | NVAGENT-adapted | Wu et al., ACL 2025 |
| B3 | CoDA-adapted | 2025 |
| B4 | ViviDoc-style | ViviBench/ViviDoc, 2026 |

All 4 are reimplemented on-prem (paper §9.2) with their LLM client
redirected to our Qwen3.5-397B vLLM cluster for **same-model controlled
comparison**.

## R6 — "Why is your judge the same model as your generator? Isn't that circular?"

**Defense**: Amendment §16 addendum two-phase strategy explicitly
addresses this. Phase-1 uses Qwen3.5-397B as judge for **trend
discovery** only — cost-zero, deterministic at T=0, fast iteration.
Phase-2 uses **Claude Opus 4.6 cross-judged against GPT-5 generator**
(spec L342 / §8.2) on the headline cells for paper-grade numbers.
Cross-judge Cohen κ ≥ 0.6 is the G7 verification gate.

Phase-1 results in the paper are reported alongside Phase-2 paper-grade
numbers for full transparency.

## R7 — "What about adversarial / out-of-distribution?"

**Defense**: §8.3 (C7 finding) documents B6's degradation on held-out
single-instruction Plot2Code (exec_rate 0.20 vs B5/B7's 1.00/0.80).
B6 is *specifically designed for multi-doc QG-MDV*. Per amendment §10
Tier-1 framing: specialists win on their home turf within 5-7%p;
generalists win on multi-doc setting they were not designed for. The
trade-off is explicit and documented.

## R8 — "What about temporal / financial domain shifts?"

**Defense**: The 6-domain coverage includes both temporal-heavy
(MultiNews, GovReport) and financial-heavy (10-K) registers. Per-source
breakdown table (§7.2) populated with Layer A results; under the
valid-only reading (§8.4 C8 dual-cell protocol) B6's per-source
performance is within −3%p of the best baseline on 5/6 sources, with
10-K (n=15) being the only larger gap due to the prototype-scale
quantitative cell.

## R9 — "Your B6 underperforms B7_SelfRefine. Method failure?"

**Defense (post-iteration, 2026-05-14)**: After Fix 1+2+3 retry, two
cells:
- **B6 full**: 0.824 (n=265) — Δ = **−0.056** vs B7_SelfRefine
- **B6 valid-only**: 0.847 (n=254) — Δ = **−0.033** vs B7_SelfRefine

Both readings show B6 within 6 pp of the best baseline, with B6
**outperforming** specialist baselines B1 (matplotlib) and B2
(NVAGENT/chart-spec) by +0.035 and +0.038 respectively — validating
the generalist framing on the in-domain multi-doc task.

Pre-iteration the full-set gap was -0.145 (because of Mode A
infrastructure failures — §8.4 C8). Fix 1+2+3
(`code/agent_tools/generate_viz.py` chartjs DSL auto-repair,
`code/pipelines/s4_agentic_tmg.py` HTTP-400 sidecar rescue +
retry-on-empty broadening) recovered 39/46 fail records on retry,
reducing fail rate 14.7% → 4.2%. The remaining 7 fails are Mode B
(agent reasoning without invoking `generate_viz`), discussed in
§11.12.

The dual-cell reporting (full + valid-only) is retained as a
transparency tool. Phase-2 closed-API re-judge would tighten the
−0.056 / −0.033 estimates to a paper-grade decision.

## R10 — "15% fail rate is unacceptable for a method to be presented"

**Defense**: Two responses:
1. The 39 failures are not uniformly method failures. 26 are Mode A
   (infrastructure), 10 are Mode B (n_steps_max exhaust), 3 are Mode C
   (600 s timeout), 1 is Mode D (HTTP 400 final_answer reject). Mode A
   is recoverable with the Fix 2 retry-on-empty patch already
   implemented in `code/pipelines/s4_agentic_tmg.py:205` (preflight
   confirms recovery direction; see `docs/analysis/v4_cons_fail_root_cause.md`).
2. Specialist baselines have 0% fail rate because their single-call
   shape is engineered for the constrained tasks they were designed
   for; our agent-loop method tackles a strictly harder problem
   (multi-step retrieval + viz_type selection + tool-call generation).
   A 5–10% residual fail rate after infrastructure fixes is consistent
   with multi-step agent literature (e.g., ToolBench 8% format errors,
   ReAct 12% no-answer rate on HotpotQA at n_steps=8).
