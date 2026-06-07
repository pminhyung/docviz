"""Deterministic value / unit / time normalization for SEF.

v0.4.3 plan §3.5 (sec:sef-build) steps (c)+(d): convert surface numeric and
temporal mentions to canonical forms so downstream viz-spec generation can
encode them faithfully. No LLM calls — pure rules.

- normalize_numeric("$3.2B")      -> NumericValue(raw="$3.2B", value=3.2e9, unit="USD")
- normalize_numeric("3.2 billion") -> 3.2e9
- normalize_numeric("3,200,000,000")-> 3.2e9
- normalize_time("July 26, 2022") -> "2022-07-26"   (best-effort ISO)

On failure the normalized field is None (surface form preserved by caller),
matching the spec rule "정규화 실패 시 normalized_value = null".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class NumericValue:
    raw: str
    normalized_value: Optional[float]
    unit: Optional[str]
    # salient = carries a currency symbol/word, %, or magnitude word. Bare
    # integers (equation refs, codes, page numbers) are NOT salient and must
    # not, on their own, manufacture a claim_unit.
    salient: bool = False


@dataclass
class TimeAnchor:
    raw: str
    normalized: Optional[str]


# --- magnitude words ------------------------------------------------------
_MAGNITUDE = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "tn": 1e12, "trillion": 1e12,
}

# --- currency / unit symbols ---------------------------------------------
_CURRENCY_SYM = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₩": "KRW"}
_CURRENCY_WORD = {
    "usd": "USD", "dollar": "USD", "dollars": "USD",
    "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
    "jpy": "JPY", "yen": "JPY", "krw": "KRW", "won": "KRW",
}

# number core: 3 / 3.2 / 3,200 / 3,200,000.5
_NUM_CORE = r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[+-]?\d+(?:\.\d+)?"

# full numeric mention: optional currency sym, number, optional magnitude/%/unit.
# Single-letter magnitudes (k/m/b/t/mn/bn/tn) must be ATTACHED (no space) — in
# math/science text "5 t" / "3 m" are variables, not thousands/millions. Word
# magnitudes (million/billion/...) may be space-separated.
_NUMERIC_RE = re.compile(
    r"(?P<sym>[$€£¥₩])?\s*"
    r"(?P<num>" + _NUM_CORE + r")"
    r"(?:(?P<magc>k|m|mn|b|bn|t|tn)\b|\s+(?P<magw>thousand|million|billion|trillion))?\s*"
    r"(?P<pct>%)?"
    r"(?:\s*(?P<word>usd|eur|gbp|jpy|krw|dollars?|euros?|pounds?|yen|won))?",
    re.IGNORECASE,
)


def normalize_numeric(text: str) -> Optional[NumericValue]:
    """Parse the first numeric mention in `text`. Returns None if none found."""
    m = _NUMERIC_RE.search(text or "")
    if not m or not m.group("num"):
        return None
    raw = m.group(0).strip()
    try:
        val = float(m.group("num").replace(",", ""))
    except ValueError:
        return NumericValue(raw=raw, normalized_value=None, unit=None)

    mag = (m.group("magc") or m.group("magw") or "").lower()
    if mag in _MAGNITUDE:
        val *= _MAGNITUDE[mag]

    unit: Optional[str] = None
    if m.group("sym"):
        unit = _CURRENCY_SYM.get(m.group("sym"))
    elif m.group("word"):
        unit = _CURRENCY_WORD.get(m.group("word").lower())
    if m.group("pct"):
        unit = "%"

    salient = bool(m.group("sym") or m.group("word") or m.group("pct") or mag)
    return NumericValue(raw=raw, normalized_value=val, unit=unit, salient=salient)


# --- time normalization ---------------------------------------------------
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_DAY_YEAR = re.compile(
    r"\b(?P<mon>[A-Za-z]{3,9})\.?\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})\b")
_ISO = re.compile(r"\b(?P<year>\d{4})-(?P<mon>\d{2})-(?P<day>\d{2})\b")
_YEAR_ONLY = re.compile(r"\b(?P<year>(?:19|20)\d{2})\b")
_QUARTER = re.compile(r"\b(?P<q>[1-4])Q\s?(?P<year>\d{2,4})\b|\bQ(?P<q2>[1-4])\s?(?P<year2>\d{4})\b")


def normalize_time(text: str) -> Optional[TimeAnchor]:
    """Best-effort ISO normalization of the first date-like mention."""
    t = text or ""
    if (m := _ISO.search(t)):
        return TimeAnchor(raw=m.group(0), normalized=m.group(0))
    if (m := _MONTH_DAY_YEAR.search(t)):
        mon = _MONTHS.get(m.group("mon").lower())
        if mon:
            return TimeAnchor(
                raw=m.group(0),
                normalized=f"{int(m.group('year')):04d}-{mon:02d}-{int(m.group('day')):02d}",
            )
    if (m := _QUARTER.search(t)):
        q = m.group("q") or m.group("q2")
        yr = m.group("year") or m.group("year2")
        if yr and len(yr) == 2:
            yr = "20" + yr
        return TimeAnchor(raw=m.group(0), normalized=f"{yr}-Q{q}")
    if (m := _YEAR_ONLY.search(t)):
        return TimeAnchor(raw=m.group(0), normalized=m.group("year"))
    return None
