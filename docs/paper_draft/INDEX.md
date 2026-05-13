# Paper Draft Index (v0.3, this session)

| Section | File | Status |
|---|---|---|
| §1 Intro | section_1_intro.md | ✓ draft |
| §2 Related Work | section_2_related_work.md | ✓ draft |
| §3 Task formalization | section_3_task.md | ✓ draft |
| §5.1 Corpus 6-source | section_5_1_corpus.md | ✓ draft |
| §5.2 Query generation | section_5_2_query_gen.md | ✓ draft |
| §6 Evaluation framework | section_6_eval_framework.md | ✓ draft |
| §7 Main result | section_7_main_result.md | 🟡 skeleton (Layer A pending) |
| §8 Failure modes | section_8_failure_modes.md | ✓ draft |
| §9 Baseline matrix | section_9_baselines.md | ✓ draft |
| §10 Cross-task summary | section_10_cross_task.md | 🟡 skeleton (P5/7/8/9 pending) |
| §11 Future work | section_11_future_work.md | ✓ draft |
| §13 Conclusion | section_13_conclusion.md | 🟡 skeleton (numbers pending) |
| §15 Experiment matrix | section_15_experiment_matrix.md | ✓ draft |
| §16 Reviewer defense | section_16_reviewer_defense.md | ✓ draft |

## Status legend

- ✓ draft: text complete, may need final polish
- 🟡 skeleton: structure complete, numerical cells await Phase 7/8/9
- (missing): §4, §12, §14 not yet drafted (lower priority; §14
  amendment-supersede; §4 is task-spec mostly covered in §3)

## Empirical placeholders

`<P5>` — Phase 5 (Layer B held-out)
`<P7>` — Phase 7 (Layer A in-domain main result) — **completed 2026-05-13**
`<P8>` — Phase 8 (Layer D pillar ablation) — running
`<P9>` — Phase 9 (paired bootstrap + closed-API gate) — auto-chained

All `<PX>` resolve as Phase X completes during the autonomous chain
run.

## Cross-cutting analyses

- `docs/analysis/v4_cons_fail_root_cause.md` — Mode A/B/C/D fail
  classification + 3-fix iteration proposal (§8.4 source).
- `docs/analysis/v4_cons_dual_gate.md` — full vs valid-only gate
  decisions (§7 + §16 source).

## v0.3 amendment compliance map

| Amendment decision | Paper section addressing |
|---|---|
| D1 (300 records) | §5.1 + §5.2 (268 prototype) |
| D2 (6 domains + GovReport + Tech Docs) | §5.1 + §16 R1 |
| D3 (held-out paradigm) | §1.2 + §16 R4 |
| D4 (B7 SelfRefine) | §9.1 |
| D5 (10 viz subtypes) | §3.3 + §9.1 (paper §4 wording in §3) |
| D6 (P0/P1/P2/P3 priority) | (operational, no paper-side artifact) |
| D7 (A5 image judge + M5 CLIPScore) | §6.3 + §16 R3 |
| §16 addendum (two-phase judge) | §6.2 + §13.3 + §16 R6 |
