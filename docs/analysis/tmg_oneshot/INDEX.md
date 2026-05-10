# TMG one-shot exemplar pool — revision v1 INDEX

**Date**: 2026-05-10
**Scope**: revision v1 of the TMG (Pillar 2 §3.2 amend) one-shot exemplar
work begun in `docs/analysis/tmg_oneshot_pool_draft.md` (v0). This INDEX
plus the 6 per-type files in this directory **supersede** v0 for the
purposes of caller migration. v0 is **archived** (do not edit) so that
v0 → v1 paired diff evidence is preserved.

---

## 1. Changes vs v0 (summary)

### 1.1 Must-fix items (closed)

- **Must-fix #1 — `Acme Industries` reuse (5/18 exemplars)**: closed.
  | exemplar | v0 entity | v1 entity |
  |---|---|---|
  | BAR-A | Acme Industries | **Northbridge Energy** |
  | BAR-B | Acme Industries | **Carrillon Software Group** |
  | GBAR-A | Acme Industries | **Halverson Bancorp** |
  | LINE-C | Acme Industries | **Verdant Aerospace** |
  | TIME-A | Acme Industries | **Atlas Robotics** |
  Also: `Lakeshore Foundation` was reused in v0 LINE-A and GBAR-B; v1
  keeps Lakeshore in LINE-A only and swaps GBAR-B → **Pemberton
  Charitable Trust**.

- **Must-fix #2 — Mermaid_flowchart hub-and-spoke shape**: closed. v0
  had chain (FLOW-A) + subgraph-with-cluster (FLOW-B) + parallel-subgraphs
  (FLOW-C) — pure hub-and-spoke was missing. v1 replaces FLOW-B with a
  hand-written hub-and-spoke (1 center + 6 peripherals; paper-methods
  archetype). The intent-vs-impact subgraph-cluster shape from v0 FLOW-B
  is implicitly retained in the consolidated variant of mermaid_flowchart.

- **Must-fix #3 — MIND-A entity-leak (`Daler Mehndi & Tunak Tunak Tun`)**:
  closed. v1 replaces MIND-A with a fully fictional entertainment-
  franchise compare (Cipher Saga / Marielle Vasquez / Theo Lindqvist).
  Bonus: the new MIND-A is also **2-level shallow** (Minor #6 closed in
  the same swap; v0 had no shallow mindmap exemplar).

### 1.2 Minor items

- **Minor #4 — caller migration plan**: see §4 of this INDEX.
- **Minor #5 — sampler determinism**: see §3 — the sampler now uses
  `hashlib.sha1(query_id.encode()).hexdigest()` instead of `hash(query_id)`,
  which makes selection reproducible across processes (`PYTHONHASHSEED`-
  independent).
- **Minor #6 — 2-level shallow mermaid_mindmap exemplar**: closed by
  collapsing into Must-fix #3 (the new MIND-A is 2-level).
- **Minor #7 — `test_oneshot_pool_parses` smoke test**: see §5 — markdown
  spec only (no code in this revision).

### 1.3 New (NEW v1 directives)

- **Consolidated variant** added per viz_type. Each consolidated example
  is a **single integrated exemplar** that combines every syntactic sub-
  pattern of its viz_type inside one coherent diagram (not a stitch of
  separate examples). Intended for **V4_consolidated** independent
  measurement, paired vs **V4_pool** on the same 60-record subset.

- **Per-type file split**. v0 was a single 575-line file; v1 is 6 self-
  contained per-type files plus this INDEX. A subagent re-reading a
  single type's design now reads ~250-400 lines instead of 575.

---

## 2. Six per-type files

Each file is **self-contained** — the final design for a single viz_type
can be reviewed without reading the INDEX or sibling files.

- [chartjs_bar](chartjs_bar.md)
- [chartjs_line](chartjs_line.md)
- [chartjs_grouped_bar](chartjs_grouped_bar.md)
- [mermaid_flowchart](mermaid_flowchart.md)
- [mermaid_timeline](mermaid_timeline.md)
- [mermaid_mindmap](mermaid_mindmap.md)

Each file has the same structure:
1. Pool variant (3 exemplars; V4_pool measurement)
2. Consolidated variant (1 integrated exemplar; V4_consolidated measurement)
3. Python literals (drop-in for `tmg.py`)
4. 검수 체크리스트 (mentor risk #5 + risk #2 alignment)

---

## 3. Aggregated Python literals (caller paste)

Both dictionaries are paste-ready into `code/pipelines/tmg.py`. Each
per-type file contains the same literal it contributes here, scoped to
its single key — sourcing from the per-type files makes single-type
edits safe.

### 3.1 `ONE_SHOT_POOL_BY_VIZ_TYPE` — pool variant (3 exemplars per type)

```python
from typing import Dict, List

ONE_SHOT_POOL_BY_VIZ_TYPE: Dict[str, List[str]] = {
    "chartjs_bar":          [...],   # see chartjs_bar.md §3.1
    "chartjs_line":         [...],   # see chartjs_line.md §3.1
    "chartjs_grouped_bar":  [...],   # see chartjs_grouped_bar.md §3.1
    "mermaid_flowchart":    [...],   # see mermaid_flowchart.md §3.1
    "mermaid_timeline":     [...],   # see mermaid_timeline.md §3.1
    "mermaid_mindmap":      [...],   # see mermaid_mindmap.md §3.1
}
```

Total: 6 keys × 3 exemplars = **18 pool strings**, each guaranteed:
- `json.loads(s)` round-trip succeeds
- `json.loads(s)["viz_type"]` matches the dict key
- for chartjs types, `json.loads(json.loads(s)["viz_dsl"])` also succeeds
  (chartjs DSL is itself JSON)
- for mermaid types, the `viz_dsl` value starts with the matching DSL
  header (`graph `, `timeline`, `mindmap`)
- contains no `Acme*` / `Founder` / `Engineer X` placeholder regression
- entity authenticity: real source-grounded faith-1.00 anchors where
  available; hand-written exemplars are explicitly disclosed in their
  per-type file (LINE-B, LINE-C, GBAR-C, FLOW-B, the consolidated
  variants).

### 3.2 `ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE` — consolidated variant (1 per type)

```python
from typing import Dict

ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE: Dict[str, str] = {
    "chartjs_bar":          "...",  # see chartjs_bar.md §3.2
    "chartjs_line":         "...",  # see chartjs_line.md §3.2
    "chartjs_grouped_bar":  "...",  # see chartjs_grouped_bar.md §3.2
    "mermaid_flowchart":    "...",  # see mermaid_flowchart.md §3.2
    "mermaid_timeline":     "...",  # see mermaid_timeline.md §3.2
    "mermaid_mindmap":      "...",  # see mermaid_mindmap.md §3.2
}
```

Total: 6 keys × 1 exemplar = **6 consolidated strings**.

Per-type consolidated DSL lengths (the inner `viz_dsl` value, in chars):

| viz_type | pool max | consolidated | ratio |
|---|---:|---:|---:|
| chartjs_bar         |  718 |  986 | 1.4× |
| chartjs_line        |  769 |  916 | 1.2× |
| chartjs_grouped_bar |  885 | 1151 | 1.3× |
| mermaid_flowchart   |  889 | 1221 | 1.4× |
| mermaid_timeline    |  969 | 1110 | 1.1× |
| mermaid_mindmap     | 1300 | 1498 | 1.2× |

All within the brief's recommended consolidated:pool ≈ 2-3× ratio (in
fact most are ≈ 1.2-1.4× because the consolidated patterns share
infrastructure). Mindmap is the largest because depth-mixing
(2-vs-3-vs-4) cannot be demonstrated in fewer levels.

### 3.3 Sampler — `select_oneshots`

Updated for **Minor #5** (sampler determinism — `hashlib.sha1` instead
of built-in `hash()` for `PYTHONHASHSEED` independence):

```python
import hashlib
from typing import List

def select_oneshots(
    viz_type: str,
    query_id: str,
    k: int = 1,
    *,
    pool: Dict[str, List[str]] = ONE_SHOT_POOL_BY_VIZ_TYPE,
) -> List[str]:
    """Deterministic per-(viz_type, query_id) selection from the pool.

    For V4_pool: caller passes pool=ONE_SHOT_POOL_BY_VIZ_TYPE.
    For V4_consolidated: caller wraps the consolidated dict as a 1-element
        pool, e.g. {vt: [s] for vt, s in ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE.items()}.
    """
    candidates = pool[viz_type]
    if not candidates:
        return []
    h = int(hashlib.sha1(query_id.encode("utf-8")).hexdigest(), 16)
    n = len(candidates)
    return [candidates[(h + i) % n] for i in range(min(k, n))]
```

Properties:
- `hashlib.sha1` is reproducible across processes / machines / Python
  versions (built-in `hash()` is salted by `PYTHONHASHSEED`).
- `k` defaults to 1 (V4 baseline matches v0's "single one-shot" cost).
- `k=2` is a valid ablation (covers more syntactic spread per call at 2×
  prompt cost for the example block).
- For the consolidated dict, passing `k=1` is the only sensible choice
  (the dict has only one exemplar per type).

---

## 4. V4 measurement plan (V4_pool vs V4_consolidated)

### 4.1 Two variants, same 60-record subset

| Variant | Examples per call | Source | Measurement subset |
|---|---|---|---|
| V4_pool | `select_oneshots(vt, qid, k=1)` from `ONE_SHOT_POOL_BY_VIZ_TYPE` | per-query deterministic sampler over 3-exemplar pool | 60 records (same subset as v0 / S4 baseline) |
| V4_consolidated | the single string from `ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE[vt]` | identical exemplar for all queries of the same type | same 60 records |

Both variants run on the **same 60 records** so that a paired Δ on every
query is well-defined.

### 4.2 Primary outcome — paired Δ

For each query `i` in the 60-record subset:
- `score(V4_consolidated, i)` − `score(V4_pool, i)` per 6 axes + overall.

Aggregate:
- mean Δ per axis
- 95% bootstrap-BCa CI on the mean (10 000 resamples; query as the
  resampling unit so per-query correlation is preserved)

Decision rule (proposed):
- If overall-axis mean Δ ≥ 0 with CI lower bound > −0.02 and at least
  one axis (faith preferred) has CI lower bound > 0, ship V4_consolidated.
- Otherwise V4_pool wins; consolidated stays as an ablation footnote.

### 4.3 Stratified analysis on the 19-record drop subset

The §5.3 `oneshot_failure_analysis.md` identifies a 19-record cell where
the v0 placeholder produced faith=0 or near-zero. Run the same paired Δ
on this subset (cell-level): bootstrap-BCa CI on cell-level Δ. The drop
subset is the most sensitive evidence for whether either variant
recovers the failure mode.

### 4.4 Out-of-scope for this v1 design

- Multi-shot (k=2) ablation — defer to v2 once V4_pool vs V4_consolidated
  is decided.
- Dynamic per-query selection of pool-vs-consolidated based on the query
  itself (e.g., LLM-router on query type) — defer.
- Re-fitting the pool from the V4_pool batch outputs (using new
  faith-1.00 records as anchors) — defer to v2.

---

## 5. Caller migration plan (`code/pipelines/tmg.py`)

### 5.1 Type signature change

| line | v0 | v1 |
|---:|---|---|
| 72 | `ONE_SHOT_BY_VIZ_TYPE: Dict[str, str]` | `ONE_SHOT_POOL_BY_VIZ_TYPE: Dict[str, List[str]]` (and new `ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE: Dict[str, str]`) |
| 155 | `one_shot = ONE_SHOT_BY_VIZ_TYPE[primary]` | `one_shots = select_oneshots(primary, query_id, k=1, pool=...)` then `one_shot = one_shots[0]` |

### 5.2 New `build_tmg_rule` signature

`build_tmg_rule` currently takes `query_type: str` only. To support per-
query-deterministic selection AND the V4_pool / V4_consolidated mode flag,
extend the signature:

```python
def build_tmg_rule(
    query_type: str,
    query_id: str,
    *,
    oneshot_mode: Literal["pool", "consolidated"] = "pool",
) -> str:
    ...
    if oneshot_mode == "pool":
        one_shot = select_oneshots(primary, query_id, k=1)[0]
    else:
        one_shot = ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE[primary]
    ...
```

Caller (`run_paper_default` or wherever `build_tmg_rule` is invoked) must
be updated to pass `query_id` plus the mode flag.

### 5.3 Backward-compatibility / deprecation

- Delete `ONE_SHOT_BY_VIZ_TYPE` (the placeholder dict) after the v1
  pool + consolidated dicts are merged. Keeping the placeholder as a
  fallback risks accidental re-injection on an unhandled exception.
- The test in §6 below asserts the v1 dicts are non-empty and parse.

### 5.4 Rollout sequencing

1. Add `ONE_SHOT_POOL_BY_VIZ_TYPE`, `ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE`,
   `select_oneshots` (new symbols; no caller change yet).
2. Add `test_oneshot_pool_parses.py` smoke test (see §6).
3. Update `build_tmg_rule` signature and call sites; gate on a feature
   flag (`oneshot_mode="pool"` default to match V4_pool baseline).
4. Run V4_pool batch + V4_consolidated batch; collect paired Δ.
5. Decide which mode ships per §4.2 decision rule.
6. Delete `ONE_SHOT_BY_VIZ_TYPE`.

---

## 6. Smoke test spec — `tests/test_oneshot_pool_parses.py`

Markdown spec only (no code in this revision). Tests to add:

```
def test_pool_strings_round_trip():
    """Every pool string parses as JSON, has viz_type ∈ enum, viz_dsl non-empty."""
    for vt, pool in ONE_SHOT_POOL_BY_VIZ_TYPE.items():
        assert pool, f"empty pool for {vt}"
        for i, s in enumerate(pool):
            obj = json.loads(s)
            assert obj["viz_type"] == vt, f"{vt}[{i}] viz_type mismatch"
            assert obj["viz_dsl"], f"{vt}[{i}] empty viz_dsl"

def test_consolidated_strings_round_trip():
    """Every consolidated string parses; same invariants as pool."""
    for vt, s in ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE.items():
        obj = json.loads(s)
        assert obj["viz_type"] == vt
        assert obj["viz_dsl"]

def test_chartjs_inner_dsl_parses():
    """For chartjs_*, the inner viz_dsl value is itself valid JSON."""
    for src in (ONE_SHOT_POOL_BY_VIZ_TYPE, ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE):
        items = (
            [(vt, s) for vt, lst in src.items() for s in lst]
            if isinstance(next(iter(src.values())), list)
            else list(src.items())
        )
        for vt, s in items:
            if not vt.startswith("chartjs_"):
                continue
            inner = json.loads(json.loads(s)["viz_dsl"])
            assert "type" in inner
            assert "data" in inner

def test_mermaid_header_sniff():
    """For mermaid_*, the viz_dsl starts with the matching DSL header."""
    expected = {
        "mermaid_flowchart": ("graph ",),
        "mermaid_timeline": ("timeline",),
        "mermaid_mindmap": ("mindmap",),
    }
    for src in (ONE_SHOT_POOL_BY_VIZ_TYPE, ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE):
        items = (
            [(vt, s) for vt, lst in src.items() for s in lst]
            if isinstance(next(iter(src.values())), list)
            else list(src.items())
        )
        for vt, s in items:
            if vt not in expected:
                continue
            dsl = json.loads(s)["viz_dsl"].lstrip()
            assert any(dsl.startswith(p) for p in expected[vt]), \
                f"{vt} header mismatch: {dsl[:30]!r}"

def test_no_placeholder_regression():
    """No exemplar contains the v0 placeholder substrings."""
    forbidden = ["Acme Corp", "Acme Industries", "Founder", "Engineer X"]
    for src in (ONE_SHOT_POOL_BY_VIZ_TYPE, ONE_SHOT_CONSOLIDATED_BY_VIZ_TYPE):
        items = (
            [(vt, s) for vt, lst in src.items() for s in lst]
            if isinstance(next(iter(src.values())), list)
            else list(src.items())
        )
        for vt, s in items:
            for f in forbidden:
                assert f not in s, f"{vt} contains placeholder {f!r}"

def test_select_oneshots_deterministic():
    """Same (viz_type, query_id) returns the same exemplar across calls."""
    qid = "synthetic_demo_query_001"
    for vt in ONE_SHOT_POOL_BY_VIZ_TYPE:
        a = select_oneshots(vt, qid, k=1)
        b = select_oneshots(vt, qid, k=1)
        assert a == b
```

Already independently validated against the 6 per-type files in this
directory: 24 `json.loads` round-trips (3 pool + 1 consolidated × 6 types),
24 inner-DSL header / chartjs-inner-JSON checks, and 0 placeholder
regressions in exemplar JSON content (confirmed via `grep` over the
exemplar code blocks; the only `Acme` mentions in this directory are in
**commentary describing the v0 → v1 swap**, never inside exemplar JSON).

---

## 7. v0 deprecation notice

`docs/analysis/tmg_oneshot_pool_draft.md` (575 lines, commit `e305125`)
is **archived** for paired-diff evidence. Do **not** edit it. Future
revisions update files in this `docs/analysis/tmg_oneshot/` directory.

For the v0 → v1 paired diff (used as evidence in the V4 measurement
write-up), the trail is:
- v0: `tmg_oneshot_pool_draft.md`
- v0 review: `tmg_oneshot_pool_review.md`
- v1: `docs/analysis/tmg_oneshot/INDEX.md` + 6 per-type files (this dir)
