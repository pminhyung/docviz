# Changelog

## v0.2 — 2026-05-08 — Q1-Q5 decisions reflected

### Resolved open questions (former §18.2)

- **Q1 Entry point + Return format**: External benchmark eval repos (vis-nlp/Text2Vis, thunlp/MatPlotAgent, TencentARC/Plot2Code) used as input/output format anchors. Internally, all baselines and DocViz-Agent emit a common `VizOutput` dataclass — see PAPER_MASTER_SPEC §3.6.
- **Q2 Web search**: Disabled in all paper experiments (`web_search=False`). Mentioned only in §8 Discussion as deployment-time future work. See PAPER_MASTER_SPEC §3.5 and §19.
- **Q3 Deterministic mode**: temperature=0, seed=42 default. Three-seed run (42, 43, 44) for all key result cells, mean ± std reported. See PAPER_MASTER_SPEC §3.5 and §19.
- **Q4 DSL-only output**: Pipeline runs in DSL-only mode (Chart.js JSON or Mermaid markdown). SVG / PNG / free-text excluded. Scope explicitly stated in PAPER_MASTER_SPEC §4.3 and §19.
- **Q5 Multi-doc bundle composition**: Source-internal only (HotpotQA / MultiNews / arXiv / 10-K each in separate bundles). No cross-source mixing. Per-source breakdown reported in §7. See PAPER_MASTER_SPEC §5.1 and §19.

### Spec sections updated

- §3.5 Implementation notes — added web search exclusion, deterministic settings, DSL-only enforcement
- §3.6 (new) Common output schema — `VizOutput` dataclass definition
- §4.3 (new) Output scope — explicit DSL-only limitation
- §5.1 — added Bundling principle, Bundle/Doc schema, per-source raw→bundle conversion logic
- §14 Week 1-2 — added external benchmark eval repo clones and source loader builds as Week 1 deliverables
- §18.1 — moved Q1-Q5 from open questions to confirmed
- §18.2 — narrowed remaining open questions to API budget, deadline, and ViviBench code release status
- §19 — added 4 new critical principles (DSL-only scope, source-internal bundles, web search disabled, three-seed reporting)

### Files

- `PAPER_MASTER_SPEC.md` — updated
- `CHANGELOG.md` — this file (new)
- Other files unchanged

## v0.1 — 2026-05-07 — Initial master spec

- 20-section paper master specification covering framing (Specialist vs Generalist), 5 contributions, 3 pipeline pillars (CIS / TMG / SAO), data setup (350 bundles, 700 queries, 150 gold), model pool (5 LLM + sanity), baseline matrix (B1-B6), evaluation framework (adapted RocketEval + 6-layer evidence chain), experiment matrix, success criteria, risk register, result scenarios, 11-12 week timeline, page allocation, reviewer attack defense
- Week 0 action guide (separate file)
- README, .gitignore, PR template, push instructions
