#!/usr/bin/env python3
"""Step 1.2: Generate Gold reference visualizations using Qwen3.5-397B.

For each document in corpus.jsonl, generates 3 visualizations
(mindmap, diagram, chart) using the existing system prompts,
post-processes, extracts structure, and renders via sidecars.

Usage:
    python -m scripts.step2_generate_gold [--max-docs N] [--viz-type mindmap|diagram|chart]
"""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.config import DATA_DIR, VIZ_TYPES
from scripts.utils.llm_clients import call_model
from scripts.utils.rendering import render_chart, render_mermaid, render_mindmap
from scripts.utils.structure_extraction import extract_structure

# Import system prompts and examples from existing code
from examples.diagram.diagram_tools import (
    CHART_DSL_EXAMPLES,
    CHART_SYSTEM_PROMPT,
    DIAGRAM_EXAMPLES,
    DIAGRAM_SYSTEM_PROMPT,
    MINDMAP_SYSTEM_PROMPT,
)

# Import doc loader from eval
from scripts.utils.doc_loader import load_doc_excerpts


GOLD_MODEL = "qwen397b"
GOLD_DIR = os.path.join(DATA_DIR, "gold")


def build_user_content(doc_text: str, viz_type: str, query: str = "") -> str:
    """Build user content from doc text, matching existing tool behavior."""
    if query:
        return f"User query: {query}\n\nDocument source:\n{doc_text}"
    return doc_text


def get_default_query(viz_type: str) -> str:
    """Default query per viz type for gold generation."""
    return {
        "mindmap": "이 문서의 핵심 내용을 마인드맵으로 정리해주세요.",
        "diagram": "Create a diagram of the key processes and relationships in this document.",
        "chart": "Create a chart of the key data in this document.",
    }[viz_type]


def get_system_prompt(viz_type: str, subtype: str) -> str:
    """Get the appropriate system prompt."""
    if viz_type == "mindmap":
        return MINDMAP_SYSTEM_PROMPT
    elif viz_type == "diagram":
        example = DIAGRAM_EXAMPLES.get(subtype, DIAGRAM_EXAMPLES["flowchart"])
        return DIAGRAM_SYSTEM_PROMPT.format(
            diagram_type=subtype, one_shot_example=example
        )
    elif viz_type == "chart":
        example = CHART_DSL_EXAMPLES.get(subtype, CHART_DSL_EXAMPLES["bar"])
        return CHART_SYSTEM_PROMPT.format(
            chart_type=subtype, one_shot_example=example
        )
    else:
        raise ValueError(f"Unknown viz_type: {viz_type}")


def generate_single(doc: dict, viz_type: str) -> dict:
    """Generate one gold visualization for a document.

    Returns result dict with success status, paths, and metadata.
    """
    doc_id = doc["doc_id"]
    subtype = ""
    if viz_type == "diagram":
        subtype = doc.get("diagram_subtype", "flowchart")
    elif viz_type == "chart":
        subtype = doc.get("chart_subtype", "bar")

    output_dir = os.path.join(GOLD_DIR, viz_type)
    os.makedirs(output_dir, exist_ok=True)

    # Check if already generated (resume support)
    source_path = os.path.join(output_dir, f"{doc_id}_source.txt")
    structure_path = os.path.join(output_dir, f"{doc_id}_structure.json")
    if os.path.exists(source_path) and os.path.exists(structure_path):
        return {"doc_id": doc_id, "viz_type": viz_type, "success": True,
                "skipped": True, "source_path": source_path}

    result = {
        "doc_id": doc_id, "viz_type": viz_type, "subtype": subtype,
        "success": False, "error": None, "source_path": "",
        "structure_path": "", "rendered_path": "", "skipped": False,
    }

    try:
        # 1. Load document text
        doc_text = load_doc_excerpts(
            [doc["doc_json_path"]],
            max_pages=30, chars_per_page=3000, max_total=50000
        )
        if not doc_text or len(doc_text.strip()) < 50:
            result["error"] = "Insufficient document text"
            return result

        # 2. Build prompt
        system_prompt = get_system_prompt(viz_type, subtype)
        query = get_default_query(viz_type)
        user_content = build_user_content(doc_text, viz_type, query)

        # 3. Call LLM (Qwen397B via LLMPool)
        raw_output = call_model(
            GOLD_MODEL, system_prompt, user_content,
            temperature=0.2,
        )

        if not raw_output or len(raw_output.strip()) < 10:
            result["error"] = "Empty LLM output"
            return result

        # 4. Save source text
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(raw_output)
        result["source_path"] = source_path

        # 5. Extract structure
        structure = extract_structure(raw_output, viz_type, subtype)
        # Convert sets to lists for JSON serialization
        if "node_labels" in structure:
            structure["node_labels"] = sorted(structure["node_labels"])
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump(structure, f, ensure_ascii=False, indent=2, default=str)
        result["structure_path"] = structure_path

        # 6. Render
        if viz_type == "mindmap":
            render_result = render_mindmap(raw_output, output_dir, doc_id)
        elif viz_type == "diagram":
            render_result = render_mermaid(raw_output, subtype, output_dir, doc_id)
        elif viz_type == "chart":
            render_result = render_chart(raw_output, subtype, output_dir, doc_id)

        result["rendered_path"] = render_result.get("rendered_path", "")
        if render_result.get("success"):
            result["success"] = True
        else:
            result["error"] = render_result.get("error", "Render failed")
            # Still mark partial success if source + structure exist
            result["success"] = True  # source and structure are the key outputs

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)}"
        traceback.print_exc()

    return result


def main():
    parser = argparse.ArgumentParser(description="Generate Gold references")
    parser.add_argument("--max-docs", type=int, default=0, help="Limit docs (0=all)")
    parser.add_argument("--viz-type", choices=VIZ_TYPES, help="Single viz type only")
    parser.add_argument("--start-from", type=int, default=0, help="Start from doc index")
    args = parser.parse_args()

    # Load corpus
    corpus_path = os.path.join(DATA_DIR, "documents", "corpus.jsonl")
    if not os.path.exists(corpus_path):
        print(f"ERROR: {corpus_path} not found. Run step1 first.")
        sys.exit(1)

    with open(corpus_path, "r", encoding="utf-8") as f:
        corpus = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(corpus)} documents from corpus")

    if args.start_from > 0:
        corpus = corpus[args.start_from:]
        print(f"  Starting from index {args.start_from}")

    if args.max_docs > 0:
        corpus = corpus[:args.max_docs]
        print(f"  Limited to {len(corpus)} documents")

    viz_types = [args.viz_type] if args.viz_type else VIZ_TYPES

    # Process
    failures_path = os.path.join(GOLD_DIR, "failures.jsonl")
    total = len(corpus) * len(viz_types)
    success_count = 0
    skip_count = 0
    fail_count = 0

    print(f"\nGenerating gold references: {len(corpus)} docs × {len(viz_types)} types = {total} total")
    print(f"Output: {GOLD_DIR}")
    print("=" * 60)

    t0 = time.time()
    for i, doc in enumerate(corpus):
        for viz_type in viz_types:
            idx = i * len(viz_types) + viz_types.index(viz_type) + 1
            subtype = ""
            if viz_type == "diagram":
                subtype = doc.get("diagram_subtype", "flowchart")
            elif viz_type == "chart":
                subtype = doc.get("chart_subtype", "bar")

            print(f"  [{idx}/{total}] {doc['doc_id'][:8]}... {viz_type}"
                  f"{'/' + subtype if subtype else ''}", end=" ", flush=True)

            result = generate_single(doc, viz_type)

            if result.get("skipped"):
                skip_count += 1
                print("SKIP (exists)")
            elif result["success"]:
                success_count += 1
                rendered = "✓ rendered" if result.get("rendered_path") else "⚠ no render"
                print(f"OK ({rendered})")
            else:
                fail_count += 1
                print(f"FAIL: {result.get('error', 'unknown')}")
                with open(failures_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "doc_id": doc["doc_id"], "viz_type": viz_type,
                        "subtype": subtype, "error": result.get("error"),
                    }, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    print("=" * 60)
    print(f"Done in {elapsed:.0f}s")
    print(f"  Success: {success_count}, Skipped: {skip_count}, Failed: {fail_count}")
    print(f"  Success rate: {(success_count + skip_count) / total * 100:.1f}%")


if __name__ == "__main__":
    main()
