"""docviz v0.4.1 §9.4 — Evidence F1 (explicit + implicit).

Two evaluation modes:
- **explicit**: the artifact carries `evidence_ids` (B6 full / -CIS / -TMG with SAO active).
  Direct set F1 against gold evidence.
- **implicit**: artifact has no evidence_ids (baselines, -SAO ablation).
  Best-match embedding from textual viz elements against gold evidence spans.
  Threshold: cosine ≥ 0.75 to count as a match.

Embedder default: `sentence-transformers/all-mpnet-base-v2` (lazy-loaded).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional


@dataclass
class EvidenceResult:
    evidence_p: float
    evidence_r: float
    evidence_f1: float
    mode: str            # "explicit" | "implicit" | "no_gold"
    n_pred: int
    n_gold: int


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _set_pr(pred: set, gold: set) -> tuple[float, float]:
    if not gold:
        return 0.0, 0.0
    if not pred:
        return 0.0, 0.0
    tp = len(pred & gold)
    p = tp / len(pred)
    r = tp / len(gold)
    return p, r


def evaluate_evidence_explicit(
    predicted_evidence_ids: Iterable[str],
    gold_evidence_ids: Iterable[str],
) -> EvidenceResult:
    """Set F1 when both sides have evidence id sets."""
    pred = set(predicted_evidence_ids)
    gold = set(gold_evidence_ids)
    if not gold:
        return EvidenceResult(0.0, 0.0, 0.0, "no_gold", len(pred), 0)
    p, r = _set_pr(pred, gold)
    return EvidenceResult(p, r, _f1(p, r), "explicit", len(pred), len(gold))


_TEXT_FRAGMENT_RE = re.compile(r'"([^"]{8,})"')   # quoted strings
_LABEL_RE = re.compile(r'(?:label|title|content)\s*[:=]\s*"?([^",}\n]+)"?', re.I)


def _extract_textual_elements_chartjs(dsl_code: str) -> list[str]:
    """Heuristic: pull labels + dataset.label + title from a Chart.js JSON string.

    Used by the implicit mode when the artifact has no evidence_ids.
    """
    import json
    try:
        spec = json.loads(dsl_code)
    except json.JSONDecodeError:
        return _TEXT_FRAGMENT_RE.findall(dsl_code)
    out: list[str] = []
    data = spec.get("data") or {}
    for lbl in (data.get("labels") or []):
        out.append(str(lbl))
    for ds in (data.get("datasets") or []):
        if isinstance(ds, dict):
            out.append(str(ds.get("label", "")))
    if title := (spec.get("options", {}).get("plugins", {})
                 .get("title", {}).get("text", "")):
        out.append(str(title))
    return [s for s in out if s.strip()]


def _extract_textual_elements_mermaid(dsl_code: str) -> list[str]:
    """Heuristic: node labels + edge labels + non-keyword lines."""
    out: list[str] = []
    for line in dsl_code.splitlines():
        line = line.strip()
        if not line or line.startswith(("graph", "flowchart", "timeline",
                                         "mindmap", "sequenceDiagram",
                                         "classDiagram")):
            continue
        # Strip mermaid syntax tokens to leave human text.
        cleaned = re.sub(r"[\[\(\{\}\)\]]", " ", line)
        cleaned = re.sub(r"-{1,3}>|={1,3}>|-\.->", " ", cleaned)
        cleaned = re.sub(r"\|[^|]*\|", " ", cleaned)
        cleaned = cleaned.strip()
        if len(cleaned) > 3:
            out.append(cleaned)
    return out


_EMBEDDER = None


def _embedder():
    """Lazy-load all-mpnet-base-v2 once per process."""
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer
        _EMBEDDER = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
    return _EMBEDDER


def evaluate_evidence_implicit(
    viz_type: str,
    dsl_code: str,
    gold_evidence: list[dict],   # [{id, text, ...}, ...]
    threshold: float = 0.75,
) -> EvidenceResult:
    """Match viz text elements against gold evidence span text via embedding."""
    if not gold_evidence:
        return EvidenceResult(0.0, 0.0, 0.0, "no_gold", 0, 0)
    if viz_type.startswith("chartjs_"):
        elements = _extract_textual_elements_chartjs(dsl_code)
    elif viz_type.startswith("mermaid_"):
        elements = _extract_textual_elements_mermaid(dsl_code)
    else:
        elements = []
    if not elements:
        return EvidenceResult(0.0, 0.0, 0.0, "implicit", 0, len(gold_evidence))

    model = _embedder()
    elem_emb = model.encode(elements, convert_to_tensor=True, show_progress_bar=False)
    span_emb = model.encode([e["text"] for e in gold_evidence],
                            convert_to_tensor=True, show_progress_bar=False)
    # Pairwise cosine.
    import torch
    elem_n = torch.nn.functional.normalize(elem_emb, dim=-1)
    span_n = torch.nn.functional.normalize(span_emb, dim=-1)
    sim = (elem_n @ span_n.T)  # (n_elem, n_span)
    matched_spans: set[str] = set()
    matched_elems: set[int] = set()
    for i, row in enumerate(sim):
        best = int(row.argmax())
        if float(row[best]) >= threshold:
            matched_elems.add(i)
            matched_spans.add(gold_evidence[best]["id"])
    p = len(matched_elems) / max(len(elements), 1)
    r = len(matched_spans) / max(len(gold_evidence), 1)
    return EvidenceResult(p, r, _f1(p, r), "implicit",
                          len(elements), len(gold_evidence))


def evaluate_evidence(
    artifact: dict,
    gold_evidence: list[dict],
) -> EvidenceResult:
    """Dispatch on artifact.evidence_ids presence."""
    pred_ids = artifact.get("evidence_ids") or []
    if pred_ids:
        gold_ids = [e["id"] for e in gold_evidence]
        return evaluate_evidence_explicit(pred_ids, gold_ids)
    return evaluate_evidence_implicit(
        viz_type=artifact.get("viz_type", ""),
        dsl_code=artifact.get("dsl_code", ""),
        gold_evidence=gold_evidence,
    )
