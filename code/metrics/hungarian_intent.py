"""docviz v0.4.1 §9.5 — Hungarian intent matching.

Pair the agent's emitted artifacts (1-3) with the query's gold intents (1-3)
to fairly score multi-valid-output cases.

Cost function:
    C[i, j] = 1.0 - (0.4 * type_match + 0.6 * content_sim)

Where:
    type_match  = 1.0 if artifact viz_type matches gold intent's
                  artifact_type_hint (chartjs_* / mermaid_*); 0 otherwise.
    content_sim = ROUGE-L F1 between artifact.intent and gold.content_summary.

Matches with C < 0.5 are accepted; others are discarded.
Returns intent_coverage = matched / n_gold and redundancy_rate.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HungarianResult:
    intent_coverage: float
    redundancy_rate: float
    n_matched: int
    n_artifacts: int
    n_gold: int
    matches: list[tuple[int, int, float]]   # (artifact_idx, gold_idx, cost)


def _rouge_l_f1(a: str, b: str) -> float:
    """Simple ROUGE-L F1 over whitespace tokens."""
    if not a or not b:
        return 0.0
    ta, tb = a.lower().split(), b.lower().split()
    if not ta or not tb:
        return 0.0
    # LCS length via DP.
    m, n = len(ta), len(tb)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ta[i - 1] == tb[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[m][n]
    if lcs == 0:
        return 0.0
    p = lcs / m
    r = lcs / n
    return 2 * p * r / (p + r)


def _type_match(artifact_viz_type: str, gold_hint: str) -> float:
    if not gold_hint or gold_hint == "any":
        return 1.0   # generous when gold doesn't constrain type
    return 1.0 if artifact_viz_type == gold_hint else 0.0


def hungarian_match(
    artifacts: list[dict],
    gold_intents: list[dict],
    accept_threshold: float = 0.5,
) -> HungarianResult:
    """Match artifacts ↔ gold intents using a small Hungarian assignment."""
    n_a = len(artifacts)
    n_g = len(gold_intents)
    if n_g == 0:
        return HungarianResult(0.0, 0.0 if n_a == 0 else 1.0,
                               0, n_a, 0, [])
    if n_a == 0:
        return HungarianResult(0.0, 0.0, 0, 0, n_g, [])

    # Build cost matrix.
    try:
        import numpy as np
        from scipy.optimize import linear_sum_assignment
    except ImportError as exc:
        raise RuntimeError(
            "hungarian_match requires numpy + scipy. Install via "
            "`uv pip install numpy scipy`."
        ) from exc

    size = max(n_a, n_g)
    C = np.full((size, size), 1.0)
    for i in range(n_a):
        a = artifacts[i]
        for j in range(n_g):
            g = gold_intents[j]
            tm = _type_match(a.get("viz_type", ""),
                             g.get("artifact_type_hint", ""))
            cs = _rouge_l_f1(a.get("intent", ""), g.get("content_summary", ""))
            C[i, j] = 1.0 - (0.4 * tm + 0.6 * cs)

    row_ind, col_ind = linear_sum_assignment(C)
    matches: list[tuple[int, int, float]] = []
    for i, j in zip(row_ind, col_ind):
        if i < n_a and j < n_g and C[i, j] < accept_threshold:
            matches.append((int(i), int(j), float(C[i, j])))

    coverage = len(matches) / n_g
    redundancy = max(0, n_a - len(matches)) / max(n_a, 1)
    return HungarianResult(
        intent_coverage=coverage,
        redundancy_rate=redundancy,
        n_matched=len(matches),
        n_artifacts=n_a,
        n_gold=n_g,
        matches=matches,
    )
