"""
Mindmap Generation Custom Tool

Generates interactive mindmaps from document content via a multi-phase LLM
extraction pipeline + mindmap-renderer sidecar.

No internal imports required — uses only context services + HTTP calls.

Sidecar services (must be running):
  - mindmap-renderer  :3004  (D3.js interactive HTML/PNG/SVG)

Usage:
    /v2/run request:
    {
        "custom_tools_path": "examples/mindmap/mindmap_tools.py",
        "custom_rules": "- Use generate_mindmap to create an interactive mindmap from the document",
        "tool_secrets": {
            "MINDMAP_API_URL": "http://localhost:3004",
            "OUTPUT_DIR": "/path/to/output"
        }
    }

Tools defined:
    - generate_mindmap: Document → hierarchical interactive mindmap (HTML/PNG/SVG)
"""
import json
import os
import re
import time
import urllib.request
import urllib.error


# ---------------------------------------------------------------------------
# Helpers (same pattern as presentation_tools.py — no internal imports)
# ---------------------------------------------------------------------------

def _get_output_dir(context: dict) -> str:
    secrets = context.get("tool_secrets") or {}
    out = secrets.get("OUTPUT_DIR") or context.get("image_dir") or "/tmp/docviz_agent_output"
    os.makedirs(out, exist_ok=True)
    return out


def _get_url(context: dict, key: str, default: str) -> str:
    secrets = context.get("tool_secrets") or {}
    return secrets.get(key, default).rstrip("/")


def _http_post_json(url: str, payload: dict, timeout: int = 60) -> dict:
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


def _http_get_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response that may include markdown fences."""
    text = text.strip()
    # Remove ```json ... ``` fences
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    # Remove <think>...</think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return text


def _safe_parse_json(text: str, fallback=None):
    """Parse JSON from LLM output, with fallback."""
    try:
        return json.loads(_extract_json(text))
    except (json.JSONDecodeError, TypeError):
        return fallback


def _gather_source_content(context: dict, max_pages: int = 12, max_chars: int = 12000) -> str:
    """Gather text from multi_docs for LLM processing."""
    multi_docs = context.get("multi_docs") or []
    parts = []
    total = 0
    for doc_idx, pages in enumerate(multi_docs):
        for page in pages[:max_pages]:
            content = page.get("content", "")
            if not content:
                continue
            if total + len(content) > max_chars:
                remaining = max_chars - total
                if remaining > 200:
                    parts.append(f"[Doc {doc_idx+1}, p.{page.get('page_num', '?')}]\n{content[:remaining]}...")
                break
            parts.append(f"[Doc {doc_idx+1}, p.{page.get('page_num', '?')}]\n{content}")
            total += len(content)
    return "\n\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# LLM Prompt Templates
# ---------------------------------------------------------------------------

PHASE1_SYSTEM = """You are an expert document analyst creating a hierarchical knowledge map.
Analyze the document and identify the 3-7 main themes/topics.

For each theme, provide:
- label: Short name (3-8 words)
- description: One-sentence summary
- importance: Score 1-10
- page_refs: Array of page numbers where this theme appears
- doc_refs: Array of document numbers where this theme appears (e.g. [1], [1,2] for multi-doc)

Output ONLY valid JSON (no markdown, no explanation):
{"themes": [{"label": "...", "description": "...", "importance": 8, "page_refs": [1,3,5], "doc_refs": [1]}]}"""

PHASE1_FOCUS_SYSTEM = """You are an expert document analyst creating a DEEP focused knowledge map.
Analyze the document SPECIFICALLY related to: {focus_query}

Identify 4-7 detailed themes/subtopics that directly address this focus area.
Go DEEPER than a general overview — extract specific arguments, evidence, data, and implications.
For each theme:
- label: Short name (3-8 words), specific to the focus area
- description: One-sentence summary of how it relates to "{focus_query}"
- importance: Score 1-10 (how central to the focus question)
- page_refs: Array of page numbers

Output ONLY valid JSON (no markdown, no explanation):
{"themes": [{"label": "...", "description": "...", "importance": 8, "page_refs": [1,3]}]}"""

PHASE1_MULTIDOC_SYSTEM = """You are an expert analyst creating a cross-document knowledge map.
You are given content from MULTIPLE documents (labeled [Doc 1], [Doc 2], etc.).

Your task: Identify 4-7 themes that capture the KEY TOPICS across these documents.
For themes appearing in multiple documents, note all document references.
Also identify themes unique to specific documents — these are equally important.

For each theme:
- label: Short name (3-8 words)
- description: One-sentence summary
- importance: Score 1-10
- page_refs: Array of page numbers
- doc_refs: Array of document numbers where this theme appears (e.g. [1,2] = both docs)

Output ONLY valid JSON (no markdown, no explanation):
{"themes": [{"label": "...", "description": "...", "importance": 8, "page_refs": [1,3], "doc_refs": [1,2]}]}"""

PHASE2_SYSTEM = """You are extracting a detailed knowledge hierarchy for a mindmap visualization.
For each theme provided, extract subtopics and supporting facts.

Rules:
- Each theme should have 2-4 topics (subtopics)
- Each topic should have 1-3 leaves (specific facts, data points, or evidence)
- Classify each node's style: fact, opinion, question, data_point, evidence
- Include page citations where possible
- If content comes from multiple documents, include doc number in citation

Output ONLY valid JSON:
{
  "extractions": [
    {
      "theme_id": "theme_0",
      "topics": [
        {
          "label": "Subtopic Name",
          "description": "One-sentence explanation",
          "node_style": "fact",
          "citation": {"doc": 1, "page": 3, "paragraph": 2},
          "leaves": [
            {
              "label": "Specific fact or data point",
              "node_style": "data_point",
              "citation": {"doc": 1, "page": 4, "paragraph": 1}
            }
          ]
        }
      ]
    }
  ]
}"""

PHASE2_FOCUS_SYSTEM = """You are extracting a DEEP knowledge hierarchy for a focused mindmap.
The focus question is: {focus_query}

For each theme, extract detailed subtopics that DIRECTLY answer or address the focus question.
Go deeper than surface-level: include specific data, arguments, counter-arguments, and implications.

Rules:
- Each theme should have 3-5 topics (more detail than usual)
- Each topic should have 2-4 leaves (specific facts, data, evidence, implications)
- Classify each node: fact, opinion, question, data_point, evidence
- Include page citations
- Prioritize specificity over breadth

Output ONLY valid JSON:
{
  "extractions": [
    {
      "theme_id": "theme_0",
      "topics": [
        {
          "label": "Specific Subtopic",
          "description": "How this relates to the focus question",
          "node_style": "fact",
          "citation": {"page": 3, "paragraph": 2},
          "leaves": [
            {"label": "Specific evidence or data point", "node_style": "data_point", "citation": {"page": 4}}
          ]
        }
      ]
    }
  ]
}"""

PHASE3_SYSTEM = """You are a knowledge graph analyst identifying relationships between topics.
Given a list of topics extracted from a document, identify 3-8 meaningful cross-references.

Relationship types:
- causes: A leads to or causes B
- contrasts_with: A contradicts or contrasts with B
- supports: A provides evidence for B
- related_to: A and B are associated
- leads_to: A temporally/logically precedes B

Output ONLY valid JSON:
{
  "cross_references": [
    {"source_id": "topic_X_Y", "target_id": "topic_X_Y", "relationship": "causes", "label": "brief explanation"}
  ]
}"""

PHASE3_MULTIDOC_SYSTEM = """You are a cross-document knowledge graph analyst.
Given topics extracted from MULTIPLE documents, identify 5-10 cross-references.

PRIORITIZE cross-document relationships:
1. **Shared topics**: Same concept discussed in different documents → "related_to" or "supports"
2. **Contradictions**: Conflicting views between documents → "contrasts_with"
3. **Cause-effect chains**: Topic in Doc A causes or leads to topic in Doc B → "causes" / "leads_to"
4. **Within-document links**: Also include 2-3 within-doc relationships

Each topic has a doc_source field. Use it to identify cross-document links.

Relationship types: causes, contrasts_with, supports, related_to, leads_to

Output ONLY valid JSON:
{
  "cross_references": [
    {"source_id": "topic_X_Y", "target_id": "topic_X_Y", "relationship": "causes", "label": "brief explanation", "cross_doc": true}
  ]
}"""

PHASE4_SYSTEM = """You are enriching a document mindmap with external context.
Given the main themes and web search results, identify 2-5 external facts that ADD NEW VALUE.

Rules:
- Only include facts providing NEW information not already in the document
- Attach each enrichment to the most relevant existing theme
- Keep labels concise (under 60 characters)

Output ONLY valid JSON:
{
  "enrichments": [
    {"label": "New external fact", "description": "Details", "attach_to_theme": "theme_0", "source_url": ""}
  ]
}"""


# ---------------------------------------------------------------------------
# GenerateMindmapTool
# ---------------------------------------------------------------------------

class GenerateMindmapTool:
    name = "generate_mindmap"
    description = (
        "Generate an interactive mindmap from the document content. "
        "Extracts themes, topics, and facts hierarchically with source citations. "
        "Outputs a self-contained interactive HTML file (with zoom/pan/search/export). "
        "Supports focus mode (drill into a specific question), web enrichment, "
        "cross-reference edges, and 6 visual themes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Central topic/title for the mindmap. If omitted, auto-detected from document.",
            },
            "focus_query": {
                "type": "string",
                "description": "Optional: Generate a focused sub-mindmap about this specific question or topic.",
            },
            "depth": {
                "type": "integer",
                "description": "Extraction depth: 2=themes+topics, 3=+leaves (default), 4=+detailed evidence.",
                "default": 3,
                "enum": [2, 3, 4],
            },
            "theme": {
                "type": "string",
                "description": "Visual theme for the mindmap.",
                "enum": ["corporate", "academic", "creative", "dark", "minimal", "nature"],
                "default": "corporate",
            },
            "layout": {
                "type": "string",
                "description": "Layout: radial (default), tree_lr (left-to-right), tree_td (top-down).",
                "enum": ["radial", "tree_lr", "tree_td"],
                "default": "radial",
            },
            "enrich_web": {
                "type": "boolean",
                "description": "Enrich mindmap with external web search context.",
                "default": False,
            },
            "output_format": {
                "type": "string",
                "description": "Output format(s).",
                "enum": ["html", "png", "svg", "all"],
                "default": "html",
            },
            "show_cross_links": {
                "type": "boolean",
                "description": "Show cross-reference relationship edges between topics.",
                "default": True,
            },
        },
        "required": [],
    }
    tool_type = "inference"

    def execute(self, args: dict, context: dict) -> str:
        call_llm = context.get("call_llm")
        if not call_llm:
            return json.dumps({"error": "call_llm not available in context"})

        # Parse args
        topic = args.get("topic", "")
        focus_query = args.get("focus_query", "")
        depth = args.get("depth", 3)
        theme = args.get("theme", "corporate")
        layout = args.get("layout", "radial")
        enrich_web = args.get("enrich_web", False)
        output_format = args.get("output_format", "html")
        show_cross_links = args.get("show_cross_links", True)

        # Gather source content
        source_content = _gather_source_content(context)
        if not source_content:
            return json.dumps({"error": "No document content available to generate mindmap"})

        language = context.get("language", "en")
        filenames = context.get("filenames") or []

        # Detect multi-document mode
        multi_docs = context.get("multi_docs") or []
        is_multidoc = len(multi_docs) >= 2

        try:
            # ===== Phase 1: Theme Extraction =====
            if focus_query:
                sys_prompt = PHASE1_FOCUS_SYSTEM.replace("{focus_query}", focus_query)
            elif is_multidoc:
                sys_prompt = PHASE1_MULTIDOC_SYSTEM
            else:
                sys_prompt = PHASE1_SYSTEM

            p1_messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"Document content:\n\n{source_content}"},
            ]
            p1_result = call_llm(p1_messages, role="extraction", temperature=0.2, max_tokens=4000)
            p1_data = _safe_parse_json(p1_result, {"themes": []})
            themes = p1_data.get("themes", [])

            if not themes:
                return json.dumps({"error": "Failed to extract themes from document", "raw": p1_result[:500]})

            # Sort by importance
            themes.sort(key=lambda t: t.get("importance", 5), reverse=True)
            themes = themes[:7]  # Max 7 themes

            # Auto-detect topic if not provided
            if not topic:
                topic = focus_query if focus_query else (filenames[0] if filenames else "Document Analysis")

            # ===== Phase 2: Deep Extraction =====
            all_topics = []
            if depth >= 2:
                # Select Phase 2 prompt based on mode
                if focus_query:
                    p2_sys = PHASE2_FOCUS_SYSTEM.replace("{focus_query}", focus_query)
                else:
                    p2_sys = PHASE2_SYSTEM

                # Batch themes (2-3 per LLM call)
                batch_size = 3
                for i in range(0, len(themes), batch_size):
                    batch = themes[i:i + batch_size]
                    theme_list = json.dumps([
                        {"theme_id": f"theme_{i+j}", "label": t["label"], "description": t.get("description", "")}
                        for j, t in enumerate(batch)
                    ], ensure_ascii=False)

                    p2_messages = [
                        {"role": "system", "content": p2_sys},
                        {"role": "user", "content": (
                            f"Themes to extract:\n{theme_list}\n\n"
                            f"Source document:\n{source_content[:8000]}"
                        )},
                    ]
                    p2_result = call_llm(p2_messages, role="extraction", temperature=0.2, max_tokens=8000)
                    p2_data = _safe_parse_json(p2_result, {"extractions": []})
                    all_topics.extend(p2_data.get("extractions", []))

            # ===== Phase 3: Cross-Reference Analysis =====
            edges = []
            if show_cross_links and depth >= 3 and len(themes) >= 2:
                # Build flat topic list for cross-ref analysis
                topic_list = []
                for ext in all_topics:
                    tid = ext.get("theme_id", "theme_0")
                    # Find which theme this belongs to, get doc_refs
                    theme_idx = int(tid.replace("theme_", "")) if tid.startswith("theme_") else 0
                    doc_refs = themes[theme_idx].get("doc_refs", [1]) if theme_idx < len(themes) else [1]
                    for j, tp in enumerate(ext.get("topics", [])):
                        entry = {
                            "id": f"{tid}_topic_{j}",
                            "label": tp.get("label", ""),
                            "theme": tid,
                        }
                        if is_multidoc:
                            entry["doc_source"] = doc_refs
                        topic_list.append(entry)

                if len(topic_list) >= 3:
                    p3_sys = PHASE3_MULTIDOC_SYSTEM if is_multidoc else PHASE3_SYSTEM
                    p3_messages = [
                        {"role": "system", "content": p3_sys},
                        {"role": "user", "content": f"Topics:\n{json.dumps(topic_list, ensure_ascii=False)}"},
                    ]
                    p3_result = call_llm(p3_messages, role="extraction", temperature=0.3, max_tokens=3000)
                    p3_data = _safe_parse_json(p3_result, {"cross_references": []})
                    edges = p3_data.get("cross_references", [])

            # ===== Phase 4: Web Enrichment (optional) =====
            enrichments = []
            if enrich_web:
                search_documents = context.get("search_documents")
                if search_documents:
                    # Search for top 3 themes
                    search_results = []
                    for t in themes[:3]:
                        try:
                            results = search_documents(t["label"])
                            if results:
                                search_results.extend(results[:3])
                        except Exception:
                            pass

                    if search_results:
                        search_text = "\n".join([
                            f"- {r.get('content', '')[:300]}" for r in search_results[:9]
                        ])
                        p4_messages = [
                            {"role": "system", "content": PHASE4_SYSTEM},
                            {"role": "user", "content": (
                                f"Main themes: {json.dumps([t['label'] for t in themes], ensure_ascii=False)}\n\n"
                                f"Web search results:\n{search_text}"
                            )},
                        ]
                        p4_result = call_llm(p4_messages, role="extraction", temperature=0.3, max_tokens=3000)
                        p4_data = _safe_parse_json(p4_result, {"enrichments": []})
                        enrichments = p4_data.get("enrichments", [])

            # ===== Assemble MindmapData JSON =====
            if is_multidoc and filenames:
                subtitle = f"Cross-document: {' vs '.join(filenames[:3])}"
            elif focus_query:
                subtitle = f"Focus: {focus_query}"
                if filenames:
                    subtitle += f" | Source: {filenames[0]}"
            elif filenames:
                subtitle = f"Source: {', '.join(filenames[:3])}"
            else:
                subtitle = ""

            mindmap_data = self._assemble_mindmap(
                topic=topic,
                subtitle=subtitle,
                themes=themes,
                all_topics=all_topics,
                edges=edges,
                enrichments=enrichments,
                theme=theme,
                layout=layout,
                show_cross_links=show_cross_links,
                depth=depth,
            )

            # ===== Render via sidecar =====
            base_url = _get_url(context, "MINDMAP_API_URL", "http://localhost:3004")
            output_dir = _get_output_dir(context)
            ts = _timestamp()
            results = {}

            formats = ["html", "png", "svg"] if output_format == "all" else [output_format]

            for fmt in formats:
                endpoint = "/render" if fmt == "html" else f"/render-{fmt}"
                try:
                    resp = _http_post_json(f"{base_url}{endpoint}", mindmap_data, timeout=60)

                    if resp["type"] == "binary" or (resp["type"] != "json"):
                        ext = fmt
                        ct = resp.get("content_type", "")
                        if "html" in ct:
                            ext = "html"
                        file_path = os.path.join(output_dir, f"mindmap_{ts}.{ext}")
                        with open(file_path, "wb") as f:
                            data_bytes = resp["data"]
                            if isinstance(data_bytes, str):
                                data_bytes = data_bytes.encode("utf-8")
                            f.write(data_bytes)
                        results[fmt] = file_path
                    elif resp["type"] == "json" and resp["data"].get("error"):
                        results[fmt] = f"error: {resp['data']['error']}"
                    else:
                        # Shouldn't happen
                        results[fmt] = "unexpected response"

                except Exception as e:
                    results[fmt] = f"error: {str(e)}"

            # Build result
            primary_path = results.get("html") or results.get("png") or results.get("svg", "")
            return json.dumps({
                "success": True,
                "file_path": primary_path,
                "files": results,
                "stats": {
                    "themes": len(themes),
                    "topics": sum(len(ext.get("topics", [])) for ext in all_topics),
                    "cross_links": len(edges),
                    "enrichments": len(enrichments),
                },
                "message": f"Interactive mindmap generated with {len(themes)} themes. "
                           f"Open the HTML file in a browser for full interactivity.",
            }, ensure_ascii=False)

        except Exception as e:
            return json.dumps({"error": f"Mindmap generation failed: {str(e)}"})

    def _assemble_mindmap(
        self, topic, subtitle, themes, all_topics, edges, enrichments,
        theme, layout, show_cross_links, depth,
    ) -> dict:
        """Assemble the MindmapData JSON for the sidecar renderer."""
        nodes = []
        node_edges = []

        # Root node
        theme_ids = [f"theme_{i}" for i in range(len(themes))]
        nodes.append({
            "id": "root",
            "label": topic,
            "type": "root",
            "description": "",
            "node_style": None,
            "citation": None,
            "children": theme_ids,
        })

        # Theme-to-extraction mapping
        ext_map = {}
        for ext in all_topics:
            tid = ext.get("theme_id", "")
            ext_map[tid] = ext

        # Theme nodes
        for i, t in enumerate(themes):
            tid = f"theme_{i}"
            ext = ext_map.get(tid, {})
            topics = ext.get("topics", [])
            topic_ids = [f"{tid}_topic_{j}" for j in range(len(topics))]

            # Add enrichment children
            enrich_ids = []
            for k, en in enumerate(enrichments):
                if en.get("attach_to_theme") == tid:
                    eid = f"enrich_{i}_{k}"
                    enrich_ids.append(eid)

            page_ref = t.get("page_refs", [])
            citation = {"doc": 1, "page": page_ref[0]} if page_ref else None

            nodes.append({
                "id": tid,
                "label": t["label"],
                "type": "theme",
                "description": t.get("description", ""),
                "node_style": None,
                "citation": citation,
                "children": topic_ids + enrich_ids,
            })

            # Topic nodes
            for j, tp in enumerate(topics):
                tpid = f"{tid}_topic_{j}"
                leaves = tp.get("leaves", [])
                leaf_ids = [f"{tpid}_leaf_{k}" for k in range(len(leaves))] if depth >= 3 else []

                nodes.append({
                    "id": tpid,
                    "label": tp.get("label", ""),
                    "type": "topic",
                    "description": tp.get("description", ""),
                    "node_style": tp.get("node_style"),
                    "citation": tp.get("citation"),
                    "children": leaf_ids,
                })

                # Leaf nodes
                if depth >= 3:
                    for k, leaf in enumerate(leaves):
                        lid = f"{tpid}_leaf_{k}"
                        nodes.append({
                            "id": lid,
                            "label": leaf.get("label", ""),
                            "type": "leaf",
                            "description": leaf.get("description", ""),
                            "node_style": leaf.get("node_style"),
                            "citation": leaf.get("citation"),
                            "children": [],
                        })

            # Enrichment nodes
            for k, en in enumerate(enrichments):
                if en.get("attach_to_theme") == tid:
                    eid = f"enrich_{i}_{k}"
                    nodes.append({
                        "id": eid,
                        "label": en.get("label", ""),
                        "type": "enrichment",
                        "description": en.get("description", ""),
                        "node_style": "external",
                        "citation": None,
                        "source_url": en.get("source_url", ""),
                        "children": [],
                    })

        # Cross-reference edges
        if show_cross_links:
            node_id_set = {n["id"] for n in nodes}
            for cr in edges:
                src = cr.get("source_id", "")
                tgt = cr.get("target_id", "")
                if src in node_id_set and tgt in node_id_set:
                    node_edges.append({
                        "source": src,
                        "target": tgt,
                        "relationship": cr.get("relationship", "related_to"),
                        "label": cr.get("label", ""),
                    })

        return {
            "title": topic,
            "subtitle": subtitle,
            "theme": theme,
            "layout": layout,
            "options": {
                "width": 1600,
                "height": 1200,
                "show_citations": True,
                "show_cross_links": show_cross_links,
                "collapse_depth": 4 if depth >= 3 else 3,
                "animation": True,
            },
            "nodes": nodes,
            "edges": node_edges,
        }
