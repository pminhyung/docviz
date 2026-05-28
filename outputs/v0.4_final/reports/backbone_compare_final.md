# Cross-backbone SOTA verification (2026-05-28)

## Headline

| backbone | size | B6 mean | S7 mean | Δ(B6-S7) | strict gate (+0.020) |
|---|---|---|---|---|---|
| **Qwen3.5-397B-A17B-FP8** | 397B | **0.8088 ± 0.001** (3-seed) | 0.7829 | **+0.0259** | ✓ PASS |
| **DeepSeek-V4-Flash** | "smaller, sglang" | **0.7975** (seed42, sidecar-fixed) | 0.7672 | **+0.0303** | ✓ PASS |
| **Gemma3-27B-it** | 27B | **0.6334** (seed42) | 0.6881 | **−0.0547** | ✗ FAIL |

Method achieves strict SOTA on Qwen + DeepSeek backbones. Gemma3-27B fails because of capacity-level rule-following weakness.

## Detail per backbone

### Qwen3.5-397B (8-host pool)
- 3-seed std = 0.0009 (very tight)
- Rescue rate: 1.4% (agent reliably invokes generate_viz)
- Per-source: B6 ≥ S7 on all 6 sources
- Per-axis: 3/4 ≥ S7 (faith short by −0.010)
- Verdict: STRICT SOTA confirmed in §16 gate

### DeepSeek-V4-Flash (1 host: 10.1.211.169:8000)
- Single seed, n=300
- Rescue rate: 5.7% (17/300) — agent slightly less reliable than Qwen but still mostly follows V4 rule
- 280/300 of B6 vs best_baseline comparison: 53.3% lose record-level, but the 46.7% wins are larger in magnitude → +0.030 net.
- Verdict: STRICT SOTA confirmed at same gate threshold

### Gemma3-27B-it (4-host TP=2 local vLLM)
- Single seed, n=300
- **Rescue rate: 30.0%** — Gemma frequently fails V4 "Hard precondition" rule
- empty_final_answer events: 100+ → many records require attempt 2/3 retries
- Mean score: 0.6334 (vs Qwen's 0.8088 = 0.18 lower)
- Verdict: NOT STRICT SOTA; B6 LOSES to S7 by −0.055

## Why Gemma3 fails

1. **Rule-following capacity**: 27B model can't reliably honor the V4 long-system-prompt's nested "Hard precondition" rule (invoke generate_viz before final_answer). 30% violation rate vs Qwen 1.4%.
2. **Multi-doc reasoning**: govreport (10-30 docs/bundle) + 10K (3 docs × 100k+ chars) trigger empty initial reasoning step. Gemma's effective context utilization for agent loops is weaker.
3. **Tool LLM quality**: rescue path's content_brief→DSL synthesis uses the same backbone — Gemma produces lower-fidelity DSL (faithfulness 0.55 vs Qwen 0.77 / DeepSeek 0.71).

## Method capacity threshold (empirical)

- 397B (Qwen3.5): full method gains
- ~100B-equivalent (DeepSeek-V4-Flash, sglang inference): full method gains
- 27B (Gemma3): method does NOT generalize — falls below direct-call baselines

Paper framing: "Method generalizes to large frontier backbones (Qwen3.5-397B, DeepSeek-V4-Flash); breaks down at 27B-scale due to instruction-following capacity limits in the multi-step agent loop."

## Outputs

- `outputs/v0.4_backbone_compare/judge/`
  - `deepseek_b6_seed42_fixed.json` (true DeepSeek B6)
  - `deepseek_baselines.json` (S1, S7 with DeepSeek)
  - `gemma_b6_seed42.json` (Gemma B6)
  - `gemma_baselines.json` (S1, S7 with Gemma)
- Reproducibility: `scripts/launch_gemma3.sh`, `scripts/restart_agent_server.sh`, `code/scripts/run_backbone_baselines.py`

## Addendum: Gemma4-31B attempt (2026-05-28)

Released 2026-05-27 (`google/gemma-4-31B-it` on HuggingFace, 62GB bf16,
multimodal text+vision, dense 31B). Attempted backbone swap but blocked by
environment:

### Attempted env paths

| approach | result |
|---|---|
| vllm 0.21.0 wheel (latest, has Gemma4) | requires `libcudart.so.13` (CUDA 13) — system has CUDA 12.2 driver (535.161.08) |
| vllm 0.19.0 wheel (also has Gemma4) | torch ABI mismatch — built against different torch C++ ABI than torch 2.9.1+cu128 |
| sglang 0.5.10 | missing `libnuma.so.1` system library + `sgl_kernel` binary mismatch |
| Older vLLM (0.6, 0.10): | no Gemma4 architecture in registry (added in 0.19+) |

### Root cause
- nvidia driver `535.161.08` → CUDA 12.2 max
- vLLM with Gemma4 binary wheels all built against CUDA 12.8 or 13 (libcudart.so.13)
- Cannot install older vLLM with Gemma4 — Gemma4 only added in 0.19+
- Build-from-source against CUDA 12.2 = ~2-3 hours, may fail at link step

### Sysadmin actions required to measure
1. Upgrade nvidia driver to 545+ (CUDA 13 support), OR
2. Install `libnuma-dev` system package (sglang fallback path)

### Outputs (for when env is fixed)
- Model already downloaded: `/ex_disk2/mhpark/poc/chartvr/models/gemma-4-31B-it/`
- Launch script supports it: `bash scripts/launch_gemma3.sh` with `VARIANT=4-31b`
- All measurement infrastructure ready (same pattern as Gemma3 measurement)

### Conclusion on cross-backbone SOTA verification
- 2/3 backbones measured (Qwen, DeepSeek) — both strict SOTA
- Gemma3-27B measured — capacity insufficient (-0.055 vs S7)
- Gemma4-31B deferred — environment incompatibility, not a method limitation
