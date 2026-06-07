"""SEF deterministic-core invariants — v0.4.3.

Asserts relationships/invariants, not snapshots (per CLAUDE.md testing rule):
normalization correctness, claim-unit precision (no LaTeX/citation noise),
and structural SEF integrity.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from code.sef import build_sef_from_markdown, build_sef_for_bundle
from code.sef.normalize import normalize_numeric, normalize_time
from code.sef.claim_units import _clean_text, extract_claim_units
from code.sef.schema import CLAIM_TYPES, AFFORDANCE_KEYS, CATEGORIES

_BUNDLES = Path("data/bundles/loong_phase2.json")


# --- normalization --------------------------------------------------------

@pytest.mark.parametrize("text,value,unit,salient", [
    ("$3.2B", 3.2e9, "USD", True),
    ("3.2 billion", 3.2e9, None, True),
    ("3,200,000,000", 3.2e9, None, False),
    ("15%", 15.0, "%", True),
    ("50 million", 5e7, None, True),
])
def test_numeric_magnitude_and_unit(text, value, unit, salient):
    nv = normalize_numeric(text)
    assert nv is not None
    assert nv.normalized_value == value
    assert nv.unit == unit
    assert nv.salient is salient


@pytest.mark.parametrize("text", ["5 t", "3 m", "section 1"])
def test_single_letter_magnitude_not_salient(text):
    """Math-variable forms (5 t, 3 m) must not become salient magnitudes."""
    nv = normalize_numeric(text)
    # may parse the bare number, but must NOT be a magnitude-scaled / salient value
    if nv is not None:
        assert nv.salient is False
        assert nv.normalized_value is None or nv.normalized_value < 1000


def test_time_normalization_forms():
    assert normalize_time("July 26, 2022").normalized == "2022-07-26"
    assert normalize_time("2021-03-15").normalized == "2021-03-15"
    assert normalize_time("in 1998").normalized == "1998"
    assert normalize_time("no date here") is None


# --- claim-unit precision -------------------------------------------------

def test_latex_and_citations_stripped():
    assert "mathscr" not in _clean_text(r"Let $\mathscr{P}$ be the set.")
    assert "et al" not in _clean_text("As shown by Stent et al. (2005), X holds.")
    # real claim survives cleaning
    assert "3.2B" in _clean_text(r"Revenue hit \$3.2B in 2023.")


def test_no_claim_from_pure_math_or_citation():
    assert extract_claim_units(r"AMS subject Classification: 60H10, 60B05.",
                               bid="B0001") == []
    assert extract_claim_units("As noted in Wen et al. (2015), a reranker helps.",
                               bid="B0002") == []


def test_salient_claim_extracted():
    cus = extract_claim_units("Cloud revenue rose to $3.2B in 2023.", bid="B0007")
    assert len(cus) >= 1
    cu = cus[0]
    assert cu.cuid.startswith("B0007#c")
    assert cu.claim_type in CLAIM_TYPES
    assert any(v.unit == "USD" for v in cu.values)


def test_claim_type_classification():
    trend = extract_claim_units("Sales grew from $100M to $150M.", bid="B1")
    assert trend and trend[0].claim_type == "numeric_trend"
    rank = extract_claim_units("Apple had the highest revenue at $400B.", bid="B2")
    assert rank and rank[0].claim_type == "ranking"


# --- structural SEF integrity (real corpus) -------------------------------

@pytest.fixture(scope="module")
def sample_sefs():
    if not _BUNDLES.exists():
        pytest.skip("loong_phase2 bundle not present")
    bundles = json.loads(_BUNDLES.read_text())
    out = []
    for b in bundles[:6]:
        out.extend(build_sef_for_bundle(b, domain="mixed"))
    return out


def test_block_ids_unique_and_reading_order_monotonic(sample_sefs):
    for sef in sample_sefs:
        bids = [b.bid for b in sef.blocks]
        assert len(bids) == len(set(bids)), f"duplicate bid in {sef.doc_id}"
        orders = [b.reading_order for b in sef.blocks]
        assert orders == sorted(orders)
        assert all(b.category in CATEGORIES for b in sef.blocks)


def test_cuids_namespaced_to_block(sample_sefs):
    for sef in sample_sefs:
        for blk in sef.blocks:
            for cu in blk.claim_units:
                assert cu.cuid.startswith(f"{blk.bid}#")
                assert cu.claim_type in CLAIM_TYPES


def test_affordance_index_references_real_eids(sample_sefs):
    for sef in sample_sefs:
        eids = sef.all_eids()
        assert set(sef.viz_affordance_index) <= set(AFFORDANCE_KEYS)
        for key, ids in sef.viz_affordance_index.items():
            for ref in ids:
                assert ref in eids, f"{key} -> {ref} not a real eid in {sef.doc_id}"


def test_cross_refs_endpoints_valid(sample_sefs):
    for sef in sample_sefs:
        bids = {b.bid for b in sef.blocks}
        for xr in sef.cross_refs:
            assert xr.from_bid in bids and xr.to_bid in bids
            assert xr.from_bid != xr.to_bid


def test_serialization_roundtrip(sample_sefs):
    for sef in sample_sefs[:2]:
        d = sef.to_dict()
        assert d["extraction_quality"] in ("full", "partial", "fallback")
        # JSON-serializable
        json.dumps(d, ensure_ascii=False)
