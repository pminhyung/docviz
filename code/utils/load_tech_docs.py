"""Tech docs loader → 50 cross-document multi-article bundles (LOADER_CONTRACT_v04).

REDESIGN 2026-05-24 (v0.4): Each bundle = 3-4 DISTINCT Wikipedia articles
from the same technology ecosystem. Replaces the v0.3 intra-article
section-split design that produced non-cross-doc bundles per the audit.

Spec (LOADER_CONTRACT_v04):
  - N_BUNDLES = 50
  - 3-5 docs/bundle (we target 3-4)
  - 15K-200K chars/bundle
  - Doc = 1 distinct Wikipedia article (intro + 1-2 main sections, trimmed)
  - random.seed(42)
  - bundle.metadata = {language: "en", bridge_entity: <ecosystem>,
                       ecosystem: ..., articles: [...]}

Ecosystems (3 chosen for ~17 bundles each):
  1. container_orchestration  — Docker, Kubernetes, Helm, Istio, ...
  2. database_systems          — PostgreSQL, Redis, MongoDB, ...
  3. js_frameworks             — React, Vue, Angular, Svelte, ...

Pipeline:
  1. For each ecosystem, fetch each curated article via Wikipedia parse API
     and cache the parsed wikitext (+ stripped sections) to
     data/prototype/sources/raw/tech_docs/{slug}.json. Resume-friendly.
  2. Convert each article into a Doc (intro + 1-2 sections, trimmed to
     ≤ PER_DOC_CHAR_CAP; minimum PER_DOC_MIN_CHARS or article is dropped).
  3. Per ecosystem, enumerate unique 3-4 article combinations with a seeded
     RNG (random.seed(42)), allocating roughly 17 bundles per ecosystem
     until N_BUNDLES = 50 is reached. Skip combinations whose total chars
     fall outside [MIN_CHARS, MAX_CHARS]; on under-shoot, switch to 4 docs.
  4. Validate every bundle with validate_bundle(min_docs=3,
     min_chars=15_000, max_chars=200_000).

Network: uses the same MediaWiki API as the v0.3 loader, with 429-aware
backoff. Disk cache means a re-run is a no-op when articles are present.
"""
from __future__ import annotations

import argparse
import html
import itertools
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


# ── Contract constants ──────────────────────────────────────────────────────
SEED = 42
N_BUNDLES = 50
MIN_DOCS = 3
MAX_DOCS = 4          # contract allows up to 5; we cap at 4 to keep variety high
MIN_CHARS = 15_000
MAX_CHARS = 200_000

# Per-doc bounds. Doc = intro + 1-2 sections, capped so 3 docs ~> ≥ 15K chars.
PER_DOC_CHAR_CAP = 18_000
PER_DOC_MIN_CHARS = 1_800     # drop too-short articles (stubs / redirects)
PER_SECTION_MIN_CHARS = 400   # drop tiny sections before counting

WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "DocViz-Agent-Research/0.4 (research; contact via repo)"

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "prototype" / "bundles" / "tech_docs.json"
RAW_CACHE_DIR = REPO_ROOT / "data" / "prototype" / "sources" / "raw" / "tech_docs"


# ── Ecosystem definitions (≤3 ecosystems × ~15-20 articles each) ────────────
ECOSYSTEMS: Dict[str, List[str]] = {
    "container_orchestration": [
        "Docker (software)",
        "Kubernetes",
        "Containerd",
        "OS-level virtualization",
        "LXC",
        "Container Linux",
        "OpenShift",
        "Rancher Labs",
        "Cloud Native Computing Foundation",
        "OpenStack",
        "Apache Mesos",
        "Docker Swarm",
        "OpenVZ",
        "FreeBSD jail",
        "Solaris Containers",
        "Hyper-V",
        "VMware ESXi",
        "Nomad (software)",
    ],
    "database_systems": [
        "PostgreSQL",
        "MySQL",
        "MongoDB",
        "Redis",
        "Apache Cassandra",
        "SQLite",
        "MariaDB",
        "Elasticsearch",
        "ClickHouse",
        "CockroachDB",
        "InfluxDB",
        "Apache Kafka",
        "RabbitMQ",
        "Memcached",
        "Neo4j",
        "Couchbase Server",
        "Amazon DynamoDB",
        "Apache HBase",
    ],
    "js_frameworks": [
        "React (software)",
        "Vue.js",
        "Angular (web framework)",
        "Svelte",
        "Next.js",
        "Nuxt",
        "Redux (software)",
        "JQuery",
        "Ember.js",
        "AngularJS",
        "Knockout (web framework)",
        "Meteor (web framework)",
        "Express.js",
        "Node.js",
        "TypeScript",
        "JavaScript",
        "Web framework",
        "Single-page application",
    ],
}

# Articles allocated per ecosystem to reach 50 bundles total
# 17 + 17 + 16 = 50
BUNDLES_PER_ECOSYSTEM: List[Tuple[str, int]] = [
    ("container_orchestration", 17),
    ("database_systems",        17),
    ("js_frameworks",           16),
]


# ── Wikipedia API client (resilient to 429 rate limits) ─────────────────────

def _slug(title: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", title.strip())
    return s.strip("_") or "untitled"


def _fetch_parse(
    title: str,
    client: httpx.Client,
    max_retries: int = 5,
) -> Optional[Dict]:
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
    """Best-effort wikitext → plain-text conversion."""
    t = text
    t = re.sub(r"<!--.*?-->", "", t, flags=re.DOTALL)
    t = re.sub(r"<ref[^/>]*?/>", "", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>", "", t, flags=re.DOTALL)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\[\[(?:File|Image):.*?\]\]", "", t, flags=re.DOTALL)
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"\{\{[^\{\}]*\}\}", "", t)
    t = re.sub(r"\[\[([^\[\]\|]+)\|([^\[\]]+)\]\]", r"\2", t)
    t = re.sub(r"\[\[([^\[\]\|]+)\]\]", r"\1", t)
    t = re.sub(r"\[(?:https?:|//)[^\s\]]+\s+([^\]]+)\]", r"\1", t)
    t = re.sub(r"\[(https?:[^\s\]]+)\]", r"\1", t)
    t = re.sub(r"'''([^']+)'''", r"\1", t)
    t = re.sub(r"''([^']+)''", r"\1", t)
    t = html.unescape(t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


_DROP_SECTION_TITLES = {
    "see also", "references", "notes", "citations", "external links",
    "further reading", "bibliography", "footnotes", "sources",
    "awards", "release history", "version history",
}


def _split_into_sections(wikitext: str) -> List[Tuple[str, str]]:
    """Split wikitext at level-2 headers; return list of (title, plaintext).
    Index 0 is always the lead (intro) under title "Introduction"."""
    level2 = re.compile(r"^==\s*([^=].*?)\s*==\s*$", re.MULTILINE)
    matches = list(level2.finditer(wikitext))

    sections: List[Tuple[str, str]] = []
    if matches:
        lead = wikitext[: matches[0].start()].strip()
        if lead:
            sections.append(("Introduction", _strip_wikitext(lead)))
        for i, m in enumerate(matches):
            title = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(wikitext)
            body = wikitext[start:end].strip()
            if body:
                sections.append((title, _strip_wikitext(body)))
    else:
        sections.append(("Article", _strip_wikitext(wikitext)))

    out: List[Tuple[str, str]] = []
    for title, body in sections:
        if title.strip().lower() in _DROP_SECTION_TITLES:
            continue
        if len(body) < PER_SECTION_MIN_CHARS:
            continue
        out.append((title, body))
    return out


# ── Per-article fetch + cache ───────────────────────────────────────────────

def _cache_path(title: str) -> Path:
    return RAW_CACHE_DIR / f"{_slug(title)}.json"


def _fetch_article_cached(
    title: str, client: httpx.Client, sleep_between: float = 1.5,
) -> Optional[Dict]:
    """Fetch + parse + strip a single article, with on-disk caching.

    Cache format (per article):
      {
        "title":     <wiki title>,
        "slug":      <filesystem slug>,
        "fetched_at": <unix ts>,
        "sections":  [{"title": ..., "body": ...}, ...]   # plain text
      }
    Returns None on persistent fetch failure or unusable article.
    """
    cache = _cache_path(title)
    if cache.exists():
        try:
            obj = json.loads(cache.read_text(encoding="utf-8"))
            if obj.get("sections"):
                return obj
        except Exception as e:
            print(f"  [cache-warn] {cache.name}: re-fetching ({e})")

    print(f"  [wiki] fetching {title!r}…")
    parse = _fetch_parse(title, client)
    if not parse:
        return None
    wikitext_obj = parse.get("wikitext") or {}
    wikitext = wikitext_obj.get("*") if isinstance(wikitext_obj, dict) else ""
    if not wikitext or len(wikitext) < 3_000:
        print(f"    [skip] wikitext too short ({len(wikitext)} chars)")
        time.sleep(sleep_between)
        return None
    sections = _split_into_sections(wikitext)
    if not sections:
        print(f"    [skip] no usable sections after stripping")
        time.sleep(sleep_between)
        return None
    obj = {
        "title": parse.get("title", title),
        "slug": _slug(title),
        "fetched_at": time.time(),
        "sections": [{"title": t, "body": b} for t, b in sections],
        "source_url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    time.sleep(sleep_between)
    return obj


def _article_to_text(article: Dict) -> str:
    """Concatenate intro + first 1-2 sections; trim to PER_DOC_CHAR_CAP.

    Strategy: greedily take sections from index 0 until we either:
      (a) have ≥ PER_DOC_MIN_CHARS chars AND >= 2 sections used, or
      (b) run out of sections.
    Then truncate to PER_DOC_CHAR_CAP to bound per-doc size.
    """
    sections = article.get("sections", [])
    if not sections:
        return ""
    parts: List[str] = []
    total = 0
    for i, sec in enumerate(sections):
        title = sec["title"]
        body = sec["body"]
        # Always include intro; include subsequent sections greedily until cap
        if i == 0:
            parts.append(body)
            total += len(body)
            continue
        if total >= PER_DOC_CHAR_CAP * 0.8 and i >= 2:
            # We have enough body from intro + 1+ sections
            break
        parts.append(f"\n\n## {title}\n\n{body}")
        total += len(body) + len(title) + 8
        if i >= 2 and total >= PER_DOC_MIN_CHARS:
            # Cap at intro + 2 main sections to leave room for other docs
            break
    text = "\n".join(parts).strip()
    return text[:PER_DOC_CHAR_CAP]


def _article_to_doc(idx: int, j: int, article: Dict) -> Optional[Doc]:
    body = _article_to_text(article)
    if len(body) < PER_DOC_MIN_CHARS:
        return None
    title = article.get("title") or "Untitled Wikipedia article"
    return Doc(
        doc_id=f"tech_docs_{idx:02d}_{j}",
        title=title[:200],
        content=body,
        page_id=article.get("slug"),
    )


# ── Bundle assembly ─────────────────────────────────────────────────────────

def _build_bundle(
    idx: int, ecosystem: str, articles: List[Dict],
) -> Optional[Bundle]:
    docs: List[Doc] = []
    for j, art in enumerate(articles):
        d = _article_to_doc(idx, j, art)
        if d is None:
            return None
        docs.append(d)
    if len(docs) < MIN_DOCS:
        return None
    return Bundle(
        bundle_id=f"tech_docs_{idx:02d}",
        source="tech_docs",
        docs=docs,
        metadata={
            "language": "en",
            "bridge_entity": ecosystem,
            "ecosystem": ecosystem,
            "articles": [a.get("title") for a in articles],
            "article_slugs": [a.get("slug") for a in articles],
            "n_docs": len(docs),
            "source_urls": [a.get("source_url") for a in articles],
            "source_corpus": "wikipedia",
        },
    )


def _enumerate_combinations(
    pool: List[Dict], n_target: int, rng: random.Random,
) -> List[List[Dict]]:
    """Yield up to n_target unique 3- or 4-article combinations from pool.

    Strategy: build the full set of 3-combinations, shuffle deterministically,
    then iterate. If a 3-combo doesn't clear MIN_CHARS, swap to 4 by appending
    one extra unused article from the pool. Returns at most n_target combos.
    """
    if len(pool) < MIN_DOCS:
        return []
    combos_3 = list(itertools.combinations(range(len(pool)), MIN_DOCS))
    rng.shuffle(combos_3)
    out: List[List[Dict]] = []
    seen_keys: set = set()
    for combo in combos_3:
        if len(out) >= n_target:
            break
        articles = [pool[i] for i in combo]
        total = sum(len(_article_to_text(a)) for a in articles)
        used_idx = set(combo)
        if total < MIN_CHARS:
            # Try to extend with one more article (largest unused one)
            unused = [i for i in range(len(pool)) if i not in used_idx]
            unused.sort(key=lambda i: -len(_article_to_text(pool[i])))
            if not unused:
                continue
            articles = articles + [pool[unused[0]]]
            used_idx.add(unused[0])
            total = sum(len(_article_to_text(a)) for a in articles)
            if total < MIN_CHARS:
                continue
        if total > MAX_CHARS:
            continue  # extremely unlikely given per-doc cap, but guard
        key = tuple(sorted(used_idx))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(articles)
    return out


def build_bundles(
    n_bundles: int = N_BUNDLES, seed: int = SEED,
    sleep_between: float = 1.5,
) -> List[Bundle]:
    rng = random.Random(seed)

    # Phase 1: fetch + cache every article, grouped by ecosystem.
    # Wikipedia redirects (e.g. "Containerd" -> "Cloud Native Computing
    # Foundation") collapse multiple input titles to the same resolved page,
    # which would create within-bundle duplicates. We dedup pools by the
    # *resolved* article title (parse.get("title")).
    ecosystem_pools: Dict[str, List[Dict]] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for eco, titles in ECOSYSTEMS.items():
            print(f"\n[tech_docs] === fetching ecosystem: {eco} ({len(titles)} candidates) ===")
            pool: List[Dict] = []
            seen_resolved: set = set()
            for title in titles:
                art = _fetch_article_cached(title, client, sleep_between=sleep_between)
                if art is None:
                    continue
                resolved = (art.get("title") or title).strip()
                if resolved in seen_resolved:
                    print(f"    [dedup] {title!r} → resolves to already-seen "
                          f"{resolved!r}; dropping")
                    continue
                body_len = len(_article_to_text(art))
                if body_len < PER_DOC_MIN_CHARS:
                    print(f"    [drop] {title!r}: only {body_len} usable chars")
                    continue
                seen_resolved.add(resolved)
                pool.append(art)
            print(f"[tech_docs] {eco}: {len(pool)} usable articles "
                  f"(after redirect-dedup)")
            ecosystem_pools[eco] = pool

    # Phase 2: per-ecosystem bundle assembly
    bundles: List[Bundle] = []
    for eco, target_n in BUNDLES_PER_ECOSYSTEM:
        if len(bundles) >= n_bundles:
            break
        pool = ecosystem_pools.get(eco, [])
        if len(pool) < MIN_DOCS:
            print(f"[tech_docs] {eco}: SKIP — only {len(pool)} articles")
            continue
        # Adjust target if other ecosystems under-shot earlier
        remaining = n_bundles - len(bundles)
        want = min(target_n, remaining)
        combos = _enumerate_combinations(pool, want, rng)
        print(f"[tech_docs] {eco}: enumerated {len(combos)} candidate combos "
              f"(want={want}, pool={len(pool)})")
        for articles in combos:
            if len(bundles) >= n_bundles:
                break
            b = _build_bundle(len(bundles), eco, articles)
            if b is None:
                continue
            errs = validate_bundle(b, min_docs=MIN_DOCS,
                                   min_chars=MIN_CHARS, max_chars=MAX_CHARS)
            if errs:
                print(f"  [skip] {eco} bundle {len(bundles)}: {errs}")
                continue
            bundles.append(b)

    # Phase 3: fallback fill (if under-shot, draw from largest pools)
    if len(bundles) < n_bundles:
        print(f"\n[tech_docs] fallback fill: have {len(bundles)} of {n_bundles}")
        # Re-enumerate combinations across all ecosystems, prefer larger pools
        for eco, pool in sorted(
            ecosystem_pools.items(), key=lambda x: -len(x[1])
        ):
            if len(bundles) >= n_bundles:
                break
            existing_keys = {
                tuple(sorted(b.metadata["articles"]))
                for b in bundles
                if b.metadata.get("ecosystem") == eco
            }
            extra = _enumerate_combinations(
                pool, n_bundles - len(bundles) + 10, rng,
            )
            for articles in extra:
                if len(bundles) >= n_bundles:
                    break
                key = tuple(sorted(a.get("title") for a in articles))
                if key in existing_keys:
                    continue
                b = _build_bundle(len(bundles), eco, articles)
                if b is None:
                    continue
                errs = validate_bundle(b, min_docs=MIN_DOCS,
                                       min_chars=MIN_CHARS, max_chars=MAX_CHARS)
                if errs:
                    continue
                bundles.append(b)
                existing_keys.add(key)

    return bundles


def main() -> int:
    ap = argparse.ArgumentParser(description="Build cross-doc tech_docs bundles.")
    ap.add_argument("--n-bundles", type=int, default=N_BUNDLES)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--sleep", type=float, default=1.5,
                    help="Sleep between Wikipedia fetches (s). >=1.5 advised "
                         "to avoid 429.")
    args = ap.parse_args()

    bundles = build_bundles(n_bundles=args.n_bundles, sleep_between=args.sleep)
    print(f"\n[tech_docs] built {len(bundles)} bundles")

    errors: List[str] = []
    for b in bundles:
        errors.extend(validate_bundle(b, min_docs=MIN_DOCS,
                                      min_chars=MIN_CHARS, max_chars=MAX_CHARS))
    if errors:
        print("[tech_docs] VALIDATION ERRORS:")
        for e in errors:
            print(f"  {e}")
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_bundles_json(bundles, str(out))
    print(f"[tech_docs] wrote {len(bundles)} bundles → {out}")
    for b in bundles:
        print(
            f"  {b.bundle_id} [{b.metadata['ecosystem']}]: "
            f"docs={len(b.docs)}, chars={b.total_chars()}, "
            f"articles={b.metadata['articles']}"
        )
    return 0 if len(bundles) >= args.n_bundles else 2


if __name__ == "__main__":
    sys.exit(main())
