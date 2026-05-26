"""GovReport loader v0.4 — cross-document multi-report bundles.

Replaces the v0.3 intra-doc section-split approach. Per
`docs/active/tracks/feat-source-loaders/LOADER_CONTRACT_v04.md`:

- Each Bundle bundles **3-5 distinct GovReport documents** that share a
  common policy area (defense / health / energy / …).
- Each Doc = one full GovReport `report` body (trimmed to ~40K chars).
- Total chars per bundle: 15K–200K.
- 50 bundles, `random.seed(42)`.
- `bundle.metadata.policy_area` doubles as the v0.4 `bridge_entity`.

Policy area is inferred per-report by keyword-counting against a small
fixed dictionary covering the common GAO/CRS topic spectrum. Reports
that don't strongly match any single area are grouped under `general`
and used as filler when a primary area cluster is short on bundles.

Source: HuggingFace `ccdv/govreport-summarization` (record schema:
`{report, summary}` only — no native title/topic metadata, so we mine
from the body itself).
"""
from __future__ import annotations

import argparse
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Pin HF cache to /ex_disk2 (root partition full on this dev box)
os.environ.setdefault("HF_HOME", "/ex_disk2/mhpark/poc/.cache/huggingface")

from datasets import load_dataset

from code.pipelines.base import Bundle, Doc
from code.utils.bundle_io import validate_bundle, write_bundles_json


SEED = 42
N_BUNDLES = 50
MIN_DOCS = 3
MAX_DOCS = 5

# Per-bundle char budget (contract v0.4)
MIN_CHARS_BUNDLE = 15_000
MAX_CHARS_BUNDLE = 200_000

# Per-doc trim cap (contract: full report body, trim if >40K chars)
DOC_TRIM_CHARS = 40_000

# Only consider reports with enough body to be a meaningful Doc on its
# own (otherwise a 3-doc bundle won't clear 15K chars in the worst case).
MIN_DOC_CHARS = 5_000
# Don't pre-filter very long reports (we trim per-doc); cap on raw body
# scan window is fine.
MAX_DOC_RAW_CHARS = 300_000

SPLIT = "train"
DATASET_ID = "ccdv/govreport-summarization"

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "govreport.json"


# ── Policy-area keyword dictionary ────────────────────────────────────
#
# Hand-picked terms for common GAO / CRS report topics. Each list is
# matched word-boundary, case-insensitive against the first ~4K chars
# of each report (title + intro region). Counts are summed; the area
# with the highest count "wins" that report. Ties → first-listed wins,
# which biases toward larger / better-represented areas — fine for
# clustering purposes.
POLICY_KEYWORDS: Dict[str, List[str]] = {
    "defense": [
        "defense", "military", "dod", "armed forces", "nato", "army",
        "navy", "marine corps", "air force", "weapon", "combat",
        "soldier", "veteran", "pentagon", "warfighter",
    ],
    "health": [
        "health", "medicare", "medicaid", "fda", "drug", "drugs",
        "hospital", "cdc", "patient", "medical", "physician", "nih",
        "disease", "vaccine", "clinical", "healthcare",
    ],
    "energy": [
        "energy", "oil", "gas", "renewable", "electricity", "nuclear",
        "emissions", "epa", "coal", "solar", "wind power", "pipeline",
        "petroleum", "grid", "utility",
    ],
    "economy": [
        "tax", "gdp", "inflation", "fiscal", "monetary", "treasury",
        "budget", "deficit", "irs", "revenue", "federal spending",
        "appropriation", "deficit", "debt", "bond",
    ],
    "education": [
        "education", "school", "schools", "student", "students",
        "teacher", "teachers", "idea", "ed.d", "department of education",
        "k-12", "title i", "pell grant", "college", "university",
    ],
    "immigration": [
        "immigration", "border", "asylum", "visa", "dhs", "ice",
        "customs", "immigrant", "refugee", "naturalization",
        "deportation", "uscis",
    ],
    "agriculture": [
        "agriculture", "farm", "farmer", "usda", "food", "crop",
        "crops", "livestock", "dairy", "agricultural", "snap",
    ],
    "transportation": [
        "transportation", "highway", "faa", "transit", "aviation",
        "airport", "rail", "amtrak", "dot", "fhwa", "ferry",
        "trucking",
    ],
    "housing": [
        "housing", "hud", "mortgage", "homelessness", "rental",
        "tenant", "landlord", "fha", "fannie mae", "freddie mac",
    ],
    "tech": [
        "cybersecurity", "cyber", "artificial intelligence", "ai ",
        "data", "internet", "fcc", "nist", "software", "computer",
        "network security", "encryption", "digital",
    ],
    "environment": [
        "environment", "environmental", "climate", "pollution",
        "wildlife", "endangered", "wetland", "national park", "forest",
        "epa", "conservation",
    ],
    "social": [
        "social security", "ssa", "disability", "welfare", "poverty",
        "tanf", "child welfare", "foster care", "elderly", "retirement",
    ],
    "justice": [
        "doj", "fbi", "prison", "prisoner", "criminal", "law enforcement",
        "court", "judicial", "drug enforcement", "dea", "atf",
    ],
}

# Compile regex per keyword (word-bounded, case-insensitive).
_KW_PATTERNS: Dict[str, List[re.Pattern]] = {
    area: [re.compile(rf"\b{re.escape(kw.strip())}\b", re.IGNORECASE)
           for kw in kws]
    for area, kws in POLICY_KEYWORDS.items()
}


def classify_policy_area(report_text: str) -> Tuple[str, int]:
    """Return (best_area, score). `general` if no area scores ≥2."""
    head = report_text[:4_000].lower()
    scores: Dict[str, int] = {}
    for area, pats in _KW_PATTERNS.items():
        hits = 0
        for p in pats:
            # Cap per-pattern contribution to avoid one repeated word
            # dominating (e.g. "tax" in a budget doc).
            hits += min(5, len(p.findall(head)))
        if hits:
            scores[area] = hits

    if not scores:
        return "general", 0

    best_area = max(scores, key=lambda a: scores[a])
    best_score = scores[best_area]
    if best_score < 2:
        return "general", best_score
    return best_area, best_score


def derive_title(report_text: str) -> str:
    """Title heuristic — first complete sentence (up to 140 chars), since
    GovReport rows don't carry a title field."""
    head = report_text[:600].strip()
    # First sentence ends at `. ` followed by capital, or hard line break.
    m = re.search(r"[\.\?\!]\s+(?=[A-Z])", head)
    if m:
        sent = head[: m.start() + 1]
    else:
        sent = head[:200]
    sent = re.sub(r"\s+", " ", sent).strip()
    return sent[:160] if sent else "GovReport"


def _build_doc(idx_in_bundle: int, bundle_idx: int, row_idx: int,
               report_text: str) -> Doc:
    title = derive_title(report_text)
    body = report_text.strip()
    if len(body) > DOC_TRIM_CHARS:
        # Trim on a sentence boundary near the cap, if possible.
        cut = body.rfind(". ", 0, DOC_TRIM_CHARS)
        if cut < DOC_TRIM_CHARS - 2_000:  # no good boundary — hard cut
            cut = DOC_TRIM_CHARS
        else:
            cut += 1
        body = body[:cut]
    return Doc(
        doc_id=f"govreport_{bundle_idx:02d}_{idx_in_bundle}_row{row_idx}",
        title=title,
        content=body,
        page_id=None,
    )


def _pack_bundle_docs(area_reports: List[Tuple[int, str]],
                      rng: random.Random) -> List[List[Tuple[int, str]]]:
    """Group reports within an area into bundles of size MIN_DOCS..MAX_DOCS
    while respecting the per-bundle char budget. Greedy, shuffle-then-pack."""
    rng.shuffle(area_reports)
    bundles: List[List[Tuple[int, str]]] = []
    current: List[Tuple[int, str]] = []
    current_chars = 0

    def doc_chars(text: str) -> int:
        return min(len(text), DOC_TRIM_CHARS)

    for row_idx, text in area_reports:
        dc = doc_chars(text)
        # If adding this doc would overflow and we already have ≥MIN_DOCS,
        # close out the current bundle and start a new one.
        if (current_chars + dc > MAX_CHARS_BUNDLE and len(current) >= MIN_DOCS):
            bundles.append(current)
            current = []
            current_chars = 0

        current.append((row_idx, text))
        current_chars += dc

        # Soft-close when at MAX_DOCS regardless of char budget.
        if len(current) >= MAX_DOCS:
            bundles.append(current)
            current = []
            current_chars = 0

    # Tail: keep only if it satisfies MIN_DOCS and MIN_CHARS.
    if len(current) >= MIN_DOCS and current_chars >= MIN_CHARS_BUNDLE:
        bundles.append(current)

    # Filter any bundle that doesn't meet the MIN_CHARS_BUNDLE floor.
    bundles = [b for b in bundles
               if sum(doc_chars(t) for _, t in b) >= MIN_CHARS_BUNDLE]
    return bundles


def load_govreport(
    n_bundles: int = N_BUNDLES,
    split: str = SPLIT,
    seed: int = SEED,
) -> List[Bundle]:
    print(f"[govreport] loading dataset {DATASET_ID} split={split}…")
    ds = load_dataset(DATASET_ID, split=split, trust_remote_code=True)
    print(f"[govreport] dataset rows: {len(ds)}")

    # Stage 1: length-filter + classify each report.
    # We iterate the whole train split since we need broad coverage to
    # find clusters of size ≥3 in each policy area.
    by_area: Dict[str, List[Tuple[int, str]]] = defaultdict(list)
    total_scanned = 0
    total_kept = 0
    for i, row in enumerate(ds):
        text = row.get("report") or ""
        if not isinstance(text, str):
            continue
        total_scanned += 1
        if not (MIN_DOC_CHARS <= len(text) <= MAX_DOC_RAW_CHARS):
            continue
        area, _ = classify_policy_area(text)
        by_area[area].append((i, text))
        total_kept += 1

    area_counts = Counter({a: len(v) for a, v in by_area.items()})
    print(f"[govreport] scanned={total_scanned}, kept={total_kept}, "
          f"areas={len(by_area)}")
    print(f"[govreport] area distribution: {area_counts.most_common()}")

    # Stage 2: pack each area into bundles. Deterministic order by area
    # name so the shuffle within each area is reproducible.
    rng = random.Random(seed)
    candidate_bundles: List[Tuple[str, List[Tuple[int, str]]]] = []

    # Process well-populated areas first (≥3 reports), then absorb tail
    # via `general` merge.
    sorted_areas = sorted(by_area.keys())
    for area in sorted_areas:
        if area == "general":
            continue
        reports = by_area[area]
        if len(reports) < MIN_DOCS:
            # Too small to form even one bundle on its own → spill into
            # `general` for later merge.
            by_area["general"].extend(reports)
            continue
        sub_rng = random.Random(seed + hash(area) % 10_000)
        for grp in _pack_bundle_docs(list(reports), sub_rng):
            candidate_bundles.append((area, grp))

    # Now process the `general` pool the same way (it may now include
    # spillover from underpopulated areas).
    if by_area.get("general"):
        sub_rng = random.Random(seed + 1)
        for grp in _pack_bundle_docs(list(by_area["general"]), sub_rng):
            candidate_bundles.append(("general", grp))

    # Stage 3: shuffle candidate bundles (so output isn't all defense
    # first) and take the first n_bundles. Use the main rng.
    rng.shuffle(candidate_bundles)
    if len(candidate_bundles) < n_bundles:
        print(f"[govreport] WARNING: only {len(candidate_bundles)} candidate "
              f"bundles formed, need {n_bundles}")

    bundles: List[Bundle] = []
    skipped_invalid = 0
    for bundle_idx, (area, grp) in enumerate(candidate_bundles):
        if len(bundles) >= n_bundles:
            break

        docs: List[Doc] = []
        report_ids: List[str] = []
        for j, (row_idx, text) in enumerate(grp):
            d = _build_doc(idx_in_bundle=j, bundle_idx=len(bundles),
                           row_idx=row_idx, report_text=text)
            docs.append(d)
            report_ids.append(f"row_{row_idx}")

        b = Bundle(
            bundle_id=f"govreport_{len(bundles):02d}",
            source="govreport",
            docs=docs,
            metadata={
                "language": "en",
                "bridge_entity": area,
                "policy_area": area,
                "report_ids": report_ids,
            },
        )
        errs = validate_bundle(b, min_docs=MIN_DOCS,
                               min_chars=MIN_CHARS_BUNDLE,
                               max_chars=MAX_CHARS_BUNDLE)
        if errs:
            skipped_invalid += 1
            print(f"[govreport] SKIP {b.bundle_id} (area={area}): {errs}")
            continue
        bundles.append(b)

    print(f"[govreport] produced {len(bundles)} bundles "
          f"(skipped {skipped_invalid} invalid)")
    # Brief area distribution of the final selection
    final_areas = Counter(b.metadata["policy_area"] for b in bundles)
    print(f"[govreport] final area distribution: {final_areas.most_common()}")
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-bundles", type=int, default=N_BUNDLES)
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    bundles = load_govreport(n_bundles=args.n_bundles)
    if not bundles:
        print("[govreport] no bundles produced — aborting write")
        return 2

    # Final validation pass — contract gate.
    all_errs: List[str] = []
    for b in bundles:
        all_errs.extend(validate_bundle(b, min_docs=MIN_DOCS,
                                        min_chars=MIN_CHARS_BUNDLE,
                                        max_chars=MAX_CHARS_BUNDLE))
    if all_errs:
        print(f"[govreport] VALIDATION FAILURES ({len(all_errs)}):")
        for e in all_errs[:20]:
            print(f"  - {e}")
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_bundles_json(bundles, str(out))
    print(f"[govreport] wrote {len(bundles)} bundles → {out}")
    for b in bundles:
        print(f"  {b.bundle_id}: docs={len(b.docs)}, "
              f"chars={b.total_chars()}, "
              f"area={b.metadata['policy_area']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
