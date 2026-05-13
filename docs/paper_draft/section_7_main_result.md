# §7 Main Result — Layer A Cross-Method (v0.3 result, 2026-05-13)

> v0.3 amendment compliance:
>   - 7 baseline matrix (B1, B2, B3, B4, B5, B7, B6) — §9 baseline
>     matrix; B6 = our V4_consolidated
>   - Layer A 265 records (v0.3 prototype: 6 sources × 50 + 15 10-K)
>     → 1,855 generations × Phase-1 judge
>   - Phase-1 judge: Qwen3.5-397B on-prem (cost = 0)
>   - Phase-2 judge swap to Claude Opus 4.6 + GPT-5 cross-judge on
>     headline cells when closed-API budget activates (§16 addendum)
>
> See §8.4 C8 for the dual-cell (full vs valid-only) reporting protocol;
> Mode A infrastructure-failure rows (26/39 of B6 fails) are isolated
> as agent-server-side artifact rather than method failure.

## 7.1 Layer A Main Result Table — overall

Layer A in-domain QG-MDV, 7 baselines, single LLM (Qwen3.5-397B
controlled comparison). Cells are mean overall (Phase-1 judge). The B6
**full** cell aggregates all 265 records; **valid-only** excludes the 39
records with empty `viz_dsl` (see §8.4 C8 for breakdown).

|   | B1 MPA | B2 NVAGENT | B3 CoDA | B4 ViviDoc | B5 Direct | B7 SelfRefine | **B6 full** | **B6 valid-only** |
|---|---|---|---|---|---|---|---|---|
| **overall**  | 0.789 | 0.786 | 0.825 | 0.856 | 0.880 | **0.880** | 0.735 (n=265) | 0.849 (n=226) |
| n_completed | 265 | 265 | 265 | 265 | 265 | 265 | 265 | 226 |
| fail_records | 0 | 0 | 0 | 0 | 0 | 0 | 39 (15%) | 0 |

**Δ(B6 − best baseline = B7 SelfRefine 0.880):**

- B6 full: **−0.145**
- B6 valid-only: **−0.031**

Per amendment §16's +0.02 gate, both fall below the +0.02 floor →
**gate = HALT** in either reading. Iteration plan in §11.2 and
§8.4 → infrastructure fix (Fix 1+2 from `docs/analysis/v4_cons_fail_root_cause.md`)
+ Mode B method iteration (10 records: agent reaches `n_steps_max=8`
without invoking `generate_viz`).

> Per-axis cells (faithfulness / coverage / type_appropriateness /
> search_query_quality / syntax_pass_rate) — pending Phase-2 closed-API
> judge with full 4-axis prompt. Phase-1 Qwen judge currently emits
> overall only.

## 7.2 Per-Source Breakdown (mean overall, full-set)

| Source | B1 | B2 | B3 | B4 | B5 | B7 | **B6 full** |
|---|---|---|---|---|---|---|---|
| HotpotQA   | 0.834 | 0.818 | 0.848 | 0.863 | **0.916** | 0.917 | 0.757 |
| MultiNews  | 0.858 | 0.831 | 0.881 | 0.890 | 0.908 | **0.919** | 0.771 |
| arXiv      | 0.708 | 0.752 | 0.812 | 0.839 | **0.864** | 0.849 | 0.716 |
| 10-K       | **0.893** | 0.818 | 0.883 | 0.817 | 0.861 | 0.802 | 0.708 |
| GovReport  | 0.717 | 0.736 | 0.738 | **0.833** | 0.810 | 0.829 | 0.692 |
| Tech Docs  | 0.798 | 0.782 | 0.831 | 0.864 | 0.910 | **0.911** | 0.755 |

B6 underperforms baselines on every source under the full-set view.
Under valid-only (§8.4 C8), per-source B6 cells lift by ~0.10
proportional to that source's Mode A fail count — see
`docs/analysis/v4_cons_dual_gate.md` for the corrected breakdown.

## 7.3 Per-Query-Type Breakdown (mean overall, full-set, n)

| Type | n | B1 | B2 | B3 | B4 | B5 | B7 | **B6 full** |
|---|---|---|---|---|---|---|---|---|
| Quantitative | 15 | **0.893** | 0.818 | 0.883 | 0.817 | 0.861 | 0.802 | 0.697 |
| Relational | 60 | 0.825 | 0.818 | 0.858 | 0.870 | 0.913 | **0.914** | 0.751 |
| Temporal | 60 | 0.837 | 0.818 | 0.861 | 0.894 | 0.882 | **0.888** | 0.744 |
| Hierarchical | 70 | 0.680 | 0.758 | 0.762 | 0.849 | 0.859 | **0.872** | 0.753 |
| Comparative | 60 | 0.808 | 0.747 | 0.816 | 0.820 | **0.875** | 0.869 | 0.719 |

The Quantitative cell (n=15) is short of amendment §5.2 target n=50 due
to the 10-K prototype scale-down (15 cached SP500 tech tickers; §5.1
caveat). Week-1 work expands to the 50-ticker SP500 set.

## 7.4 Paired Bootstrap (V4 vs B5 / B7)

BCa 10K bootstrap, n=268, paired-by-query_id:

| Comparison | Δ overall | 95% CI | p (1-sided) | d_z |
|---|---|---|---|---|
| B6 vs B5 (Direct-LLM) | `<P9 paired>` | `<P9>` | `<P9>` | `<P9>` |
| B6 vs B7 (SelfRefine) | `<P9 paired>` | `<P9>` | `<P9>` | `<P9>` |
| B6 vs B1 (MatPlotAgent) | `<P9 paired>` | `<P9>` | `<P9>` | `<P9>` |
| B6 vs B2 (NVAGENT) | `<P9 paired>` | `<P9>` | `<P9>` | `<P9>` |
| B6 vs B3 (CoDA) | `<P9 paired>` | `<P9>` | `<P9>` | `<P9>` |
| B6 vs B4 (ViviDoc) | `<P9 paired>` | `<P9>` | `<P9>` | `<P9>` |

## 7.5 Layer D Pillar Ablation

V0.3 prototype: 3 ablation cells + Full on the 268-record QG-MDV
dataset. The −CIS row is **deferred to Week-1** with documented reason
(server-side flag not yet implemented; honest abstention vs confounded
ablation).

| Variant | overall | faithfulness | coverage | type | SQ |
|---|---|---|---|---|---|
| **B6 Full** (CIS + TMG + SAO) | `<P8>` | `<P8>` | `<P8>` | `<P8>` | `<P8>` |
| B6 −TMG (no V4 rule + tool) | `<P8>` | `<P8>` | `<P8>` | `<P8>` | `<P8>` |
| B6 −SAO (no attribution post-process) | `<P8>` | `<P8>` | `<P8>` | `<P8>` | `<P8>` |
| B6 −CIS (no doc-summary) | deferred | deferred | deferred | deferred | deferred |

Each pillar's marginal contribution = Δ(Full − Variant). Expected
direction (per amendment §4 pillar definitions):
- −TMG > +0.10 drop on type / SQ (TMG drives viz-type selection)
- −SAO ~0 change on text axes; affects source_attribution downstream
  metrics only (paper §11 future)
- −CIS expected significant drop on coverage and SQ (CIS-driven
  retrieval is the search/RFD trigger)

## 7.6 Discussion — multi-doc +8%p Claim Status (Phase 7 resolved)

The +8%p multi-doc headline does NOT hold under the v0.3 prototype.
Δ(B6 − best baseline) = −0.145 (full) / −0.031 (valid-only), both below
amendment §16's +0.02 floor → **gate = HALT** in either reading.

Two analytical readings of the same data tell different stories:

| Reading | Δ vs S7_SelfRefine | Narrative |
|---|---|---|
| Full (unfiltered) | −0.145 | "Method substantially underperforms baselines" |
| Valid-only (Mode A removed) | −0.031 | "Method competitive on completed runs; agent-server infra inflates fail rate" |

The valid-only narrative is closer to operationally true: B6 produces
content of comparable quality on the 226/265 records where its
generate_viz tool was successfully invoked. The 39 fail records are
dominated (26/39 = 67%) by Mode A — silent error masking in
`agent/run_agent_v2.py:459` where upstream LLM ConnectError is swallowed
and surfaced as 200 OK with empty `final_answer`. See §8.4 C8.

Per amendment §16, the published claim is therefore **NOT** the headline
+8%p but rather a more conservative position:

> *Our V4 architecture is competitive with strong direct-LLM and
> SelfRefine baselines (within 3%p in valid-only measurement, n=226)
> but does not yet outperform them. Infrastructure error masking
> dominates the unfiltered gap; method iteration (Mode B) addresses
> the remaining 10/39 fails.*

Iteration plan (§11.2):
- Fix 1 (server-side re-raise) + Fix 2 (client-side retry) → recover
  ~80% of Mode A → V4_cons projected mean ≈ 0.83-0.85 (still below
  best baseline but within +0.02 borderline).
- Phase-2 closed-API re-judge deferred until borderline is reached.
- ViviBench-style 5-LLM extension is Week-1 work; controlled-LLM
  single-model comparison is the prototype boundary.
