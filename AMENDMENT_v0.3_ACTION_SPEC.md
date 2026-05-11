# Amendment v0.3 — Detailed Action Specification

> **Purpose**: Translate the v0.3 strategic decisions into concrete actions the research agent can execute. No timeline — work is prioritized by impact on the paper's contribution, with dependencies marked.
> **Predecessors**: PAPER_MASTER_SPEC.md (v0.2), QG-MDV_Week0_Action_Guide.md, CHANGELOG.md
> **Decision context**: 6 strategic decisions consolidated from this revision cycle.

---

## 0. Why v0.3 exists

The v0.2 spec had three measurable issues:
1. **Test set 700 was larger than reference precedent** for method papers (SciDoc2 1,080 / Plot2Code 132 / MatPlotBench 100 / ViviBench 101 cluster around 100-1,100). API cost ballooned to ~$2,680.
2. **Source domain diversity was below precedent**. Only 4 domains (Wikipedia / news / academic / financial). MMLongBench-Doc (NeurIPS 2024 D&B) used 7 domains, ZeroSCROLLS uses 7. Reviewer will ask why our coverage is narrower.
3. **Layer C (within-method ablation S4_ZS / S4_FS / S4_SR / S4_Full) was redundant**. SciDoc2 was the only reference using it; ChartLlama / ChartX / InstructBLIP / METAL / UnifiedVisual all skip it. Layer A (cross-method B1-B6) + Layer D (pillar ablation) already cover the same evidence.

v0.3 fixes all three plus formalizes two framing decisions (held-out paradigm, viz subtype enumeration) and clarifies one new requirement (domain diversity expansion).

---

## 1. Seven decisions — high-level summary

| # | Decision | Impact level |
|---|---|---|
| D1 | Reduce in-domain test set: 700 records → **300 records** (60 per query type) | P0 critical (anchors all Layer A experiments + budget) |
| D2 | Expand source domains: 4 → **6** by adding GovReport and Technical Documentation | P0 critical (reviewer-attack defense) |
| D3 | Adopt held-out evaluation paradigm framing (T0 / FLAN / InstructBLIP / UnifiedVisual precedent) | P1 high (paper framing, no compute cost) |
| D4 | Remove Layer C (within-method ablation) — keep only S4_SelfRefine as B7 baseline | P1 high (removes redundancy, saves ~$325 + 1 week) |
| D5 | Enumerate viz subtypes: 6 → **10** (add pie, scatter, sequenceDiagram, classDiagram) | P1 high (peer-benchmark coverage match) |
| D6 | Reorder all work by importance (no calendar timeline) | P2 medium (operational clarity) |
| **D7** | **Add image-level visual quality evaluation (A5 axis on 100-record sub-sample + M5 CLIPScore on all viz). Judge config: Claude Sonnet primary via `claude -p` CLI + time-sleep; cross-judge GPT-4V or Gemini 3.0-preview (final choice TBD)** | **P0 critical (reviewer-attack defense, image-modal coverage)** |

---

## 2. ACTION D1 — Reduce in-domain test set to 300 records

### 2.1 Why this size

| Reference | Type | Size |
|---|---|---|
| MatPlotBench | Method+Bench | 100 |
| ViviBench | Method+Bench | 101 |
| Plot2Code | Method+Bench | 132 |
| SciDoc2DiagramBench | Bench+Method | 1,080 |
| Our v0.2 | Bench+Method | 700 |
| **Our v0.3** | **Method+Bench** | **300** |

300 sits comfortably above pure-method benchmarks (100-132) and below pure-benchmark scale (1,080+). For 5 query types × 60 each, statistical breakdown trends are reliable (n=60 ≥ 30 threshold). API cost on Layer A drops from ~$1,575 → ~$675 (-57%).

### 2.2 Concrete action items

| ID | Action | Inputs | Outputs | Verification |
|---|---|---|---|---|
| D1.1 | Modify each source loader to produce a fixed quota of bundles per source (50 each across 6 sources — see D2) | 4 existing loaders + 2 new (D2.3, D2.4) | 50 bundles per source × 6 = 300 bundles | Each loader yields exactly 50 bundles; len(bundles) == 300 |
| D1.2 | Modify query generator to produce exactly 1 query per bundle (instead of 2) | 300 bundles | 300 queries (60 per query type after balanced type assignment) | Per-type count distribution: each type in [55, 65] |
| D1.3 | Type-assignment table adjusted to 6 sources (see D2.7) | New 6-source mix | Each bundle gets exactly 1 query type | All 5 query types covered ≥ 50 instances each |
| D1.4 | Gold subset rebalanced: 90 records (15 per type × 6 sources, but cap at 90 to limit Prolific cost) | 300 records | 90-record subset for human verification | 18 records per query type, balanced across sources |

### 2.3 What does NOT change

- The 5-query-type taxonomy (Quantitative / Relational / Temporal / Hierarchical / Comparative)
- The bundle structure (each bundle internally multi-doc)
- The cross-source-mixing prohibition (each bundle is source-internal)

---

## 3. ACTION D2 — Expand source domains 4 → 6 (NEW critical)

### 3.1 Why this matters (reviewer-attack defense)

| Long-doc benchmark precedent | Domain count |
|---|---|
| LongBench v2 | 6 task categories, multi-domain within |
| ZeroSCROLLS | 7 domains (gov / TV / meetings / story / academic / Wikipedia / hotel / books) |
| MMLongBench-Doc (NeurIPS 2024 D&B) | **7 domains** (academic / financial / industrial / government / brochures / books / tutorials) |
| InfiniteBench | 12 tasks across multi-domain (math / code / novels / dialogues / retrieval) |
| **Our v0.2** | **4 domains** ← below precedent |
| **Our v0.3** | **6 domains** ← matched to ZeroSCROLLS / approaching MMLongBench-Doc |

Reviewer who knows MMLongBench-Doc will immediately ask: "Why only 4 domains? The closest precedent uses 7." Without an answer, this is a reject-quality concern. v0.3 fixes by adding 2 high-value domains.

### 3.2 New 6-domain mix (50 bundles each, 300 total)

| ID | Source | Domain | Bundle composition | Why this domain | License |
|---|---|---|---|---|---|
| S1 | HotpotQA | Encyclopedic / Wikipedia general knowledge | 2-3 supporting Wikipedia paragraphs | Standard multi-hop QA reference | CC-BY-SA |
| S2 | MultiNews | News articles | 2-5 articles per cluster | Standard multi-doc summarization | usage rights |
| S3 | arXiv | Academic abstracts | 3-5 paper abstracts in same conference track | Academic research diversity | CC-BY |
| S4 | EDGAR 10-K | Financial regulatory filings | Item 7 (MD&A) + Item 7A (Risk Factors) | Financial domain, quantitative-rich | public domain |
| **S5 (NEW)** | **GovReport** | **US Congressional reports / government** | 1 report (long-form, ~10K-40K tokens) chunked into 2-3 section docs | ZeroSCROLLS / SCROLLS standard. Hierarchical, temporal, comparative — strong viz fit | usage rights, public |
| **S6 (NEW)** | **Technical Documentation** | **Software / system technical docs** | 2-4 sections from related technical documentation pages | Software docs / RFC. Strongly visualization-friendly (flowchart, sequence diagram, class diagram). MMLongBench-Doc precedent includes "tutorials" | Apache/MIT/CC for most |

**S6 sub-source options for the research agent to choose** (pick one for simplicity, time-cost tradeoff):

| Option | Source | Pros | Cons |
|---|---|---|---|
| S6-a | Wikipedia long technical articles (e.g., "Transformer (machine learning model)", "OAuth 2.0", "RAID", "TCP/IP", "Kubernetes architecture") | Clean license, high quality, easy scraping | Less varied than real docs |
| S6-b | Software project documentation (Kubernetes docs, TensorFlow docs, Linux kernel docs from GitHub) | Real-world, multi-doc natural | License audit needed per project |
| S6-c | IETF RFC documents | Well-structured, public domain | Narrow style |

**Default**: S6-a (Wikipedia long technical articles) — easiest, license-clean. Switch to S6-b if S6-a yields too narrow a style.

### 3.3 Concrete action items for S5 GovReport loader

| ID | Action | Inputs | Outputs | Verification |
|---|---|---|---|---|
| D2.1 | Download GovReport from HuggingFace `ccdv/govreport-summarization` or SCROLLS `gov_report` | HuggingFace dataset API | Raw GovReport text | Loader yields ≥ 200 candidate reports |
| D2.2 | Filter reports to length 10K-40K tokens (multi-doc challenge calibrated) | Raw reports | ~150 filtered candidates | Token-length filter pass-rate ≥ 60% |
| D2.3 | Split each report into 2-3 section docs (by section headers; if no clear headers, split evenly into 3 docs by paragraph) | 150 filtered candidates | 50 bundles (random.seed(42) sample) | Each bundle has 2-3 docs of plain text |
| D2.4 | Construct Bundle objects with `source = "govreport"`, `metadata = {report_id, original_topic}` | 50 split reports | 50 GovReport bundles | Each bundle passes Bundle schema (D1.1) |

### 3.4 Concrete action items for S6 Technical Docs loader (default S6-a Wikipedia)

| ID | Action | Inputs | Outputs | Verification |
|---|---|---|---|---|
| D2.5 | Define a list of 60-80 long technical Wikipedia articles spanning ML / networking / databases / OS / cryptography / software architecture (curated list to be authored by the research agent and reviewed) | Manual curation | Article title list (60-80 entries) | List approved by human researcher before bulk download |
| D2.6 | Use Wikipedia API to download each article's full text + section structure | Title list | Raw article text + section tree | All articles successfully downloaded (≥ 95%) |
| D2.7 | For each article, group 2-4 related sub-sections into a single bundle (e.g., "Transformer" + "Attention mechanism" + "BERT" → 1 bundle) — alternatively, just take 2-4 contiguous sections from one article | Raw articles | 50 bundles | Each bundle has 2-4 docs |
| D2.8 | Construct Bundle objects with `source = "tech_docs"`, `metadata = {article_titles, topic}` | 50 grouped | 50 Technical Docs bundles | Each bundle passes Bundle schema |

### 3.5 Updated type-assignment table (D1.3 reference)

Each source gets 2 primary query types based on natural content fit:

| Source | Query type primary | Query type secondary |
|---|---|---|
| HotpotQA | Relational | Comparative |
| MultiNews | Temporal | Comparative |
| arXiv | Hierarchical | Comparative |
| 10-K | Quantitative | Temporal |
| **GovReport** | **Temporal** | **Hierarchical** |
| **Technical Docs** | **Hierarchical** | **Relational** |

Per-source 50 bundles × 1 query each → 300 queries. Balance across 5 query types: Quantitative ~50 / Relational ~60 / Temporal ~60 / Hierarchical ~70 / Comparative ~60. Some imbalance OK; adjust by D1.3 to land at [55, 65] per type.

### 3.6 Per-source breakdown reporting (paper §7)

A new sub-table in §7 reports DocViz-Agent and all baselines per-source. This is the direct evidence of cross-domain generality.

```
Domain         | B1 MPA | B2 NVA | B3 CoDA | B4 ViDoc | B5 Direct | B7 SelfR | B6 DocViz | Δ vs best base |
HotpotQA       | X      | X      | X       | X        | X         | X        | X★        | +Y%p           |
MultiNews      | X      | X      | X       | X        | X         | X        | X★        | +Y%p           |
arXiv          | X      | X      | X       | X        | X         | X        | X★        | +Y%p           |
10-K           | X      | X      | X       | X        | X         | X        | X★        | +Y%p           |
GovReport      | X      | X      | X       | X        | X         | X        | X★        | +Y%p           |
Technical Docs | X      | X      | X       | X        | X         | X        | X★        | +Y%p           |
Cross-domain avg | X    | X      | X       | X        | X         | X        | X★        | +Y%p           |
```

Reviewer "Why only 6 domains?" defense (paper §2 or §5):
> *"We select 6 domains spanning encyclopedic / news / academic / financial / governmental / technical content, covering both general and specialized registers. This matches the domain coverage of MMLongBench-Doc (7 domains) and ZeroSCROLLS (7 domains), the closest long-context document benchmarks. Domains beyond these (legal, medical, narrative) are noted as future extensions."*

---

## 4. ACTION D3 — Adopt held-out evaluation paradigm framing

### 4.1 What changes

In paper §1 (Intro) and §5 (Evaluation Setup), explicitly frame the external benchmarks (Text2Vis / ViviBench / Plot2Code) as **held-out tasks** for zero-shot generalist evaluation, and frame QG-MDV as both a new task definition and the in-domain primary evaluation.

### 4.2 Why

- T0 / FLAN / InstructBLIP / UnifiedVisual all use the held-out paradigm to demonstrate generalist value.
- **UnifiedVisual is EMNLP 2025 Main** — direct EMNLP precedent.
- This framing answers the reviewer question "what does it mean to be a generalist here?" preemptively.

### 4.3 Concrete action item

| ID | Action | Inputs | Outputs | Verification |
|---|---|---|---|---|
| D3.1 | Add a paragraph to paper draft §1 or §5 explicitly framing held-out paradigm with T0 / FLAN / InstructBLIP / UnifiedVisual citations | Draft outline | Section paragraph | Paragraph includes 4 citations and articulates the training-free distinction |

Suggested paragraph (research agent may polish during writing):
> *"Following the held-out evaluation paradigm of unified multi-task models (T0; FLAN; InstructBLIP; UnifiedVisual, EMNLP 2025 Main), we treat Text2Vis, ViviBench, and Plot2Code as held-out tasks evaluating zero-shot generalization. QG-MDV serves as both a new task definition and our in-domain primary evaluation. Unlike instruction-tuned generalists, DocViz-Agent is a training-free generalist achieved through prompting and tool composition, removing the training-domain bias that confounds InstructBLIP-style evaluations."*

### 4.4 Impact

Cost: 0. Time: minimal (writing only).
Paper strength: +1 reviewer-attack defense + EMNLP precedent alignment.

---

## 5. ACTION D4 — Remove Layer C, add B7 SelfRefine

### 5.1 What changes

- Drop S4_ZS variant (redundant with B5 Direct-LLM)
- Drop S4_FS variant (multi-doc setting is ill-fit for naive few-shot)
- Keep S4_SelfRefine variant — but **promote to B7 baseline**, not a within-method variant
- Final baseline matrix: B1, B2, B3, B4, B5, **B7 SelfRefine**, B6 DocViz-Agent (Ours)

### 5.2 Concrete action items

| ID | Action | Inputs | Outputs | Verification |
|---|---|---|---|---|
| D4.1 | Implement B7 SelfRefine wrapper following Madaan et al. 2023 protocol: initial generation → self-critique → refine | DocViz-Agent base infrastructure | B7 SelfRefine baseline class | B7 produces VizOutput on 5 sample test |
| D4.2 | Remove S4_ZS, S4_FS scaffolding from any Layer C plan documents | v0.2 spec references | Updated spec | No mention of S4_ZS / S4_FS in v0.3 docs |
| D4.3 | Update baseline matrix in paper §5 / §7 to show B1-B5 + B7 + B6 (7 rows; +1 over v0.2's 6 baselines) | v0.2 table | Updated baseline table | 7 baselines listed |

### 5.3 Impact

Cost: ~$325 saved.
Within-method evidence retained:
- "Method beats direct prompting" → B5 Direct-LLM vs B6 DocViz-Agent (Layer A)
- "Method beats self-refine" → B7 SelfRefine vs B6 DocViz-Agent (Layer A)
- "Each pillar contributes" → Layer D pillar ablation (`-CIS / -TMG / -SAO`)

This covers all evidence that Layer C would have provided.

---

## 6. ACTION D5 — Viz subtype enumeration: 10 types

### 6.1 Final list (10 types)

| ID | DSL | Type | Used for query type |
|---|---|---|---|
| 1 | Chart.js | bar | Quantitative (categorical) |
| 2 | Chart.js | line | Quantitative (continuous) / Temporal |
| 3 | Chart.js | grouped_bar | Comparative (categorical) |
| 4 | **Chart.js** | **pie** (NEW) | Comparative (proportional) |
| 5 | **Chart.js** | **scatter** (NEW) | Quantitative (correlation) |
| 6 | Mermaid | flowchart | Relational (process) |
| 7 | Mermaid | timeline | Temporal |
| 8 | Mermaid | mindmap | Hierarchical |
| 9 | **Mermaid** | **sequenceDiagram** (NEW) | Relational (interaction) |
| 10 | **Mermaid** | **classDiagram** (NEW) | Hierarchical (structural) |

### 6.2 Why these 4 additions

- **pie**: ChartQA / Plot2Code standard, common for Comparative (proportional)
- **scatter**: ChartQA standard, essential for Quantitative correlation queries
- **sequenceDiagram**: complements flowchart, captures temporal interaction
- **classDiagram**: complements mindmap, captures structural/compositional hierarchy

10 types matches or exceeds peer benchmarks (ChartQA 4 chart, VisJudge-Bench 6, MindBench 1, current VisuBench 6 → 10) and stays manageable for one-shot pool curation.

### 6.3 Concrete action items

| ID | Action | Inputs | Outputs | Verification |
|---|---|---|---|---|
| D5.1 | Update viz_type enum in `VizOutput` dataclass and Pipeline classifier (TMG pillar) | v0.2 enum (6 types) | Enum with 10 types | Code passes mypy/linting; classifier prompt updated |
| D5.2 | Update TYPE_TO_VIZ routing table (used by TMG) to map 5 query types to 10 viz types with primary/secondary fallback | Old routing table | New routing table | Each query type has ≥ 2 viz type options |
| D5.3 | Update DSL renderer to support 4 new types (pie, scatter, sequenceDiagram, classDiagram) | Renderer code | Updated renderer | Renderer produces PNG for all 10 types on test fixtures |
| D5.4 | Update DSL parser to extract structural elements from 4 new types (for SAO + M3 metric) | Parser code | Updated parser | Parser returns element list for all 10 types |
| D5.5 | If using one-shot pool: prepare 2-3 examples per new type, total +8 to +12 new examples | One-shot pool from prior work | Updated pool | Pool covers all 10 types with ≥ 2 examples each |

### 6.4 Paper §3 / §4 wording

> *"DocViz-Agent supports 10 visualization subtypes across two DSLs: 5 Chart.js types (bar, line, grouped_bar, pie, scatter) covering quantitative and comparative information; 5 Mermaid types (flowchart, timeline, mindmap, sequenceDiagram, classDiagram) covering relational, temporal, hierarchical, and structural information. This coverage is comparable to or exceeds peer benchmarks (ChartQA 4 types, VisJudge-Bench 6, MindBench 1, current visualization-generation benchmarks 4-8). Extension beyond 10 (e.g., heatmap, gantt, ER) is straightforward via renderer plugin and viz-type addition; we cap at 10 for one-shot pool curation tractability."*

---

## 7. ACTION D7 — Image-level Visual Quality Evaluation

### 7.0 Why this matters (reviewer-attack defense)

Text/DSL-only evaluation is below precedent. 10 surveyed peer papers — 9 of them perform image-level evaluation:

| Paper | Venue | Image-level eval used |
|---|---|---|
| SciDoc2-MAF | EMNLP Findings 2024 | GPT-4V Layout/Faithfulness Likert + CLIPScore |
| MatPlotAgent | ACL Findings 2024 | GPT-4V automatic evaluation |
| Plot2Code | 2024 | GPT-4V overall rating |
| ChartLlama | CVPR 2024 Highlight | GPT-4V quality assessment |
| ChartMimic | NeurIPS 2024 | image fidelity / visual similarity |
| METAL | ACL 2025 | visual critique agent |
| Text2Vis | EMNLP 2025 Main | visual accuracy + readability |
| ViviBench (ViviDoc) | 2026 | LLM-as-judge: content richness + interaction quality (image) |
| VisJudge-Bench | ICLR 2026 | 6-dimensional visual quality |
| DiagramEval | EMNLP Main 2025 | partial (text-graph oriented) |

Without image-level evaluation, the first reviewer question is: *"How do you know rendered visualizations are actually readable / well-laid-out / aesthetically usable?"* — and our text-axis metrics cannot answer it.

### 7.1 Decision (Option 1 chosen)

**A5-Sample + M5 CLIPScore (cost-balanced)**:
- A5 Visual Rendering Quality axis on a **100-record sub-sample** balanced across query types × sources
- M5 CLIPScore deterministic metric on **all viz** (every cell)
- Additional cost ~$300; v0.3 total budget rises to ~$1,800-2,100

### 7.2 A5 axis definition

Three sub-dimensions, each 0 / 0.5 / 1 (axis score = average):

| Sub-dim | What is judged | Anchor signal |
|---|---|---|
| Readability | Labels visible, no truncation, no overlap | A label that overlaps or is clipped scores 0 |
| Layout | Alignment, balance, spacing | Elements crowded into one corner score 0 |
| Overall visual quality | End-user usability for the query | Rated holistically given the query intent |

This is intentionally close to SciDoc2's 3-axis (Completeness / Faithfulness / Layout, with Layout being the closest analog) and Plot2Code's GPT-4V overall rating. The protocol is reviewer-precedented.

### 7.3 Judge configuration

**Primary judge (default for A5 image scoring)**: **Claude Sonnet** (vision-capable, latest version — verify at runtime via web search; expected Claude Sonnet 4.6 or newer).

- Invocation method: **`claude -p` CLI** (Claude Code's print/headless mode) with explicit time-sleep between requests to (a) respect rate limits, (b) reuse Claude Code subscription session credits rather than per-call API billing, (c) avoid session-cap throttling.
- Rationale: significant API cost reduction vs. pay-per-call OpenAI/Anthropic API for high-volume image judging while preserving Anthropic-grade quality.

**Cross-judge (for image-axis validity)**: **GPT-4V** or **Gemini 3.0-preview** — **final choice TBD by human researcher**. Run on 20-30 sample subset for cross-judge agreement check (Cohen κ target ≥ 0.6).

**Text-axis judge config (A1-A4) remains unchanged from v0.2**: GPT-5 generator + Claude Opus 4.6 scorer. D7 only affects A5 (image-axis).

### 7.4 M5 CLIPScore (deterministic, all viz)

CLIPScore (Hessel et al., EMNLP 2021) measures text-image semantic alignment. Applied to every viz:

- **Input**: rendered PNG + a textual summary of the visual claims (auto-generated from the DSL element list)
- **Output**: cosine similarity in CLIP embedding space, range typically [0, 1]
- **Cost**: $0 (open-source CLIP model, GPU optional)
- **Precedent**: SciDoc2-MAF uses CLIPScore as one of 4 automatic metrics

### 7.5 Concrete action items

| ID | Action | Inputs | Outputs | Verification |
|---|---|---|---|---|
| D7.1 | Add `visual_quality_score: Optional[Dict]` field to VizOutput dataclass with sub-keys {readability, layout, overall, clipscore} | `VizOutput` v0.2 schema | Updated schema | Existing baselines' VizOutput passes schema (Optional) |
| D7.2 | Implement Claude Sonnet judge wrapper using `claude -p` CLI with: (a) image input via base64 or file path, (b) sleep delay configurable (default 3-5s), (c) retry on rate-limit, (d) explicit session credit tracking | rendered PNG + query + sources | A5 score JSON {readability, layout, overall, raw_response} | 5 sample test passes; rate-limit handled gracefully |
| D7.3 | Implement cross-judge wrapper for GPT-4V and Gemini 3.0-preview (pluggable via config flag) | rendered PNG + query | A5 score JSON | Both wrappers tested on 5 samples |
| D7.4 | Implement CLIPScore (M5) pipeline using `clip-by-openai` or `open_clip` Python package | rendered PNG + DSL-derived text summary | float ∈ [0, 1] | 10 sample test produces reasonable values (≥ 0.5 for well-aligned, ≤ 0.3 for mismatched control) |
| D7.5 | Define 100-record A5 sub-sample selection: stratified by query type (20 per type) and source (~17 per source) | 300 in-domain records | sub-sample index list (deterministic seed=42) | Sub-sample respects both stratifications within ±2 |
| D7.6 | Run A5 evaluation: 7 baselines × 5 LLMs × 100 sub-sample = 3,500 image judge calls (primary) | rendered PNGs + judge wrapper | A5 scores per cell | All 3,500 calls complete or logged as failed with reason |
| D7.7 | Run M5 CLIPScore on all viz across all settings: ~26,580 viz total | all rendered PNGs | M5 score per viz | All viz have CLIPScore field populated |
| D7.8 | Cross-judge agreement check: 20-30 viz judged by both Claude Sonnet primary and selected secondary (GPT-4V or Gemini 3.0-preview), report Cohen κ | sub-sample of 20-30 | Cohen κ ≥ 0.6 | If κ < 0.6, escalate before reporting A5 in paper |
| D7.9 | Add §7 result reporting: A5 sub-sample heatmap (LLM × baseline × A5 score) + M5 CLIPScore distribution per baseline | All A5/M5 outputs | Paper §7 sub-section | A5 sub-table is present; CLIPScore plot is present |

### 7.6 Updated experiment cost (v0.3 + D7)

| Item | v0.3 cost | + D7 incremental | v0.3 + D7 |
|---|---|---|---|
| Layer A 10,500 gen | ~$525 | — | ~$525 |
| Layer B 10,000 gen | ~$520 | — | ~$520 |
| Layer D pillar ablation | ~$300 | — | ~$300 |
| Judge scoring (text-axis A1-A4) | ~$300 | — | ~$300 |
| **A5 image judge (sub-sample 3,500 calls via `claude -p` CLI)** | — | **~$150-250** (Sonnet rates via CLI subscription, far lower than pay-per-call API) | **~$200** |
| **A5 cross-judge spot 20-30 samples** | — | **~$10-30** | **~$20** |
| **M5 CLIPScore (deterministic, no API)** | — | **$0** | **$0** |
| Human Prolific (90 record naturalness) | ~$300 | — | ~$300 |
| **Total** | **~$1,500-1,800** | **~$220** | **~$1,720-2,020** |

D7 adds ~$220 (well below the earlier ~$300 estimate thanks to Claude Sonnet via `claude -p` CLI subscription path vs pay-per-call API).

### 7.7 Open decision for human researcher

**Cross-judge final selection**: GPT-4V vs Gemini 3.0-preview. Decide before D7.8 runs.

| Option | Pros | Cons | Notes |
|---|---|---|---|
| GPT-4V | Established, widely cited in vision eval | Older generation by 2026 standards | OpenAI API direct |
| Gemini 3.0-preview | Latest, multi-modal native | Preview status, possible behavior changes | Google AI Studio |

If both are available, prefer the one whose preview/stable status is most stable at experiment runtime. Verify availability via web search before D7.3 implementation.

### 7.8 Verification gate (added)

See §11 G9 — A5 judge validity + M5 CLIPScore range sanity.

---

## 8. ACTION D6 — Work prioritization (no timeline)

### 8.1 Priority tiers and dependencies

```
P0 (anchor) — required for any meaningful paper claim
   A1 │ 4 existing source loaders (S1 HotpotQA, S2 MultiNews, S3 arXiv, S4 10-K) — 50 bundles each
   A2 │ 2 NEW source loaders (S5 GovReport, S6 Tech Docs) — 50 bundles each [depends on D2.1-D2.8]
   A3 │ Query generator producing 1 query per bundle = 300 queries [depends on A1+A2, type table D3.5]
   A4 │ VizOutput dataclass with 10-type enum + visual_quality_score field [depends on D5.1, D7.1]
   A5 │ DSL renderer + parser supporting all 10 types [depends on D5.3, D5.4]
   A6 │ Existing user pipeline wired as B6 DocViz-Agent producing VizOutput on 5 sample
   A7 │ M1 render-success metric (deterministic) [depends on A5]
   A8 │ Adapted RocketEval 4-axis text-judge with cross-judge config (GPT-5 gen + Claude Opus 4.6 score)
   A9 │ A5 image-judge wrapper: Claude Sonnet via `claude -p` CLI with time-sleep + retry (D7.2)
   A10 │ M5 CLIPScore pipeline (deterministic, no API) (D7.4)

P1 (core experiments) — Layer A + Layer B + Layer D
   B1 │ Layer A: 5 LLM × 7 baseline (B1-B5, B7, B6) × 300 records — main result table [depends on all P0 + D4.1]
   B2 │ Layer B: 3 external benchmarks via eval-repo adapters — Text2Vis 100 / ViviBench 101 / Plot2Code 50 [depends on adapters]
   B3 │ Layer D: Pillar ablation (-CIS / -TMG / -SAO) × 5 LLM × 300 records [depends on A6, A8]
   B4 │ A5 image-judge on 100-record sub-sample × 7 baselines × 5 LLMs = 3,500 calls (D7.6) [depends on A9, Layer A]
   B5 │ M5 CLIPScore on all viz across all settings (D7.7) [depends on A10, Layer A+B+D]

P2 (validation anchors) — Layer E + Layer F
   C1 │ Layer E human eval: Prolific 50 records × 3 raters × 3 axis Likert; cross-judge spot 10-20 records
   C2 │ Layer F failure mode taxonomy: 30 sample manual analysis, 5-category labeling
   C3 │ Naturalness Prolific: 90-record gold subset × 3 raters [depends on A3]
   C4 │ A5 cross-judge agreement: 20-30 viz judged by both Claude Sonnet and GPT-4V/Gemini 3.0-preview, Cohen κ (D7.8) [depends on B4]

P3 (writing + reviewer simulation)
   D1 │ Draft paper §1-§8 covering 5 contributions + reviewer-attack defenses (incl. image-modal coverage answer)
   D2 │ Reviewer simulation pass + revision
   D3 │ Submission ready
```

### 8.2 Dependency graph (linear-ish)

```
A1, A2 → A3
A4 → A5 → A7
A5 → A10 (M5 CLIPScore needs rendered images)
A4 → A9 (A5 judge wrapper independent of renderer except for image input)
A6 (parallel to A1-A5)
A1-A10 all complete → P1 can start
B1 (Layer A) → B4 (A5 image judge runs on rendered viz from Layer A)
B1 + B2 + B3 → B5 (M5 CLIPScore runs on all rendered viz)
P1 complete → P2 can start (P2 partly parallel)
P1 + P2 complete → P3 starts
```

### 8.3 What can be parallelized

- A1, A2, A4 are independent loaders / data definitions — research agent can parallel-build
- A6 (user pipeline wiring) is independent of data work — can start in parallel with A1-A5
- A9 (image judge wrapper) is independent of all data work — can start anytime
- A10 (CLIPScore pipeline) needs only an example PNG to test — can start anytime
- C3 (naturalness Prolific) can start as soon as A3 completes, before P1
- Layer B external benchmark adapters can be built in parallel with Layer A execution
- B4 A5 image judge can run incrementally as Layer A batches complete (no need to wait for full Layer A)
- B5 M5 CLIPScore is offline batch processing once images are written to disk

---

## 9. New baseline matrix (7 baselines)

| ID | Name | Description | Adaptation needed | Reference |
|---|---|---|---|---|
| B1 | MatPlotAgent-adapted | Concat all docs into context, pass with query to MatPlotAgent agentic pipeline | Wrap input format only | thunlp/MatPlotAgent |
| B2 | NVAGENT-adapted | Concat docs → extract pseudo-table → pass to NVAGENT VQL pipeline | Pseudo-table extraction | ACL 2025 |
| B3 | CoDA-adapted | Treat docs as text dataset → run CoDA's analyzer agent | Treat docs as CSV-like | 2025 |
| B4 | ViviDoc-style | Use query as topic → run ViviDoc planner-executor | Topic = query reframing | 2026 |
| B5 | Direct-LLM | Concat docs + query → single LLM call → DSL output | None | Standard |
| **B7** | **SelfRefine** (NEW) | Direct-LLM initial → self-critique → refine to DSL output | Madaan 2023 protocol | NeurIPS 2023 |
| B6 | DocViz-Agent (Ours) | Full pipeline with CIS + TMG + SAO three pillars | None (our method) | Ours |

Specialist references on home turfs (Tier 1 only):
- B8_TextVis = Text2Vis-original on Text2Vis benchmark
- B9_ViviDoc = ViviDoc-original on ViviBench
- B10_MPA = MatPlotAgent on Plot2Code

These specialists run only on their home turfs to provide the reference "competitive within 5-7%p" benchmark.

---

## 10. New experiment matrix

| Layer | Setting | # baselines | # LLMs | # records | Total generations | Notes |
|---|---|---|---|---|---|---|
| A | QG-MDV (in-domain) | 7 (B1-B5, B7, B6) | 5 | 300 | 10,500 | Primary main result |
| B-1 | Text2Vis (held-out) | 7 + B8 specialist | 5 | 100 | 4,000 | Tier 1 home-turf |
| B-2 | ViviBench (held-out) | 7 + B9 specialist | 5 | 101 | 4,040 | Tier 1 home-turf |
| B-3 | Plot2Code (held-out, optional) | 7 + B10 specialist | 5 | 50 | 2,000 | Tier 1 home-turf |
| D | Pillar ablation on QG-MDV | 4 variants (Full / -CIS / -TMG / -SAO) | 5 | 300 | 6,000 | Pillar evidence |
| **D7-A5** | **A5 image judge sub-sample (QG-MDV)** | 7 | 5 | 100 sub-sample | **3,500 image judge calls** | Image-modal coverage (Sonnet via `claude -p` CLI) |
| **D7-M5** | **M5 CLIPScore (all viz)** | all | all | all rendered viz | **~26,580 CLIPScore evals (deterministic)** | Text-image alignment (free) |
| E | Human eval | — | — | 50 viz × 3 raters | 150 ratings | Judge validity |
| E2 | Cross-judge spot (text axes) | — | — | 20 viz × 2 judges | 40 cross-ratings | Text judge validity |
| **E3** | **A5 cross-judge spot (image axis)** | — | — | **20-30 viz × Sonnet + (GPT-4V or Gemini 3.0-preview)** | **40-60 cross-ratings** | Image judge validity (D7.8) |
| F | Failure mode | — | — | 30 manual | 0 (analysis only) | Mechanism |
| **Total** | | | | | **~26,580 generations + 3,540 A5 image judge + CLIPScore + 250 human** | |

Approx API budget:
- Layer A: ~$525
- Layer B (all 3): ~$520
- Layer D: ~$300
- Text-axis judge scoring across all: ~$300
- **A5 image judge (Claude Sonnet via `claude -p` CLI): ~$200** ← far below pay-per-call API thanks to CLI subscription path
- **A5 cross-judge spot (GPT-4V or Gemini 3.0-preview): ~$20**
- **M5 CLIPScore: $0 (deterministic)**
- Human Prolific: ~$300
- **Total ~$1,720-2,020** (still well under v0.2's ~$2,680, with image-modal coverage now included)

---

## 11. Master spec sections to update (v0.3 amendment)

| Section | Change |
|---|---|
| §1 Intro | Add held-out paradigm framing paragraph (D3) |
| §2 Related Work | Add 5-paradigm reference table (ChartLlama / ChartX / InstructBLIP / METAL / UnifiedVisual) + clarify why MMLongBench-Doc precedent matters; add SciDoc2 / MatPlotAgent / Plot2Code precedent for image-level eval (D7) |
| §3.6 VizOutput | Update enum to 10 types (D5); add `visual_quality_score: Optional[Dict]` field (D7.1) |
| §4 Task formalization | Mention 10 viz types and 5 query types explicitly |
| §5.1 Document corpus | Replace 4-source table with **6-source table** (50 each, total 300) including S5 GovReport and S6 Technical Docs |
| §5.2 Query generation | Update from 700 to 300 queries; updated type-assignment table (D3.5) |
| §5.3 Gold subset | Update from 150 to 90 records |
| §6 Evaluation framework | Add **A5 axis (image-level Visual Rendering Quality)** with Claude Sonnet primary judge via `claude -p` CLI + GPT-4V/Gemini 3.0-preview cross-judge; add **M5 CLIPScore** deterministic metric (D7) |
| §7 Baseline matrix | Add **B7 SelfRefine**; remove S4_ZS / S4_FS variants from any plan |
| §9 Experiment matrix | Update generation counts; remove Layer C; keep Layer A/B/D/E/F; add D7-A5 (image sub-sample) and D7-M5 (CLIPScore all) rows |
| §10 Success criteria | Re-state Tier 1/2/3 thresholds against new baseline matrix; add A5/M5 thresholds |
| §14 Timeline | **DELETE** — replace with P0/P1/P2/P3 priority structure from §8 of this amendment |
| §16 Reviewer attack defense | Add 3 new defenses: "Why 6 domains?" (MMLongBench-Doc precedent), "Held-out generalist framing" (T0/FLAN/InstructBLIP precedent), and **"How is image quality evaluated?"** (A5 axis + M5 CLIPScore, SciDoc2/Plot2Code precedent) |
| §18.1 Confirmed by user | Add: 6 sources / 300 records / 10 viz types / held-out paradigm / B7 SelfRefine / A5 image judge config (Sonnet primary via `claude -p`) / M5 CLIPScore |
| §18.2 Open questions | Add cross-judge selection (GPT-4V vs Gemini 3.0-preview) before D7.8 |
| §19 Critical principles | Add: "6-domain coverage match MMLongBench-Doc precedent"; add: "Image-level evaluation included (A5 + M5) — no text-only evaluation" |

---

## 12. Verification gates (per action)

Before any P1 experiment runs, verify:

| Gate | Check | Pass criterion |
|---|---|---|
| G1 | 6 source loaders produce exactly 50 bundles each | `sum(len(loader.bundles)) == 300` |
| G2 | 300 queries balanced across 5 types | each type count in [55, 65] |
| G3 | All 10 viz types render successfully on test fixtures | render-success rate ≥ 95% on synthetic test set per type |
| G4 | DSL parser extracts element list for all 10 types | parser returns non-empty for ≥ 95% of valid DSL |
| G5 | B6 DocViz-Agent produces valid VizOutput on 5-sample test | 5/5 pass schema validation |
| G6 | B7 SelfRefine produces valid VizOutput on 5-sample test | 5/5 pass schema validation |
| G7 | Cross-judge text-axis agreement (GPT-5 vs Claude Opus 4.6) on 20 sample | Cohen κ ≥ 0.6 |
| G8 | Naturalness Prolific 90-record gold subset | Mean ≥ 4.0, inter-rater κ ≥ 0.6 |
| **G9** | **A5 image judge (Claude Sonnet via `claude -p`) on 5 sample test**: outputs valid {readability, layout, overall} scores in [0, 1] each | **5/5 sample pass schema; rate-limit + retry path verified** |
| **G10** | **M5 CLIPScore on 10 sample**: sanity values (well-aligned viz ≥ 0.5; deliberately mismatched control ≤ 0.3) | **Sanity range met on 8/10+ samples** |
| **G11** | **A5 cross-judge agreement (Claude Sonnet vs GPT-4V or Gemini 3.0-preview) on 20-30 sample** | **Cohen κ ≥ 0.6 (or escalate if < 0.6)** |

If any gate fails, halt and escalate to human researcher before proceeding to next layer.

---

## 13. Critical non-negotiables (do not deviate without explicit approval)

These principles, if violated, collapse the paper's contribution:

- **Specialist vs Generalist framing**: never claim SOTA on external benchmarks; always frame as Tier 1/2/3
- **3 Pillars coexist**: CIS, TMG, SAO must all be in B6 implementation; ablation removes one at a time
- **No circular evaluation**: checklist generator ≠ scorer model; A5 primary judge ≠ A5 cross-judge
- **Web search disabled**: all experiments run with `web_search=False`
- **DSL-only output**: no SVG / PNG / free text in experiments (Note: PNG rendering for A5/M5 evaluation only — model output is still DSL)
- **Source-internal bundle composition**: no cross-source bundle mixing
- **Three-seed reporting for key cells**: Main Result Table cells reported as mean ± std over seeds 42, 43, 44
- **6-domain coverage**: never drop below 6 source domains without compensating evidence
- **Honest reporting**: if Tier 1 fails, reframe as "specialist retains advantage in home setting" trade-off, don't hide
- **Latest model versions**: verify model versions via web search at experiment runtime
- **Image-level evaluation included**: A5 axis (Claude Sonnet primary + GPT-4V/Gemini 3.0-preview cross-judge) on 100-record sub-sample AND M5 CLIPScore on all viz are both required — text-only evaluation is below precedent (SciDoc2 / Plot2Code / MatPlotAgent all do image-level)
- **Claude Sonnet primary via `claude -p` CLI**: A5 image judge uses Claude Sonnet (latest vision-capable version verified at runtime) through Claude Code CLI with explicit time-sleep between calls. Pay-per-call API for image judging is forbidden unless `claude -p` is unavailable, in order to keep budget within v0.3 envelope

---

## 14. Open issues left for human researcher (post-v0.3)

These items still need explicit human decision before final paper draft:

| Issue | Default if no answer | Final decision needed by |
|---|---|---|
| API budget hard cap per week | $400/week | Before P1 starts |
| EMNLP 2026 main submission cycle (direct vs ARR) | Direct submission | Before P3 starts |
| ViviBench eval code release status: if not released, reimplement 4-dim eval from paper §4 | Reimplement (estimated 1-2 days) | Before B-2 starts |
| S6 sub-source choice (Wikipedia tech articles vs Software docs vs RFC) | S6-a Wikipedia | Before D2.5 starts |
| Plot2Code inclusion (optional Tier 1) | Include if S5+S6 loaders + P1 finish ahead of schedule | Before B-3 starts |
| Industry track dual submission | Skip unless production deployment evidence emerges | Before P3 starts |
| **A5 cross-judge selection: GPT-4V vs Gemini 3.0-preview** | Verify availability via web search at runtime; if both available, choose by stability of preview/stable status at experiment time | Before D7.3 implementation completes |
| **Claude Sonnet exact version for `claude -p` CLI** | Latest vision-capable Sonnet at experiment runtime (expected Sonnet 4.6 or newer); verify via web search | Before A9 / D7.2 implementation completes |

---

## 15. Quick-start for the research agent

Day 1 actions (no order assumed; parallelize where possible):
1. Read this document end to end.
2. Read PAPER_MASTER_SPEC.md v0.2.
3. Verify access to all 5 LLM APIs and Mermaid CLI / Chart.js renderer.
4. Confirm Claude Sonnet vision availability via `claude -p` CLI; test on 1 sample image input.
5. Verify GPT-4V availability and Gemini 3.0-preview availability via web search; report which is more stable at runtime for A5 cross-judge.
6. Confirm user pipeline entry point and adapt to VizOutput schema (D5.1, D7.1).
7. Begin A1 (existing 4 source loaders) and A2 (2 new source loaders) in parallel.
8. Begin A4 (10-type enum + classifier prompt + visual_quality_score field) in parallel.
9. Begin A6 (user pipeline wiring as B6) in parallel.
10. Begin A9 (Claude Sonnet `claude -p` image judge wrapper) and A10 (CLIPScore pipeline) in parallel — both independent of data work.

When all P0 anchors (A1-A10) complete and G1-G6, G9, G10 pass, proceed to P1 in order: Layer A → Layer B → Layer D. B4 (A5 image judge) and B5 (CLIPScore) can run incrementally as Layer A batches complete.

Report progress at the end of each layer via `docs/weekly_reports/PROGRESS_<LAYER>.md` containing all gate verifications + raw numbers.

---

## END OF AMENDMENT v0.3

This amendment supersedes any conflicting guidance in v0.2 spec. CHANGELOG.md entry v0.3 will be added once this amendment is merged.

Headline of the paper, restated under v0.3:

> **First training-free generalist pipeline for query-grounded multi-document visualization across 6 content domains and 10 visualization subtypes. Competitive with specialist methods on their home turfs (within 5-7%p) and substantially superior in the previously-uncovered multi-document setting (+8%p), with the best cross-task average across 4 evaluation settings, evaluated via both text-axis checklist judging (4 axes) and image-axis quality assessment (A5 vision judge + M5 CLIPScore).**
