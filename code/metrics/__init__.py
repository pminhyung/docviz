"""docviz v0.4.1 metric implementations.

Per IMPLEMENTATION_GUIDE_v0.4.1.md §9.1, this package holds the deterministic
structured-evaluation metrics that replace the v0.3 4-axis judge composite as
the paper headline. Each module exposes pure functions that consume an
`ArtifactSpec` (from a B6/baseline pipeline output) + `Gold*` (from the gold
construction pipeline) and return per-metric dicts.

Layout:
    chart_metrics.py        §9.2 — Chart.js → table F1 + cell precision
    mermaid_metrics.py      §9.3 — Mermaid → graph node/edge F1
    evidence_metrics.py     §9.4 — Evidence F1 (explicit + implicit)
    hungarian_intent.py     §9.5 — Hungarian intent matching
    challenge_specific.py   §3.2 — per-challenge-type signals
    clipscore.py            REUSE legacy 205 LOC

NO `composite_fsos.py` — the headline is per-metric, no weighted composite.
"""
