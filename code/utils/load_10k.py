"""10-K loader → 5 source-internal multi-doc Bundles.

Per PAPER_MASTER_SPEC §5.1:
  - 5 SP500 tickers
  - Item 7 (MD&A) and Item 7A (Quantitative & Qualitative Risk) become 2 Docs
  - Item 7 truncated to 15K chars, Item 7A to 5K chars

The SEC EDGAR fetch uses `sec_edgar_downloader`. Raw filings land under
`data/prototype/sources/raw/10k_raw/` (gitignored). The bundle JSON contains
only the parsed text excerpts.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sec_edgar_downloader import Downloader
from selectolax.parser import HTMLParser

from code.pipelines.base import Bundle, Doc
from code.utils.bundle_io import validate_bundle, write_bundles_json


N_BUNDLES = 5
TICKERS = ["AAPL", "MSFT", "TSLA", "NVDA", "META"]
ITEM7_CAP = 15_000
ITEM7A_CAP = 5_000

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "prototype" / "sources" / "raw" / "10k_raw"
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "10k.json"

ITEM7_HEAD = re.compile(
    r"Item\s*7[.\s\xa0]+Management['’s]*\s*Discussion",
    re.IGNORECASE,
)
ITEM7A_HEAD = re.compile(
    r"Item\s*7A[.\s\xa0]+Quantitative",
    re.IGNORECASE,
)
ITEM8_HEAD = re.compile(
    r"Item\s*8[.\s\xa0]+(?:Financial|Consolidated|Index)",
    re.IGNORECASE,
)
WS_RE = re.compile(r"[ \t\xa0]+")
MULTILINE_RE = re.compile(r"\n{3,}")


def _flatten_text(s: str) -> str:
    s = WS_RE.sub(" ", s)
    s = MULTILINE_RE.sub("\n\n", s)
    return s.strip()


def _largest_section(text: str, start_re: re.Pattern, end_re: re.Pattern) -> str:
    """Return the longest substring of `text` that begins at any match of
    start_re and ends at the next match of end_re. Trims whitespace.

    Filings repeat section headers in the TOC and forward-looking references;
    the actual section is always the largest captured run.
    """
    starts = [m.start() for m in start_re.finditer(text)]
    if not starts:
        return ""
    ends = [m.start() for m in end_re.finditer(text)]
    best = ""
    for s_pos in starts:
        # Find the smallest end-position strictly greater than s_pos.
        candidates = [e for e in ends if e > s_pos]
        if not candidates:
            continue
        e_pos = min(candidates)
        chunk = _flatten_text(text[s_pos:e_pos])
        if len(chunk) > len(best):
            best = chunk
    return best


def _extract_items(text: str) -> Tuple[str, str]:
    item7 = _largest_section(text, ITEM7_HEAD, ITEM7A_HEAD)[:ITEM7_CAP]
    item7a = _largest_section(text, ITEM7A_HEAD, ITEM8_HEAD)[:ITEM7A_CAP]
    return item7, item7a


def _read_filing_text(filing_path: Path) -> str:
    raw = filing_path.read_text(encoding="utf-8", errors="ignore")
    # The full-submission.txt typically embeds the 10-K HTML; let
    # selectolax extract visible text. Fallback to raw text on failure.
    try:
        tree = HTMLParser(raw)
        text = tree.text(separator="\n")
        if len(text) >= 1000:
            return text
    except Exception:
        pass
    return raw


def _ensure_filing(ticker: str) -> Path | None:
    """Ensure the latest 10-K is downloaded; return path to its text/HTML."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dl = Downloader(
        company_name="docviz-research",
        email_address=os.environ.get("DOCVIZ_EDGAR_EMAIL", "researcher@example.com"),
        download_folder=str(RAW_DIR),
    )
    try:
        dl.get("10-K", ticker, limit=1, after="2024-01-01")
    except Exception as e:
        print(f"  [{ticker}] download failed: {type(e).__name__}: {e}")
        return None

    base = RAW_DIR / "sec-edgar-filings" / ticker / "10-K"
    if not base.is_dir():
        return None
    candidates = sorted(base.iterdir(), reverse=True)
    if not candidates:
        return None
    folder = candidates[0]
    for fn in ("primary-document.html", "full-submission.txt"):
        path = folder / fn
        if path.exists():
            return path
    htmls = list(folder.glob("*.htm")) + list(folder.glob("*.html"))
    return htmls[0] if htmls else None


def _build_bundle(idx: int, ticker: str, item7: str, item7a: str) -> Bundle:
    docs: List[Doc] = []
    if item7:
        docs.append(Doc(
            doc_id=f"10k_{idx:02d}_mda",
            title=f"{ticker} 10-K Item 7 (MD&A)",
            content=item7,
            page_id="item7",
        ))
    if item7a:
        docs.append(Doc(
            doc_id=f"10k_{idx:02d}_risk",
            title=f"{ticker} 10-K Item 7A (Quantitative & Qualitative Risk)",
            content=item7a,
            page_id="item7a",
        ))
    return Bundle(
        bundle_id=f"10k_{idx:02d}",
        source="10k",
        docs=docs,
        metadata={
            "language": "en",
            "ticker": ticker,
            "item7_chars": len(item7),
            "item7a_chars": len(item7a),
        },
    )


def build_bundles() -> List[Bundle]:
    bundles: List[Bundle] = []
    for idx, ticker in enumerate(TICKERS):
        if idx >= N_BUNDLES:
            break
        print(f"[10k] {ticker}: ensuring filing…")
        path = _ensure_filing(ticker)
        if path is None:
            print(f"  [{ticker}] no filing found; skipping")
            continue
        text = _read_filing_text(path)
        item7, item7a = _extract_items(text)
        if not item7 or not item7a:
            print(f"  [{ticker}] item extraction incomplete: "
                  f"item7={len(item7)} item7a={len(item7a)}")
            continue
        bundles.append(_build_bundle(idx, ticker, item7, item7a))
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser(description="Build 10-K bundles.")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    bundles = build_bundles()
    errors: List[str] = []
    for b in bundles:
        errors.extend(validate_bundle(b))
    if errors:
        print("  [VALIDATION ERRORS]")
        for e in errors:
            print(f"    {e}")
        # Don't hard-fail on validation: 10-K parsing is fragile, surface
        # warnings and let merge step decide.
    write_bundles_json(bundles, args.out)
    print(f"[10k] wrote {len(bundles)} bundles → {args.out}")
    for b in bundles:
        print(f"    {b.bundle_id} ({b.metadata['ticker']}): docs={len(b.docs)}, "
              f"chars={b.total_chars()}")
    return 0 if bundles else 2


if __name__ == "__main__":
    sys.exit(main())
