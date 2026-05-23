# Project guide — docviz

## Answer style: test/audit/eval result analysis

When reporting analysis of test, audit, or evaluation results, structure the answer as the **6-slot template**:

1. **한 줄 목적** — what this fix/observation targets, in one sentence.
2. **메커니즘 (구체 예시로)** — walk through the cause-and-effect with a concrete example, not abstract terms.
3. **원래 의도/기준** — what the system/judge/test was *supposed* to do (so the deviation is visible).
4. **Evidence sample** — 1–2 actual records from the dataset (qid + quoted fact).
5. **Leverage 분석** — why this fix helps us (B6) more than other baselines, or honestly: why it doesn't.
6. **정직한 caveat** — sample-size limits, generalization risk, known counter-cases.

Keep markdown headers light. Optimize for the reader's first-pass comprehension over completeness — long structured dumps fail when the reader can't navigate them.

If the analysis is multi-axis or multi-fix, **handle one at a time** with this template; do not interleave.
