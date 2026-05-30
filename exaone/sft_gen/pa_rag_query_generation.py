"""
PA-RAG Inspired Query Generator for Domain-Specific SFT Data
=============================================================
- Diverse, real-world user-style queries (no rigid structure)
- Grounded in document but designed to elicit teacher's parametric knowledge
- Round-robin answer style balancing
- Hallucination-minimizing design at query level
"""

import itertools
import re
import json
from typing import List, Tuple, Optional
from collections import Counter

# ============================================================
# 1. Style Definitions & Schedule
# ============================================================

STYLES = ["S1", "S2", "S3", "S4", "S5"]
STYLE_NAMES = {
    "S1": "List",
    "S2": "Extractive",
    "S3": "Inferential",
    "S4": "Definitional",
    "S5": "Exemplary",
}


def generate_style_schedule(
    num_queries: int,
    max_styles_per_query: int = 1,
    styles: List[str] = STYLES,
) -> List[Tuple[str, ...]]:
    if max_styles_per_query == 1:
        cycle = itertools.cycle(styles)
        return [(next(cycle),) for _ in range(num_queries)]

    pool = []
    for size in range(1, max_styles_per_query + 1):
        for combo in itertools.combinations(styles, size):
            pool.append(combo)

    cycle = itertools.cycle(pool)
    return [next(cycle) for _ in range(num_queries)]


def format_style_schedule(schedule: List[Tuple[str, ...]]) -> str:
    lines = []
    for i, st in enumerate(schedule, 1):
        s_str = "+".join(st)
        n_str = " + ".join(STYLE_NAMES[s] for s in st)
        lines.append(f"- Q{i}: [{s_str}] ({n_str})")
    return "\n".join(lines)


def get_style_tuple_for_index(index: int, styles: List[str] = STYLES) -> Tuple[str, ...]:
    """Return a single-query style tuple for round-robin cursor index."""
    safe_styles = styles or STYLES
    safe_index = max(0, int(index))
    return (safe_styles[safe_index % len(safe_styles)],)


def verify_balance(schedule: List[Tuple[str, ...]], label: str = ""):
    style_counts = Counter()
    for combo in schedule:
        for s in combo:
            style_counts[s] += 1
    total = sum(style_counts.values())
    print(f"\n[{label}] Total style assignments: {total}")
    for s in STYLES:
        c = style_counts.get(s, 0)
        pct = c / total * 100
        print(f"  {s} ({STYLE_NAMES[s]:>13s}): {c:3d} ({pct:5.1f}%)")


# ============================================================
# 2. Prompt Template Builder
# ============================================================

PROMPT_TEMPLATE = """\
<s> [INST]
You are generating realistic user queries for a domain-specific chat service.

A real user has access to a knowledge base and is asking questions through a chat interface. \
Your job is to write queries that such users would naturally type — varying in length, \
formality, specificity, and intent. Some users are experts; others are beginners. \
Some ask precisely; others ramble or are vague. Mimic this full spectrum.

=== DOCUMENT CONTEXT ===
<document>
{document_chunk}
</document>

=== YOUR TASK ===
Generate {num_queries} user queries grounded in the above document.

=== CRITICAL GUIDELINES ===

(A) DIVERSITY — each query must feel like it comes from a DIFFERENT person:
  - Vary sentence length (short vs. long), tone (casual vs. formal), and vocabulary level.
  - Mix question forms freely: direct questions, imperative requests, incomplete thoughts, \
comparisons, troubleshooting asks, "what if" scenarios, follow-up style queries, etc.
  - Do NOT repeat syntactic patterns across queries. If Q1 starts with "What is...", \
the next queries must use completely different openings and structures.
  - Some queries may be slightly ambiguous or underspecified, as real users often are.

(B) DOCUMENT GROUNDING + KNOWLEDGE ELICITATION:
  - Every query MUST be answerable using the document as the primary source.
  - However, craft queries so that a knowledgeable answerer would naturally supplement \
the document with accurate broader domain context — for instance, by asking about \
implications, comparisons with industry standards, best practices, or "why" behind \
what the document states.
  - This means: go beyond simple lookup. Ask about relationships, trade-offs, \
practical consequences, or connections to wider domain concepts that the document touches on.

(C) ANTI-HALLUCINATION BY DESIGN:
  - The core factual anchor of each query must exist in the document. \
Do NOT invent entities, features, or claims not present in the document.
  - Queries that invite the answerer to go beyond the document should do so \
in directions where accurate domain knowledge is likely available \
(e.g., well-known standards, widely-accepted practices), not in speculative or obscure areas.

(D) ANSWER STYLE HINT — each query is tagged with a target answer style. \
This is a soft signal for what kind of answer the query should naturally elicit. \
Do NOT let this tag dictate the query's surface form. Instead, the query's \
*intent and scope* should make the tagged style a natural fit for answering:
  - S1 (List): query whose complete answer involves multiple items, steps, or components
  - S2 (Extractive): query targeting a specific fact, value, name, or passage-level detail
  - S3 (Inferential): query requiring synthesis, reasoning, or reading between the lines
  - S4 (Definitional): query about what something is, means, or how a concept works
  - S5 (Exemplary): query best answered with concrete examples or illustrative scenarios

**Style Schedule:**
{style_schedule}

=== OUTPUT ===
For each query Q1..Q{num_queries}, produce output in the order of the style schedule above.
Repeat the following block exactly {num_queries} times, one per query.

Output format must be strictly:
[QUERY]
(one new {lang} query grounded in the NEW DOCUMENT CONTEXT)
[/QUERY]
[/INST]"""


def build_prompt(
    document_chunk: str,
    num_queries: int = 10,
    max_styles_per_query: int = 1,
    lang: str = "Korean",
) -> str:
    schedule = generate_style_schedule(num_queries, max_styles_per_query)
    schedule_text = format_style_schedule(schedule)

    return PROMPT_TEMPLATE.format(
        document_chunk=document_chunk,
        num_queries=num_queries,
        style_schedule=schedule_text,
        lang=lang,
    )


def build_single_query_prompt(
    document_chunk: str,
    lang: str,
    style_idx: int,
) -> str:
    """Build a single-query prompt with one deterministic style schedule entry."""
    schedule = [get_style_tuple_for_index(style_idx)]
    return PROMPT_TEMPLATE.format(
        document_chunk=document_chunk,
        num_queries=1,
        style_schedule=format_style_schedule(schedule),
        lang=lang,
    )


# ============================================================
# 3. Query Parser
# ============================================================

# Regex: capture content between [QUERY] and [/QUERY], stripping whitespace
_QUERY_PATTERN = re.compile(
    r"\[QUERY\]\s*\n?(.*?)\n?\s*\[/QUERY\]",
    re.DOTALL,
)


def parse_queries(raw_output: str) -> List[str]:
    """
    Extract all queries from LLM output using [QUERY]...[/QUERY] tags.
    Returns list of cleaned query strings.
    """
    matches = _QUERY_PATTERN.findall(raw_output)
    return [m.strip() for m in matches if m.strip()]


def parse_queries_with_styles(
    raw_output: str,
    schedule: List[Tuple[str, ...]],
) -> List[dict]:
    """
    Extract queries and pair them with their assigned style from the schedule.
    Returns list of {"query": str, "styles": list[str], "style_names": list[str]}.
    """
    queries = parse_queries(raw_output)
    results = []
    for i, q in enumerate(queries):
        style_tuple = schedule[i] if i < len(schedule) else ("UNKNOWN",)
        results.append({
            "query": q,
            "styles": list(style_tuple),
            "style_names": [STYLE_NAMES.get(s, s) for s in style_tuple],
        })
    return results


# ============================================================
# 4. Demo & Validation
# ============================================================

def demo():
    # --- Simulated document chunk ---
    doc_chunk = """\
IBM FlashSystem uses REST APIs to automate storage provisioning tasks. \
The system supports both synchronous and asynchronous API calls. \
For authentication, an API key must be generated through the management GUI \
under Settings > Security > API Keys. Rate limiting is enforced at 100 requests \
per minute per authenticated session. Bulk operations can be batched using \
the /v1/batch endpoint, which accepts up to 50 operations in a single request. \
Error responses follow RFC 7807 Problem Details format."""

    # --- Build prompt ---
    num_q = 10
    max_s = 2
    lang = "Korean"

    prompt = build_prompt(doc_chunk, num_q, max_s, lang)
    print("=" * 70)
    print("GENERATED PROMPT (first 2000 chars):")
    print("=" * 70)
    print(prompt[:2000])
    print("... [truncated]")

    # --- Simulate LLM output for parser testing ---
    simulated_output = """\
[QUERY]
FlashSystem에서 REST API 인증을 설정하려면 어떻게 해야 하나요?
[/QUERY]
[QUERY]
API 호출 시 rate limiting이 적용되는 기준이 뭔가요? 세션당인지 IP당인지 궁금합니다
[/QUERY]
[QUERY]
배치 엔드포인트로 한 번에 보낼 수 있는 최대 작업 수랑, 만약 그 이상 보내면 어떻게 되는지 알려주세요
[/QUERY]
[QUERY]
RFC 7807이 뭔데 에러 응답에 쓰이는 거죠?
[/QUERY]
[QUERY]
동기 vs 비동기 API 호출 각각 어떤 상황에서 쓰는 게 좋을까요? 스토리지 프로비저닝 자동화 맥락에서요
[/QUERY]
"""

    print("\n" + "=" * 70)
    print("PARSED QUERIES:")
    print("=" * 70)

    schedule = generate_style_schedule(num_q, max_s)
    parsed = parse_queries_with_styles(simulated_output, schedule)

    for i, item in enumerate(parsed, 1):
        style_str = "+".join(item["styles"])
        name_str = ", ".join(item["style_names"])
        print(f"\n  Q{i} [{style_str}] ({name_str}):")
        print(f"    → {item['query']}")

    # --- Balance verification ---
    verify_balance(schedule, f"max_styles={max_s}, n={num_q}")

    # --- JSON export example ---
    print("\n" + "=" * 70)
    print("JSON EXPORT (first 2 entries):")
    print("=" * 70)
    print(json.dumps(parsed[:2], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    demo()
