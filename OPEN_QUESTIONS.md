# Open Questions for Advisor

Tracked here so each PR description can link back. Items the advisor's
prior `CHANGELOG.md v0.2` already resolved are listed in the *Resolved*
section for reference.

## Open (active)

### Q-A. Mermaid CLI install permission
**Context.** PR6 needs to render Mermaid DSL to PNG to compute the M1 render-success metric.

**Plan (auto, no advisor input required unless objected).** Use `npx @mermaid-js/mermaid-cli` invoked per render — no global install, no `sudo`. Falls back to the existing sidecar at `agent/sidecars/mermaid-renderer/` (Node service) if `npx` overhead is too high.

### Q-B. Cross-judge in Week 0 prototype
**Context.** PAPER_MASTER_SPEC §6.1 mandates cross-judge (different LLMs for checklist gen vs scoring). User direction: use Qwen3.6-27B for both as a temporary measure.

**Plan (auto).** Run homo-judge in PR7. WEEK0_REPORT.md flags the self-judging caveat. If judge↔human Spearman r ≥ 0.5 still holds, accept as Week-0-acceptable. If r < 0.5, JUDGE-FIX path: launch a second open-weight model (candidates: Mistral-Small-3.1-24B, gpt-oss-20b — both available under `chartvr/models/`) on a free GPU and re-score 100 viz with the second model in the scoring slot.

### Q-C. multi-doc concat formatting variant
**Context.** User direction: follow eval-repo style. PR1 chose LongBench-flavored

```
Passage [N]
Title: <doc.title>

<doc.content>
```

**Plan (auto).** Stay on this format unless the advisor requests an alternative (HotpotQA-style "Wikipedia Title:", MultiNews-style "|||||" delimiter, or per-source customization). Bundle.metadata records the mapping so future format changes do not invalidate cached bundles.

## Resolved (from CHANGELOG v0.2)

- ~~Q1. API budget cap / weekly spend~~ — closed-API runs deferred to final validation stage; advisor will provide keys then. No budget needed in Week 0.
- ~~Q2. EMNLP cycle / deadline detail~~ — not on critical path now.
- ~~Q3. ViviBench code release status~~ — not on critical path now.
- ~~Q4. Pipeline entry point / return format~~ — `VizOutput` dataclass per §3.6, plus an agent-side adapter that goes through `/v2/run`.
- ~~Q5. Web search default~~ — disabled (`web_search=False` enforced via `custom_rules` injection in `AgentClient.run_paper_default`).
- ~~Q6. Deterministic mode~~ — temperature=0, seed=42 baked into `AgentClient` and `QwenDirectClient` defaults.
- ~~Q7. DSL-only output~~ — schema and rules enforced via `_extract_dsl_block` parser plus `custom_rules` in PR4.
- ~~Q8. Cross-source bundling~~ — source-internal only. Each loader emits a single `source` value.
