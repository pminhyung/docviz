"""Chart.js DSL parser → NormalizedTable (v0.4.1 §7.1, §9.2).

For P0 parser pilot, only `parse_chartjs_to_table` is exercised. Full metric
implementations (`evaluate_chartjs`) come in P4.

The parser is dependency-free (json + light dict navigation). Returns `None`
on syntax error.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass(frozen=True)
class Cell:
    """One data point in a normalized table view of a Chart.js spec."""
    row: str          # x-axis label (column header in the JSON source)
    col: str          # dataset label (series name)
    value: Any        # numeric or string


@dataclass(frozen=True)
class Series:
    """One Chart.js dataset, normalized."""
    label: str
    values: List[Any]


@dataclass(frozen=True)
class NormalizedTable:
    """The chart in row × col × value form, suitable for F1 over cells."""
    chart_type: str           # "bar" | "grouped_bar" | "line" | "pie" | …
    columns: List[str]        # x-axis labels (e.g. years, categories)
    series: List[Series]      # dataset labels + raw values
    cells: List[Cell]         # flattened (col, row, value) triples

    def as_dict(self) -> dict:
        return {
            "chart_type": self.chart_type,
            "columns": list(self.columns),
            "n_columns": len(self.columns),
            "n_series": len(self.series),
            "n_cells": len(self.cells),
        }


def _repair_json_braces(text: str) -> str:
    """Recover from Qwen's two most common Chart.js JSON errors:
    1-3 trailing extra/missing braces. Iteratively strip trailing `}` until
    parse succeeds; if still failing, append missing `}` to balance opens.
    Mirrors `_legacy/code/judge/dsl_parser.py` _repair_json_braces.
    """
    text = text.strip()
    candidate = text
    for _ in range(5):
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            if candidate.endswith("}"):
                candidate = candidate[:-1].rstrip()
                continue
            break
    opens = text.count("{")
    closes = text.count("}")
    if opens > closes:
        return text + "}" * (opens - closes)
    return text


def parse_chartjs_to_table(dsl_code: str) -> Optional[NormalizedTable]:
    """Deterministic Chart.js DSL → NormalizedTable. Returns None on syntax error.

    Handles ``"type": "bar"`` with optional ``"grouped"`` flag → maps to
    ``chart_type = "grouped_bar"`` for chart-type-accuracy comparison.
    """
    if not dsl_code or not dsl_code.strip():
        return None

    try:
        spec = json.loads(dsl_code)
    except json.JSONDecodeError:
        repaired = _repair_json_braces(dsl_code)
        try:
            spec = json.loads(repaired)
        except json.JSONDecodeError:
            return None

    if not isinstance(spec, dict):
        return None

    raw_type = (spec.get("type") or "").strip().lower()
    data = spec.get("data") or {}
    if not isinstance(data, dict):
        return None
    raw_labels = data.get("labels") or []
    raw_datasets = data.get("datasets") or []
    if not isinstance(raw_labels, list) or not isinstance(raw_datasets, list):
        return None

    # Normalize chart_type: detect grouped bar via multiple datasets on a bar.
    chart_type = raw_type
    if raw_type == "bar" and len(raw_datasets) > 1:
        chart_type = "grouped_bar"

    columns = [str(x) for x in raw_labels]
    series: List[Series] = []
    cells: List[Cell] = []
    for ds in raw_datasets:
        if not isinstance(ds, dict):
            continue
        label = str(ds.get("label", ""))
        values = ds.get("data") or []
        if not isinstance(values, list):
            continue
        series.append(Series(label=label, values=list(values)))
        for i, v in enumerate(values):
            if i >= len(columns):
                break  # silently truncate if dataset length exceeds labels
            cells.append(Cell(row=columns[i], col=label, value=v))

    return NormalizedTable(
        chart_type=chart_type,
        columns=columns,
        series=series,
        cells=cells,
    )


# ── §9.2 evaluate_chartjs — Chart Data F1 + chart_type accuracy ────────────

def _cell_key(c) -> tuple:
    """Cells match if (col, row) coincide; value compared separately."""
    return (str(getattr(c, "col", c.get("col") if isinstance(c, dict) else "")),
            str(getattr(c, "row", c.get("row") if isinstance(c, dict) else "")))


def _cell_value(c):
    return getattr(c, "value", c.get("value") if isinstance(c, dict) else None)


def _values_match(a, b, tol_pct: float = 0.05) -> bool:
    """Numeric within ±5% tolerance; otherwise exact string equality."""
    try:
        fa, fb = float(a), float(b)
        if fa == 0 and fb == 0:
            return True
        scale = max(abs(fa), abs(fb))
        return abs(fa - fb) / max(scale, 1e-9) <= tol_pct
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()


def evaluate_chartjs(artifact: dict, gold_table: dict) -> dict:
    """Chart.js eval against a gold_table dict (§9.2).

    Returns: {chart_type_acc, chart_data_p, chart_data_r, chart_data_f1,
              numeric_mae, hallucination_row_rate, parse_failed}
    """
    dsl = artifact.get("dsl_code") or artifact.get("viz_dsl", "")
    table = parse_chartjs_to_table(dsl)
    if table is None:
        return {
            "chart_type_acc": 0.0,
            "chart_data_p": 0.0,
            "chart_data_r": 0.0,
            "chart_data_f1": 0.0,
            "numeric_mae": float("inf"),
            "hallucination_row_rate": 1.0,
            "parse_failed": True,
        }

    gold_type = (gold_table.get("chart_type") or "").lower()
    pred_type = (table.chart_type or "").lower()
    type_acc = float(pred_type == gold_type) if gold_type else 0.0

    pred_cells = {_cell_key(c): _cell_value(c) for c in table.cells}
    gold_cells = {_cell_key(c): _cell_value(c) for c in gold_table.get("cells", [])}

    if not gold_cells:
        return {
            "chart_type_acc": type_acc,
            "chart_data_p": 0.0,
            "chart_data_r": 0.0,
            "chart_data_f1": 0.0,
            "numeric_mae": float("inf"),
            "hallucination_row_rate": 1.0 if pred_cells else 0.0,
            "parse_failed": False,
        }

    tp = 0
    mae_acc, mae_n = 0.0, 0
    for k, gv in gold_cells.items():
        pv = pred_cells.get(k)
        if pv is None:
            continue
        if _values_match(pv, gv):
            tp += 1
        try:
            mae_acc += abs(float(pv) - float(gv))
            mae_n += 1
        except (TypeError, ValueError):
            pass

    n_pred = len(pred_cells)
    n_gold = len(gold_cells)
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    mae = mae_acc / mae_n if mae_n else float("inf")
    hallu = max(0, n_pred - tp) / max(n_pred, 1)
    return {
        "chart_type_acc": type_acc,
        "chart_data_p": p,
        "chart_data_r": r,
        "chart_data_f1": f1,
        "numeric_mae": mae,
        "hallucination_row_rate": hallu,
        "parse_failed": False,
    }
