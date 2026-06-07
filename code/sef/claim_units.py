"""Claim-unit decomposition — v0.4.3 plan §3.5 (sec:sef-build) step (b).

Per the spec: spaCy NER (person/org/money/date) + regex for number-unit-time
patterns. A sentence whose tokens combine "value + unit + time anchor" becomes
one claim_unit. claim_type is assigned by deterministic keyword rules:

  numeric_value  — a single value (+unit/+time)
  numeric_trend  — trend keyword (increase/decrease/rise/fall/...) + >=2 values
  ranking        — ranking keyword (highest/lowest/top/Nth/...)
  categorical    — >=2 comparable values sharing a unit
  temporal_event — only a time anchor, no value

No LLM. Entity canonicalization (step c) is applied here via an injected
synonym map; numeric/time normalization (step d) delegates to normalize.py.
"""
from __future__ import annotations

import re
from typing import Optional

from .normalize import normalize_numeric, normalize_time, NumericValue
from .schema import ClaimUnit, Entity, Value, TimeRef

_NLP = None

# LaTeX / markup noise that must be removed before NER + numeric scanning,
# else equation labels (60H10), inline math ($\mathscr{P}$), and \commands
# manufacture spurious claims and mislabeled entities.
_DISPLAY_MATH = re.compile(r"\$\$.*?\$\$|\\begin\{[^}]*\}.*?\\end\{[^}]*\}", re.DOTALL)
# inline math: $...$ ONLY when the span carries a LaTeX char (\ { } ^ _). This
# avoids eating currency: "$100M to $150M" has no LaTeX char between the $ and
# must survive as two USD figures, while "$\mathscr{P}$" is stripped.
_INLINE_MATH = re.compile(r"\$(?=[^$]*[\\{}^_])[^$]+\$")
_LATEX_CMD = re.compile(r"\\[a-zA-Z]+\*?(?:\{[^}]*\})?|\\[^a-zA-Z]")
_HTML_TAG = re.compile(r"<[^>]+>")
# bibliographic / classification noise: "60H10, 60B05", "10.1234/x"
_MSC_CODE = re.compile(r"\b\d{2}[A-Z]\d{2}\b")
# inline academic citations: "Stent et al. (2005)", "(Young, 2013)",
# "Cheyer and Guzzoni (2007)", "Wen et al., 2015". The author+year grammar is
# distinct from real events; the year (19xx/20xx) is the discriminator. Left in,
# they manufacture temporal_event noise in every science paper.
_INLINE_CITE = re.compile(
    r"\(?\b[A-Z][A-Za-z.'’-]+"
    r"(?:\s+(?:et\s+al\.?|and\s+[A-Z][A-Za-z.'’-]+|&\s+[A-Z][A-Za-z.'’-]+))?"
    r",?\s*\(?(?:19|20)\d{2}[a-z]?\)?\)?")


def _clean_text(text: str) -> str:
    """Strip LaTeX math, commands, HTML, and inline citations before analysis."""
    t = _DISPLAY_MATH.sub(" ", text or "")
    t = _INLINE_MATH.sub(" ", t)
    t = _LATEX_CMD.sub(" ", t)
    t = _HTML_TAG.sub(" ", t)
    t = _MSC_CODE.sub(" ", t)
    t = _INLINE_CITE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def _nlp():
    """Lazy spaCy load (en_core_web_sm). Disabled components kept minimal."""
    global _NLP
    if _NLP is None:
        import spacy
        # need parser for sentence boundaries + ner for entities
        _NLP = spacy.load("en_core_web_sm", disable=["lemmatizer"])
    return _NLP


# entity labels we keep (map spaCy -> SEF entity type)
_KEEP_ENT = {
    "PERSON": "person", "ORG": "organization", "GPE": "location",
    "MONEY": "money", "DATE": "date", "TIME": "date", "PERCENT": "percent",
    "QUANTITY": "quantity", "CARDINAL": "number", "PRODUCT": "product",
}

_TREND_KW = re.compile(
    r"\b(increas|decreas|ris(?:e|ing|en)|fell|fall|grow|grew|declin|"
    r"surg|drop|jump|expand|shrink|up\b|down\b|higher|lower|"
    r"증가|감소|상승|하락|성장)\w*", re.IGNORECASE)
_RANK_KW = re.compile(
    r"\b(highest|lowest|largest|smallest|top|bottom|leading|"
    r"\d+(?:st|nd|rd|th)\b|rank(?:ed|ing)?|first|second|third|"
    r"최고|최저|최대|최소|\d+위|순위)\w*", re.IGNORECASE)

# all numeric mentions in a sentence (re-use normalize core). Magnitude letters
# attached; word magnitudes space-separated — mirrors normalize._NUMERIC_RE.
_NUM_SCAN = re.compile(
    r"[$€£¥₩]?\s*(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:(?:k|m|mn|b|bn|t|tn)\b|\s+(?:thousand|million|billion|trillion))?\s*%?",
    re.IGNORECASE)


def _scan_values(sentence: str) -> list[NumericValue]:
    out: list[NumericValue] = []
    for m in _NUM_SCAN.finditer(sentence):
        frag = m.group(0).strip()
        if not frag or not re.search(r"\d", frag):
            continue
        nv = normalize_numeric(frag)
        if nv is not None:
            out.append(nv)
    return out


def _classify(sentence: str, values: list[NumericValue],
              time_anchor: Optional[TimeRef]) -> Optional[str]:
    """Return claim_type, or None if the sentence carries no real claim.

    Precision over recall: a bare integer (equation ref, code, page number)
    must not become a claim. A value counts toward a numeric claim only when it
    is *salient* (currency/%/magnitude word) or co-occurs with a time anchor,
    or the sentence has an explicit ranking/trend cue.
    """
    salient = [v for v in values if v.salient]
    if _RANK_KW.search(sentence) and (salient or (values and time_anchor)):
        return "ranking"
    if _TREND_KW.search(sentence) and len(values) >= 2:
        return "numeric_trend"
    if len(salient) >= 2:
        units = {v.unit for v in salient if v.unit}
        if len(units) <= 1:
            return "categorical"
    if salient:
        return "numeric_value"
    if time_anchor is not None:
        return "temporal_event"
    return None


def extract_claim_units(text: str, *, bid: str, section_path: str = "",
                        synonyms: Optional[dict[str, str]] = None,
                        ) -> list[ClaimUnit]:
    """Decompose a text block into claim_units. cuid = f"{bid}#c{n}"."""
    syn = {k.lower(): v for k, v in (synonyms or {}).items()}
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    doc = _nlp()(cleaned)
    units: list[ClaimUnit] = []
    n = 0
    for sent in doc.sents:
        s = sent.text.strip()
        if not s:
            continue
        values = _scan_values(s)
        ta = normalize_time(s)
        ents: list[Entity] = []
        for ent in sent.ents:
            etype = _KEEP_ENT.get(ent.label_)
            if etype is None:
                continue
            surf = ent.text.strip()
            ents.append(Entity(
                surface=surf,
                canonical=syn.get(surf.lower()),
                type=etype,
            ))
        ctype = _classify(s, values, ta)
        # bare temporal_event needs an entity subject, else it is date noise
        # (affiliation dates, "Received July 26, 2022").
        if ctype == "temporal_event" and not ents:
            ctype = None
        if ctype is None:
            continue
        n += 1
        units.append(ClaimUnit(
            cuid=f"{bid}#c{n}",
            claim_text=s,
            claim_type=ctype,
            entities=ents,
            values=[Value(v.raw, v.normalized_value, v.unit) for v in values],
            time_anchors=[ta] if ta else [],
            section_path=section_path,
        ))
    return units
