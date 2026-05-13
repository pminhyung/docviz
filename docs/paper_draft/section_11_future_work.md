# §11 Future Work (v0.3 draft)

> What v0.3 prototype defers to Week-1, with explicit scope-bounding.

## 11.1 Scale to Full 300-Record Dataset

- **10-K source 18 → 50 tickers**: EDGAR rate-limit bottleneck
  (~20 min/uncached ticker) made the SP500-50 fetch a multi-hour
  batch. Week-1 work writes a parallel-fetch wrapper around
  `sec_edgar_downloader` that issues 5-8 concurrent ticker fetches
  with backoff, bringing the full 50-ticker build under 1 hour.
  Q-axis distribution rises from 18 → 50, restoring amendment §3.5
  footnote target.

## 11.2 Multi-LLM Generalization (Layer A 5-LLM scale)

- v0.3 prototype runs all 7 baselines on **Qwen3.5-397B** alone
  (same-model controlled comparison; §9.2). Week-1 scales to 5 LLMs
  per amendment §10: e.g., GPT-4, Claude 3.5 Sonnet, Gemini 2.0,
  Llama 3.3-70B, Qwen3.5-397B.
- Layer A becomes 5 × 7 × 300 = 10,500 generations (~$525 per
  amendment §10).
- Cross-LLM consistency check: are the per-method Δ patterns
  consistent across LLMs? If yes, the method-shape conclusion is
  LLM-agnostic.

## 11.3 ViviBench Acquisition + Layer B-2

- ViviBench (2026) data not yet publicly downloadable (per probe
  2026-05-12). Per amendment §14, if released, reimplement
  4-dim eval; if not, defer until release. Week-1 monitors release;
  if still unavailable, B-2 row in §10 Cross-Task remains marked
  "deferred — awaiting public data release".

## 11.4 −CIS Ablation Implementation

- Layer D −CIS variant is **deferred** in v0.3 because clean ablation
  requires an agent-server flag (`skip_doc_step` in RunRequestV2).
  Substituting raw concat for doc_summary would test "long context
  tolerance", not "Pillar 1 contribution" — confounded. Week-1
  implements the server flag and runs the −CIS cell.

## 11.5 Closed-API Phase 2 Re-Judge

- Phase 1 Qwen self-judge produces trend signal for paper §7. Per
  amendment §16 addendum, paper-grade headline cells (Layer A main +
  Layer D ablation + Layer B home-turf) get **Phase-2 re-judge** under
  Claude Opus 4.6 scorer + GPT-5 cross-judge. Budget projection
  ~$1,265 (well within §10 envelope).
- Cross-judge κ ≥ 0.6 (G7) becomes the judge-validity evidence row in
  §6 / §8.2.

## 11.6 A5 Image-Judge Batch

- A5 image-judge wrapper (`code/judge/image_judge.py`) is complete
  and 2-fixture verified. Full 100-record sub-sample × 7 baselines =
  700 calls pending closed-API budget activation.
- Cost projection: ~$50-100 (Claude Code subscription via `claude -p`
  CLI; well below pay-per-call API).

## 11.7 SAO Full Implementation

- v0.3 SAO is a stub: `source_attribution` field exists but is
  populated trivially. Week-1 implements per-viz-element source
  binding by:
  1. Augmenting the agent's `generate_viz` tool to emit element-level
     source citations alongside the DSL
  2. Post-processing the DSL parse output to map each element to its
     contributing source doc_id
- Paper §3.5 Pillar 3 claim re-evaluated under full SAO.

## 11.8 Bundle Diversity Extensions

- Per amendment §3.5 line 89, the 6-domain coverage is calibrated to
  ZeroSCROLLS / MMLongBench-Doc precedent. Future extensions: legal
  (e.g., USPTO patents), medical (PubMed abstracts), and narrative
  (Project Gutenberg long stories). Each adds an additional
  domain-shift evaluation row in §7.2 per-source breakdown.

## 11.9 Single-Doc Generalization for B6

- v0.3 §8.3 (C7 finding): B6 V4_consolidated has poor single-doc
  generalization (Plot2Code exec_rate 0.20). Week-1 work: detect
  single-doc input at pipeline entry and degenerate to B5-style
  single-call (vs the full 4-step agent loop). Maintains
  multi-doc strength while removing the held-out-Plot2Code weakness.

## 11.10 Three-Seed Reporting

- v0.3 §7 cells are single-seed (seed=42). Amendment §13
  non-negotiable: "Three-seed reporting for key cells" (seeds 42,
  43, 44, mean ± std). Week-1 work multiplies Layer A + Layer D
  total runtime by 3 (~6-9h compute on workers=3-4). All paper-
  headline numbers must be mean ± std across seeds.

## 11.11 Infrastructure Hardening (C8 follow-up)

§8.4 C8 documented agent-server silent error masking. v0.3 Layer A
B6_full mean (0.735) is dominated by 26/265 Mode A records that
returned 200 OK with empty `final_answer` due to swallowed upstream-LLM
ConnectError in `agent/run_agent_v2.py:459`. Two-fix iteration plan
(see `docs/analysis/v4_cons_fail_root_cause.md`):

1. **Server-side**: re-raise the agent-loop exception so the handler
   surfaces HTTP 503 / non-empty `warnings`. Removes the silent-failure
   class entirely. Requires agent server restart (current uvicorn
   workers=1 instance has been running since 2026-05-11).
2. **Client-side**: detect empty `final_answer` + tokens=0 + duration<5s
   → retry once on a different `_next_reasoner_url()` reasoner host.
   *Implemented in this session* (`s4_agentic_tmg.py:205-230`).
   Preflight on 5 known Mode A records — `hotpot_22_relational` already
   recovered on retry (viz_type=mermaid_timeline, dsl_len=590).

After both fixes are in, Week-1 re-batch of the 26 Mode A records is
expected to recover ~80% (~21 records) to non-empty viz_dsl, lifting
V4_cons full mean from 0.735 → ~0.83-0.85 and bringing Δ vs best
baseline into the +0.02 borderline gate region (per amendment §16
two-phase judge protocol).

## 11.12 Mode B Iteration — agent loop not invoking tool

10 records (Mode B in §8.4 C8) reached `n_steps_max=8` with substantial
reasoning output (10K–120K tokens) but never invoked `generate_viz`.
Hypotheses:
- The rule-17/18 mandatory-tool-call instruction is overridden by the
  model's learned `search → final_answer` prior on long reasoning
  chains.
- Tool prompt's "exemplar = format-only" instruction conflicts with
  the model's tendency to emit DSL directly in reasoning.

Week-1 experiments:
- Increase `n_steps_max` to 12-16 and measure recovery rate.
- Add a soft penalty for "search-only" trajectories (sample fine-tune
  on n=200 multi-doc QG-MDV with positive tool-call labels).
- Test on Qwen3.5-32B-Instruct (smaller model, less learned prior).
