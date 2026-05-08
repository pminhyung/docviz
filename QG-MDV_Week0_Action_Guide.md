# QG-MDV Week 0 — Research Agent Action Guide

> **Project**: Query-Grounded Multi-Document Visualization (QG-MDV)
> **Target venue**: EMNLP 2026 Findings (Industry Track 옵션)
> **Phase**: Week 0 — Prototype & Go/No-Go validation
> **Owner**: Solo researcher
> **Last updated**: 2026-05-07

---

## 0. Project Snapshot (1-page overview)

### 0.1 Task definition

> *Given a user query Q and a multi-document corpus D = {D₁, ..., Dₙ}, generate a visualization V (Chart.js / Mermaid.js DSL) that (a) faithfully reflects D, (b) answers Q, (c) uses an appropriate viz type for the information.*

### 0.2 Headline contributions (이 paper의 main claim)

1. **Task formalization**: Query-Grounded Multi-Document Visualization (QG-MDV) — 새 task + 5 query type taxonomy
2. **Pipeline strategy comparison**: 4 strategy × 5 LLM × 4 evaluation axis
3. **Search query mechanism finding**: agentic dynamic query generation의 +X%p 우위 + step-level information gain mechanism

### 0.3 Pipeline strategies

| Strategy | Form | Search Query |
|---|---|---|
| S1 Direct | (concat docs + query) → LLM → viz | none |
| S2 Standard RAG | query → retrieve top-k → LLM → viz | static (=Q) |
| S3 Query-Decompose RAG | query → sub-queries (1 shot) → retrieve → synthesize → viz | static decomposed |
| **S4 Agentic (Ours)** | **multi-step: search query → retrieve → summarize → continue or exit → viz** | **dynamic, multi-turn** |

### 0.4 Evaluation: RocketEval-adapted checklist judge with 5 external anchors

| Anchor | Form | Required min |
|---|---|---|
| **Primary metric** | 4-axis checklist judge (Faithfulness / Coverage / Type / Search-Q) | — |
| Anchor 1: Human | 50 viz × 3 Prolific × 4 axis | Spearman r ≥ 0.65 |
| Anchor 2: Deterministic | Render-success / Numeric-exactness / Entity-coverage / Structural-validity | Cross-rank Spearman ≥ 0.5 |
| Anchor 3: External transfer | nvBench quantitative subset 200 sample | S4 ≥ S1 by ≥ 5%p |
| Anchor 4: Reverse-direction QA | VLM이 our viz 보고 query 답 | S4 viz answer-acc ≥ S1 viz answer-acc |
| Anchor 5: Replicate finding | ChartMuseum의 visual-text drop pattern 재현 | drop ≥ 30% |

### 0.5 Models (latest 2026 — 실행 시점 web search로 재확인)

| Model | Tier | Use |
|---|---|---|
| GPT-5 | closed flagship | main + Anchor 4 reader |
| Claude Opus 4.6 | closed flagship | main + cross-judge |
| Gemini 2.5 Pro | closed flagship | main |
| Qwen3-Coder-30B-A3B | open large | main + DSL fluency |
| DeepSeek V3.5 | open frontier | cost baseline |
| Template-based heuristic | sanity floor | non-LLM baseline |

---

## 1. Week 0 Goal & Decision Gates

### 1.1 Week 0 single-line objective

> **Validate two assumptions before committing 5 weeks of full experimentation:**
> 1. **Judge assumption** — Adapted RocketEval checklist judge correlates with human ratings (Spearman r ≥ 0.5 on prototype 30 sample).
> 2. **Method assumption** — Agentic strategy (S4) shows positive effect direction over Direct (S1) on at least one query type (≥ +5%p).

### 1.2 Go/No-Go decision matrix (Day 14)

| Judge r | S4 effect | Decision |
|---|---|---|
| ≥ 0.5 | ≥ +5%p in ≥1 type | **GO** — proceed to Week 1 full benchmark |
| ≥ 0.5 | < +5%p anywhere | **REFRAME** — pivot to "diagnostic + framework" paper, reduce method emphasis |
| < 0.5 | any | **JUDGE FIX** — try cross-judge with Claude Opus 4.6, retry. If still < 0.5 → switch judge model or simplify checklist |
| < 0.3 | any | **PIVOT** — checklist judge approach failed, fall back to mixed metric (NLI + structural) |

### 1.3 Week 0 deliverables

- `data/prototype/bundles/` — 30 multi-doc bundles (JSON)
- `data/prototype/queries/` — 50 synthetic queries (JSON)
- `outputs/prototype/viz/` — 60 viz outputs (1 LLM × 2 strategies × 30 bundles)
- `outputs/prototype/judge_scores/` — 60 viz × 4 axis scores
- `outputs/prototype/human_ratings/` — 30 viz × 2 raters × 4 axis
- `notebooks/W0_analysis.ipynb` — Spearman, S4 vs S1 comparison
- `WEEK0_REPORT.md` — Go/No-Go decision report

---

## 2. Day-by-Day Action Plan

### **Day 1-2: Bundle Acquisition (30 bundles total)**

#### 2.1 Source allocation

| Source | # bundles | Bundle = | Why |
|---|---|---|---|
| HotpotQA dev | 10 | 1 question + 2 supporting Wikipedia paragraphs | Standard multi-doc QA, relational queries 강함 |
| MultiNews val | 10 | 2-5 news articles per cluster | Temporal + comparative queries 강함 |
| arXiv | 5 | 3 paper abstracts in same conference track | Hierarchical + comparative queries |
| EDGAR 10-K | 5 | 1 company's 10-K Item-7 + Item-7A (MD&A + Risk) | Quantitative queries (financial numbers) |

#### 2.2 Action items

**Action 2.2.1** — Setup workspace
```bash
mkdir -p data/prototype/{bundles,queries,sources}
mkdir -p outputs/prototype/{viz,judge_scores,human_ratings}
mkdir -p notebooks
mkdir -p code/{pipelines,judge,utils}
```

**Action 2.2.2** — HotpotQA download (10 bundles)
```python
# code/utils/load_hotpotqa.py
import json, requests, random

URL = "http://curtis.ml.cmu.edu/datasets/hotpot/hotpot_dev_distractor_v1.json"
random.seed(42)

# Download
data = requests.get(URL).json()  # ~7400 examples

# Filter: keep examples where answer involves multi-hop reasoning + 2 supporting facts
# We want: relational, comparative, or quantitative query types
candidates = [
    ex for ex in data
    if ex['type'] in ['comparison', 'bridge']
    and len(ex['supporting_facts']) >= 2
]
sampled = random.sample(candidates, 10)

# Build bundles
bundles = []
for i, ex in enumerate(sampled):
    # Extract supporting paragraphs
    supporting_titles = set(t for t, _ in ex['supporting_facts'])
    docs = [
        {"id": f"hotpot_{i}_{j}", "title": title, "content": " ".join(sentences)}
        for j, (title, sentences) in enumerate(ex['context'])
        if title in supporting_titles
    ]
    bundles.append({
        "bundle_id": f"hotpot_{i:02d}",
        "source": "hotpotqa",
        "docs": docs,
        "original_question": ex['question'],  # store for query-gen seeding
        "original_answer": ex['answer'],
        "type_hint": ex['type'],  # 'comparison' or 'bridge'
    })

with open("data/prototype/bundles/hotpot.json", "w") as f:
    json.dump(bundles, f, indent=2)
```

**Action 2.2.3** — MultiNews download (10 bundles)
```python
# code/utils/load_multinews.py
from datasets import load_dataset
import random, json

random.seed(42)
ds = load_dataset("multi_news", split="validation")  # ~5,600 clusters

# Filter: clusters with 2-5 articles, total length 3-15K tokens (rough)
def cluster_size(ex):
    return ex['document'].count("|||||")  # MultiNews separates docs with |||||

candidates = [ex for ex in ds if 2 <= cluster_size(ex) <= 5]
sampled = random.sample(candidates, 10)

bundles = []
for i, ex in enumerate(sampled):
    docs_raw = ex['document'].split("|||||")
    docs = [
        {"id": f"multinews_{i}_{j}", "title": f"Article {j}", "content": d.strip()}
        for j, d in enumerate(docs_raw) if d.strip()
    ]
    bundles.append({
        "bundle_id": f"multinews_{i:02d}",
        "source": "multinews",
        "docs": docs,
        "reference_summary": ex['summary'],
    })

with open("data/prototype/bundles/multinews.json", "w") as f:
    json.dump(bundles, f, indent=2)
```

**Action 2.2.4** — arXiv bundles (5 bundles)
```python
# code/utils/load_arxiv.py
# Use arXiv OAI-PMH API or arxiv pip package
import arxiv, random, json

random.seed(42)
# Pick 5 query topics → fetch 3 papers each, same year
TOPICS = [
    "long context language models",
    "retrieval augmented generation",
    "chain of thought reasoning",
    "multi-document summarization",
    "document understanding visualization",
]

bundles = []
for i, topic in enumerate(TOPICS):
    search = arxiv.Search(
        query=topic, max_results=10, sort_by=arxiv.SortCriterion.SubmittedDate,
    )
    papers = list(search.results())[:3]  # 3 papers per bundle
    docs = [
        {
            "id": f"arxiv_{i}_{j}",
            "title": p.title,
            "content": (p.summary + "\n\n" + (p.comment or ""))[:8000]  # cap
        }
        for j, p in enumerate(papers)
    ]
    bundles.append({
        "bundle_id": f"arxiv_{i:02d}",
        "source": "arxiv",
        "docs": docs,
        "topic_seed": topic,
    })

with open("data/prototype/bundles/arxiv.json", "w") as f:
    json.dump(bundles, f, indent=2)
```

**Action 2.2.5** — 10-K bundles (5 bundles)
```python
# code/utils/load_10k.py
# Use sec-edgar-downloader package
from sec_edgar_downloader import Downloader
import json, re, os, random

random.seed(42)
TICKERS = ["AAPL", "MSFT", "TSLA", "NVDA", "META"]  # 5 companies

dl = Downloader("YourName", "your@email", "data/prototype/sources/10k_raw")
for tick in TICKERS:
    dl.get("10-K", tick, limit=1, after="2024-01-01")

# Parse: extract Item 7 (MD&A) and Item 7A (Risk)
def extract_item7_7a(html_path):
    # Use selectolax or BeautifulSoup
    import selectolax.parser as sp
    with open(html_path) as f:
        tree = sp.HTMLParser(f.read())
    text = tree.text()
    # Regex extraction (rough — refine in prototype)
    item7_match = re.search(
        r"Item\s*7[.\s]+Management[\'s]?\s*Discussion(.*?)Item\s*7A",
        text, re.DOTALL | re.IGNORECASE
    )
    item7a_match = re.search(
        r"Item\s*7A[.\s]+Quantitative(.*?)Item\s*8",
        text, re.DOTALL | re.IGNORECASE
    )
    return (
        item7_match.group(1)[:15000] if item7_match else "",
        item7a_match.group(1)[:5000] if item7a_match else "",
    )

bundles = []
for i, tick in enumerate(TICKERS):
    # Find downloaded file
    base = f"data/prototype/sources/10k_raw/sec-edgar-filings/{tick}/10-K"
    folder = os.listdir(base)[0]
    html_path = f"{base}/{folder}/full-submission.txt"
    item7, item7a = extract_item7_7a(html_path)
    if not item7 or not item7a:
        continue
    bundles.append({
        "bundle_id": f"10k_{i:02d}",
        "source": "10k",
        "ticker": tick,
        "docs": [
            {"id": f"10k_{i}_mda", "title": f"{tick} 10-K MD&A", "content": item7},
            {"id": f"10k_{i}_risk", "title": f"{tick} 10-K Risk", "content": item7a},
        ],
    })

with open("data/prototype/bundles/10k.json", "w") as f:
    json.dump(bundles, f, indent=2)
```

**Action 2.2.6** — Merge bundles
```python
# code/utils/merge_bundles.py
import json, glob

all_bundles = []
for path in glob.glob("data/prototype/bundles/*.json"):
    if path.endswith("/all.json"): continue
    with open(path) as f:
        all_bundles.extend(json.load(f))

# Validate
assert len(all_bundles) == 30, f"Expected 30, got {len(all_bundles)}"
for b in all_bundles:
    assert len(b['docs']) >= 2, f"{b['bundle_id']} has <2 docs"
    total_chars = sum(len(d['content']) for d in b['docs'])
    assert 3000 <= total_chars <= 80000, f"{b['bundle_id']} length {total_chars}"

with open("data/prototype/bundles/all.json", "w") as f:
    json.dump(all_bundles, f, indent=2)
print(f"OK — {len(all_bundles)} bundles merged")
```

#### 2.3 Day 1-2 verification gate

- [ ] `data/prototype/bundles/all.json` has 30 bundles
- [ ] Each bundle has ≥ 2 docs
- [ ] Total char count per bundle in [3K, 80K]
- [ ] At least 5 unique source types used? No (4 sources: hotpot/multinews/arxiv/10k) — that's fine

---

### **Day 3-4: Synthetic Query Generation (50 queries)**

#### 3.1 5-type taxonomy

| Query Type | Definition | Doc precondition |
|---|---|---|
| Quantitative | Numerical comparison/trend | ≥5 numbers in docs |
| Relational | Entity-entity dependency/relation | ≥2 named entities + linking verbs |
| Temporal | Time-ordered events | ≥3 time markers |
| Hierarchical | Categorization/taxonomy | nested classification cues |
| Comparative | Multi-entity feature comparison | ≥2 comparable entities |

#### 3.2 Query generation prompt (saved to `code/utils/query_gen_prompt.py`)

```python
QUERY_GEN_PROMPT = """\
You are creating a realistic user query for a document visualization assistant.

Documents (you may reference any/all):
{docs_concat}

Your task: Generate ONE natural user query that:
1. Falls into the query type: **{query_type}**
2. Can be answered by visualizing information found in these documents
3. Is realistic — what a real user would actually ask
4. Is specific enough that the answer requires actual document content (not generic knowledge)
5. Implicitly suggests a visualization (chart/diagram/mindmap) is appropriate

Definition of {query_type}:
{type_def}

Output ONLY the query, no preamble. Maximum 25 words.
"""

TYPE_DEFS = {
    "quantitative": "Numerical comparison or trend (e.g., 'How did revenue change across regions?')",
    "relational": "Entity-entity relations or dependencies (e.g., 'How do these risk factors interconnect?')",
    "temporal": "Time-ordered events (e.g., 'Show the regulatory milestones over the past decade')",
    "hierarchical": "Categorization/taxonomy (e.g., 'What are the main business segments and their sub-units?')",
    "comparative": "Multi-entity feature comparison (e.g., 'Compare the architecture choices of these three models')",
}
```

#### 3.3 Action items

**Action 3.3.1** — Generate queries
```python
# code/utils/generate_queries.py
import json, openai, time, os
from query_gen_prompt import QUERY_GEN_PROMPT, TYPE_DEFS

client = openai.OpenAI()  # uses OPENAI_API_KEY env

with open("data/prototype/bundles/all.json") as f:
    bundles = json.load(f)

# For prototype: assign 1-2 query types per bundle based on content heuristic
# Simple rule: hotpot→relational+comparative, multinews→temporal+comparative,
# arxiv→hierarchical+comparative, 10k→quantitative+temporal

TYPE_ASSIGNMENT = {
    "hotpotqa": ["relational", "comparative"],
    "multinews": ["temporal", "comparative"],
    "arxiv": ["hierarchical", "comparative"],
    "10k": ["quantitative", "temporal"],
}

queries = []
for bundle in bundles:
    types = TYPE_ASSIGNMENT[bundle['source']]
    for qtype in types[:2]:  # max 2 per bundle → 30 × 2 = 60 → cap to 50
        if len(queries) >= 50: break
        docs_concat = "\n\n---\n\n".join(
            f"[{d['title']}]\n{d['content'][:3000]}" for d in bundle['docs']
        )
        prompt = QUERY_GEN_PROMPT.format(
            docs_concat=docs_concat,
            query_type=qtype,
            type_def=TYPE_DEFS[qtype],
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",  # cheap for prototype query gen
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=100,
        )
        query_text = resp.choices[0].message.content.strip().strip('"')
        queries.append({
            "query_id": f"{bundle['bundle_id']}_{qtype}",
            "bundle_id": bundle['bundle_id'],
            "query_type": qtype,
            "query": query_text,
        })
        time.sleep(0.3)
    if len(queries) >= 50: break

with open("data/prototype/queries/all.json", "w") as f:
    json.dump(queries, f, indent=2)
print(f"Generated {len(queries)} queries")
```

**Action 3.3.2** — Manual quality check (10 random queries)
```
For 10 random queries, check by hand:
- Is the query natural? (1-5 score)
- Is it answerable from the bundle? (yes/no)
- Does it match the assigned type? (yes/no)

Pass criterion: 8/10 natural ≥ 4, 9/10 answerable, 9/10 type-matched
If fail: refine prompt and regenerate
```

#### 3.4 Day 3-4 verification gate

- [ ] 50 queries generated, distributed across 5 types
- [ ] Manual 10-sample naturalness ≥ 4.0 mean
- [ ] All 50 queries have non-empty `bundle_id` and `query`

---

### **Day 5-6: Pipeline Implementation (S1 Direct, S4 Agentic)**

#### 4.1 Common pipeline interface

```python
# code/pipelines/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class VizOutput:
    viz_dsl: str           # raw DSL code (Mermaid or Chart.js)
    viz_type: str          # "mermaid_flowchart" | "mermaid_mindmap" | "chartjs_bar" | etc
    retrieved_chunks: List[Dict]  # snippets used (for grounding)
    sub_queries: List[str]  # search queries generated (S4 only, list len = #steps)
    total_tokens_in: int
    total_tokens_out: int
    api_cost_usd: float

class Pipeline(ABC):
    name: str
    @abstractmethod
    def run(self, query: str, bundle: dict) -> VizOutput: ...
```

#### 4.2 S1 Direct implementation

```python
# code/pipelines/s1_direct.py
from .base import Pipeline, VizOutput
import openai, json

VIZ_GEN_PROMPT = """\
You are a visualization assistant.

User query: {query}

Source documents (multi-doc):
{docs}

Generate the most appropriate visualization in ONE of these formats:
1. Mermaid flowchart/sequence/state diagram (for relational/temporal/process)
2. Mermaid mindmap (for hierarchical)
3. Chart.js JSON spec (for quantitative)

Output a single JSON:
{{"viz_type": "<one of: mermaid_flowchart, mermaid_mindmap, chartjs_bar, chartjs_line>",
  "viz_dsl": "<the DSL code>"}}
Use only the documents above. Do not fabricate facts.
"""

class S1Direct(Pipeline):
    name = "S1_Direct"
    def __init__(self, model="gpt-5"): self.model = model

    def run(self, query, bundle):
        docs_concat = "\n\n---\n\n".join(
            f"[{d['title']}]\n{d['content']}" for d in bundle['docs']
        )
        prompt = VIZ_GEN_PROMPT.format(query=query, docs=docs_concat)
        resp = openai.OpenAI().chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        out = json.loads(resp.choices[0].message.content)
        return VizOutput(
            viz_dsl=out['viz_dsl'],
            viz_type=out['viz_type'],
            retrieved_chunks=[{"doc_id": d['id'], "content": d['content']} for d in bundle['docs']],
            sub_queries=[],  # S1 has no search
            total_tokens_in=resp.usage.prompt_tokens,
            total_tokens_out=resp.usage.completion_tokens,
            api_cost_usd=...,  # compute from token count + price table
        )
```

#### 4.3 S4 Agentic implementation (사용자 pipeline 사용)

> **NOTE for the agent**: 사용자가 이미 가지고 있는 agentic pipeline (long doc + query → search query gen → retrieve → summarize → viz)을 여기에 wire함. 아래는 placeholder skeleton. 사용자 코드를 import 또는 adapt.

```python
# code/pipelines/s4_agentic.py
from .base import Pipeline, VizOutput
# import user_pipeline  # 사용자 코드 import

class S4Agentic(Pipeline):
    name = "S4_Agentic"
    def __init__(self, user_pipeline_handle, model="gpt-5"):
        self.up = user_pipeline_handle
        self.model = model

    def run(self, query, bundle):
        # User pipeline expects: query, doc list (or doc store)
        # Returns: viz output + intermediate sub-queries + retrieved chunks
        result = self.up.execute(
            query=query,
            documents=bundle['docs'],
            return_trace=True,
        )
        return VizOutput(
            viz_dsl=result.viz_dsl,
            viz_type=result.viz_type,
            retrieved_chunks=result.retrieved_chunks,  # cumulative across steps
            sub_queries=result.search_query_trace,  # ordered list of step queries
            total_tokens_in=result.tokens_in,
            total_tokens_out=result.tokens_out,
            api_cost_usd=result.cost,
        )
```

> **Action 4.3.1** — User pipeline wiring task: 사용자 pipeline의 entry point가 위 interface와 일치하는지 확인. 차이나면 thin adapter 작성. **예상 시간 4-8 hours.**

#### 4.4 Day 5-6 verification gate

- [ ] S1 runs end-to-end on 1 sample → produces valid VizOutput
- [ ] S4 runs end-to-end on 1 sample → produces valid VizOutput, sub_queries non-empty
- [ ] 두 pipeline 모두 same VizOutput schema 출력

---

### **Day 7-8: Viz Generation (60 viz outputs)**

#### 5.1 Action items

**Action 5.1.1** — Run all combinations
```python
# code/run_prototype.py
import json
from pipelines.s1_direct import S1Direct
from pipelines.s4_agentic import S4Agentic

with open("data/prototype/bundles/all.json") as f:
    bundles = {b['bundle_id']: b for b in json.load(f)}
with open("data/prototype/queries/all.json") as f:
    queries = json.load(f)

s1 = S1Direct(model="gpt-5")
s4 = S4Agentic(user_pipeline_handle=..., model="gpt-5")  # wire up
strategies = {"S1": s1, "S4": s4}

results = []
for q in queries:
    bundle = bundles[q['bundle_id']]
    for strat_name, strat in strategies.items():
        try:
            out = strat.run(q['query'], bundle)
            results.append({
                "query_id": q['query_id'],
                "bundle_id": q['bundle_id'],
                "query_type": q['query_type'],
                "query": q['query'],
                "strategy": strat_name,
                "viz_dsl": out.viz_dsl,
                "viz_type": out.viz_type,
                "retrieved_chunks": out.retrieved_chunks,
                "sub_queries": out.sub_queries,
                "tokens_in": out.total_tokens_in,
                "tokens_out": out.total_tokens_out,
                "cost_usd": out.api_cost_usd,
            })
        except Exception as e:
            print(f"FAIL {q['query_id']} {strat_name}: {e}")

with open("outputs/prototype/viz/all.json", "w") as f:
    json.dump(results, f, indent=2)
```

#### 5.2 Cost estimate

```
50 queries × 2 strategies = 100 calls
Average: 15K input + 1K output tokens (multi-doc setting)
GPT-5 price (assumed $5/M input, $15/M output):
  Per call: 15 × $5/1000 + 1 × $15/1000 = $0.075 + $0.015 = $0.090
  100 calls × $0.09 = $9 (S1)
  S4 has 3-5 steps avg → ~3× cost = $27
  Total: ~$36 for prototype (very cheap)
```

#### 5.3 Day 7-8 verification gate

- [ ] 100 viz outputs (50 queries × 2 strategies) successfully generated, ≥ 95% no errors
- [ ] All viz_dsl renders successfully (Mermaid CLI / Chart.js validator) ≥ 90% rate
- [ ] S4 sub_queries non-empty (avg ≥ 2 sub-queries per call)
- [ ] Cost log: total spend < $50 (or pivot to gpt-4o-mini if budget concern)

---

### **Day 9-10: Checklist Judge Implementation**

#### 6.1 Adapted RocketEval checklist judge — design

**Checklist generation (per (query, bundle, viz) instance)**:

```python
# code/judge/checklist_gen_prompt.py
CHECKLIST_GEN_PROMPT = """\
You are creating a quality checklist for a query-grounded multi-document visualization.

Inputs:
- User query: {query}
- Query type: {query_type}
- Source documents:
{sources}

Generate a JSON list of 10-14 yes/no questions, distributed across 4 axes:
- "faithfulness" (4 items): Does each visual element accurately reflect source content?
- "coverage" (3 items): Are the key information needed to answer the query represented?
- "type_appropriateness" (2 items): Is the visualization type appropriate for this query?
- "search_query_quality" (2-3 items): If the visualization is built from sub-searches, are those searches well-targeted? (skip if not applicable)

Each item: {{"axis": "faithfulness|coverage|type_appropriateness|search_query_quality",
            "question": "Yes/no question about the viz",
            "evidence_hint": "What part of source/viz to look at"}}

Output JSON only.
"""
```

**Checklist scoring (per item)**:

```python
# code/judge/scorer_prompt.py
SCORER_PROMPT = """\
Evaluate this checklist item for a visualization.

Question: {question}
Evidence hint: {evidence_hint}

Visualization (DSL):
{viz_dsl}

Visualization (parsed structure):
{viz_parsed}

Source documents:
{sources}

(For search_query_quality axis only) Sub-queries used:
{sub_queries}

Answer with exactly one of: YES | NO | PARTIAL
Then give 1-sentence justification.

Format:
{{"answer": "YES|NO|PARTIAL", "justification": "..."}}
"""
```

#### 6.2 DSL parser

```python
# code/judge/dsl_parser.py
def parse_mermaid_flowchart(dsl: str) -> dict:
    # Use mermaid-py or regex
    nodes = re.findall(r"(\w+)\[(.+?)\]", dsl)
    edges = re.findall(r"(\w+)\s*-->\s*(\w+)", dsl)
    return {"nodes": nodes, "edges": edges, "num_nodes": len(nodes), "num_edges": len(edges)}

def parse_chartjs(dsl: str) -> dict:
    spec = json.loads(dsl)
    return {
        "type": spec.get("type"),
        "labels": spec.get("data", {}).get("labels", []),
        "datasets": spec.get("data", {}).get("datasets", []),
    }

def parse_viz(dsl: str, viz_type: str) -> dict:
    if viz_type.startswith("mermaid"): return parse_mermaid_flowchart(dsl)
    elif viz_type.startswith("chartjs"): return parse_chartjs(dsl)
    else: return {"raw": dsl}
```

#### 6.3 Run judge

```python
# code/judge/run_judge.py
import openai, json
from checklist_gen_prompt import CHECKLIST_GEN_PROMPT
from scorer_prompt import SCORER_PROMPT
from dsl_parser import parse_viz

JUDGE_MODEL_GEN = "gpt-5"        # generate checklists
JUDGE_MODEL_SCORE = "claude-opus-4-6"  # score (cross-model for cross-judge)

with open("outputs/prototype/viz/all.json") as f:
    viz_results = json.load(f)
with open("data/prototype/bundles/all.json") as f:
    bundles = {b['bundle_id']: b for b in json.load(f)}

scored_results = []
for r in viz_results:
    bundle = bundles[r['bundle_id']]
    sources = "\n\n---\n\n".join(
        f"[{d['title']}]\n{d['content']}" for d in bundle['docs']
    )
    # Step 1: generate checklist
    cl_prompt = CHECKLIST_GEN_PROMPT.format(
        query=r['query'], query_type=r['query_type'], sources=sources,
    )
    cl_resp = openai_call(JUDGE_MODEL_GEN, cl_prompt, json_mode=True)
    checklist = json.loads(cl_resp)

    # Step 2: score each item (use Claude for cross-judge)
    viz_parsed = parse_viz(r['viz_dsl'], r['viz_type'])
    item_scores = []
    for item in checklist:
        sc_prompt = SCORER_PROMPT.format(
            question=item['question'],
            evidence_hint=item['evidence_hint'],
            viz_dsl=r['viz_dsl'],
            viz_parsed=json.dumps(viz_parsed, indent=2),
            sources=sources,
            sub_queries="\n".join(r.get('sub_queries', [])) or "(none)",
        )
        sc_resp = anthropic_call(JUDGE_MODEL_SCORE, sc_prompt, json_mode=True)
        item_scores.append({**item, **json.loads(sc_resp)})

    # Aggregate by axis
    axis_scores = {}
    for axis in ["faithfulness", "coverage", "type_appropriateness", "search_query_quality"]:
        axis_items = [it for it in item_scores if it['axis'] == axis]
        if not axis_items: continue
        score = sum({"YES": 1.0, "PARTIAL": 0.5, "NO": 0.0}[it['answer']] for it in axis_items) / len(axis_items)
        axis_scores[axis] = score

    scored_results.append({**r, "checklist": item_scores, "axis_scores": axis_scores})

with open("outputs/prototype/judge_scores/all.json", "w") as f:
    json.dump(scored_results, f, indent=2)
```

#### 6.4 Day 9-10 verification gate

- [ ] All 100 viz scored across 4 axes (search_query_quality only for S4)
- [ ] Average axis score in [0.2, 0.8] range (not all max/min — discriminative)
- [ ] Checklist generation cost ≤ $30 (50 unique (query, bundle) pairs × 1 gen call)
- [ ] Scoring cost ≤ $40 (100 viz × 12 items × 1 call)

---

### **Day 11-12: Human Spot Validation**

#### 7.1 Setup

> **Option A (recommended for prototype)**: Self + 1 colleague rate 30 viz manually. Faster, free, sufficient for Week 0.
> **Option B**: Prolific 30 viz × 2 raters × 4 axis (~$80, slower setup).

For Week 0, **Option A** is sufficient. Reserve Prolific for Week 4 full validation.

#### 7.2 Rating UI

```python
# code/utils/rating_cli.py — simple CLI rating interface
import json, csv
results = json.load(open("outputs/prototype/judge_scores/all.json"))
sample = random.sample(results, 30)  # 30 viz to rate

with open("outputs/prototype/human_ratings/template.csv", "w") as f:
    w = csv.writer(f)
    w.writerow(["query_id", "strategy", "query", "viz_dsl", "viz_type",
                "rater", "faith_score", "coverage_score", "type_score", "notes"])
    for r in sample:
        w.writerow([r['query_id'], r['strategy'], r['query'][:100],
                    r['viz_dsl'][:300], r['viz_type'], "", "", "", "", ""])

# Each rater fills in: faith_score (0/0.5/1), coverage_score (0/0.5/1), type_score (0/0.5/1)
# Same scale as judge YES/PARTIAL/NO
```

#### 7.3 Rating protocol (give to each rater)

```
For each viz:
1. Read the query and the viz DSL.
2. Mentally render the viz.
3. Score on 3 axes (0=NO, 0.5=PARTIAL, 1=YES):
   - Faithfulness: Does the viz only contain claims supported by the source docs?
                   (If you don't have access to docs, score conservatively based on plausibility.)
   - Coverage: Does the viz address the main aspects of the query?
   - Type appropriateness: Is the viz type (chart/diagram/mindmap) appropriate for the query?
4. Add notes if anything is borderline.

Time per viz: ~3 minutes. 30 viz = ~1.5 hours per rater.
```

#### 7.4 Day 11-12 verification gate

- [ ] 30 viz × 2 raters = 60 ratings collected
- [ ] Inter-rater Cohen's κ ≥ 0.5 on each axis (else: refine rubric and re-rate 10)

---

### **Day 13-14: Analysis & Go/No-Go Decision**

#### 8.1 Notebook: `notebooks/W0_analysis.ipynb`

```python
import pandas as pd, json
from scipy.stats import spearmanr, pearsonr

# Load
results = pd.DataFrame(json.load(open("outputs/prototype/judge_scores/all.json")))
ratings = pd.read_csv("outputs/prototype/human_ratings/all.csv")
# (assume merged)

# === ANCHOR 1: Judge ↔ Human Spearman per axis ===
for axis in ["faithfulness", "coverage", "type_appropriateness"]:
    judge_col = f"axis_{axis}"
    human_col = f"human_{axis}_mean"  # avg across 2 raters
    merged = results.merge(ratings.groupby('query_id')[human_col].mean().reset_index(), on='query_id')
    r, p = spearmanr(merged[judge_col], merged[human_col])
    print(f"{axis}: Spearman r = {r:.3f}, p = {p:.3f}")

# === HEADLINE: S4 vs S1 effect ===
agg = results.groupby(['strategy', 'query_type'])[['axis_faithfulness', 'axis_coverage']].mean()
print(agg)

# === Per query type effect ===
for qtype in results['query_type'].unique():
    s1 = results[(results['strategy']=='S1') & (results['query_type']==qtype)]
    s4 = results[(results['strategy']=='S4') & (results['query_type']==qtype)]
    delta = s4[['axis_faithfulness','axis_coverage']].mean().mean() - s1[['axis_faithfulness','axis_coverage']].mean().mean()
    print(f"{qtype}: S4 - S1 = {delta:+.3f}")

# === Cost ===
print("Total API spend:", results['cost_usd'].sum())
print("Avg S4 sub-queries:", results[results['strategy']=='S4']['sub_queries'].apply(len).mean())
```

#### 8.2 Go/No-Go Report (`WEEK0_REPORT.md`)

Template:

```markdown
# Week 0 Prototype Report — QG-MDV
Date: YYYY-MM-DD

## Decision: GO / REFRAME / JUDGE-FIX / PIVOT

## Numbers
- Bundles: 30
- Queries: 50 (10 per type × 5 types)
- Viz generated: 100 (50 × 2 strategies)
- Total API cost: $XX
- Total wall time: XX days

## Judge Validation (Anchor 1)
| Axis | Spearman r | n | Verdict |
|---|---|---|---|
| Faithfulness | X.XX | 30 | OK / FAIL |
| Coverage | X.XX | 30 | OK / FAIL |
| Type appropriateness | X.XX | 30 | OK / FAIL |

Threshold: r ≥ 0.5 → judge usable, ≥ 0.65 → strong
Result: ...

## S4 vs S1 Effect (headline)
| Query type | S1 mean | S4 mean | Δ | Verdict |
|---|---|---|---|---|
| Quantitative | X.XX | X.XX | +X.XX | strong / modest / null |
| Relational | ... | ... | ... | ... |
| Temporal | ... | ... | ... | ... |
| Hierarchical | ... | ... | ... | ... |
| Comparative | ... | ... | ... | ... |

## Cost-quality
S4 cost / S1 cost ratio: X.X×
Quality margin: +X%p

## Decision rationale
[1 paragraph based on numbers above]

## Next-week plan
- If GO: scale to 200 bundles, add S2/S3, add 4 more LLMs
- If REFRAME: switch focus from "S4 method paper" to "diagnostic + framework paper"
- If JUDGE-FIX: try Claude Opus 4.6 as both checklist gen + scorer
- If PIVOT: fall back to mixed metric (NLI + structural) and re-evaluate
```

#### 8.3 Day 13-14 verification gate

- [ ] `WEEK0_REPORT.md` written with all numbers filled
- [ ] Decision documented with rationale
- [ ] If GO: Week 1 task list drafted
- [ ] If REFRAME / PIVOT: alternative plan drafted

---

## 3. File & Directory Structure (final state of Week 0)

```
visubench/
├── code/
│   ├── pipelines/
│   │   ├── base.py
│   │   ├── s1_direct.py
│   │   └── s4_agentic.py        ← user pipeline wiring
│   ├── judge/
│   │   ├── checklist_gen_prompt.py
│   │   ├── scorer_prompt.py
│   │   ├── dsl_parser.py
│   │   └── run_judge.py
│   ├── utils/
│   │   ├── load_hotpotqa.py
│   │   ├── load_multinews.py
│   │   ├── load_arxiv.py
│   │   ├── load_10k.py
│   │   ├── merge_bundles.py
│   │   ├── query_gen_prompt.py
│   │   └── generate_queries.py
│   └── run_prototype.py
├── data/
│   └── prototype/
│       ├── bundles/
│       │   ├── hotpot.json
│       │   ├── multinews.json
│       │   ├── arxiv.json
│       │   ├── 10k.json
│       │   └── all.json (30 bundles)
│       ├── queries/
│       │   └── all.json (50 queries)
│       └── sources/
│           └── 10k_raw/...
├── outputs/
│   └── prototype/
│       ├── viz/
│       │   └── all.json (100 viz)
│       ├── judge_scores/
│       │   └── all.json (100 scored)
│       └── human_ratings/
│           └── all.csv (60 ratings)
├── notebooks/
│   └── W0_analysis.ipynb
├── WEEK0_REPORT.md
└── QG-MDV_Week0_Action_Guide.md   ← this file
```

---

## 4. API Keys & Cost Budget

### 4.1 Required API access

| Provider | Model | Use | Set env var |
|---|---|---|---|
| OpenAI | gpt-5, gpt-4o-mini | viz gen + checklist gen | `OPENAI_API_KEY` |
| Anthropic | claude-opus-4-6 | scoring (cross-judge) | `ANTHROPIC_API_KEY` |
| (Optional) Google | gemini-2.5-pro | future weeks | `GOOGLE_API_KEY` |

### 4.2 Week 0 cost budget

| Item | Estimate |
|---|---|
| Query generation (50 × gpt-4o-mini) | $5 |
| Viz generation S1 (50 × gpt-5) | $9 |
| Viz generation S4 (50 × gpt-5, ~3 steps avg) | $27 |
| Checklist generation (50 × gpt-5) | $25 |
| Checklist scoring (100 viz × 12 items × claude-opus-4-6) | $35 |
| Buffer (retries, errors) | $20 |
| **Week 0 total** | **~$120** |

**Stop-loss**: if Week 0 spend exceeds $200, halt and audit.

---

## 5. Risk Register & Mitigation

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| User pipeline (S4) has incompatible interface | Med | High | Day 1: spend 2h reading user pipeline, write adapter spec before Day 5 |
| GPT-5 / Claude rate limits | Med | Med | Use OpenAI/Anthropic batch API (50% discount, slower) |
| Mermaid render failures > 20% | Med | Med | Add format validation prompt-side; allow 2 retry; log failures |
| Judge-Human r < 0.5 | Med | High | Try cross-judge (gpt-5 score on opus-generated checklist or vice versa); simplify checklist to 6 items |
| S4 cost 3-5× S1 makes scaling infeasible | Low | Med | If single S4 call > $1, consider Qwen3-Coder-30B for S4 backbone |
| 10-K parsing fails | Low | Low | Replace with another company or use plain text from EDGAR |
| HotpotQA license / EDGAR throttling | Low | Low | Use random.seed(42), cache results; run downloads off-hours |

---

## 6. Success Criteria for Week 0 (Definition of Done)

A successful Week 0 produces:

1. ✅ 30 bundles, 50 queries, 100 viz outputs — all on disk
2. ✅ Judge-Human Spearman ≥ 0.5 on at least 2 of 3 axes (faithfulness, coverage, type)
3. ✅ Effect direction: |S4 mean - S1 mean| ≥ 0.05 in at least 1 query type, with **same sign** across faithfulness AND coverage axes
4. ✅ Cost ≤ $200 spent
5. ✅ `WEEK0_REPORT.md` with explicit decision (GO / REFRAME / JUDGE-FIX / PIVOT)
6. ✅ Week 1 plan drafted

If any of 1-5 fails, do NOT proceed to Week 1 without a documented mitigation.

---

## 7. Hand-off to Week 1 (if GO)

If decision is GO, Week 1's first action is:

> Scale from 30 → 200 bundles using the same source mix (HotpotQA 60, MultiNews 50, arXiv 50, 10-K 40). Reuse `code/utils/load_*.py` scripts with seed change. Run `merge_bundles.py` to produce the full benchmark v1.

Week 1 also adds:
- S2 (Standard RAG) and S3 (Query-Decompose) implementations
- 3 additional LLMs (Gemini 2.5 Pro, Qwen3-Coder-30B, DeepSeek V3.5)
- Query naturalness Prolific (50 × 3 raters)
- Anchor 2 deterministic metrics (M1-M4) implementation

---

## 8. Open questions for the human (defer if unsure)

- [ ] User pipeline의 정확한 entry point / invocation form? (Day 1 확인 필수)
- [ ] User pipeline이 multi-doc input을 어떤 form으로 받는가? (list of dicts? concatenated string? doc store handle?)
- [ ] User pipeline이 web search를 사용하나? (prototype에서는 doc-only로 ablate해서 fair compare)
- [ ] Mermaid version은? (v10+ vs v11+ syntax 차이 있음)
- [ ] Render check를 위한 Mermaid CLI는 설치되었나? (`npm install -g @mermaid-js/mermaid-cli`)

---

## 9. Quick-start checklist for Day 1 morning

```bash
# 1. Setup
cd D:\Downloads\visubench\visubench
python -m venv venv && source venv/bin/activate  # or Scripts\activate on Windows
pip install openai anthropic datasets arxiv sec-edgar-downloader scipy pandas selectolax

# 2. Set API keys
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."

# 3. Make folders
mkdir -p code/{pipelines,judge,utils} data/prototype/{bundles,queries,sources} outputs/prototype/{viz,judge_scores,human_ratings} notebooks

# 4. First action: read user pipeline code, write adapter spec
# Output: code/pipelines/s4_agentic.py with at least the interface stubbed
```

---

**This document is the operational source of truth for Week 0. Update `WEEK0_REPORT.md` as you go; do not modify this guide unless the user (researcher) approves a change.**
