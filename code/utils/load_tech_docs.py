"""Technical Docs loader (v0.3 amendment D2.5-D2.8) → 50 multi-doc Bundles.

Sub-source S6-a (default): long Wikipedia technical articles. Per
AMENDMENT_v0.3_ACTION_SPEC.md §3.4:

  - Curated list of 60-80 Wikipedia long technical articles spanning
    ML / networking / databases / OS / cryptography / software arch
  - Download via Wikipedia REST API (`/page/{title}` and section APIs)
  - Group 2-4 contiguous top-level sections per article → 1 bundle
    (alternative grouping: 2-4 related articles per bundle, kept for
    later if S6-a yields too narrow a style)
  - 50 bundles, source="tech_docs", random.seed(42)
  - metadata = {article_title, source_url, sections, topic}

Verification gate D2.8: each bundle has 2-4 docs of plain text and
passes Bundle schema validation.

Bundles use 1 article × 2-4 sections (intra-article multi-doc). This
keeps each bundle thematically coherent — multi-section flow within
one technical topic, mirroring how a user would reference one technical
doc with multiple chapters. Cross-article bundling is the secondary
strategy if intra-article diversity proves insufficient.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("HF_HOME", "/ex_disk2/mhpark/poc/.cache/huggingface")

from code.pipelines.base import Bundle, Doc
from code.utils.bundle_io import validate_bundle, write_bundles_json


SEED = 42
N_BUNDLES = 50
MIN_DOCS = 2
MAX_DOCS = 4
MIN_SECTION_CHARS = 1500       # skip stub sections
BODY_CAP_CHARS = 18_000        # cap per section to keep bundle ≤ 80K total
WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "DocViz-Agent-Research/0.3 (research; contact via repo)"

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "tech_docs.json"


# Curated article titles, chosen for: (a) substantial body length (>20K chars
# typical), (b) clean top-level section structure, (c) topic breadth across
# 6 sub-domains. 60 entries — enough to skip a few stubs and still yield 50.
ARTICLES: List[Tuple[str, str]] = [
    # (article_title, topic_tag)
    # ── ML / AI ───────────────────────────────────────────────────────────
    ("Transformer (deep learning architecture)", "ml"),
    ("Attention (machine learning)",             "ml"),
    ("BERT (language model)",                    "ml"),
    ("Convolutional neural network",             "ml"),
    ("Recurrent neural network",                 "ml"),
    ("Gradient descent",                          "ml"),
    ("Backpropagation",                           "ml"),
    ("Reinforcement learning",                   "ml"),
    ("Generative adversarial network",           "ml"),
    ("Diffusion model",                           "ml"),
    # ── Networking ────────────────────────────────────────────────────────
    ("Transmission Control Protocol",             "net"),
    ("Internet Protocol",                          "net"),
    ("OSI model",                                  "net"),
    ("Hypertext Transfer Protocol",                "net"),
    ("HTTPS",                                       "net"),
    ("Domain Name System",                         "net"),
    ("Border Gateway Protocol",                    "net"),
    ("OAuth",                                       "net"),
    ("OpenID Connect",                              "net"),
    ("Transport Layer Security",                   "net"),
    # ── Databases ─────────────────────────────────────────────────────────
    ("ACID",                                        "db"),
    ("B-tree",                                      "db"),
    ("SQL",                                          "db"),
    ("NoSQL",                                       "db"),
    ("MapReduce",                                  "db"),
    ("Multiversion concurrency control",            "db"),
    ("Entity–relationship model",                  "db"),
    ("Database normalization",                      "db"),
    ("CAP theorem",                                 "db"),
    ("Shard (database architecture)",              "db"),
    # ── Operating systems ────────────────────────────────────────────────
    ("Process (computing)",                         "os"),
    ("Thread (computing)",                          "os"),
    ("Mutex",                                       "os"),
    ("Semaphore (programming)",                     "os"),
    ("Page replacement algorithm",                  "os"),
    ("Virtual memory",                              "os"),
    ("File system",                                 "os"),
    ("Linux kernel",                                "os"),
    ("Kubernetes",                                  "os"),
    ("Container (computing)",                       "os"),
    # ── Cryptography ─────────────────────────────────────────────────────
    ("Advanced Encryption Standard",                "crypto"),
    ("RSA cryptosystem",                            "crypto"),
    ("SHA-2",                                       "crypto"),
    ("Diffie–Hellman key exchange",                 "crypto"),
    ("Public-key cryptography",                     "crypto"),
    ("Cryptographic hash function",                 "crypto"),
    ("Digital signature",                           "crypto"),
    ("Elliptic-curve cryptography",                 "crypto"),
    ("Block cipher",                                "crypto"),
    ("Zero-knowledge proof",                        "crypto"),
    # ── Software architecture ────────────────────────────────────────────
    ("Microservices",                               "swa"),
    ("Representational state transfer",             "swa"),
    ("Model–view–controller",                       "swa"),
    ("Event sourcing",                              "swa"),
    ("Publish–subscribe pattern",                   "swa"),
    ("Service mesh",                                "swa"),
    ("API gateway",                                 "swa"),
    ("Command Query Responsibility Segregation",    "swa"),
    ("Domain-driven design",                        "swa"),
    ("Saga (computer science)",                     "swa"),
]


# ── Wikipedia API client ────────────────────────────────────────────────────

def _fetch_parse(
    title: str,
    client: httpx.Client,
    max_retries: int = 5,
) -> Optional[Dict]:
    """Call MediaWiki parse API for a given page title with 429 backoff.

    Returns the parsed `{sections, text}` dict, or None on persistent failure.
    """
    params = {
        "action": "parse",
        "page": title,
        "format": "json",
        "prop": "sections|wikitext",
        "redirects": "1",
    }
    backoff = 4.0
    for attempt in range(max_retries):
        try:
            resp = client.get(WIKI_API, params=params, timeout=30.0)
            if resp.status_code == 429:
                # Honor Retry-After when present; otherwise exponential backoff
                ra = resp.headers.get("Retry-After")
                wait = float(ra) if ra and ra.replace(".", "").isdigit() else backoff
                print(f"  [429] {title!r}: sleeping {wait:.0f}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                backoff = min(backoff * 2.0, 60.0)
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  [warn] fetch failed for {title!r}: {e}")
            if attempt + 1 < max_retries:
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 60.0)
                continue
            return None
        parse = data.get("parse")
        if not parse:
            err = data.get("error", {}).get("info", "unknown")
            print(f"  [warn] no parse data for {title!r}: {err}")
            return None
        return parse
    print(f"  [give up] {title!r} after {max_retries} retries")
    return None


def _strip_wikitext(text: str) -> str:
    """Best-effort wikitext → plain-text conversion.

    Handles the most common Wikipedia markup: links, templates, comments,
    HTML tags, references, files, formatting. This is not a full
    wikitext parser — full parsing would require mwparserfromhell, but
    for retrieval-context purposes a coarse strip is sufficient.
    """
    t = text
    # Strip HTML comments
    t = re.sub(r"<!--.*?-->", "", t, flags=re.DOTALL)
    # Strip <ref>...</ref> citations (both inline and named)
    t = re.sub(r"<ref[^/>]*?/>", "", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>", "", t, flags=re.DOTALL)
    # Strip remaining HTML tags
    t = re.sub(r"<[^>]+>", "", t)
    # Strip files/images: [[File:...]] / [[Image:...]]
    t = re.sub(r"\[\[(?:File|Image):.*?\]\]", "", t, flags=re.DOTALL)
    # Strip nested templates {{...}} (iterative, since they can nest)
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"\{\{[^\{\}]*\}\}", "", t)
    # Convert wiki links: [[target|display]] → display ; [[target]] → target
    t = re.sub(r"\[\[([^\[\]\|]+)\|([^\[\]]+)\]\]", r"\2", t)
    t = re.sub(r"\[\[([^\[\]\|]+)\]\]", r"\1", t)
    # Convert external links: [url display] → display ; [url] → url
    t = re.sub(r"\[(?:https?:|//)[^\s\]]+\s+([^\]]+)\]", r"\1", t)
    t = re.sub(r"\[(https?:[^\s\]]+)\]", r"\1", t)
    # Strip bold/italic markers
    t = re.sub(r"'''([^']+)'''", r"\1", t)
    t = re.sub(r"''([^']+)''", r"\1", t)
    # HTML entities
    t = html.unescape(t)
    # Collapse whitespace
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def _split_into_sections(wikitext: str, sections_meta: List[Dict]) -> List[Tuple[str, str]]:
    """Split wikitext by top-level section headers (`== Section ==`).

    Returns list of (section_title, section_body_plaintext). Drops the
    lead section if it's shorter than MIN_SECTION_CHARS, and stubs (e.g.,
    "See also", "References", "External links", "Further reading").
    """
    # Match level-2 headers: `\n== Title ==\n`. Level-2 is the top-level
    # section divider on Wikipedia (level-1 is the page title itself).
    level2 = re.compile(r"^==\s*([^=].*?)\s*==\s*$", re.MULTILINE)
    matches = list(level2.finditer(wikitext))

    sections: List[Tuple[str, str]] = []
    if matches:
        # Lead section (before first H2)
        lead = wikitext[: matches[0].start()].strip()
        if lead:
            sections.append(("Introduction", _strip_wikitext(lead)))
        for i, m in enumerate(matches):
            title = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(wikitext)
            body = wikitext[start:end].strip()
            if not body:
                continue
            sections.append((title, _strip_wikitext(body)))
    else:
        # No section headers — treat whole article as one section
        sections.append(("Article", _strip_wikitext(wikitext)))

    # Drop boilerplate sections + stubs
    DROP_TITLES = {
        "see also", "references", "notes", "citations", "external links",
        "further reading", "bibliography", "footnotes", "sources",
    }
    out: List[Tuple[str, str]] = []
    for title, body in sections:
        if title.strip().lower() in DROP_TITLES:
            continue
        if len(body) < MIN_SECTION_CHARS:
            continue
        out.append((title, body[:BODY_CAP_CHARS]))
    return out


def _build_bundle(idx: int, article_title: str, sections: List[Tuple[str, str]],
                  topic: str) -> Optional[Bundle]:
    if len(sections) < MIN_DOCS:
        return None

    # If more than MAX_DOCS sections, take first MAX_DOCS (intro + early sections
    # are usually the most informative).
    used = sections[:MAX_DOCS]

    docs: List[Doc] = []
    for j, (sec_title, body) in enumerate(used):
        docs.append(Doc(
            doc_id=f"tech_docs_{idx:02d}_{j}",
            title=f"{article_title} — {sec_title}"[:160],
            content=body,
            page_id=None,
        ))

    return Bundle(
        bundle_id=f"tech_docs_{idx:02d}",
        source="tech_docs",
        docs=docs,
        metadata={
            "language": "en",
            "article_title": article_title,
            "source_url": f"https://en.wikipedia.org/wiki/{article_title.replace(' ', '_')}",
            "topic": topic,
            "section_titles": [s[0] for s in used],
        },
    )


def _load_existing_titles(path: Path) -> set[str]:
    """Read existing tech_docs.json (if any) and return the set of
    article titles already in it, so a resume run can skip them."""
    if not path.exists():
        return set()
    try:
        from code.utils.bundle_io import read_bundles_json
        existing = read_bundles_json(str(path))
        return {b.metadata.get("article_title") for b in existing
                if b.metadata.get("article_title")}
    except Exception as e:
        print(f"  [warn] could not read existing bundles for resume: {e}")
        return set()


def load_tech_docs(
    n_bundles: int = N_BUNDLES,
    seed: int = SEED,
    sleep_between: float = 0.5,
    existing_titles: Optional[set[str]] = None,
) -> List[Bundle]:
    rng = random.Random(seed)
    articles = list(ARTICLES)
    rng.shuffle(articles)

    bundles: List[Bundle] = []
    skipped_existing = 0
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for art_idx, (title, topic) in enumerate(articles):
            if len(bundles) >= n_bundles:
                break
            if existing_titles and title in existing_titles:
                skipped_existing += 1
                continue
            print(f"[tech_docs] {art_idx+1:02d}/{len(articles)} fetching {title!r}…")
            parse = _fetch_parse(title, client)
            if not parse:
                time.sleep(sleep_between)
                continue
            wikitext_obj = parse.get("wikitext") or {}
            wikitext = wikitext_obj.get("*") if isinstance(wikitext_obj, dict) else ""
            if not wikitext or len(wikitext) < 5000:
                print(f"  [skip] wikitext too short ({len(wikitext)} chars)")
                time.sleep(sleep_between)
                continue
            sections_meta = parse.get("sections") or []
            sections = _split_into_sections(wikitext, sections_meta)
            print(f"  → {len(sections)} usable sections")
            b = _build_bundle(len(bundles), title, sections, topic)
            if b is None:
                print(f"  [skip] not enough sections after filtering")
                time.sleep(sleep_between)
                continue
            try:
                validate_bundle(b)
            except Exception as e:
                print(f"  [skip] bundle validation failed: {e}")
                time.sleep(sleep_between)
                continue
            bundles.append(b)
            time.sleep(sleep_between)  # be a polite Wikipedia API user

    print(f"\n[tech_docs] produced {len(bundles)} new bundles (skipped {skipped_existing} already present)")
    for b in bundles[:5]:
        print(
            f"  {b.bundle_id} [{b.metadata.get('topic')}]: docs={len(b.docs)}, "
            f"chars={b.total_chars()}, article={b.metadata.get('article_title')!r}"
        )
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-bundles", type=int, default=N_BUNDLES)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--sleep", type=float, default=2.0,
                    help="Sleep between successful Wikipedia API requests (s). "
                         "Use 2.0+ to avoid 429 rate-limit responses.")
    ap.add_argument("--resume", action="store_true",
                    help="Skip article titles already present in --out and "
                         "merge new bundles into the existing file.")
    args = ap.parse_args()

    out = Path(args.out)
    existing: List[Bundle] = []
    existing_titles: set[str] = set()
    if args.resume and out.exists():
        from code.utils.bundle_io import read_bundles_json
        existing = read_bundles_json(str(out))
        existing_titles = {b.metadata.get("article_title") for b in existing
                           if b.metadata.get("article_title")}
        print(f"[tech_docs] resume: {len(existing)} existing bundles "
              f"({len(existing_titles)} known article titles)")

    need = max(args.n_bundles - len(existing), 0)
    if need == 0:
        print("[tech_docs] resume target already met")
        return 0

    new_bundles = load_tech_docs(
        n_bundles=need,
        sleep_between=args.sleep,
        existing_titles=existing_titles,
    )
    if not new_bundles and not existing:
        print("[tech_docs] no bundles produced — aborting write")
        return 1

    # Re-number when resuming so bundle_ids stay sequential across merge.
    merged: List[Bundle] = []
    next_idx = 0
    for b in (existing + new_bundles):
        # Re-assign sequential idx
        new_id = f"tech_docs_{next_idx:02d}"
        if b.bundle_id != new_id:
            # Rewrite the bundle_id + doc_ids to stay consistent
            for j, d in enumerate(b.docs):
                d.doc_id = f"{new_id}_{j}"
            b.bundle_id = new_id
        merged.append(b)
        next_idx += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    write_bundles_json(merged, str(out))
    print(f"[tech_docs] wrote {len(merged)} bundles → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
