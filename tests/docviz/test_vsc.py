"""VSC core invariants — v0.4.3 §4.5 (canonical spec → DSL → validate → repair).

Invariant-style (per CLAUDE.md testing rule): deterministic conversion keeps the
contract by construction; the validator detects each violation class; repair is
one-shot and falls to M1=0 on persistent failure.
"""
from __future__ import annotations

import json
import os
import shutil

import pytest

from code.vsc import (
    parse_spec, spec_to_dsl, validate_spec, validate_dsl, run_vsc,
    VIZ_TYPE_POOL, DIAGRAM_TYPES, CHART_TYPES,
)

_HAS_MMDC = shutil.which("mmdc") or os.path.exists(
    "/home/poc/.npm-global/bin/mmdc")


def _diagram(viz_type):
    return parse_spec({
        "viz_type": viz_type,
        "nodes": [{"id": "a", "label": "Alpha", "source_eid": "B0#c1"},
                  {"id": "b", "label": "Beta", "source_eid": "B0#c2"},
                  {"id": "c", "label": "Gamma", "source_eid": "B0#c2"}],
        "edges": [{"from": "a", "to": "b", "rel_label": "leads", "source_eid": "B0#c1"},
                  {"from": "b", "to": "c", "rel_label": "then", "source_eid": "B0#c2"}],
    })


def _chart(viz_type):
    return parse_spec({
        "viz_type": viz_type, "x_label": "Year", "y_label": "USD",
        "datapoints": [
            {"series": "A", "category": "2022", "value": 100, "unit": "USD", "source_eid": "B1#c1"},
            {"series": "A", "category": "2023", "value": 150, "unit": "USD", "source_eid": "B1#c1"},
            {"series": "B", "category": "2022", "value": 80, "source_eid": "B1#c2"},
        ],
    })


# --- deterministic conversion keeps the contract --------------------------

@pytest.mark.parametrize("viz_type", sorted(CHART_TYPES))
def test_chart_conversion_is_dimension_consistent(viz_type):
    """R2 holds by construction: every dataset aligns to the label axis."""
    dsl, res = validate_spec(_chart(viz_type), sef_eids={"B1#c1", "B1#c2"},
                             render=False)
    obj = json.loads(dsl)
    labels = obj["data"]["labels"]
    for ds in obj["data"]["datasets"]:
        if viz_type == "chartjs_scatter":
            assert len(ds["data"]) == len(labels)
        else:
            assert len(ds["data"]) == len(labels)
    assert res.by_rule()["R2"] == 0


@pytest.mark.parametrize("viz_type", sorted(DIAGRAM_TYPES))
def test_diagram_edges_reference_declared_nodes(viz_type):
    """R3 holds by construction for a well-formed DiagramSpec."""
    _, res = validate_spec(_diagram(viz_type), sef_eids={"B0#c1", "B0#c2"},
                           render=False)
    assert res.by_rule()["R3"] == 0
    assert res.by_rule()["R5"] == 0


# --- R1 real render across every mermaid primitive ------------------------

@pytest.mark.skipif(not _HAS_MMDC, reason="mmdc not installed")
@pytest.mark.parametrize("viz_type", sorted(DIAGRAM_TYPES))
def test_every_mermaid_primitive_renders(viz_type):
    dsl, res = validate_spec(_diagram(viz_type), sef_eids={"B0#c1", "B0#c2"},
                             render=True)
    assert res.by_rule()["R1"] == 0, f"{viz_type} failed R1: {res.summary()}\n{dsl}"


# --- each violation class is detected -------------------------------------

def test_R4_unsupported_marker():
    res = validate_dsl("chartjs_pie3d", "{}", render=False)
    assert res.by_rule()["R4"] == 1 and not res.ok


def test_R3_broken_edge_detected():
    bad = parse_spec({"viz_type": "mermaid_flowchart",
                      "nodes": [{"id": "a", "label": "A"}],
                      "edges": [{"from": "a", "to": "ghost"}]})
    _, res = validate_spec(bad, sef_eids=set(), render=False)
    assert res.by_rule()["R3"] >= 1


def test_R5_invalid_source_ref_detected():
    bad = parse_spec({"viz_type": "mermaid_flowchart",
                      "nodes": [{"id": "a", "label": "A", "source_eid": "NOPE#c9"}],
                      "edges": []})
    _, res = validate_spec(bad, sef_eids={"B0#c1"}, render=False)
    assert res.by_rule()["R5"] == 1


def test_R2_metric_on_ragged_baseline_chartjs():
    ragged = json.dumps({"type": "bar", "data": {
        "labels": ["a", "b", "c"], "datasets": [{"label": "s", "data": [1, 2]}]}})
    res = validate_dsl("chartjs_bar", ragged, render=False)
    assert res.by_rule()["R2"] == 1


def test_R5_skipped_for_baselines_without_source_eids():
    """R5 is B6-only: a baseline DSL with no source_eids never trips R5."""
    res = validate_dsl("mermaid_flowchart", "flowchart TD\n  a-->b\n",
                       sef_eids={"B0#c1"}, render=False)
    assert res.by_rule()["R5"] == 0


# --- one-shot repair semantics --------------------------------------------

def test_repair_fixes_violation_once():
    bad = parse_spec({"viz_type": "mermaid_flowchart",
                      "nodes": [{"id": "a", "label": "A"}],
                      "edges": [{"from": "a", "to": "ghost"}]})

    def repair_fn(spec, violations, prompt):
        # drop the broken edge — a valid one-shot fix
        spec.edges = [e for e in spec.edges if e.to_id in spec.node_ids()]
        return spec

    out = run_vsc(bad, sef_eids=set(), repair_fn=repair_fn, render=False)
    assert out.repaired and out.ok and out.violations["R3"] == 0


def test_repair_failure_scores_m1_zero():
    bad = parse_spec({"viz_type": "mermaid_flowchart",
                      "nodes": [{"id": "a", "label": "A"}],
                      "edges": [{"from": "a", "to": "ghost"}]})

    def repair_fn(spec, violations, prompt):
        return spec  # no-op: violation persists

    out = run_vsc(bad, sef_eids=set(), repair_fn=repair_fn, render=False)
    assert out.repaired and not out.ok  # M1 = 0


def test_no_repair_fn_reports_violation():
    bad = parse_spec({"viz_type": "mermaid_flowchart",
                      "nodes": [{"id": "a", "label": "A"}],
                      "edges": [{"from": "a", "to": "ghost"}]})
    out = run_vsc(bad, sef_eids=set(), repair_fn=None, render=False)
    assert not out.ok and not out.repaired


# --- scorer tab:vsc metric helper -----------------------------------------

def test_scorer_vsc_flags():
    from code.judge.score_phase1 import _vsc_flags
    clean = _vsc_flags("mermaid_flowchart", "flowchart TD\n a-->b\n", True)
    assert sum(clean.values()) == 0
    assert _vsc_flags("mermaid_flowchart", "x", False)["R1"] == 1
    ragged = json.dumps({"type": "bar", "data": {
        "labels": ["a", "b", "c"], "datasets": [{"label": "s", "data": [1, 2]}]}})
    assert _vsc_flags("chartjs_bar", ragged, True)["R2"] == 1
    assert _vsc_flags("chartjs_pie3d", "{}", True)["R4"] == 1
