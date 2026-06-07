"""generate_viz × VSC wiring — v0.4.3 (approach B).

Mocks the internal synthesis LLM (so the test is hermetic) but exercises the
real VSC convert→validate→repair path + sidecar contract. Asserts the −VSC arm
keeps the direct-DSL path and that SAO/contract fields land in the sidecar.
"""
from __future__ import annotations

import json
import os
import shutil

import pytest

import exaone.viz_tools.handle_generate_viz as gv

_HAS_MMDC = shutil.which("mmdc") or os.path.exists("/home/poc/.npm-global/bin/mmdc")
pytestmark = pytest.mark.skipif(not _HAS_MMDC, reason="mmdc not installed (R1 render)")


def _read_sidecars(result_json: str) -> list[dict]:
    res = json.loads(result_json)
    data = res.get("data") or res  # tool_result envelope shape tolerant
    out = []
    for e in data["emitted"]:
        out.append(json.loads(open(e["sidecar"]).read()))
    return out


@pytest.fixture
def sidecar_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCVIZ_VIZ_SIDECAR_DIR", str(tmp_path / "viz"))
    monkeypatch.setenv("DOCVIZ_VARIANT", "full")
    return tmp_path


def test_vsc_full_path_writes_contract_fields(sidecar_dir, monkeypatch):
    spec = {"viz_type": "mermaid_flowchart", "title": "Flow",
            "nodes": [{"id": "a", "label": "Revenue", "source_eid": "B0#c1"},
                      {"id": "b", "label": "Growth", "source_eid": "B0#c2"}],
            "edges": [{"from": "a", "to": "b", "rel_label": "drives",
                       "source_eid": "B0#c1"}]}
    monkeypatch.setattr(gv, "_synthesize_spec", lambda *a, **k: dict(spec))

    out = gv.handle_generate_viz(
        {"artifacts": [{"viz_type": "mermaid_flowchart", "intent": "show flow",
                        "content_brief": "Revenue drives growth.",
                        "evidence_ids": ["B0#c1", "B0#c2"]}]},
        context={"task_id": "t1", "sef_eids": ["B0#c1", "B0#c2"]})

    sc = _read_sidecars(out)[0]
    assert sc["vsc_enabled"] is True
    assert sc["vsc_ok"] is True
    assert sc["dsl_code"].startswith("flowchart")
    assert set(sc["source_eids"]) <= {"B0#c1", "B0#c2"}
    assert sc["evidence_ids"] == ["B0#c1", "B0#c2"]
    assert sum(sc["vsc_violations"].values()) == 0


def test_vsc_repairs_bad_source_ref(sidecar_dir, monkeypatch):
    bad = {"viz_type": "mermaid_flowchart",
           "nodes": [{"id": "a", "label": "Alpha", "source_eid": "GHOST#c9"},
                     {"id": "b", "label": "Beta", "source_eid": "B0#c2"}],
           "edges": [{"from": "a", "to": "b", "rel_label": "to",
                      "source_eid": "GHOST#c9"}]}
    good = {"viz_type": "mermaid_flowchart",
            "nodes": [{"id": "a", "label": "Alpha", "source_eid": "B0#c1"},
                      {"id": "b", "label": "Beta", "source_eid": "B0#c2"}],
            "edges": [{"from": "a", "to": "b", "rel_label": "to",
                       "source_eid": "B0#c1"}]}
    monkeypatch.setattr(gv, "_synthesize_spec", lambda *a, **k: dict(bad))
    # repair_fn re-synthesizes to the corrected spec
    from code.vsc import parse_spec
    monkeypatch.setattr(gv, "_make_repair_fn",
                        lambda: (lambda s, v, p: parse_spec(dict(good))))

    out = gv.handle_generate_viz(
        {"artifacts": [{"viz_type": "mermaid_flowchart", "intent": "x",
                        "content_brief": "A.", "evidence_ids": ["B0#c1"]}]},
        context={"task_id": "t2", "sef_eids": ["B0#c1", "B0#c2"]})
    sc = _read_sidecars(out)[0]
    assert sc["vsc_repaired"] is True
    assert sc["vsc_ok"] is True
    assert sc["vsc_violations"].get("R5", 0) == 0


def test_novsc_arm_uses_direct_dsl(sidecar_dir, monkeypatch):
    monkeypatch.setenv("DOCVIZ_VARIANT", "novsc")
    monkeypatch.setattr(gv, "_synthesize_dsl",
                        lambda *a, **k: "flowchart TD\n    a-->b\n")

    out = gv.handle_generate_viz(
        {"artifacts": [{"viz_type": "mermaid_flowchart", "intent": "x",
                        "content_brief": "A to B.", "evidence_ids": []}]},
        context={"task_id": "t3"})
    sc = _read_sidecars(out)[0]
    assert sc["vsc_enabled"] is False
    assert sc["dsl_code"].startswith("flowchart")


def test_sef_eids_loaded_from_dir(tmp_path, monkeypatch):
    sef = {"blocks": [{"bid": "B0", "claim_units": [{"cuid": "B0#c1"}]},
                      {"bid": "B1", "claim_units": []}]}
    d = tmp_path / "sef"
    d.mkdir()
    (d / "task9.json").write_text(json.dumps(sef))
    monkeypatch.setenv("DOCVIZ_SEF_DIR", str(d))
    eids = gv._sef_eids_for_task("task9", None)
    assert eids == {"B0", "B0#c1", "B1"}
