"""
Built-in Tool Implementations

이 모듈의 도구들은 커스텀 툴과 동일한 계약을 따른다:
  execute(args: dict, context: dict) -> str

Client는 이 도구를 참조 구현(reference implementation)으로 활용하여
자신만의 tool action을 작성할 수 있다.

IMPORTANT: 커스텀 툴은 context["record_training"]을 통해 학습 데이터를
기록한다. builtin 도구는 _extraction_sink에 메타데이터를 append하여
caller(_execute_tool)가 builder event로 변환한다.

These tools are automatically loaded by ToolRegistry when
include_builtin=True (default).
"""

import json
from typing import Dict, List, Any, Set


def dedup_keep_first(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate pages by (filename, page) key, keeping first occurrence.
    Re-assigns Index starting from 1.

    This follows the original pipeline's dedup_keep_first policy.

    Args:
        pages: List of page dicts with 'filename', 'page', 'Index', etc.

    Returns:
        Deduplicated list with re-assigned Index values
    """
    seen: Set[tuple] = set()
    out: List[Dict[str, Any]] = []
    new_idx = 1

    for d in pages:
        # Web results (no filename/page)
        if 'filename' not in d or 'page' not in d:
            d['Index'] = new_idx
            out.append(d)
            new_idx += 1
            continue

        key = (d['filename'], d['page'])
        if key in seen:
            continue
        seen.add(key)
        d['Index'] = new_idx
        out.append(d)
        new_idx += 1

    return out


class SearchTool:
    """
    Search for relevant pages in documents or the web.
    """
    name = "search"
    description = "Performs batched searches over the selected source: supply an array 'query'; the tool retrieves the top 10 results for each query in one invoke."

    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Array of query string(s). Include one or multiple complementary (if necessary) search queries in a single invoke."
            },
            "source": {
                "type": "string",
                "enum": ["web", "doc"],
                "description": "Selects the corpus to search. Must use only a single source type (web or doc) per action."
            },
            "document_number": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "The one or more internal document number(s) to be used for retrieval with the query above. Required if source is 'doc' above, omitted for 'web'. An array of documents' numbers (e.g. [1] or [1, 2, 3]; not use 0)."
            }
        },
        "required": ["query", "source", "document_number (only if source is 'doc')"]
    }
    tool_type = "search"

    def execute(self, args: dict, context: dict) -> str:
        """Execute search using selector (doc) or web search client (web)."""
        source = args.get("source", "doc")
        queries = args.get("query", [])

        if source == "web":
            return self._execute_web(queries, context)
        else:
            return self._execute_doc(queries, args, context)

    def _execute_doc(self, queries: list, args: dict, context: dict) -> str:
        """Document search via SelectorClient."""
        doc_indices = args.get("document_number", [1])
        multi_docs = context.get("multi_docs", [])
        filenames = context.get("filenames", [])
        reasoning = context.get("reasoning", "")
        searched_indices = context.get("searched_indices")

        # Use SelectorClient (preferred) or legacy selector_fn
        selector_client = context.get("selector_client")
        selector_fn = context.get("selector_fn")

        if selector_client is None and selector_fn is None:
            return json.dumps({"error": "No selector available in context"})

        results = []
        for doc_id in doc_indices:
            for query in queries:
                try:
                    if selector_client is not None:
                        selected = selector_client.select_for_doc(
                            query, reasoning, multi_docs, int(doc_id), filenames
                        )
                    else:
                        selected = selector_fn(query, reasoning, multi_docs, int(doc_id), filenames)
                    if selected:
                        results.extend(selected)
                except Exception as e:
                    print(f"[Warning] Search failed: {e}")

        # Deduplicate and re-index
        deduped = dedup_keep_first(results)

        # Update searched_indices (side effect)
        if searched_indices is not None:
            searched_indices.extend([p.get("Index") for p in deduped])

        return json.dumps(deduped, ensure_ascii=False)

    def _execute_web(self, queries: list, context: dict) -> str:
        """Web search via WebSearchClient."""
        web_client = context.get("web_search_client")
        if web_client is None:
            return json.dumps({"error": "web_search_client not provided in context"})

        search_pages = context.get("search_pages", [])

        all_results = []
        for query in queries:
            try:
                passages = web_client.search_web(query)
                all_results.extend(passages)
            except Exception as e:
                print(f"[Warning] Web search failed: {e}")

        # Apply global index offset based on existing search_pages
        offset = len(search_pages)
        for j, r in enumerate(all_results):
            r["Index"] = j + offset + 1

        # Accumulate into shared search_pages (side effect)
        search_pages.extend(all_results)

        return json.dumps(all_results, ensure_ascii=False)


class ReadFullDocumentTool:
    """
    Read and summarize the entire document using extraction model.
    """
    name = "ReadFullDocument"
    description = "Reads the full content in the selected source (internal document) and returns a goal-oriented summary. Must follow the source-specific rules: it is used only when summarizing the **entire internal document** explicitly required in current user's question."

    parameters = {
        "type": "object",
        "properties": {
            "document_number": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "an array containing exactly single internal document number to read full content at a time (e.g., [1] or [2]; not use 0)."
            },
            "goal": {
                "type": "string",
                "description": "The information goal for which the full item is read and summarized."
            }
        },
        "required": ["document_number", "goal"]
    }
    tool_type = "search"

    def execute(self, args: dict, context: dict) -> str:
        """Execute document reading and summarization."""
        from .model_router import ModelRole
        from agent.config.training_prompts import EXTRACTOR_DOC_PROMPT

        doc_id = args.get("document_number", [1])
        if isinstance(doc_id, list):
            doc_id = doc_id[0]
        goal = args.get("goal", context.get("user_query", ""))

        multi_docs = context.get("multi_docs", [])
        router = context.get("model_router")

        if not router:
            return json.dumps({"error": "model_router not provided in context"})

        if not (0 < doc_id <= len(multi_docs)):
            return json.dumps({"error": f"Document {doc_id} not found"})

        # Get full document content
        pages = multi_docs[doc_id - 1]
        content = "\n\n".join([
            f"[Page {p.get('page')}]\n{p.get('content', '')}"
            for p in pages
        ])

        # Call extraction model via ModelRouter
        client = router.get_proxy_client(ModelRole.EXTRACTION)
        messages = [{"role": "user", "content": EXTRACTOR_DOC_PROMPT.format(
            webpage_content=content[:50000],
            goal=goal
        )}]

        response = client.chat.completions.create(
            messages=messages,
            temperature=0.2,
            max_tokens=16384
        )

        result = response.choices[0].message.content

        # Delegate extraction metadata to sink (caller converts to builder event)
        extraction_sink = context.get("_extraction_sink")
        if extraction_sink is not None:
            extraction_sink.append({
                "tool_name": "ReadFullDocument",
                "messages": messages,
                "result": result,
            })

        return result


class GetPageTool:
    """
    Get specific page content from documents.
    """
    name = "GetPage"
    description = "Retrieves and summarizes specific page(s) from internal document(s)."

    parameters = {
        "type": "object",
        "properties": {
            "doc_page": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Each element must STRICTLY follow the format 'documentNumber-pageNumber' (e.g., '1-3'). This format is mandatory and must always use a dash ('-')."
            }
        },
        "required": ["doc_page"]
    }
    tool_type = "search"

    def execute(self, args: dict, context: dict) -> str:
        """Execute page retrieval."""
        doc_pages = args.get("doc_page", [])
        multi_docs = context.get("multi_docs", [])
        results = []

        for dp in doc_pages:
            try:
                doc_id, page_num = dp.split("-")
                doc_id = int(doc_id)
                page_num = int(page_num)

                if 0 < doc_id <= len(multi_docs):
                    pages = multi_docs[doc_id - 1]
                    for p in pages:
                        if p.get("page") == page_num:
                            results.append(p)
                            break
            except Exception as e:
                print(f"[Warning] GetPage failed for {dp}: {e}")

        return json.dumps(results, ensure_ascii=False)


class ReadFullTextTool:
    """
    Read full text content from web URLs via cache + extraction LLM.
    """
    name = "ReadFullText"
    description = "read full content in web documents and return the goal-oriented summary of the content."

    parameters = {
        "type": "object",
        "properties": {
            "indices": {
                "type": "array",
                "items": {"type": "int"},
                "description": "The web document index(s) of the document(s) to read full contents. An array of indices (e.g. [1] or [1, 2, 3])."
            },
            "goal": {
                "type": "string",
                "description": "The information goal for which the full web document is read and summarized."
            }
        },
        "required": ["url", "goal"]
    }
    tool_type = "search"

    def execute(self, args: dict, context: dict) -> str:
        """Execute web content reading with extraction LLM."""
        from .model_router import ModelRole
        from agent.config.training_prompts import EXTRACTOR_PROMPT

        indices = args.get("indices") or args.get("index", [])
        goal = args.get("goal", context.get("user_query", ""))
        search_pages = context.get("search_pages", [])
        web_client = context.get("web_search_client")
        router = context.get("model_router")

        if web_client is None:
            return json.dumps({"error": "web_search_client not provided in context"})

        if router is None:
            return json.dumps({"error": "model_router not provided in context"})

        # Step 1: Index -> URL mapping (from search_pages)
        urls_to_read = []
        for idx in indices:
            if 0 < idx <= len(search_pages):
                page = search_pages[idx - 1]
                if "url" in page:  # web results have url field
                    urls_to_read.append(page["url"])

        if not urls_to_read:
            return json.dumps({"error": "No valid URLs to read from the given indices"})

        # Step 2: Read from cache (populated by search_web)
        page_contents = web_client.read_multiple_pages(urls_to_read)
        accessible = [
            {"url": pc.url, "contents": pc.content}
            for pc in page_contents if pc.success
        ]

        if not accessible:
            return "Failed to access the webpages."

        # Step 3: Extraction LLM call
        client = router.get_proxy_client(ModelRole.EXTRACTION)
        messages = [{"role": "user", "content": EXTRACTOR_PROMPT.format(
            webpage_content=str(accessible),
            goal=goal,
        )}]

        response = client.chat.completions.create(
            messages=messages,
            temperature=0.2,
            max_tokens=16384,
        )
        result = response.choices[0].message.content

        # Delegate extraction metadata to sink (caller converts to builder event)
        extraction_sink = context.get("_extraction_sink")
        if extraction_sink is not None:
            extraction_sink.append({
                "tool_name": "ReadFullText",
                "messages": messages,
                "result": result,
            })

        # Step 5: Parse JSON response + format
        try:
            content = result
            if "```json" in content:
                content = content.replace("```json", "").replace("```", "")
            parsed = json.loads(content)
            return (
                f"The useful information for goal '{goal}':\n\n"
                f"Rationale: {parsed.get('rational', '')}\n\n"
                f"Evidence: {parsed.get('evidence', '')}\n\n"
                f"Summary: {parsed.get('summary', '')}\n\n"
            )
        except json.JSONDecodeError:
            return result


# List of all built-in tool classes for registration
BUILTIN_TOOL_CLASSES = [
    SearchTool,
    ReadFullDocumentTool,
    GetPageTool,
    ReadFullTextTool,
]
