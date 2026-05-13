# §5.1 Document Corpus — 6 Source Domains, 268-300 Bundles (v0.3 draft)

> v0.3 amendment compliance:
>   - D1.1: scale from 30 bundles → 50 per source × 6 sources = 300
>   - D2: 4 → 6 source domains (+ GovReport, + Technical Docs)
>   - §3.6 per-source breakdown table for Tier-1 reviewer-attack defense

## 5.1.1 Source Domain Selection

We assemble 268-300 source-internal multi-doc bundles across 6 content
domains:

| Source | Domain | Bundle composition | License | n |
|---|---|---|---|---|
| HotpotQA      | Wikipedia / encyclopedic                | 2-3 supporting Wikipedia paragraphs (HF `hotpot_qa/distractor`) | CC-BY-SA | 50 |
| MultiNews     | News articles (validation clusters)     | 2-5 articles per cluster (HF `multi_news`)            | usage rights | 50 |
| arXiv         | Academic preprints                      | 3-4 sections from one long paper (visubench docai)     | CC-BY-* | 50 |
| EDGAR 10-K    | Financial regulatory filings            | Item 7 (MD&A) + Item 7A (Risk) per SP500 ticker        | public domain | 18 † |
| **GovReport** (D2) | US Congressional / regulatory reports | 2-3 sections per report (HF `ccdv/govreport-summarization`) | usage rights | 50 |
| **Tech Docs** (D2) | Software / system technical documentation | 2-4 sections from one Wikipedia long technical article | CC-BY-SA | 50 |

† 10-K covers 18 cached SP500 tickers in v0.3 prototype scale.
  EDGAR's rate-limited fetch (~20 min per uncached ticker via the
  `sec_edgar_downloader` package) makes 50 tickers a multi-hour batch.
  Week-1 will scale to 50 tickers via a parallel-fetch wrapper; the
  prototype's quantitative-axis coverage caveat is documented in §10.

**Total: 268 bundles** in v0.3 prototype (vs 300 amendment target).

## 5.1.2 6-Domain Coverage Rationale

The 6-domain mix matches the closest long-context document benchmarks:

| Long-doc benchmark precedent | Domain count |
|---|---|
| LongBench v2 | 6 task categories, multi-domain within |
| ZeroSCROLLS | 7 domains (gov / TV / meetings / story / academic / Wikipedia / hotel / books) |
| MMLongBench-Doc (NeurIPS 2024 D&B) | **7 domains** (academic / financial / industrial / government / brochures / books / tutorials) |
| InfiniteBench | 12 tasks across multi-domain |
| QG-MDV (ours, v0.3) | **6 domains** ← matched to ZeroSCROLLS / MMLongBench-Doc level |

The 6-domain set spans:

- *Encyclopedic / general knowledge* (HotpotQA)
- *News / journalism* (MultiNews)
- *Academic / scientific* (arXiv)
- *Financial regulatory* (EDGAR 10-K)
- *Governmental* (GovReport, NEW D2)
- *Technical documentation* (Wikipedia tech, NEW D2)

This covers both *general* and *specialized* registers and answers the
reviewer-attack question *"Why not only Wikipedia / only news?"* — paper
§16 expanded reviewer-attack defense.

## 5.1.3 Bundle Schema and Validation

Each bundle is a `Bundle(bundle_id, source, docs, metadata)` per `code/
pipelines/base.py`:

- `bundle_id`: source-prefixed unique identifier (e.g., `arxiv_03`)
- `source`: one of the 6 domain tags
- `docs`: list of `Doc(doc_id, title, content, page_id)` with ≥2 entries
- `metadata`: per-source extras (article_title, ticker, report_id, etc.)

Validation gates (G1):
- 6 loaders each produce ≥18 bundles (10-K) or 50 bundles (others)
- Each bundle has 2-4 docs
- Total bundle char count ∈ [3K, 100K] (per-source min; max relaxed for
  GovReport which can be 90K+ when 3 docs are concatenated)

Validation gate G1 passes at total ≥ 268.

## 5.1.4 Bundle Construction Pattern

For each source loader the construction is:

1. **HF dataset / external corpus / EDGAR fetch** → raw records
2. **Per-source filter** (length range, language, license check)
3. **Doc partition** (split long content into 2-4 sub-document chunks
   at natural section boundaries; falls back to char-equal split for
   sources without explicit structure)
4. **`random.seed(42)`-shuffled sample** of 50 (or 18 for 10-K)
5. **Schema validation** then write to `data/prototype/bundles/<src>.json`
6. **Merge** via `code/utils/merge_bundles.py` → `all.json` (268 records
   in v0.3 prototype)

Validation gate G1 wraps step 5; merge step is gate G1's aggregate
check.
