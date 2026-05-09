# Human Spot Validation — Rating Protocol (Week 0 §7)

## Why this exists
We need an independent human signal to validate that our LLM-based checklist
judge tracks human perception of viz quality. The Week 0 Go/No-Go gate
requires Spearman r ≥ 0.5 between the judge's per-axis scores and the
average human rater score on at least 2 of 3 axes (faithfulness, coverage,
type appropriateness).

## What you'll do
- 30 viz instances, ~3 minutes each → ~1.5 hours total per rater.
- Two raters minimum (e.g., yourself + a colleague). Each rater works
  independently from a fresh copy of `template.csv`.

## Setup
1. Copy `template.csv` to your own file:
   ```bash
   cp outputs/prototype/human_ratings/template.csv \
      outputs/prototype/human_ratings/ratings_<your-name>.csv
   ```
2. Open it in a spreadsheet (Excel / Numbers / LibreOffice / Google Sheets).
   Lock columns A-H so you don't accidentally edit them.

## For each row
1. **Read the query.** That's the user's question.
2. **Read `source_brief`.** That's the underlying bundle (truncated for
   readability).
3. **Read `viz_dsl`.** That's the candidate visualization.
4. **Mentally render the viz** — picture the chart / diagram / mindmap it
   describes. (You don't need to actually render it; the structure is
   what matters.)
5. **Score each axis on the {0, 0.5, 1} scale:**

| Score | Meaning |
|---|---|
| **1.0** | YES — clearly, unambiguously satisfies the criterion |
| **0.5** | PARTIAL — partially satisfies, ambiguous, mixed |
| **0.0** | NO — fails to satisfy, or is contradicted by the source |

### The three axes

- **`faith_score` — Faithfulness**
  *Does the viz only contain claims supported by `source_brief`?*
  Penalise: invented numbers, dates the source doesn't mention, entities
  that don't appear in the source.
  Bonus pass: if `source_brief` is truncated and the claim is plausibly
  in the rest of the document, give 0.5 not 0.

- **`coverage_score` — Coverage**
  *Does the viz address the main aspects the query asks about?*
  Penalise: viz that ignores half the query, viz that visualizes
  unrelated content.

- **`type_score` — Type appropriateness**
  *Is the viz format (mermaid_flowchart / mermaid_timeline /
  mermaid_mindmap / chartjs_bar / chartjs_line / chartjs_grouped_bar)
  appropriate for the query type and content?*
  Examples:
    - temporal query → timeline / line chart = good; flowchart with
      time labels on edges = partial; pie chart = NO.
    - hierarchical query → mindmap / tree = good; flat bar chart = NO.
    - quantitative query → bar / line / grouped_bar = good; mindmap = NO.

### `notes`
Drop a half-sentence whenever a score is borderline or surprising
("invented Q2 figure", "right type but only 2 of 4 entities shown", etc.).
This becomes invaluable for the W0_REPORT failure-mode analysis.

## What NOT to do
- **Do not look up `query_id` in any other file** before scoring — that
  would tell you the strategy (S1 vs S4) and bias you. The
  `strategy_blind` column shows only `A` or `B`.
- **Do not score `search_query_quality`** — that's machine-only.
- **Do not skip rows.** If a viz looks broken, score 0 across the board
  and note "broken DSL" in `notes`.

## Submission
Save as `ratings_<your-name>.csv` in the same folder. When at least two
raters' files are present:

```bash
python -m code.judge.analyze_correlation
```

This computes:
- **Spearman r** between mean human rating and judge per-axis scores.
- **Cohen's κ** (linear-weighted) between any two raters per axis.
- A by-record table flagging the largest judge↔human disagreements.
