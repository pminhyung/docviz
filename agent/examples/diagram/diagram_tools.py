"""
Unified Diagram & Mindmap Generation Custom Tool

Generates diagrams, charts, and mindmaps from document content.
- diagram_type="mindmap" → MINDMAP_SYSTEM_PROMPT + D3.js mindmap-renderer (:3004)
- diagram_type in CHART_TYPES → CHART_SYSTEM_PROMPT + Chart.js interactive HTML (:3005/render-chart)
- diagram_type in MERMAID_TYPES → DIAGRAM_SYSTEM_PROMPT + mermaid SVG (:3005/render)

Sidecar services (must be running):
  - mermaid-renderer   :3005  (SVG/PNG via mermaid.js + Chart.js interactive HTML)
  - mindmap-renderer   :3004  (D3.js interactive mindmap HTML/PNG/SVG)

Usage:
    /v2/run request:
    {
        "custom_tools_path": "examples/diagram/diagram_tools.py",
        "tool_secrets": {
            "MERMAID_API_URL": "http://localhost:3005",
            "MINDMAP_API_URL": "http://localhost:3004",
            "OUTPUT_DIR": "/path/to/output"
        }
    }

Tools defined:
    - generate_diagram: Document content → diagram/chart/mindmap
"""
import json
import os
import re
import time
import traceback
import urllib.request
import urllib.error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _http_post(url: str, payload: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ct = resp.headers.get("Content-Type", "")
        body = resp.read()
        if "application/json" in ct:
            return {"type": "json", "data": json.loads(body)}
        else:
            return {"type": "binary", "data": body, "content_type": ct}


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _get_output_dir(context: dict) -> str:
    secrets = context.get("tool_secrets") or {}
    d = secrets.get("OUTPUT_DIR", "/tmp/diagram_output")
    os.makedirs(d, exist_ok=True)
    return d


def _get_api_url(context: dict, key: str, default: str) -> str:
    secrets = context.get("tool_secrets") or {}
    return secrets.get(key, default)


# ---------------------------------------------------------------------------
# Type pools — 3-way routing: chart (Chart.js) / mermaid / mindmap (D3.js)
# ---------------------------------------------------------------------------

CHART_TYPES = [
    "bar", "grouped-bar", "stacked-bar", "line", "combo",
    "pie", "donut", "scatter", "heatmap", "funnel", "waterfall", "subplot",
]

MERMAID_TYPES = [
    "flowchart", "sequenceDiagram", "gantt", "timeline",
    "quadrantChart", "xychart", "erDiagram", "stateDiagram-v2",
    "classDiagram", "sankey", "journey", "block",
    "kanban", "radar-beta", "zenuml",
]

ALL_TYPES = CHART_TYPES + MERMAID_TYPES + ["mindmap"]

# ---------------------------------------------------------------------------
# Mermaid diagram type pool — one-shot examples
# ---------------------------------------------------------------------------

DIAGRAM_EXAMPLES = {
    "flowchart": """\
flowchart TD
    A[Receive Application] --> B{Documents Complete?}
    B -->|Yes| C[Review Committee]
    B -->|No| D[Request Missing Docs]
    D --> A
    C --> E{Approved?}
    E -->|Yes| F[Issue Certificate]
    E -->|No| G[Send Rejection Notice]""",

    "sequenceDiagram": """\
sequenceDiagram
    participant U as User
    participant S as Server
    participant DB as Database
    U->>S: Login Request
    S->>DB: Validate Credentials
    DB-->>S: User Record
    alt Valid
        S-->>U: 200 OK + Token
    else Invalid
        S-->>U: 401 Unauthorized
    end""",

    "gantt": """\
gantt
    title Project Schedule
    dateFormat YYYY-MM-DD
    section Phase 1
        Requirements    :a1, 2024-01-01, 15d
        Design          :a2, after a1, 10d
    section Phase 2
        Development     :b1, after a2, 30d
        Testing         :b2, after b1, 15d
    section Phase 3
        Deployment      :c1, after b2, 5d""",

    "timeline": """\
timeline
    title Company Milestones
    section 2020
        Q1 : Founded
        Q3 : Series A Funding
    section 2021
        Q1 : Product Launch
        Q4 : 100K Users
    section 2022
        Q2 : International Expansion
        Q4 : IPO""",

    "quadrantChart": """\
quadrantChart
    title Product Priority Matrix
    x-axis Low Impact --> High Impact
    y-axis Low Effort --> High Effort
    quadrant-1 Strategic Investment
    quadrant-2 Quick Wins
    quadrant-3 Deprioritize
    quadrant-4 Major Projects
    Feature A: [0.8, 0.3]
    Feature B: [0.2, 0.7]
    Feature C: [0.7, 0.8]
    Feature D: [0.3, 0.2]""",

    "xychart": """\
xychart-beta
    title Quarterly Revenue (Million USD)
    x-axis [Q1, Q2, Q3, Q4]
    y-axis "Revenue" 0 --> 500
    bar [120, 180, 250, 380]
    line [120, 180, 250, 380]""",

    "erDiagram": """\
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : "ordered in"
    CUSTOMER {
        int id PK
        string name
        string email
    }
    ORDER {
        int id PK
        date created_at
        string status
    }
    PRODUCT {
        int id PK
        string name
        float price
    }""",

    "stateDiagram-v2": """\
stateDiagram-v2
    [*] --> Draft
    Draft --> UnderReview : Submit
    UnderReview --> Approved : Approve
    UnderReview --> Rejected : Reject
    Rejected --> Draft : Revise
    Approved --> Published : Publish
    Published --> Archived : Archive
    Published --> Draft : Unpublish
    Archived --> [*]""",

    "classDiagram": """\
classDiagram
    class Document {
        +int id
        +String title
        +String content
        +getPages()
        +search(query)
    }
    class Page {
        +int number
        +String text
        +List~Image~ images
    }
    class Image {
        +String url
        +String caption
    }
    Document "1" --> "*" Page : contains
    Page "1" --> "*" Image : has""",

    "sankey": """\
sankey-beta

Budget,Personnel,450
Budget,Infrastructure,280
Budget,Marketing,170
Personnel,Engineering,300
Personnel,Operations,150
Infrastructure,Cloud,200
Infrastructure,Hardware,80
Marketing,Digital,120
Marketing,Events,50""",

    "journey": """\
journey
    title Customer Onboarding Experience
    section Discovery
        Visit website: 5: Customer
        Read documentation: 3: Customer
    section Sign Up
        Create account: 4: Customer
        Verify email: 3: Customer, System
    section First Use
        Complete tutorial: 4: Customer
        Create first project: 5: Customer""",

    "block": """\
block-beta
    columns 3
    space Client space
    space:3
    LB["Load Balancer"]
    space:3
    API1["API Server 1"] API2["API Server 2"] API3["API Server 3"]
    space:3
    DB[("Database")] Cache["Cache"] Queue["Message Queue"]

    Client --> LB
    LB --> API1
    LB --> API2
    LB --> API3
    API1 --> DB
    API2 --> Cache
    API3 --> Queue""",

    "kanban": """\
kanban
    column1[To Do]
        task1[Define Requirements]
        task2[Design Architecture]
    column2[In Progress]
        task3[Implement API]
        task4[Write Tests]
    column3[Done]
        task5[Setup CI/CD]
        task6[Deploy Staging]""",

    "radar-beta": """\
radar-beta
    title Capability Assessment
    axis Security, Performance, Scalability, Usability, Reliability
    curve Product A {85, 70, 90, 60, 80}
    curve Product B {60, 90, 70, 85, 75}
    max 100""",

    "zenuml": """\
zenuml
    @Actor Client
    @Lambda APIGateway
    @DynamoDB Database
    Client->APIGateway.request() {
        APIGateway->Database.query() {
            return result
        }
        return response
    }""",
}


# ---------------------------------------------------------------------------
# Mermaid diagram system prompt
# ---------------------------------------------------------------------------

DIAGRAM_SYSTEM_PROMPT = """\
You are a mermaid diagram generator. Given document content and a diagram type, produce ONLY valid mermaid source code.

Rules:
1. Output ONLY the mermaid source code. No markdown fences, no explanation, no preamble.
2. Use descriptive labels derived from the document content. Do NOT use placeholder text.
3. Keep the diagram focused and readable: 5-15 nodes for graph types, 3-8 items for list types.
4. For data-oriented types (pie, xychart, gantt), extract actual values from the document. If exact values are not available, use reasonable estimates based on the text and note it with a comment.
5. Ensure syntax is strictly valid for the specified diagram type.
6. CRITICAL: ALL labels MUST use the SAME language as the source document. Korean document → Korean labels ONLY. English document → English labels ONLY. NEVER translate labels to a different language.

Diagram type: {diagram_type}

Reference example for this type (follow this syntax exactly):
{one_shot_example}

Now generate mermaid source for the following document content."""


# ---------------------------------------------------------------------------
# Chart system prompt (Chart.js via DSL)
# ---------------------------------------------------------------------------

CHART_DSL_EXAMPLES = {
    "bar": """\
chart:bar
title: Quarterly Revenue (Billion KRW)
x: [Q1, Q2, Q3, Q4]
series:
  Revenue: [320, 450, 380, 520]""",

    "grouped-bar": """\
chart:grouped-bar
title: Segment Revenue by Year
x: [Albums, Concerts, MD, Content, Fan Club]
series:
  2023: [520, 246, 319, 204, 200]
  2024E: [568, 452, 398, 320, 213]""",

    "stacked-bar": """\
chart:stacked-bar
title: Revenue Composition by Year
x: [2022, 2023, 2024E]
series:
  Albums: [480, 520, 568]
  Concerts: [200, 246, 452]
  MD: [280, 319, 398]""",

    "line": """\
chart:line
title: EPS & PER Trend
x: [2021, 2022, 2023E, 2024E]
series:
  EPS: [1200, 1500, 1800, 2400]
  PER: [25, 22, 18, 15]""",

    "combo": """\
chart:combo
title: Revenue and Operating Margin
x: [2021, 2022, 2023E, 2024E]
y-left: "Revenue (Billion KRW)" 0 --> 2500
y-right: "Operating Margin (%)" 0 --> 15
bar y-left Revenue: [1257, 1665, 1608, 2071]
line y-right Operating Margin: [7.5, 8.9, 8.1, 12.8]""",

    "pie": """\
chart:pie
title: Revenue by Segment (2024E)
series:
  Albums: 568
  Concerts: 452
  MD: 398
  Content: 320
  Fan Club: 213""",

    "donut": """\
chart:donut
title: Market Share
series:
  Company A: 35
  Company B: 28
  Company C: 22
  Others: 15""",

    "scatter": """\
chart:scatter
title: PER vs EPS Relationship
x: PER
y: EPS (KRW)
series:
  Data Points: [[25, 1200], [22, 1500], [18, 1800], [15, 2400]]""",

    "heatmap": """\
chart:heatmap
title: Quarterly Performance by Segment
x: [Q1, Q2, Q3, Q4]
y: [Albums, Concerts, MD, Content]
data:
  [85, 92, 78, 95]
  [60, 75, 88, 70]
  [72, 68, 82, 90]
  [55, 65, 70, 80]""",

    "funnel": """\
chart:funnel
title: R&D Budget by Phase
stages:
  Basic Research: 500
  Applied Research: 380
  Development: 250
  Pilot: 150
  Commercialization: 80""",

    "waterfall": """\
chart:waterfall
title: Revenue Bridge (2023 → 2024)
stages:
  2023 Base: 1608
  Album Growth: 48
  Concert Growth: 206
  MD Growth: 79
  Content Growth: 116
  Fan Club Growth: 14""",

    "subplot": """\
chart:subplot 1x2
---
type: bar
title: Revenue
x: [2022, 2023E, 2024E]
series:
  Company A: [1665, 1608, 2071]
  Company B: [1200, 1350, 1500]
---
type: line
title: Operating Margin (%)
x: [2022, 2023E, 2024E]
series:
  Company A: [8.9, 8.1, 12.8]
  Company B: [6.5, 7.2, 9.1]""",
}

CHART_SYSTEM_PROMPT = """\
You are a data chart generator. Given document content and a chart type, produce ONLY valid chart DSL source code.

Rules:
1. Output ONLY the chart DSL code. No markdown fences, no explanation, no preamble.
2. Use ONLY exact numerical values extracted from the document. NEVER fabricate or estimate data.
3. If exact values are not available for the requested chart, add a comment: %% Note: values estimated from context
4. Keep charts focused: max 8 categories on x-axis, max 6 series.
5. CRITICAL: ALL labels (title, series names, x-axis labels) MUST use the SAME language as the source document. Korean document → Korean labels ONLY. NEVER translate.
6. Add %% Source: [Index] comments to cite data sources.

Chart type: {chart_type}

DSL format reference:
- First line: chart:{chart_type}
- title: <descriptive title>
- x: [category1, category2, ...]
- series: (indented name: [values])
- For combo: y-left/y-right axis config, bar/line series with axis binding
- For subplot: chart:subplot <rows>x<cols>, panels separated by ---

Reference example (follow this syntax exactly):
{one_shot_example}

Now generate chart DSL for the following document content."""


# ---------------------------------------------------------------------------
# Mindmap system prompt (from mindmap_tools.py)
# ---------------------------------------------------------------------------

MINDMAP_SYSTEM_PROMPT = """\
Convert the document content into a mindmap markdown. Output ONLY the markdown.

The input includes a user query and document source material. The source may be:
1. A structured markdown summary with [index] citations (from ReadFullDocument)
2. A JSON array of page objects: [{"Index": N, "filename": "...", "content": "..."}]

Each [index] refers to a globally unique page Index from the source document.
Cite using [index] form (e.g. [1][2][4]). Preserve citations exactly — do not change, guess, or omit them.

Structure the mindmap to address the user's query focus. If the user asks for comparison, organize by comparison axes. If the user asks for a specific topic, emphasize that topic.

Format:
## Theme Name
- Topic name [1][2]
  - Sub-detail [1]
  - Sub-detail [3]

## Relationships
- "Topic A" → supports → "Topic B"

Rules:
1. EVERY topic and sub-detail MUST have at least one [index] citation. Copy citations from the input source. If a topic spans multiple pages, include all relevant [index] references. Do NOT leave any line without citations. Do NOT use [Page X] form.
2. NEVER include numbers, percentages, amounts, or data values. Write only descriptive topic names.
   BAD: "Revenue 2,071 billion won [1]"
   GOOD: "Revenue and profit forecast [1][6]"
3. 3-7 themes, 2-4 topics per theme, 1-3 sub-details per topic.
4. End with ## Relationships (2-5 semantic links). No sequential links (Ch1→Ch2).
5. For multi-document input (contains [Document 1] and [Document 2] sections):
   You MUST create themes from BOTH documents. Do NOT skip any document.
   Use ## [Doc 1] Topic / ## [Doc 2] Topic to distinguish sources.
   If the query asks for comparison, organize by comparison axes (e.g. ## Revenue Comparison, ## Strategy Comparison).
6. CRITICAL: Output ALL topic names and sub-details in the SAME LANGUAGE as the source document.
   If the document is in Korean, ALL labels must be in Korean. If in English, use English.
   NEVER translate labels to a different language. Preserve the original language exactly."""


MINDMAP_MERMAID_SYSTEM_PROMPT = """\
Convert the document content into a Mermaid mindmap. Output ONLY the mermaid source code.

The input includes a user query and document source material. Each [index] refers to a globally unique page index.

Structure the mindmap to address the user's query focus. If the user asks for comparison, organize by comparison axes.

Format (Mermaid mindmap syntax — indentation matters, 2 spaces per depth level):
mindmap
  root((Central Topic))
    Theme A
      Topic A1
        Sub-detail
        Sub-detail
      Topic A2
        Sub-detail
    Theme B
      Topic B1
      Topic B2

Rules:
1. First line MUST be exactly `mindmap`. Second line MUST be `  root((Central Topic))`.
2. Use 2-space indentation per depth level. Do NOT use tabs. Do NOT use bullet markers (-, *).
3. Do NOT include citation brackets like [1][2] in Mermaid output — plain text labels only.
4. NEVER include numbers, percentages, amounts, or data values inside labels.
   BAD: "Revenue 2071 billion won"
   GOOD: "Revenue and profit forecast"
5. 3-7 themes, 2-4 topics per theme, 1-3 sub-details per topic. Max depth 4 below root.
6. If a label contains special characters (parentheses, colons, quotes), wrap it in double quotes: `["My: label"]`.
7. Output ALL labels in the SAME LANGUAGE as the source document. NEVER translate.
8. Do NOT wrap output in markdown fences (```). Do NOT include any explanation before or after the mindmap block."""


# ---------------------------------------------------------------------------
# Mermaid post-processing
# ---------------------------------------------------------------------------

_TYPE_KEYWORDS = {
    "flowchart": ["flowchart", "graph"],
    "sequenceDiagram": ["sequenceDiagram"],
    "gantt": ["gantt"],
    "timeline": ["timeline"],
    "quadrantChart": ["quadrantChart"],
    "xychart": ["xychart-beta", "xychart"],
    "erDiagram": ["erDiagram"],
    "stateDiagram-v2": ["stateDiagram-v2", "stateDiagram"],
    "classDiagram": ["classDiagram"],
    "sankey": ["sankey-beta", "sankey"],
    "journey": ["journey"],
    "block": ["block-beta", "block"],
    "kanban": ["kanban"],
    "radar-beta": ["radar-beta", "radar"],
    "zenuml": ["zenuml"],
}


def _strip_llm_wrapper(text: str) -> str:
    """Strip <think> blocks and code fences from LLM output."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    fence_match = re.search(r"```(?:\w+)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        text = re.sub(r"```(?:\w+)?\s*\n?", "", text)
        text = re.sub(r"```\s*$", "", text)
    return text.strip()


def _extract_mermaid_source(text: str, expected_type: str) -> str:
    """Extract and validate mermaid source from LLM output."""
    text = _strip_llm_wrapper(text)

    valid_starts = _TYPE_KEYWORDS.get(expected_type, [expected_type])
    if not any(text.startswith(kw) for kw in valid_starts):
        for kw in valid_starts:
            idx = text.find(kw)
            if idx >= 0:
                text = text[idx:]
                break
        else:
            text = f"{valid_starts[0]}\n{text}"

    return text


def _render_mermaid(source: str, context: dict, fmt: str = "svg",
                    theme: str = "corporate") -> str:
    """Send mermaid source to sidecar for rendering. Returns saved file path."""
    api_url = _get_api_url(context, "MERMAID_API_URL", "http://localhost:3005")
    output_dir = _get_output_dir(context)

    try:
        resp = _http_post(f"{api_url}/render", {
            "mermaid_source": source,
            "format": fmt,
            "theme": theme,
        }, timeout=30)
    except Exception as e:
        print(f"[diagram] Render request failed: {e}")
        return ""

    ext = "png" if fmt == "png" else "svg"
    filename = f"diagram_{_timestamp()}.{ext}"
    filepath = os.path.join(output_dir, filename)

    if resp["type"] == "binary":
        with open(filepath, "wb") as f:
            f.write(resp["data"])
        print(f"[diagram] Rendered {ext.upper()}: {filepath} ({len(resp['data'])} bytes)")
        return filepath
    elif resp["type"] == "json" and "error" in resp.get("data", {}):
        print(f"[diagram] Render error: {resp['data']}")
        return ""

    return ""


# ---------------------------------------------------------------------------
# Chart DSL post-processing & rendering
# ---------------------------------------------------------------------------

def _extract_chart_dsl(text: str, expected_type: str) -> str:
    """Extract chart DSL from LLM output, stripping thinking/fences.

    Also strips any leading `%% ...` comment lines (qwen397b often prepends a
    `%% Note: ...` explanatory comment which the chart sidecar parser rejects
    with HTTP 422 "Invalid chart header"). Inline comments inside the DSL
    body remain untouched.
    """
    text = _strip_llm_wrapper(text)

    # Strip any leading `%%` comment lines or blank lines so the first
    # non-empty line is `chart:<type>`.
    lines = text.splitlines()
    drop = 0
    for line in lines:
        s = line.strip()
        if s == "" or s.startswith("%%"):
            drop += 1
        else:
            break
    if drop:
        text = "\n".join(lines[drop:])

    if not text.startswith("chart:"):
        idx = text.find("chart:")
        if idx >= 0:
            text = text[idx:]
        else:
            text = f"chart:{expected_type}\n{text}"

    return text


def _render_chart(source: str, context: dict, theme: str = "corporate") -> str:
    """Send chart DSL to /render-chart endpoint. Returns saved HTML file path."""
    api_url = _get_api_url(context, "MERMAID_API_URL", "http://localhost:3005")
    output_dir = _get_output_dir(context)

    try:
        resp = _http_post(f"{api_url}/render-chart", {
            "chart_source": source,
            "theme": theme,
        }, timeout=30)
    except Exception as e:
        print(f"[chart] Render request failed: {e}")
        return ""

    if resp["type"] == "json":
        data = resp.get("data", {})
        if "error" in data:
            print(f"[chart] Render error: {data}")
            return ""
        html = data.get("html", "")
        if html:
            filename = f"chart_{_timestamp()}.html"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"[chart] Rendered HTML: {filepath} ({len(html)} bytes)")
            return filepath

    return ""


# ---------------------------------------------------------------------------
# Mindmap post-processing & parsing (from mindmap_tools.py)
# ---------------------------------------------------------------------------

# SYNC-SOURCE: Functions below are copied from mindmap_tools.py for custom tool self-containment.
# Source of truth: agent/examples/mindmap/mindmap_tools.py
# Copied: _postprocess_mindmap_markdown, _extract_visual_elements, _parse_markdown_to_nodes,
#          _correct_page_refs, _build_index_to_page_map, _resolve_citations,
#          _auto_attach_visual_children, _attach_page_snippets

def _postprocess_mindmap_markdown(text: str) -> str:
    """Code-based post-processing to enforce format rules. 0 LLM cost."""
    text = re.sub(r'\[Page\s*(\d+)\]', r'[\1]', text, flags=re.IGNORECASE)
    lines = text.strip().split("\n")
    result = []
    in_content = False
    last_cite = None

    for line in lines:
        stripped = line.rstrip()
        if not in_content:
            if stripped.startswith("## "):
                in_content = True
            else:
                continue

        cite_match = re.findall(r'\[\d+\]', stripped)
        if cite_match:
            last_cite = cite_match[-1]

        if re.match(r'^  *- ', stripped):
            cleaned = re.sub(r'\b\d[\d,.]+\s*(%|원|십억원|억원|만|천|달러|billion|million|trillion)\b', '', stripped)
            cleaned = re.sub(r'\b\d{1,4}\s*년\b', '', cleaned)
            cleaned = re.sub(r'\s{2,}', ' ', cleaned).rstrip()
            content_after = re.sub(r'^  *- ', '', cleaned).strip()
            content_after = re.sub(r'\[\d+\]', '', content_after).strip()
            if len(content_after) < 3:
                continue
            if not re.search(r'\[\d+\]', cleaned) and last_cite:
                cleaned = cleaned.rstrip() + " " + last_cite
            result.append(cleaned)
        else:
            result.append(stripped)

    return "\n".join(result)


def _extract_visual_elements(context: dict) -> list:
    """Extract image/table metadata from raw docai JSON. Code only, 0 LLM."""
    secrets = context.get("tool_secrets") or {}
    doc_json_path = secrets.get("DOC_JSON_PATH")
    if not doc_json_path or not os.path.exists(doc_json_path):
        return []
    try:
        with open(doc_json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    outputs = raw.get("outputs", [])
    if not outputs:
        return []
    images_dict = outputs[0].get("images", {})
    elements = []
    for page_str, page_data in images_dict.items():
        if not page_str.isdigit():
            continue
        if isinstance(page_data, dict):
            results = page_data.get("results", [])
        elif isinstance(page_data, list):
            results = page_data
        else:
            continue
        for item in results:
            if not isinstance(item, dict):
                continue
            caption = item.get("caption", "")
            description = item.get("description", "")
            if not caption and not description:
                continue
            elements.append({
                "page": int(page_str),
                "caption": caption,
                "description": description,
                "category": (item.get("Category") or "figure").lower(),
                "image_path": item.get("images", ""),
            })
    elements.sort(key=lambda e: e["page"])
    return elements


def _parse_markdown_to_nodes(text: str, visual_elements: list = None) -> tuple:
    """Parse structured markdown → nodes/edges arrays. Pure code, 0 LLM calls."""
    visual_elements = visual_elements or []
    ve_by_page = {}
    for ve in visual_elements:
        ve_by_page.setdefault(ve["page"], []).append(ve)

    nodes = []
    edges = []

    visual_ref_pattern = re.compile(
        r'\[(차트|표|그림|chart|table|figure|diagram)\s*p?\.?\s*(\d+)\]',
        re.IGNORECASE,
    )
    page_ref_pattern = re.compile(r'\[(?:page|p)?\s*\.?\s*(\d+)\]', re.IGNORECASE)
    CATEGORY_MAP = {
        "차트": "chart", "chart": "chart",
        "표": "table", "table": "table",
        "그림": "figure", "figure": "figure",
        "diagram": "diagram",
    }

    def _extract_page_ref(text_str):
        vm = visual_ref_pattern.search(text_str)
        if vm:
            return int(vm.group(2))
        pm = page_ref_pattern.search(text_str)
        if pm:
            return int(pm.group(1))
        return None

    def _clean_label(text_str):
        cleaned = visual_ref_pattern.sub("", text_str)
        cleaned = page_ref_pattern.sub("", cleaned)
        return cleaned.strip()

    normalized = "\n" + text.strip()
    sections = re.split(r'\n##\s+', normalized)
    sections = [s for s in sections[1:] if s.strip()]

    content_sections = []
    relationship_section = None
    for s in sections:
        first_line = s.split("\n")[0].strip().lower()
        if first_line in ("관계", "relationships", "relations", "cross-references"):
            relationship_section = s
        else:
            content_sections.append(s)

    theme_ids = []
    theme_counter = 0
    for section in content_sections:
        lines = section.split("\n")
        theme_label_raw = lines[0].strip()
        if not theme_label_raw:
            continue

        tid = f"theme_{theme_counter}"
        theme_counter += 1
        theme_ids.append(tid)
        theme_label = _clean_label(theme_label_raw)

        topic_nodes = []
        current_topic = None
        current_leaves = []
        for line in lines[1:]:
            stripped = line.rstrip()
            if not stripped:
                continue
            if re.match(r'^  +- ', stripped):
                leaf_text = re.sub(r'^  +- ', '', stripped).strip()
                if leaf_text:
                    current_leaves.append(leaf_text)
            elif re.match(r'^- ', stripped):
                if current_topic is not None:
                    topic_nodes.append((current_topic, list(current_leaves)))
                current_topic = re.sub(r'^- ', '', stripped).strip()
                current_leaves = []
        if current_topic is not None:
            topic_nodes.append((current_topic, list(current_leaves)))

        topic_ids_list = []
        for j, (topic_text, leaf_texts) in enumerate(topic_nodes):
            tpid = f"{tid}_topic_{j}"
            topic_ids_list.append(tpid)

            leaf_ids = []
            for k, leaf_text in enumerate(leaf_texts):
                lid = f"{tpid}_leaf_{k}"
                leaf_ids.append(lid)
                page = _extract_page_ref(leaf_text)
                label = _clean_label(leaf_text) or leaf_text

                vm = visual_ref_pattern.search(leaf_text)
                if vm:
                    cat = CATEGORY_MAP.get(vm.group(1).lower(), "figure")
                    desc = ""
                    for ve in ve_by_page.get(page, []):
                        if ve["category"] == cat:
                            desc = ve.get("description", "")
                            break
                    nodes.append({
                        "id": lid, "label": label or f"{cat} (p.{page})",
                        "type": "visual", "description": desc,
                        "node_style": "visual",
                        "citation": {"page": page} if page else None,
                        "visual_ref": {"page": page, "category": cat, "caption": label},
                        "children": [],
                    })
                else:
                    nodes.append({
                        "id": lid, "label": label, "type": "leaf",
                        "description": "", "node_style": None,
                        "citation": {"page": page} if page else None,
                        "children": [],
                    })

            topic_page = _extract_page_ref(topic_text)
            topic_label = _clean_label(topic_text) or topic_text
            tvm = visual_ref_pattern.search(topic_text)
            topic_type = "topic"
            topic_visual_ref = None
            if tvm and not leaf_ids:
                cat = CATEGORY_MAP.get(tvm.group(1).lower(), "figure")
                topic_type = "visual"
                topic_visual_ref = {"page": topic_page, "category": cat, "caption": topic_label}

            node = {
                "id": tpid, "label": topic_label,
                "type": topic_type, "description": "",
                "node_style": "visual" if topic_type == "visual" else None,
                "citation": {"page": topic_page} if topic_page else None,
                "children": leaf_ids,
            }
            if topic_visual_ref:
                node["visual_ref"] = topic_visual_ref
            nodes.append(node)

        nodes.append({
            "id": tid, "label": theme_label or theme_label_raw,
            "type": "theme", "description": "",
            "node_style": None, "citation": None,
            "children": topic_ids_list,
        })

    nodes.insert(0, {
        "id": "root", "label": "Document Analysis",
        "type": "root", "description": "",
        "node_style": None, "citation": None,
        "children": theme_ids,
    })

    # Parse relationships → edges
    if relationship_section:
        rel_pattern = re.compile(
            r'["\u201c]([^"\u201d]+)["\u201d]\s*→\s*(\w+)\s*→\s*["\u201c]([^"\u201d]+)["\u201d]'
        )
        label_to_id = {}
        for n in nodes:
            if n["type"] in ("topic", "visual"):
                label_to_id[n["label"].lower().strip()] = n["id"]

        for line in relationship_section.split("\n"):
            m = rel_pattern.search(line)
            if m:
                src_label, rel_type, tgt_label = m.group(1), m.group(2), m.group(3)
                src_id = label_to_id.get(src_label.lower().strip())
                tgt_id = label_to_id.get(tgt_label.lower().strip())
                if not src_id:
                    for lbl, nid in label_to_id.items():
                        if src_label.lower() in lbl or lbl in src_label.lower():
                            src_id = nid
                            break
                if not tgt_id:
                    for lbl, nid in label_to_id.items():
                        if tgt_label.lower() in lbl or lbl in tgt_label.lower():
                            tgt_id = nid
                            break
                if src_id and tgt_id and src_id != tgt_id:
                    valid_rels = {"causes", "supports", "contrasts_with", "related_to", "leads_to"}
                    edges.append({
                        "source": src_id, "target": tgt_id,
                        "relationship": rel_type if rel_type in valid_rels else "related_to",
                        "label": f"{src_label} → {tgt_label}",
                    })

    # Citation inheritance
    node_map = {n["id"]: n for n in nodes}
    for n in nodes:
        if n.get("type") not in ("topic", "leaf", "visual") or n.get("citation"):
            continue
        for cid in n.get("children", []):
            child = node_map.get(cid)
            if child and child.get("citation"):
                n["citation"] = dict(child["citation"])
                break
    for n in nodes:
        if not n.get("citation") or n.get("type") not in ("topic", "theme"):
            continue
        for cid in n.get("children", []):
            child = node_map.get(cid)
            if child and not child.get("citation"):
                child["citation"] = dict(n["citation"])

    return nodes, edges


def _correct_page_refs(nodes: list, multi_docs: list):
    """Correct page references by fuzzy-matching node labels against page content."""
    if not multi_docs:
        return
    page_texts = {}
    for doc_idx, pages in enumerate(multi_docs):
        for page in pages:
            pg = page.get("page", 0)
            content = page.get("content", "").lower()
            if pg and content:
                page_texts[pg] = content
    if not page_texts:
        return
    for node in nodes:
        if node.get("type") not in ("topic", "visual", "leaf"):
            continue
        label = node.get("label", "").lower()
        if not label or len(label) < 3:
            continue
        keywords = [w for w in re.split(r'[\s/·,]+', label) if len(w) >= 2]
        if not keywords:
            continue
        best_page = None
        best_score = 0
        for pg, text in page_texts.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_page = pg
        if best_page and best_score >= max(2, len(keywords) * 0.4):
            current_page = (node.get("citation") or {}).get("page")
            if current_page != best_page:
                node["citation"] = {"page": best_page}
                if node.get("visual_ref"):
                    node["visual_ref"]["page"] = best_page


def _build_index_to_page_map(multi_docs: list, filenames: list) -> dict:
    """Build global Index → (doc_name, page) mapping for user-facing display."""
    idx_map = {}
    for doc_idx, pages in enumerate(multi_docs):
        doc_name = filenames[doc_idx] if doc_idx < len(filenames) else f"Doc {doc_idx+1}"
        for p in pages:
            idx_map[p.get("Index")] = {
                "doc_name": doc_name,
                "page": p.get("page", 0),
                "doc_idx": doc_idx + 1,
            }
    return idx_map


def _resolve_citations(nodes: list, idx_map: dict):
    """Convert global Index citations to user-facing doc_name + page."""
    for node in nodes:
        citation = node.get("citation")
        if not citation or not citation.get("page"):
            continue
        global_idx = citation["page"]
        if global_idx in idx_map:
            info = idx_map[global_idx]
            citation["doc_name"] = info["doc_name"]
            citation["doc_page"] = info["page"]
            citation["doc_idx"] = info["doc_idx"]
            node["description"] = node.get("description", "")
            if node.get("visual_ref"):
                node["visual_ref"]["page"] = info["page"]


def _auto_attach_visual_children(nodes: list, visual_elements: list):
    """Auto-attach visual element nodes to topics based on page citation match."""
    if not visual_elements:
        return
    ve_by_page = {}
    for ve in visual_elements:
        ve_by_page.setdefault(ve["page"], []).append(ve)
    existing_ids = {n["id"] for n in nodes}
    attached_pages = set()
    new_nodes = []
    for node in nodes:
        if node["type"] not in ("topic",):
            continue
        citation = node.get("citation")
        if not citation or not citation.get("page"):
            continue
        page = citation["page"]
        if page in attached_pages:
            continue
        for idx, ve in enumerate(ve_by_page.get(page, [])):
            cap = (ve.get("caption") or "").strip()
            if not cap or cap.lower() == "none":
                cap = (ve.get("description") or "")[:40].strip()
            if not cap or len(cap) < 3:
                continue
            vid = f"{node['id']}_ve_{ve['category']}_{page}_{idx}"
            if vid in existing_ids:
                continue
            existing_ids.add(vid)
            new_nodes.append({
                "id": vid,
                "label": f"{cap} (p.{page})",
                "type": "visual",
                "description": ve.get("description", ""),
                "node_style": "visual",
                "visual_ref": {"page": page, "category": ve["category"], "caption": cap},
                "citation": {"page": page},
                "children": [],
            })
            node["children"].append(vid)
        if ve_by_page.get(page):
            attached_pages.add(page)
    nodes.extend(new_nodes)


def _attach_page_snippets(nodes: list, multi_docs: list, max_snippet: int = 200):
    """Attach raw page content snippets to nodes with page references (tooltip용)."""
    page_lookup = {}
    for doc_idx, pages in enumerate(multi_docs):
        for page in pages:
            key = page.get("page", 0)
            content = page.get("content", "")
            if key and content:
                page_lookup[key] = content[:max_snippet]
    for node in nodes:
        citation = node.get("citation")
        if citation and citation.get("page") and not node.get("description"):
            pg = citation["page"]
            if pg in page_lookup:
                node["description"] = page_lookup[pg]


def _render_mindmap(markdown_text: str, context: dict) -> str:
    """Parse mindmap markdown → nodes/edges → post-process → render via sidecar."""
    # 1. Extract visual elements from docai JSON (code only, 0 LLM)
    visual_elements = _extract_visual_elements(context)

    # 2. Parse markdown → nodes/edges (with visual element awareness)
    nodes, edges = _parse_markdown_to_nodes(markdown_text, visual_elements)

    # 3. Post-processing pipeline (all code-only, 0 LLM)
    multi_docs = context.get("multi_docs") or []
    filenames = context.get("filenames") or []
    if multi_docs:
        _correct_page_refs(nodes, multi_docs)
    if visual_elements:
        _auto_attach_visual_children(nodes, visual_elements)
    if multi_docs:
        _attach_page_snippets(nodes, multi_docs)
        idx_map = _build_index_to_page_map(multi_docs, filenames)
        _resolve_citations(nodes, idx_map)

    output_dir = _get_output_dir(context)
    ts = _timestamp()

    # 4. Layout auto-selection based on node count
    n_themes = sum(1 for n in nodes if n.get("type") == "theme")
    n_visuals = sum(1 for n in nodes if n.get("type") == "visual")
    total = len(nodes)
    if total > 60:
        layout = "radial"
    elif n_visuals > 0 or total > 30:
        layout = "tree_lr"
    else:
        layout = "radial"

    # 5. Collapse depth auto-selection
    if total > 60:
        collapse_depth = 2
    elif n_visuals > 0 or total > 30:
        collapse_depth = 3
    else:
        collapse_depth = 4

    # 6. Metadata
    secrets = context.get("tool_secrets") or {}
    metadata = {
        "user_query": context.get("user_query", ""),
        "doc_json_path": secrets.get("DOC_JSON_PATH", ""),
        "created_at": ts,
        "mode": "markdown",
    }
    doc_json_path = secrets.get("DOC_JSON_PATH", "")
    if doc_json_path and os.path.exists(doc_json_path):
        try:
            with open(doc_json_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            fname = raw.get("outputs", [{}])[0].get("file_name", "")
            if fname:
                metadata["doc_title"] = fname.replace(".pdf", "")
        except Exception:
            pass

    mindmap_data = {
        "title": nodes[0]["label"] if nodes else "Mindmap",
        "subtitle": "",
        "theme": "corporate",
        "layout": layout,
        "options": {
            "width": 1600, "height": 1200,
            "show_citations": True,
            "show_cross_links": len(edges) > 0,
            "collapse_depth": collapse_depth,
            "animation": True,
        },
        "nodes": nodes,
        "edges": edges,
        "metadata": metadata,
    }

    # Save JSON for debugging
    json_path = os.path.join(output_dir, f"mindmap_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(mindmap_data, f, ensure_ascii=False, indent=2)

    # Render HTML via mindmap-renderer sidecar
    api_url = _get_api_url(context, "MINDMAP_API_URL", "http://localhost:3004")
    file_path = ""
    try:
        resp = _http_post(f"{api_url}/render", mindmap_data, timeout=60)
        if resp["type"] != "json":
            html_path = os.path.join(output_dir, f"mindmap_{ts}.html")
            data_bytes = resp["data"]
            if isinstance(data_bytes, str):
                data_bytes = data_bytes.encode("utf-8")
            with open(html_path, "wb") as f:
                f.write(data_bytes)
            file_path = html_path
            print(f"[mindmap] Rendered HTML: {html_path} ({len(data_bytes)} bytes)")
    except Exception as e:
        print(f"[mindmap] Render request failed: {e}")

    return file_path


# ---------------------------------------------------------------------------
# GenerateDiagramTool — unified diagram + chart + mindmap (3-way)
# ---------------------------------------------------------------------------

class GenerateDiagramTool:
    name = "generate_diagram"
    description = (
        "Generate a diagram, chart, or mindmap from document content. "
        "Requires ReadFullDocument or search+GetPage to be called first. "
        "The tool reads document extractions, generates visual content via LLM, "
        "and renders it. "
        "Supported types: "
        "Charts (interactive Chart.js): bar, grouped-bar, stacked-bar, line, combo, "
        "pie, donut, scatter, heatmap, funnel, waterfall, subplot. "
        "Diagrams (mermaid SVG): flowchart, sequenceDiagram, gantt, timeline, "
        "quadrantChart, xychart, erDiagram, stateDiagram-v2, classDiagram, "
        "sankey, journey, block, kanban, radar-beta, zenuml. "
        "Mindmap (interactive D3.js): mindmap."
    )
    parameters = {
        "type": "object",
        "properties": {
            "diagram_type": {
                "type": "string",
                "enum": ALL_TYPES,
                "description": (
                    "The visualization type. Choose based on content: "
                    "CHARTS (interactive, hover tooltips, legend toggle): "
                    "bar (single category comparison), "
                    "grouped-bar (multi-series side-by-side comparison), "
                    "stacked-bar (composition over categories), "
                    "line (trends over time, multi-series), "
                    "combo (bar+line dual y-axis, e.g. revenue + margin), "
                    "pie (proportions, market share), "
                    "donut (proportions with center label), "
                    "scatter (correlation between two variables), "
                    "heatmap (matrix intensity, cross-category patterns), "
                    "funnel (staged pipeline, decreasing stages), "
                    "waterfall (cumulative impact, bridge analysis), "
                    "subplot (multi-panel comparison, NxM grid). "
                    "DIAGRAMS (mermaid SVG): "
                    "flowchart (processes, decisions), "
                    "sequenceDiagram (interactions, protocols), "
                    "gantt (schedules, phases), timeline (milestones), "
                    "quadrantChart (2x2 analysis), xychart (simple bar/line via mermaid), "
                    "erDiagram (entity relationships), stateDiagram-v2 (state machines), "
                    "classDiagram (data models), sankey (flow volumes), "
                    "journey (user experience), block (architecture), "
                    "kanban (task stages), radar-beta (multi-axis comparison), "
                    "zenuml (service architecture, API interactions, cloud component diagrams). "
                    "MINDMAP: mindmap (document overview, topic hierarchy with citations — "
                    "interactive D3.js HTML with zoom/pan/search)."
                ),
            },
        },
        "required": ["diagram_type"],
    }
    tool_type = "inference"
    custom_rules = (
        "MANDATORY: You MUST call generate_diagram before giving your final answer. "
        "Even if you already have enough information to answer, you MUST still call generate_diagram. "
        "NEVER skip generate_diagram — it is required for every response. "
        "SOURCE TOOL SELECTION: "
        "For data charts (bar, line, combo, pie, scatter, etc.) that need exact numbers: "
        "use search(doc) or GetPage to retrieve raw table data BEFORE generate_diagram. "
        "ReadFullDocument gives summaries — insufficient for precise data charts. "
        "For structure diagrams (flowchart, sequenceDiagram, mindmap): ReadFullDocument is sufficient. "
        "TYPE SELECTION GUIDE: "
        "(A) Numerical data, percentages, ratios → CHART types: "
        "pie/donut (proportions), bar/grouped-bar/stacked-bar (category comparison), "
        "line (trends over time), combo (dual metrics e.g. revenue + margin), "
        "scatter (correlation), waterfall (cumulative bridge), funnel (pipeline stages). "
        "(B) Multi-series comparison across entities → subplot (side-by-side panels). "
        "(C) Processes, workflows, interactions → DIAGRAM types: "
        "flowchart, sequenceDiagram, stateDiagram-v2, gantt, timeline. "
        "(D) Relationships, structures → erDiagram, classDiagram, sankey, block, zenuml (service/API architecture). "
        "(E) Document overview, topic hierarchy → mindmap. "
        "Do NOT use mindmap for data analysis. Do NOT use xychart when Chart.js types are better. "
        "FINAL ANSWER RULES: "
        "(1) Include BOTH text explanation AND reference to the generated visualization. "
        "(2) All citations MUST use global Index [N], never page numbers. "
        "(3) NEVER include chart DSL, mermaid source code, or mindmap markdown in your final answer. "
        "The visualization is already rendered as a separate file. Describe what it shows in plain text only."
    )

    _MAX_SOURCE_CHARS = 12000

    def execute(self, args: dict, context: dict) -> str:
        diagram_type = args.get("diagram_type", "")
        if diagram_type not in ALL_TYPES:
            return json.dumps({
                "error": f"Invalid diagram_type: {diagram_type}. "
                         f"Supported: {', '.join(ALL_TYPES)}"
            })

        extractions = context.get("extractions", [])
        if not extractions:
            return (
                "Error: No source information available. "
                "Gather source info first (ReadFullDocument, search, GetPage), then retry generate_diagram."
            )

        try:
            parts = []
            total_chars = 0
            for ext in extractions:
                part = ext["result"]
                if total_chars + len(part) > self._MAX_SOURCE_CHARS and parts:
                    break
                parts.append(part)
                total_chars += len(part)
            rfd_text = "\n\n---\n\n".join(parts)

            user_query = context.get("user_query", "")

            # ===== 3-way branch: mindmap / chart / mermaid diagram =====
            if diagram_type == "mindmap":
                return self._execute_mindmap(rfd_text, user_query, context)
            elif diagram_type in CHART_TYPES:
                return self._execute_chart(rfd_text, user_query, diagram_type, context)
            else:
                return self._execute_diagram(rfd_text, user_query, diagram_type, context)

        except Exception as e:
            print(f"[diagram] Generation failed: {e}")
            print(traceback.format_exc())
            return json.dumps({"error": f"Generation failed: {str(e)}"})

    @staticmethod
    def _call_llm(system_prompt: str, user_content: str) -> str:
        """Call LLM pool with standard settings. Returns raw text output."""
        from agent.core.llm_pool import get_default_pool
        pool = get_default_pool()
        resp = pool.call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        return resp.choices[0].message.content

    @staticmethod
    def _record_inference(context: dict, system_prompt: str,
                          user_content: str, output: str):
        """Record inference for SFT training JSONL if recorder is available."""
        record = context.get("record_inference")
        if record:
            record(
                [
                    {"role": "system", "content": system_prompt, "loss_masking": True},
                    {"role": "user", "content": user_content, "loss_masking": True},
                ],
                output,
            )

    @staticmethod
    def _build_user_content(user_query: str, rfd_text: str) -> str:
        if user_query:
            return f"User query: {user_query}\n\nDocument source:\n{rfd_text}"
        return f"Document source:\n{rfd_text}"

    def _execute_mindmap(self, rfd_text: str, user_query: str, context: dict) -> str:
        """Mindmap branch: MINDMAP_SYSTEM_PROMPT → markdown → D3.js render."""
        user_content = self._build_user_content(user_query, rfd_text)
        # Mindmap uses raw rfd_text (no "Document source:" prefix) when no query
        if not user_query:
            user_content = rfd_text

        raw = self._call_llm(MINDMAP_SYSTEM_PROMPT, user_content)
        markdown_text = _postprocess_mindmap_markdown(raw)
        self._record_inference(context, MINDMAP_SYSTEM_PROMPT, user_content, markdown_text)

        render_path = _render_mindmap(markdown_text, context)
        render_note = (
            f"\n\nRendered HTML saved to: {render_path}" if render_path
            else "\n\n(Rendering skipped — mindmap-renderer sidecar not available.)"
        )
        return f"mindmap generated. mindmap source text:\n\n{markdown_text}{render_note}"

    def _execute_chart(self, rfd_text: str, user_query: str,
                       chart_type: str, context: dict) -> str:
        """Chart branch: CHART_SYSTEM_PROMPT → chart DSL → Chart.js interactive HTML."""
        one_shot = CHART_DSL_EXAMPLES.get(chart_type, "")
        system_prompt = CHART_SYSTEM_PROMPT.format(
            chart_type=chart_type,
            one_shot_example=one_shot,
        )
        user_content = self._build_user_content(user_query, rfd_text)

        raw = self._call_llm(system_prompt, user_content)
        chart_dsl = _extract_chart_dsl(raw, chart_type)
        self._record_inference(context, system_prompt, user_content, chart_dsl)

        render_path = _render_chart(chart_dsl, context)
        render_note = (
            f"\n\nRendered interactive HTML saved to: {render_path}" if render_path
            else "\n\n(Rendering skipped — chart renderer sidecar not available.)"
        )
        return (
            f"Chart generated (type: {chart_type}). "
            f"Chart DSL source:\n\n{chart_dsl}{render_note}"
        )

    def _execute_diagram(self, rfd_text: str, user_query: str,
                         diagram_type: str, context: dict) -> str:
        """Mermaid diagram branch: DIAGRAM_SYSTEM_PROMPT → mermaid source → SVG render."""
        one_shot = DIAGRAM_EXAMPLES.get(diagram_type, "")
        system_prompt = DIAGRAM_SYSTEM_PROMPT.format(
            diagram_type=diagram_type,
            one_shot_example=one_shot,
        )
        user_content = self._build_user_content(user_query, rfd_text)

        raw = self._call_llm(system_prompt, user_content)
        mermaid_source = _extract_mermaid_source(raw, diagram_type)
        self._record_inference(context, system_prompt, user_content, mermaid_source)

        render_path = _render_mermaid(mermaid_source, context, fmt="svg")
        render_note = (
            f"\n\nRendered SVG saved to: {render_path}" if render_path
            else "\n\n(Rendering skipped — mermaid-renderer sidecar not available.)"
        )
        return (
            f"Diagram generated (type: {diagram_type}). "
            f"Mermaid source:\n\n{mermaid_source}{render_note}"
        )
