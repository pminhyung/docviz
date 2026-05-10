"""Smoke tests for code/agent_tools/oneshot_pool.json (mentor minor #7).

Validates the V4 exemplar sidecar invariants relied on by:
  - viz_output_mapper._extract_dsl_block (strategy 1a fast-path)
  - generate_viz tool's exemplar-injection prompt
  - the agent's final_answer round-trip

Adapted from the spec at docs/analysis/tmg_oneshot/INDEX.md §6, with
two extensions for the 10-type enum (commit 40a9716):
  - mermaid_sequenceDiagram + mermaid_classDiagram header sniff
  - chartjs_pie + chartjs_scatter inner-type acceptance

Run:  python -m pytest tests/test_oneshot_pool_sidecar.py -v
or:   python -m unittest tests.test_oneshot_pool_sidecar
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
SIDECAR_PATH = REPO_ROOT / "code" / "agent_tools" / "oneshot_pool.json"


def _load_sidecar() -> Dict[str, Any]:
    return json.loads(SIDECAR_PATH.read_text(encoding="utf-8"))


_EXPECTED_MERMAID_HEADS = {
    "mermaid_flowchart": ("graph ", "flowchart "),
    "mermaid_timeline": ("timeline",),
    "mermaid_mindmap": ("mindmap",),
    "mermaid_sequenceDiagram": ("sequenceDiagram",),
    "mermaid_classDiagram": ("classDiagram",),
}

_EXPECTED_CHARTJS_INNER_TYPES = {
    "chartjs_bar": {"bar"},
    "chartjs_line": {"line"},
    "chartjs_grouped_bar": {"bar"},  # grouped is a multi-dataset bar
    "chartjs_pie": {"pie", "doughnut"},
    "chartjs_scatter": {"scatter", "bubble"},
}

_PLACEHOLDER_REGRESSIONS = (
    "Acme Corp",
    "Acme Industries",
    "Founder",
    "Engineer X",
)


class TestOneshotPoolSidecar(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.sidecar = _load_sidecar()
        cls.pool = cls.sidecar["pool"]
        cls.consolidated = cls.sidecar["consolidated"]

    # ── Coverage ──────────────────────────────────────────────────────────

    def test_pool_covers_all_10_viz_types(self):
        from code.agent_tools.generate_viz import VIZ_TYPE_POOL
        for vt in VIZ_TYPE_POOL:
            self.assertIn(vt, self.pool, f"pool missing viz_type={vt}")

    def test_consolidated_covers_all_10_viz_types(self):
        from code.agent_tools.generate_viz import VIZ_TYPE_POOL
        for vt in VIZ_TYPE_POOL:
            self.assertIn(vt, self.consolidated,
                          f"consolidated missing viz_type={vt}")

    # ── Schema round-trip ────────────────────────────────────────────────

    def test_pool_strings_round_trip(self):
        for vt, items in self.pool.items():
            self.assertTrue(items, f"empty pool for {vt}")
            for i, s in enumerate(items):
                obj = json.loads(s)
                self.assertEqual(
                    obj.get("viz_type"), vt,
                    f"pool[{vt}][{i}] viz_type mismatch: {obj.get('viz_type')!r}"
                )
                self.assertTrue(obj.get("viz_dsl"),
                                f"pool[{vt}][{i}] empty viz_dsl")

    def test_consolidated_strings_round_trip(self):
        for vt, s in self.consolidated.items():
            obj = json.loads(s)
            self.assertEqual(obj.get("viz_type"), vt)
            self.assertTrue(obj.get("viz_dsl"))

    # ── chartjs inner DSL (the viz_dsl is itself a JSON spec) ────────────

    def test_chartjs_inner_dsl_parses(self):
        for src in (self.pool, self.consolidated):
            items = self._flatten(src)
            for vt, s in items:
                if not vt.startswith("chartjs_"):
                    continue
                outer = json.loads(s)
                inner = json.loads(outer["viz_dsl"])
                self.assertIn("type", inner,
                              f"{vt}: chartjs inner missing 'type'")
                self.assertIn("data", inner,
                              f"{vt}: chartjs inner missing 'data'")
                expected = _EXPECTED_CHARTJS_INNER_TYPES[vt]
                self.assertIn(
                    inner["type"], expected,
                    f"{vt}: chartjs inner.type={inner['type']!r} "
                    f"not in {expected}",
                )

    # ── mermaid header sniff (matches viz_output_mapper strategy 2) ──────

    def test_mermaid_header_sniff(self):
        for src in (self.pool, self.consolidated):
            items = self._flatten(src)
            for vt, s in items:
                if not vt.startswith("mermaid_"):
                    continue
                expected = _EXPECTED_MERMAID_HEADS[vt]
                dsl = json.loads(s)["viz_dsl"].lstrip()
                self.assertTrue(
                    any(dsl.startswith(p) for p in expected),
                    f"{vt} header mismatch: {dsl[:40]!r}; expected one of {expected}",
                )

    # ── Anti-regression on the v0 placeholder content ───────────────────

    def test_no_placeholder_regression(self):
        for src in (self.pool, self.consolidated):
            items = self._flatten(src)
            for vt, s in items:
                for f in _PLACEHOLDER_REGRESSIONS:
                    self.assertNotIn(
                        f, s,
                        f"{vt}: forbidden placeholder {f!r} found in exemplar",
                    )

    # ── Tool sampler determinism ─────────────────────────────────────────

    def test_select_exemplar_deterministic(self):
        """Same (viz_type, query_id, mode) returns the same exemplar."""
        from code.agent_tools.generate_viz import _select_exemplar
        qid = "synthetic_demo_query_001"
        for vt in self.pool:
            a = _select_exemplar(vt, qid, mode="v4_pool")
            b = _select_exemplar(vt, qid, mode="v4_pool")
            self.assertEqual(a, b, f"v4_pool {vt}: non-deterministic selection")

        for vt in self.consolidated:
            a = _select_exemplar(vt, qid, mode="v4_consolidated")
            b = _select_exemplar(vt, qid, mode="v4_consolidated")
            self.assertEqual(a, b, f"v4_consolidated {vt}: non-deterministic")

    def test_select_exemplar_mode_dispatch(self):
        """v4_pool vs v4_consolidated return different exemplars."""
        from code.agent_tools.generate_viz import _select_exemplar
        qid = "any_qid"
        for vt in self.pool:
            pool_pick = _select_exemplar(vt, qid, mode="v4_pool")
            cons_pick = _select_exemplar(vt, qid, mode="v4_consolidated")
            # They might coincidentally be equal if pool[0] == consolidated;
            # but our exemplars were authored differently, so this should
            # hold for the current sidecar.
            self.assertNotEqual(
                pool_pick, cons_pick,
                f"{vt}: pool and consolidated unexpectedly equal "
                "(check the sidecar — this normally indicates a build error)",
            )

    # ── Helper ────────────────────────────────────────────────────────────

    @staticmethod
    def _flatten(src):
        first_value = next(iter(src.values()))
        if isinstance(first_value, list):
            return [(vt, s) for vt, lst in src.items() for s in lst]
        return list(src.items())


if __name__ == "__main__":
    unittest.main()
