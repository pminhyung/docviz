# §13 Conclusion (v0.3 draft)

> Restates headline + main empirical message. Numbers populate after
> Phase 7 + Phase 9.

## 13.1 What We Built

DocViz-Agent (B6) is a **training-free generalist pipeline** for
Query-Grounded Multi-Document Visualization (QG-MDV). The 3-pillar
architecture — Contextual Input Selection, Type-Mapped Generation,
Source-Attributed Output — operates over 2-N source documents in 6
content domains, emitting one of 10 visualization subtypes that answers
the user's query.

## 13.2 What We Showed (v0.3 prototype, Phase 7 resolved)

- **In-domain QG-MDV** (Layer A, 265 records, 7 baselines, Phase-1
  Qwen3.5-397B judge): B6 does not outperform the strongest baseline.
  Δ(B6 full − B7_SelfRefine) = −0.145; Δ(B6 valid-only − B7_SelfRefine)
  = −0.031 (§7.1). The full-vs-valid spread is dominated by Mode A
  agent-server infrastructure noise (§8.4 C8).
- **Held-out generalization** (Layer B-3 Plot2Code 5-record preflight):
  B6 exec_rate 0.20 vs B5 1.00, B7 0.80 — the single-doc single-call
  setting penalizes our multi-doc agent loop. Tier-1 home-turf framing
  applies (§8.3 C7). Layer B-1 Text2Vis full evaluation deferred to
  Week-1 (`<P5/P6>` cells pending).
- **Each pillar's marginal contribution** (Layer D, 265 × 3 ablation
  cells, running): full results pending; B6_NoTMG mid-run shows the
  Mode A infrastructure pattern is present in the −TMG variant too,
  meaning ablation Δ's must be read under the §8.4 dual-cell protocol.
- **Cross-task average**: not yet computed (Layer B + closed-API gate
  pending Week-1 work).

## 13.3 What We Defer

Per the cost-efficient two-phase strategy (§16 addendum) and
honest-abstention principle (§7.5 −CIS row):
- Phase 2 closed-API re-judge (paper-grade Opus 4.6 numbers): pending
  budget activation (~$1,265)
- A5 image-judge batch (700 calls via `claude -p` Sonnet): pending
  budget activation (~$50-100)
- ViviBench (Layer B-2): pending public data release
- −CIS ablation: pending agent-server `skip_doc_step` flag
  implementation (Week-1)
- Three-seed reporting (mean ± std): Week-1 work (multiplies Layer A
  + D compute by 3×)
- 10-K source 18 → 50 tickers (Q-axis full coverage): Week-1
  parallel-fetch wrapper

## 13.4 Reproducibility

All baseline implementations (B1-B7), the agent server, judge code,
renderer, CLIPScore pipeline, and source loaders are in this
repository's `code/` and `agent/` trees. Run via:

```
bash code/scripts/v4_chain.sh         # (legacy V4-internal study)
bash /tmp/layer_a_chain.sh            # v0.3 Phase 7 Layer A
python -m code.run_prototype --strategies B1,B2,B3,B4,S1,S7_SelfRefine,S4_TMGv4_consolidated
python -m code.judge.run_judge        # Phase-1 Qwen judge
python -m code.analysis.v4_paired_bootstrap  # paired Δ + Cohen's d_z
```

Seed = 42 throughout. On-prem Qwen3.5-397B-A17B-FP8 vLLM cluster
specified in `code/adapters/agent_client.py:QWEN_HOSTS`. Setting
`DOCVIZ_HOST_MODE=multi` enables the 9-host round-robin queue with
30s cooldown + 3s-retry semantics (§3.7).

## 13.5 Headline Claim — v0.3 Prototype Status

The +8%p multi-doc headline that motivated v0.3 does not hold under the
prototype's full-set reading (Δ = −0.145). Per amendment §16, the
publishable claim is therefore *contingent on Week-1 infrastructure
fixes* (§11.11) and accompanying re-batch:

> *"DocViz-Agent (B6) is the first training-free generalist pipeline for
> query-grounded multi-document visualization across 6 content domains
> and 10 visualization subtypes. On the v0.3 prototype (265 records),
> B6 is **competitive with strong direct-LLM and SelfRefine baselines
> on successfully-completed cases** (mean 0.849 vs best baseline 0.880,
> Δ = −0.031 over n=226 valid-only records) but does not yet outperform
> them. The remaining gap is dominated by infrastructure noise in the
> agent-server's silent error-masking path (§8.4 C8), which Week-1
> fixes 1+2 (§11.11) project to recover ~80% of."*

This is **NOT** a paper-publishable headline under amendment §16's gate
protocol (HALT on Δ < +0.02). The published paper must wait on Week-1
re-batch with fixes applied, OR re-frame around a positive secondary
result (e.g., per-source/per-type wins on relational/hierarchical
multi-doc cells where baselines depend on luck-of-the-draw retrieval).

Per amendment §16 two-phase strategy, no Phase-2 closed-API re-judge is
triggered (Δ does not reach +0.05 nor +0.02 borderline). The Week-1
iteration plan is the next gate before paper submission.
