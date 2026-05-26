"""10-K loader → 50 cross-document multi-company bundles (LOADER_CONTRACT_v04).

Each bundle = 3 SP500 companies in the *same GICS sector*. Each Doc is the
Item 7 (MD&A) section of one company's most-recent 10-K, parsed via
selectolax DOM (no regex item-extraction on the full 60MB filing).

Pipeline:
  1. Fetch / cache the SP500 ticker → GICS sector list (Wikipedia table).
  2. For each sector, walk tickers in deterministic (seeded) order:
      a. Ensure the latest 10-K is cached locally; fetch via
         sec_edgar_downloader (parallel pool) when not.
      b. Extract Item 7 from the filing using selectolax (see
         `_extract_item7`).
      c. Trim to DOC_CHAR_CAP; keep tickers whose Item 7 cleared
         MIN_DOC_CHARS. Skip tickers with "incorporated by reference"
         Item 7 (e.g. WFC, INTC) — no text content in the filing itself.
  3. Group accepted tickers per sector into bundles of 3. Stop at
     N_BUNDLES = 50. Random seed = 42.

selectolax usage:
  - SEC `full-submission.txt` is a SGML/multipart wrapper around the
    actual 10-K HTML. We isolate the first `<DOCUMENT><TYPE>10-K …
    <TEXT>…</TEXT></DOCUMENT>` block (typically 0.4–13 MB) before
    handing it to `HTMLParser`. Parsing the full 60 MB raw file stalls
    selectolax (>60 s on WFC/BAC/JPM) — extracting the embedded HTML
    first brings it to 0.1–14 s.
  - Item 7 / Item 7A / Item 8 boundaries are detected on the
    *whitespace-collapsed plain text* returned by
    `tree.text(separator=" ")`. We pick the *largest* span between the
    first Item 7 heading and the next Item 7A (or Item 8) heading —
    filings repeat headings in the TOC, but only the actual section
    yields a multi-KB chunk.

Output bundle.metadata fields (per LOADER_CONTRACT_v04 §Bundle.metadata):
  - language: "en"
  - bridge_entity: gics_sector
  - gics_sector: e.g. "Information Technology"
  - tickers: ["AAPL", "MSFT", "NVDA"]
  - filing_dates: ["2025-…", …]   (parsed from accession-number path)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from selectolax.parser import HTMLParser  # noqa: E402

from code.pipelines.base import Bundle, Doc  # noqa: E402
from code.utils.bundle_io import validate_bundle, write_bundles_json  # noqa: E402

# ── Contract knobs ────────────────────────────────────────────────────────
N_BUNDLES = 50
TICKERS_PER_BUNDLE = 3
DOC_CHAR_CAP = 50_000          # per-Doc cap; 3 × 50K = 150K worst-case
MIN_DOC_CHARS = 5_000          # individual Item 7 must clear this
MIN_BUNDLE_CHARS = 15_000      # contract gate
MAX_BUNDLE_CHARS = 200_000     # contract gate
SEED = 42

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "prototype" / "sources" / "raw" / "10k_raw"
SP500_CACHE = REPO_ROOT / "data" / "prototype" / "sources" / "raw" / "sp500_gics.json"
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "10k.json"

USER_AGENT = (
    "docviz-research/0.1 "
    "contact: " + os.environ.get("DOCVIZ_EDGAR_EMAIL", "pminhyung12@g.skku.edu")
)

# ── Regex: only for boundary detection on already-parsed text ────────────
# (we do NOT regex-walk the 60MB raw filing)
RE_DOC_10K = re.compile(
    r"<DOCUMENT>\s*<TYPE>10-K\b.*?<TEXT>(.*?)</TEXT>", re.S | re.I
)
RE_XBRL_WRAP = re.compile(r"<XBRL>(.*?)</XBRL>", re.S | re.I)
RE_WHITESPACE = re.compile(r"\s+")
RE_ITEM7 = re.compile(r"Item\s*7\.?\s*Management", re.I)
RE_ITEM7A = re.compile(r"Item\s*7A\.?\s*Quantitative", re.I)
RE_ITEM8 = re.compile(r"Item\s*8\.?\s*(?:Financial|Consolidated)", re.I)


# ── SP500 + GICS sector list ─────────────────────────────────────────────
def _fetch_sp500_gics() -> Dict[str, List[str]]:
    """Return {gics_sector: [ticker, ...]}; cached on disk."""
    if SP500_CACHE.exists():
        try:
            return json.loads(SP500_CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="ignore")
    tree = HTMLParser(html)
    rows = tree.css("table.wikitable")[0].css("tr")
    by_sector: Dict[str, List[str]] = defaultdict(list)
    for row in rows[1:]:
        cells = row.css("td")
        if len(cells) < 4:
            continue
        sym = cells[0].text(strip=True).replace(".", "-")  # BRK.B → BRK-B
        sec = cells[2].text(strip=True)
        if sym and sec:
            by_sector[sec].append(sym)
    SP500_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SP500_CACHE.write_text(json.dumps(by_sector, indent=2), encoding="utf-8")
    return dict(by_sector)


# ── Selectolax-based Item 7 extraction ───────────────────────────────────
def _isolate_10k_html(raw: str) -> Optional[str]:
    """Pull the embedded 10-K HTML out of the multi-document SGML wrapper.

    A SEC `full-submission.txt` is structured as:
        <SEC-DOCUMENT>...<SEC-HEADER>...</SEC-HEADER>
        <DOCUMENT><TYPE>10-K<SEQUENCE>1<TEXT>... actual filing ...</TEXT></DOCUMENT>
        <DOCUMENT><TYPE>EX-21<TEXT>...</TEXT></DOCUMENT>
        ...
    We want only the first 10-K DOCUMENT body. This shrinks 60 MB → ~1-13 MB
    and makes selectolax tractable.
    """
    m = RE_DOC_10K.search(raw)
    if not m:
        return None
    body = m.group(1)
    inner = RE_XBRL_WRAP.search(body)
    if inner:
        body = inner.group(1)
    return body.strip()


def _largest_span(text: str, start_pat: re.Pattern,
                  end_pats: List[re.Pattern], min_len: int = 3000) -> str:
    """Return the longest substring beginning at any start_pat hit and ending
    at the next hit of any end_pat. The actual section is always the
    largest captured run; the TOC matches are short.
    """
    starts = [m.start() for m in start_pat.finditer(text)]
    if not starts:
        return ""
    ends = sorted({m.start() for p in end_pats for m in p.finditer(text)})
    best = ""
    for s in starts:
        cands = [e for e in ends if e > s and (e - s) >= min_len]
        if not cands:
            continue
        chunk = text[s:min(cands)].strip()
        if len(chunk) > len(best):
            best = chunk
    return best


def _extract_item7(filing_path: Path) -> str:
    """Parse a SEC full-submission.txt and return the Item 7 plain text.

    Returns '' if the filing incorporates Item 7 by reference (no inline
    MD&A content), or if the body cannot be located.
    """
    raw = filing_path.read_text(encoding="utf-8", errors="ignore")
    body = _isolate_10k_html(raw)
    if body is None:
        return ""
    try:
        tree = HTMLParser(body)
        text = tree.text(separator=" ", strip=True)
    except Exception:
        return ""
    text = RE_WHITESPACE.sub(" ", text)
    # Prefer Item 7 → Item 7A; if too short or absent, fall back to Item 8.
    section = _largest_span(text, RE_ITEM7, [RE_ITEM7A], min_len=3000)
    if len(section) < MIN_DOC_CHARS:
        section = _largest_span(text, RE_ITEM7, [RE_ITEM7A, RE_ITEM8],
                                min_len=3000)
    return section[:DOC_CHAR_CAP]


# ── Filing cache / fetch ────────────────────────────────────────────────
def _cached_filing_path(ticker: str) -> Optional[Path]:
    base = RAW_DIR / "sec-edgar-filings" / ticker / "10-K"
    if not base.is_dir():
        return None
    subdirs = sorted([d for d in base.iterdir() if d.is_dir()], reverse=True)
    for sub in subdirs:
        p = sub / "full-submission.txt"
        if p.exists() and p.stat().st_size > 100_000:
            return p
        # primary-document.html is a viable fallback (no SGML wrapper)
        p = sub / "primary-document.html"
        if p.exists():
            return p
    return None


def _fetch_filing(ticker: str) -> Optional[Path]:
    """Download the latest 10-K for `ticker`. Returns the filing path."""
    cached = _cached_filing_path(ticker)
    if cached:
        return cached
    try:
        from sec_edgar_downloader import Downloader
    except ImportError:
        return None
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dl = Downloader(
        company_name="docviz-research",
        email_address=os.environ.get(
            "DOCVIZ_EDGAR_EMAIL", "pminhyung12@g.skku.edu"),
        download_folder=str(RAW_DIR),
    )
    try:
        # most-recent 10-K, no after-date filter so we always get one
        dl.get("10-K", ticker, limit=1, download_details=False)
    except Exception as e:
        print(f"  [{ticker}] download failed: {type(e).__name__}: {e}",
              file=sys.stderr)
        return None
    return _cached_filing_path(ticker)


def _process_ticker(ticker: str) -> Tuple[str, str, Optional[str]]:
    """Return (ticker, item7_text, filing_date). item7_text='' on failure.

    filing_date is parsed from the accession-number directory name.
    """
    path = _fetch_filing(ticker)
    if path is None:
        return ticker, "", None
    try:
        item7 = _extract_item7(path)
    except Exception as e:
        print(f"  [{ticker}] extract failed: {type(e).__name__}: {e}",
              file=sys.stderr)
        return ticker, "", None
    # accession dir name looks like "0000320193-25-000079"; the middle
    # two digits are the YY filing year — informational only.
    filing_date = path.parent.name
    return ticker, item7, filing_date


# ── Bundle assembly ─────────────────────────────────────────────────────
def _make_bundle(idx: int, sector: str, tickers: List[str],
                 item7_by_ticker: Dict[str, str],
                 date_by_ticker: Dict[str, str]) -> Bundle:
    docs: List[Doc] = []
    for j, tk in enumerate(tickers):
        docs.append(Doc(
            doc_id=f"10k_{idx:02d}_{j:02d}_{tk}",
            title=f"{tk} 10-K Item 7 — Management's Discussion & Analysis",
            content=item7_by_ticker[tk],
            page_id="item7",
        ))
    return Bundle(
        bundle_id=f"10k_{idx:02d}",
        source="10k",
        docs=docs,
        metadata={
            "language": "en",
            "bridge_entity": sector,
            "gics_sector": sector,
            "tickers": list(tickers),
            "filing_dates": [date_by_ticker.get(tk, "") for tk in tickers],
            "n_docs": len(tickers),
        },
    )


def _select_tickers(sp500: Dict[str, List[str]], rng: random.Random,
                    max_fetch_per_sector: int = 30) -> Dict[str, List[str]]:
    """Per sector, return a deterministic shuffle of tickers — caller decides
    how many to actually fetch/process. We cap how many we try per sector
    so a single sector with many failing tickers doesn't block the run.
    """
    out: Dict[str, List[str]] = {}
    for sector, tickers in sp500.items():
        shuffled = list(tickers)
        rng.shuffle(shuffled)
        out[sector] = shuffled[:max_fetch_per_sector]
    return out


def build_bundles() -> List[Bundle]:
    rng = random.Random(SEED)
    sp500 = _fetch_sp500_gics()
    print(f"[10k] SP500 sectors: {len(sp500)}, "
          f"total tickers: {sum(len(v) for v in sp500.values())}")

    # Plan: each sector contributes up to ceil(50/11) = 5 bundles = 15 tickers.
    # We try up to 24 tickers/sector to absorb ~40% extraction failures
    # (incorporated-by-reference is common in Financials/Utilities).
    target_bundles_per_sector = max(
        TICKERS_PER_BUNDLE,
        (N_BUNDLES + len(sp500) - 1) // len(sp500),
    )
    candidates_per_sector = max(
        target_bundles_per_sector * TICKERS_PER_BUNDLE * 2,  # 2× over-provision
        TICKERS_PER_BUNDLE * 3,
    )
    selected = _select_tickers(sp500, rng,
                               max_fetch_per_sector=candidates_per_sector)

    # Flatten the per-sector candidate lists and parallel-process them.
    # Cached tickers complete instantly; uncached ones hit EDGAR (10 req/s
    # default limit — keep workers ≤ 5 to stay polite).
    flat = [(s, t) for s, ts in selected.items() for t in ts]
    print(f"[10k] candidate tickers: {len(flat)} "
          f"(target ≥{N_BUNDLES * TICKERS_PER_BUNDLE} successful)")
    t_start = time.time()

    item7_by_ticker: Dict[str, str] = {}
    date_by_ticker: Dict[str, str] = {}
    n_cache_hits = 0
    n_cache_miss = 0
    n_extract_ok = 0
    n_extract_fail = 0

    def _job(arg):
        sector, ticker = arg
        cached = _cached_filing_path(ticker) is not None
        return sector, ticker, _process_ticker(ticker), cached

    # Pre-count cache hits to print a quick estimate.
    pre_cached = sum(1 for _, t in flat if _cached_filing_path(t) is not None)
    print(f"[10k] cache hits expected: {pre_cached}/{len(flat)}")

    # Bound EDGAR concurrency. Sequential is fine since the fetcher
    # is already rate-limited; threads still help by overlapping I/O on
    # extraction of cached files vs. fetching of uncached ones.
    by_sector_ok: Dict[str, List[str]] = defaultdict(list)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_job, x): x for x in flat}
        for fut in as_completed(futs):
            sector, ticker, (tk, item7, fdate), was_cached = fut.result()
            if was_cached:
                n_cache_hits += 1
            else:
                n_cache_miss += 1
            if item7 and len(item7) >= MIN_DOC_CHARS:
                item7_by_ticker[tk] = item7
                date_by_ticker[tk] = fdate or ""
                by_sector_ok[sector].append(tk)
                n_extract_ok += 1
            else:
                n_extract_fail += 1
                print(f"  [{tk}] ({sector}) item7={len(item7)} — skip")
            # Early stop: enough sectors have enough tickers
            ready_sectors = sum(
                1 for v in by_sector_ok.values()
                if len(v) >= TICKERS_PER_BUNDLE * target_bundles_per_sector
            )
            # we don't actually cancel futures (selectolax extract is fast);
            # just print progress
            if (n_extract_ok + n_extract_fail) % 25 == 0:
                print(f"  progress: ok={n_extract_ok} fail={n_extract_fail} "
                      f"sectors_ready={ready_sectors}/{len(sp500)} "
                      f"elapsed={time.time()-t_start:.1f}s")

    print(f"[10k] extract done: ok={n_extract_ok} fail={n_extract_fail} "
          f"(cache_hits={n_cache_hits} cache_miss={n_cache_miss}) "
          f"elapsed={time.time()-t_start:.1f}s")

    # Assemble bundles. Round-robin across sectors so we don't pack the
    # first 30 bundles all into Industrials/Financials.
    bundles: List[Bundle] = []
    # Sort sectors deterministically; rng-shuffled per-sector lists are
    # already deterministic.
    sectors = sorted(by_sector_ok.keys())
    sector_cursors: Dict[str, int] = {s: 0 for s in sectors}
    idx = 0
    while idx < N_BUNDLES:
        progress = False
        for sector in sectors:
            tickers = by_sector_ok[sector]
            c = sector_cursors[sector]
            if c + TICKERS_PER_BUNDLE > len(tickers):
                continue
            bundle_tickers = tickers[c:c + TICKERS_PER_BUNDLE]
            sector_cursors[sector] = c + TICKERS_PER_BUNDLE
            # Verify the assembled bundle clears char gate; if a single
            # ticker has < (MIN_BUNDLE_CHARS/3) chars and the sum < min,
            # we still emit it — validate_bundle catches it downstream.
            b = _make_bundle(idx, sector, bundle_tickers,
                             item7_by_ticker, date_by_ticker)
            total = b.total_chars()
            if total < MIN_BUNDLE_CHARS:
                # downgrade Item 7 → not enough text in this triple; skip
                print(f"  [{b.bundle_id}] ({sector}) chars={total} "
                      f"<{MIN_BUNDLE_CHARS} — skipping")
                continue
            if total > MAX_BUNDLE_CHARS:
                # uniformly trim each Doc to fit the cap
                allowance = MAX_BUNDLE_CHARS // TICKERS_PER_BUNDLE
                for d in b.docs:
                    if len(d.content) > allowance:
                        d.content = d.content[:allowance]
            bundles.append(b)
            idx += 1
            progress = True
            if idx >= N_BUNDLES:
                break
        if not progress:
            break  # exhausted all sectors' candidates

    return bundles


def main() -> int:
    ap = argparse.ArgumentParser(description="Build 10-K bundles (v0.4 contract).")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    bundles = build_bundles()

    all_errors: List[str] = []
    for b in bundles:
        errs = validate_bundle(b, min_docs=3, min_chars=MIN_BUNDLE_CHARS,
                               max_chars=MAX_BUNDLE_CHARS)
        all_errors.extend(errs)

    out_path = Path(args.out)
    write_bundles_json(bundles, out_path)
    print(f"\n[10k] wrote {len(bundles)} bundles → {out_path}")
    for b in bundles:
        sec = b.metadata.get("gics_sector", "?")
        tks = ",".join(b.metadata.get("tickers", []))
        print(f"    {b.bundle_id} [{sec}] docs={len(b.docs)} "
              f"chars={b.total_chars()} ({tks})")

    if all_errors:
        print(f"\n[10k] VALIDATION ERRORS ({len(all_errors)}):")
        for e in all_errors[:20]:
            print(f"    {e}")
        return 2
    print("[10k] all bundles passed validate_bundle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
