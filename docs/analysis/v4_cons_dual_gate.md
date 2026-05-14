# V4_cons Dual-Cell Gate Analysis (full vs valid-only)

Per `docs/analysis/v4_cons_fail_root_cause.md` Mode A (26 records of
agent-server silent error masking) inflates V4_cons fail rate to 15.1%.
This report computes both the unfiltered headline (full) and the
infrastructure-corrected reference (valid-only).

## Per-strategy mean overall

| Strategy | Full mean (n) | Valid-only mean (n) | Drag from fails |
|---|---|---|---|
| B1_MatPlotAgent | 0.7894 (265) | 0.7894 (265) | +0.0000 |
| B2_NVAGENT | 0.7859 (265) | 0.7859 (265) | +0.0000 |
| B3_CoDA | 0.8253 (265) | 0.8253 (265) | +0.0000 |
| B4_ViviDoc | 0.8555 (265) | 0.8555 (265) | +0.0000 |
| B6_NoTMG | 0.6328 (265) | 0.8465 (195) | +0.2137 |
| S1_Direct | 0.8803 (265) | 0.8803 (265) | +0.0000 |
| S4_AgenticTMGv4_consolidated | 0.8243 (265) | 0.8432 (258) | +0.0189 |
| S7_SelfRefine | 0.8804 (265) | 0.8804 (265) | +0.0000 |

## Gate decisions per amendment §16

| View | Best baseline | B6 mean | Δ(B6 − best) | Decision |
|---|---|---|---|---|
| Full (unfiltered) | S7_SelfRefine = 0.8804 | 0.8243 | -0.0561 | HALT — method iteration needed |
| Valid-only (Mode A corrected) | S7_SelfRefine = 0.8804 | 0.8432 | -0.0372 | HALT — method iteration needed |

## Mode A breakdown for B6

- B6 fail records (empty `viz_dsl`): **7** of 265
- Fail rate: **2.6%**
- Mean judge score on fail records: 0.1280
  (judge scored them low but non-zero → drag effect on full mean)
