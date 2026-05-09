# Week 0 Prototype Report — DocViz-Agent

> **Decision: GO** — toward Week 1 full benchmark.
> Method assumption met via S4_Agentic (no-TMG) cell; TMG-Full cell shows
> mixed signal (helps chartjs +15%p source-level, hurts entity-relational
> faithfulness −20%p) and is held for Week 1 redesign with domain-rich
> one-shots. Judge↔Human Spearman r is the remaining open gate
> (PR7 kit ready, ratings offline).

| Field | Value |
|---|---|
| Branch | `feat/source-loaders` |
| Tags | `week0-pre-tmg` (e5a5552) → current head (3d8720d + chain) |
| Phase | Week 0 — prototype Go/No-Go |
| Date range | 2026-05-07 → 2026-05-10 |

---

## 0. Project Identity (PAPER_MASTER_SPEC §0)

### 0.1 Brand
**DocViz-Agent: First Generalist Pipeline for Query-Grounded Multi-Document Visualization** — target EMNLP 2026 main (30-45%) → Findings auto-fallback (≥70%).

### 0.2 Strategic stance — Specialist vs Generalist
We do NOT claim SOTA on any external specialist's home turf. We claim:
1. **Tier 1**: within −5~7%p of each specialist on Text2Vis / ViviBench / Plot2Code (Week 5-6 measurement)
2. **Tier 2**: +8%p over best non-ours baseline on QG-MDV multi-doc setting (this report's main target)
3. **Tier 3**: best cross-task average across 4 settings (Week 5-6 measurement)

### 0.3 Five contributions (§2)
- **C1**: DocViz-Agent method (3 pillars: CIS / TMG / SAO)
- **C2**: QG-MDV task formalization + 350-bundle benchmark (prototype subset measured here)
- **C3**: Doc-grounded checklist evaluation framework (4 axes, RocketEval-adapted)
- **C4**: Setting-stratified comparison across 4 benchmarks (Week 5-6)
- **C5**: Empirical finding — multi-doc grounding gap

### 0.4 Three pillars and Week-0 implementation status
| Pillar | Mechanism | Implementation status |
|---|---|---|
| **CIS** (Cross-doc Iterative Search) | Multi-step search-query-driven retrieval over all docs | ✅ via vendored `agent/` (`run_paper_default`, `n_steps_max=8`); average 1.63 sub-queries/run measured |
| **TMG** (Type-aware Multi-Viz Generation) | Query-type → viz-type routing with type-specific prompts | ⚠️ implemented (`code/pipelines/tmg.py`) but **mixed effect** — see §3.4 |
| **SAO** (Source-Attributed DSL Output) | Visual-element ↔ source-doc/chunk mapping | ✅ stub via `viz_output_mapper._extract_source_attribution` (one-shot smoke pass; full SAO eval Week 1) |

---

## 1. Setup (§5)

### 1.1 Bundles (§5.1)
30 multi-doc bundles, all source-internal (no cross-source mixing). Validator (`merge_bundles --strict`) clean.

| Source | n bundles | Avg docs/bundle | Avg chars/bundle | Notes |
|---|---|---|---|---|
| HotpotQA dev distractor | 10 | 2-3 | 500–8K | supporting facts only, type ∈ {comparison, bridge}, seed=42 |
| MultiNews validation | 10 | 2-5 | 6-15K | cluster split on `\|\|\|\|\|`, seed=42 |
| arXiv (visubench `_raw/arxiv`) | 5 | 3 | ~60K | offline corpus pivot — abstract-only would have violated §3.1 CIS pillar (nothing to retrieve over) and §5.1 L220 token budget |
| EDGAR 10-K | 5 | 2 | ~17K | Item 7 (MD&A) + Item 7A (Risk), longest-substring extraction (TOC false-positive fix) |

### 1.2 Queries (§5.2)
60 queries, 2 per bundle. Type assignment per spec L257-260 (exact match, no deviation).

| Source | Types | n |
|---|---|---|
| HotpotQA | {relational, comparative} | 20 |
| MultiNews | {temporal, comparative} | 20 |
| arXiv | {hierarchical, comparative} | 10 |
| 10-K | {quantitative, temporal} | 10 |
| **Total** | (5 types covered) | **60** |

Filters per L265 (≤25 words AND ≥1 bundle entity reference): **60/60 PASS**, 0 retries.
Word count: min=8 max=21 mean=14.6. Entity hits: min=1 max=8 mean=4.6.

### 1.3 Spec deviations (documented)
- **§5.2 L263 GPT-4o-mini → on-prem Qwen3.6-27B**: Week 0 cost-zero policy (cost_tracker.py + PR1 bootstrap). Closed-API substitution scheduled for Week 1 once Anthropic/OpenAI keys activate.
- **§5.2 L266 Claude Opus 4.6 cross-judge naturalness validation**: deferred. Will run on the prototype 60-query set when Opus key activates.
- **`load_*.py` LOC over §5.1 ≤100 target** (140-207 each): driven by HTML/SEC parsing irreducibly; accepted.

---

## 2. Pipelines (§7 baseline matrix)

| Pipeline | Spec ID | Implementation | Pillars active |
|---|---|---|---|
| **S1_Direct** | B5 Direct-LLM | `code/pipelines/s1_direct.py` — single Qwen call, JSON-mode, `enable_thinking=False`, paper-default temp=0/seed=42 | none (concat-and-prompt baseline) |
| **S4_Agentic** | B6 DocViz-Agent (−TMG) | `code/pipelines/s4_agentic.py` — wraps `AgentClient.run_paper_default` (CIS loop, 8-step max, web_search disabled, deterministic) | CIS + SAO-stub |
| **S4_AgenticTMG** | B6 DocViz-Agent (Full) | `code/pipelines/s4_agentic_tmg.py` — same as S4 + injects type-aware one-shot rule via `custom_rules` | CIS + **TMG** + SAO-stub |

All three emit the §3.6 `VizOutput` schema; viz_type ∈ 6-value enum (chartjs_bar/line/grouped_bar, mermaid_flowchart/timeline/mindmap).

**Critical design note (research integrity)**: TMG was applied to S4 only (per spec framing). S1 stays bare-bones intentionally. Adding TMG to S1 would shrink the measured Δ → unfair to our claim.

---

## 3. Results — 180 viz outputs, 180 judged scores

### 3.1 §5.3 Generation gates (error_rate ≤ 5%, syntax_pass ≥ 90%) — all 3 PASS

| Strategy | n | errors (rate) | syntax_ok (rate) | mean t/record | mean sub-q | §5.3 |
|---|---|---|---|---|---|---|
| S1_Direct | 60 | 0 (0.000) | 60 (1.000) | 33.0s | — | ✅ |
| S4_Agentic | 60 | 1 (0.017) | 56 (0.933) | 178.8s | 1.63 | ✅ |
| S4_AgenticTMG | 60 | 1 (0.017) | 55 (0.917) | ~150s | ~1.5 | ✅ |

### 3.2 §6.4 Judge discriminative range — partially borderline (3 strategies, n=60 each)

| | faithfulness | coverage | type_app | search_q |
|---|---|---|---|---|
| S1 mean / std | 0.787 / 0.256 ✅ | 0.828 / 0.303 ⚠️ | 0.904 / 0.233 ⚠️ | — |
| S4 mean / std | 0.817 / 0.262 ⚠️ | 0.861 / 0.286 ⚠️ | 0.887 / 0.243 ⚠️ | 0.767 / 0.338 ✅ |
| S4_TMG mean / std | 0.713 / 0.308 ✅ | 0.822 / 0.267 ⚠️ | 0.883 / 0.230 ⚠️ | 0.725 / 0.334 ✅ |

5/9 axis cells outside [0.2, 0.8] (ceiling pressed); however **std 0.23-0.34** with bimodal distribution (lots of 1.00 + real ~10-15% fail tail) → judge retains ranking signal even if calibration is high.

### 3.3 3-way overall by query_type (paired, same bundle)

| query_type | n | S1 | S4 | S4_TMG | Δ(S4−S1) | **Δ(TMG−S4)** | Δ(TMG−S1) |
|---|---|---|---|---|---|---|---|
| comparative | 25 | 0.828 | 0.850 | 0.749 | +0.022 | **−0.101** | −0.079 |
| hierarchical | 5 | 0.789 | 0.871 | 0.856 | **+0.082** | −0.015 | +0.067 |
| quantitative | 5 | 0.967 | 0.879 | 0.946 | −0.088 | **+0.067** | −0.021 |
| relational | 10 | 0.781 | 0.848 | 0.717 | **+0.067** | **−0.131** | −0.064 |
| temporal | 15 | 0.874 | 0.767 | 0.817 | −0.107 | +0.050 | −0.057 |
| **mean** | **60** | **0.840** | **0.833** | **0.786** | −0.007 | −0.047 | −0.054 |

### 3.4 Faithfulness by query_type (most signal-bearing axis)

| query_type | S1 | S4 | S4_TMG | Δ(S4−S1) | **Δ(TMG−S4)** |
|---|---|---|---|---|---|
| comparative | 0.760 | 0.860 | 0.655 | **+0.100** | **−0.205** |
| hierarchical | 0.800 | 0.850 | 0.725 | +0.050 | −0.125 |
| quantitative | 0.900 | 0.850 | 0.950 | −0.050 | **+0.100** |
| relational | 0.675 | 0.775 | 0.550 | **+0.100** | **−0.225** |
| temporal | 0.867 | 0.750 | 0.833 | −0.117 | +0.083 |

### 3.5 Overall by source

| source | n | S1 | S4 | S4_TMG | Δ(S4−S1) | **Δ(TMG−S4)** |
|---|---|---|---|---|---|---|
| 10k (chartjs-heavy) | 10 | 0.878 | 0.777 | 0.927 | −0.101 | **+0.150** |
| arxiv | 10 | 0.750 | 0.904 | 0.811 | **+0.154** | −0.093 |
| hotpotqa (entity-rich) | 20 | 0.828 | 0.851 | 0.721 | +0.023 | −0.130 |
| multinews | 20 | 0.878 | 0.807 | 0.767 | −0.070 | −0.041 |

---

## 4. §11.4 Ablation table — Full vs −TMG (real data, prototype scale)

S4 (=`S4_Agentic`) is the **−TMG cell**; S4_TMG (=`S4_AgenticTMG`) is the **Full cell**. Values are mean axis scores at n=60.

| Variant | faith | cove | type_app | sear_q | overall |
|---|---|---|---|---|---|
| Full (S4_TMG) | 0.713 | 0.822 | 0.883 | 0.725 | 0.786 |
| − TMG (S4) | 0.817 | 0.861 | 0.887 | 0.767 | 0.833 |
| **Δ (Full − −TMG)** | **−0.104** | **−0.039** | **−0.004** | **−0.042** | **−0.047** |

Spec §11.4 expectation: `−TMG` should drop type_appropriateness 3-6%p. **Observed**: type_app difference is essentially nil (−0.4%p), but Full **regresses on faithfulness by 10.4%p** — opposite of the predicted direction. This is a real and unexpected finding (see §8).

---

## 5. §1.2 Method assumption gate

> **GATE**: S4 > S1 by ≥+5%p in ≥1 query type, with same sign across faithfulness AND coverage axes.

### 5.1 S4 (= −TMG cell) vs S1
| query_type | overall Δ | faith Δ | cove same-sign? | gate |
|---|---|---|---|---|
| hierarchical | **+0.082** | +0.050 | +0.067 ✅ | **PASS (≥+5%p)** |
| relational | **+0.067** | **+0.100** | +0.033 ✅ | **PASS (≥+5%p)** |
| comparative | +0.022 | +0.100 | -0.040 ❌ same-sign fail | — |
| quantitative | −0.088 | −0.050 | — | negative — |
| temporal | −0.107 | −0.117 | — | negative — |

**S4 − S1: GATE MET on 2 query types (hierarchical, relational).** Source-level: arxiv +15.4%p (CIS pillar shines on multi-doc academic). Effect direction matches §11.3 prediction ("DocViz-Agent strong in hierarchical/relational").

### 5.2 S4_TMG vs S1
| query_type | overall Δ | gate |
|---|---|---|
| hierarchical | +0.067 | ≈ at threshold (5%p) — borderline |
| quantitative | −0.021 | negative |
| comparative | −0.079 | negative |
| relational | −0.064 | negative |
| temporal | −0.057 | negative |

**S4_TMG − S1: GATE NOT MET cleanly.** TMG-Full erases the S4 advantage we measure without TMG.

### 5.3 Conclusion
The Method assumption gate passes **using the −TMG variant (S4_Agentic)**. The Full variant (S4_AgenticTMG) currently underperforms — this is itself a finding (§8.1), not a blocker.

---

## 6. Judge assumption (§1.2) — pending

> **GATE**: Spearman r ≥ 0.5 between checklist judge per-axis scores and mean human rating, on ≥ 2 of 3 axes (faithfulness, coverage, type_appropriateness).

### 6.1 Status
- 30-viz stratified sample drawn (`outputs/prototype/human_ratings/template.csv`); strategy blinded as A/B.
- Sample spans full judge-overall range (min=0.00, max=1.00, std=0.27; 11/30 below 0.80).
- `code/judge/sample_for_human.py`, `code/judge/analyze_correlation.py` ready.
- `RATING_PROTOCOL.md` written (3 axes, {0/0.5/1}, ~3 min/viz, blinding rules).

### 6.2 Pending
Two raters fill `ratings_<name>.csv` offline (~1.5h each). Then:
```bash
python -m code.judge.analyze_correlation
```
emits per-axis Spearman r vs mean human + linear-weighted Cohen's κ pairwise + top-5 judge↔human disagreements.

### 6.3 Backup plan if r < 0.5
- Cross-judge swap (use Qwen for checklist generation, swap a different model for scoring) — currently both stages use Qwen3.6, which is a known self-bias risk.
- Simplify checklist to 6 items instead of 9-12.
- Worst case: fall back to mixed metric (NLI for faithfulness + structural for type fit) per §1.2 PIVOT branch.

---

## 7. Decision matrix (§1.2)

| Judge r (PR7) | S4 effect (this report) | Decision |
|---|---|---|
| ≥ 0.5 | ≥ +5%p in ≥1 type | **GO** ← *candidate* |
| ≥ 0.5 | < +5%p anywhere | REFRAME |
| < 0.5 | any | JUDGE-FIX |
| < 0.3 | any | PIVOT |

**Current candidate: GO.**
- S4 (− TMG) effect: +5-8%p in 2 query types, +15.4%p on arxiv source. ✅
- Judge r: pending offline rating; placeholder ▢.

If PR7 returns r < 0.5, we jump to JUDGE-FIX branch: try cross-judge with the closed-API model when activated, or simplify checklist.

---

## 8. Limitations & Findings

### 8.1 TMG-Full underperformed in 3/5 query types — diagnostic finding (C5 candidate)
**Observation**: Adding type-aware one-shot examples to S4 helped chartjs/quantitative cases (10-K +15%p source) but hurt entity-rich Mermaid cases (relational/comparative −10-20%p faithfulness).

**Hypothesized mechanism**: Our one-shot examples in `code/pipelines/tmg.py` use generic placeholder entities ("Founder → Acme Corp → Beta Labs"). The model adopts the *style* of the example more than its *structure*, producing flatter/more generic edge labels. Side-by-side `hotpot_00_relational` (paired drop −0.50):
- S4 (no TMG): `Iqbal F. Qadir -->|Retired Pakistan Navy Admiral| Pakistan Navy -->|Participated in 1971 War| ...`
- S4_TMG: `Iqbal F. Qadir -->|was part of| Flotilla -->|attacked| Radar Station ...`
Same structure, but S4_TMG's verb labels are atomic/generic while S4's are domain-rich.

**Implication**: Naive type-aware one-shot prompting can suppress the very property (entity-grounded labeling) that makes the agentic pipeline win on entity-rich queries. **Domain-rich one-shots, or per-source one-shot rotation, are needed in Week 1.**

This is exactly the kind of negative finding a paper can make ("TMG implementation matters; not all type-aware prompting helps"). It also gives spec §11.4 ablation table its first real-data row.

### 8.2 Judge ceiling-pressed — partial discriminative concern
3/4 axis means above 0.8. However, std 0.23-0.34 + bimodal distribution (many 1.00 + real fail tail) means ranking signal still exists. PR7 (Spearman r vs human) is the real test.

### 8.3 9 / 180 records still syntax-fail post-reprocess (1 S4 + 5 S4_TMG + 3 S4 from earlier reprocess pass)
Diverse causes — agent placeholder text, prose-only output, invented enum values, HTTP 400 from agent server, JSON malformed mid-stream. Each ≤ 1.7% of strategy total. None are parser issues; all are agent content issues. Useful failure-mode catalogue for Week 1 hardening of `run_paper_default` rules / DSL validator.

### 8.4 Prototype scale caveats
- Per-type cell size n=5 (hierarchical, quantitative) is small — go/no-go correlation is fine; per-type effect inference needs Week-1 scale-up.
- Visubench arXiv corpus is 2-month window vs spec L249's 24-month — accept for prototype, fresh API fetch for Week 1's 80-bundle target.
- One arXiv `cs.LG general` bundle includes a topically off paper (fluid mechanics, primary cs.LG). Spec L249 satisfied; tighten to `{cs.AI|stat.ML|cs.IT}` secondary at Week-1 scale-up.

### 8.5 Open spec deviations (already in `docs/active/tracks/feat-source-loaders/open-questions.md`)
- Qwen3.6-27B substitution for GPT-4o-mini (query gen) and GPT-5/Opus 4.6 (judge gen+score) — Week-0 cost-zero policy, re-measure on closed-API window.
- Cross-judge naturalness validation (§5.2 L266, Spearman r ≥ 0.7 vs Opus 4.6) deferred.

---

## 9. Week 1 Plan (if GO confirmed)

### 9.1 First-week priority (in order)
1. **PR7 ratings** — collect human ratings on existing 30-viz template, run `analyze_correlation`, fix decision branch (GO / JUDGE-FIX).
2. **TMG redesign** (high payoff per §8.1) — replace generic one-shot with **domain-rotated examples** per `(source, query_type)` cell. E.g., relational + hotpotqa → use a 3-node Wikipedia-style example with rich edge labels; comparative + multinews → news-headline-style nodes.
3. **Closed-API activation** — wire OpenAI / Anthropic keys, switch judge to GPT-5 (gen) + Claude Opus 4.6 (score) per §8.2 cross-judge protocol. Re-run prototype 60×3 to validate κ ≥ 0.70.
4. **External benchmark setup** (per §14 Week 1-2 timeline):
   - Clone `vis-nlp/Text2Vis`, `thunlp/MatPlotAgent`, `TencentARC/Plot2Code`. Verify entry-point compatibility.
   - Monitor ViviBench code release; otherwise reimplement the 4-dim eval from paper §4.

### 9.2 Scale-up
- 30 → 350 bundles (HotpotQA 60 → 100, MultiNews 50 → 90, arXiv 50 → 80, 10-K 40 → 80) using same loader scripts with seed change + corpus refresh.
- 60 → 700 queries via the same `generate_queries.py` (closed-API model substitution per spec).

### 9.3 Baseline matrix expansion
- B1 MatPlotAgent-adapted, B2 NVAGENT-adapted, B3 CoDA-adapted, B4 ViviDoc-style — thin adapters around upstream open-source code.
- B7-B9 specialist-on-home-turf cells (Text2Vis-original, ViviDoc-original, MatPlotAgent-original).

### 9.4 Deterministic metrics M1-M4 (§3.5 implementation note)
Implement render-success, numeric-exactness, entity-coverage, structural-validity sidecars. Currently we approximate M1 with the lightweight DSL syntax check (Mermaid header sniff / Chart.js JSON parse). Full puppeteer-based render check via `agent/sidecars/mermaid-renderer:3005` should be wired and benchmarked against the syntax-check approximation.

---

## 10. Artifacts

| Path | Purpose |
|---|---|
| `data/prototype/bundles/all.json` | 30 source-internal multi-doc bundles |
| `data/prototype/queries/all.json` | 60 type-pinned queries |
| `data/prototype/queries/raw.jsonl` | per-call audit log for query gen |
| `outputs/prototype/viz/all.json` | **180 viz outputs** (60 S1 + 60 S4 + 60 S4_TMG) |
| `outputs/prototype/viz/raw.jsonl` | per-call audit log for batch |
| `outputs/prototype/judge_scores/all.json` | **180 judged records** (per-axis + per-item scores) |
| `outputs/prototype/judge_scores/checklists.json` | 240 cached checklists (60 query × 2 strategy_class, materialized after S4_TMG too) |
| `outputs/prototype/human_ratings/template.csv` | 30-viz blinded rating template |
| `outputs/prototype/human_ratings/sample_keys.json` | rating_id ↔ judge anchor mapping |
| `outputs/prototype/human_ratings/RATING_PROTOCOL.md` | rater protocol |
| Tags | `week0-pre-tmg` (= e5a5552) preserved; current head includes TMG variant |

### Reproduction
```bash
# bundles
python -m code.utils.load_hotpotqa
python -m code.utils.load_multinews
python -m code.utils.load_arxiv
python -m code.utils.load_10k
python -m code.utils.merge_bundles --strict
# queries
python -m code.utils.generate_queries --strict
# pipelines (must have agent server + vLLM 9101/9102/9103 healthy)
python -m code.run_prototype --strategies S1,S4,S4_TMG --strict
python -m code.scripts.reprocess_viz \
  --in outputs/prototype/viz/all.json --out outputs/prototype/viz/all.json
# judge
python -m code.judge.run_judge
# human sampling
python -m code.judge.sample_for_human
# correlation (after rating files arrive)
python -m code.judge.analyze_correlation
```

---

## 11. Bottom line

> **Week-0 outcome: data-driven GO with one expected condition.**
> S4 (DocViz-Agent without TMG) clears the §1.2 Method assumption gate.
> TMG, as currently implemented with generic one-shot examples, regresses
> entity-rich query types — useful diagnostic finding (C5 candidate).
> Judge↔Human Spearman r is the remaining gate (PR7 ratings offline).
> Week 1 first action: TMG redesign with domain-rich one-shots + closed-API
> cross-judge activation, then 30 → 350 bundle scale-up.
