#!/usr/bin/env python3
"""Step 1.3: Generate model outputs for benchmark comparison.

Async multi-server inference (chartvr eval_multi_server.py pattern).
Distributes requests across N vLLM servers per model for max throughput.
Resume support: per-sample JSONL append, skips completed samples.

Usage:
    python -m scripts.step3_generate_models --model qwen397b
    python -m scripts.step3_generate_models --model qwen9b --ports 8100,8101,8110,8111
    python -m scripts.step3_generate_models --model internvl3 --ports 8112,8113,8114,8115
    python -m scripts.step3_generate_models --all-local
"""
import asyncio
import argparse
import json
import os
import re
import shutil
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import AsyncOpenAI

from scripts.config import DATA_DIR, MODEL_CONFIGS, VIZ_TYPES
from scripts.utils.rendering import render_chart, render_mermaid, render_mindmap
from scripts.utils.structure_extraction import extract_structure
from scripts.utils.doc_loader import load_doc_excerpts

from examples.diagram.diagram_tools import (
    CHART_DSL_EXAMPLES, CHART_SYSTEM_PROMPT,
    DIAGRAM_EXAMPLES, DIAGRAM_SYSTEM_PROMPT,
    MINDMAP_SYSTEM_PROMPT,
    MINDMAP_MERMAID_SYSTEM_PROMPT,
)

GOLD_DIR = os.path.join(DATA_DIR, "gold")
MODEL_OUTPUT_DIR = os.path.join(DATA_DIR, "model_outputs")


_LANG_NAMES = {"ko": "Korean", "en": "English", "zh": "Chinese"}


def get_system_prompt(viz_type: str, subtype: str, lang: str = "") -> str:
    if viz_type == "mindmap":
        if os.environ.get("VISUBENCH_MINDMAP_FORMAT", "").lower() == "mermaid":
            prompt = MINDMAP_MERMAID_SYSTEM_PROMPT
        else:
            prompt = MINDMAP_SYSTEM_PROMPT
    elif viz_type == "diagram":
        example = DIAGRAM_EXAMPLES.get(subtype, DIAGRAM_EXAMPLES["flowchart"])
        prompt = DIAGRAM_SYSTEM_PROMPT.format(diagram_type=subtype, one_shot_example=example)
    elif viz_type == "chart":
        example = CHART_DSL_EXAMPLES.get(subtype, CHART_DSL_EXAMPLES["bar"])
        prompt = CHART_SYSTEM_PROMPT.format(chart_type=subtype, one_shot_example=example)
    else:
        raise ValueError(f"Unknown viz_type: {viz_type}")

    # Append explicit language constraint if lang is known
    if lang and lang in _LANG_NAMES:
        lang_name = _LANG_NAMES[lang]
        prompt += (f"\n\nIMPORTANT: The source document is in {lang_name}. "
                   f"ALL output labels MUST be in {lang_name}.")

    return prompt


def get_default_query(viz_type: str) -> str:
    return {
        "mindmap": "이 문서의 핵심 내용을 마인드맵으로 정리해주세요.",
        "diagram": "Create a diagram of the key processes and relationships in this document.",
        "chart": "Create a chart of the key data in this document.",
    }[viz_type]


def make_specific_chart_query(doc_id: str, lang: str = "") -> str | None:
    """Build a specific chart query from gold chart structure.

    Extracts chart_type, title, x_labels, series names from gold structure
    to ensure comparison models target the same data as gold.
    Returns None if gold structure not found.
    """
    gold_path = os.path.join(GOLD_DIR, "chart", f"{doc_id}_structure.json")
    if not os.path.exists(gold_path):
        return None

    try:
        with open(gold_path, "r", encoding="utf-8") as f:
            gold = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    chart_type = gold.get("chart_type", "bar")
    title = gold.get("title", "")
    x_labels = gold.get("x_labels", [])
    series_names = list(gold.get("series", {}).keys())

    if not title and not series_names:
        return None

    # Truncate x_labels for prompt brevity
    x_display = x_labels[:8]
    if len(x_labels) > 8:
        x_display.append("...")

    if lang == "ko":
        parts = [f"다음 조건에 맞는 {chart_type} 차트를 생성하세요."]
        if title:
            parts.append(f"제목: {title}")
        if x_display:
            parts.append(f"X축: {x_display}")
        if series_names:
            parts.append(f"데이터 시리즈: {', '.join(series_names)}")
        parts.append("아래 문서에서 정확한 수치를 추출하여 사용하세요.")
    else:
        parts = [f"Create a {chart_type} chart"]
        if title:
            parts.append(f"titled '{title}'")
        if x_display:
            parts.append(f"with x-axis categories {x_display}")
        if series_names:
            parts.append(f"and data series: {', '.join(series_names)}")
        parts.append("using exact numerical values from the document.")

    return " ".join(parts)


# ── Gold copy (qwen397b) ──────────────────────────────────────────────────

def copy_gold_as_model_output(doc: dict, model_id: str = "qwen397b"):
    for viz_type in VIZ_TYPES:
        doc_id = doc["doc_id"]
        gold_dir = os.path.join(GOLD_DIR, viz_type)
        out_dir = os.path.join(MODEL_OUTPUT_DIR, model_id, viz_type)
        os.makedirs(out_dir, exist_ok=True)
        for suffix in ["_source.txt", "_structure.json", "_rendered.png",
                        "_rendered.html", "_rendered.svg"]:
            src = os.path.join(gold_dir, f"{doc_id}{suffix}")
            dst = os.path.join(out_dir, f"{doc_id}{suffix}")
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)


# ── Resume support ─────────────────────────────────────────────────────────

def load_done_ids(log_path: str) -> set:
    """Load completed (doc_id, viz_type) pairs from log JSONL."""
    done = set()
    if os.path.exists(log_path):
        with open(log_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if r.get("success"):
                        done.add((r["doc_id"], r["viz_type"]))
                except (json.JSONDecodeError, KeyError):
                    pass
    return done


# ── Sync post-processing (render + structure) ─────────────────────────────

def postprocess_and_save(doc_id: str, model_id: str, viz_type: str,
                          subtype: str, raw_output: str) -> dict:
    """Post-process LLM output: save source, extract structure, render."""
    output_dir = os.path.join(MODEL_OUTPUT_DIR, model_id, viz_type)
    os.makedirs(output_dir, exist_ok=True)

    source_path = os.path.join(output_dir, f"{doc_id}_source.txt")
    structure_path = os.path.join(output_dir, f"{doc_id}_structure.json")

    result = {"doc_id": doc_id, "model_id": model_id, "viz_type": viz_type,
              "subtype": subtype, "success": False, "error": None}

    try:
        # Strip <think> blocks
        clean = re.sub(r'<think>.*?</think>', '', raw_output, flags=re.DOTALL).strip()
        if not clean or len(clean) < 10:
            result["error"] = "Empty output after think stripping"
            return result

        # Save source
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(clean)

        # Extract structure
        structure = extract_structure(clean, viz_type, subtype)
        if "node_labels" in structure:
            structure["node_labels"] = sorted(structure["node_labels"])
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump(structure, f, ensure_ascii=False, indent=2, default=str)

        # Render
        if viz_type == "mindmap":
            rr = render_mindmap(clean, output_dir, doc_id, model_id=model_id)
        elif viz_type == "diagram":
            rr = render_mermaid(clean, subtype, output_dir, doc_id)
        elif viz_type == "chart":
            rr = render_chart(clean, subtype, output_dir, doc_id)

        result["success"] = True
        result["rendered"] = rr.get("success", False)

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)}"

    return result


# ── Async multi-server inference (chartvr pattern) ─────────────────────────

async def run_async_inference(model_id: str, corpus: list, server_urls: list,
                               model_name: str, max_docs: int = 0,
                               viz_type_filter: str = ""):
    """Async parallel inference across multiple vLLM servers.

    Pattern from chartvr/eval_multi_server.py:
    - AsyncOpenAI clients, round-robin distribution
    - Semaphore(servers * 5) concurrency control
    - Per-sample JSONL append for resume
    """
    log_dir = os.path.join(MODEL_OUTPUT_DIR, model_id)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "render_log.jsonl")

    done_ids = load_done_ids(log_path)

    # Build task list (respect viz_type filter if set)
    viz_types = [viz_type_filter] if viz_type_filter else VIZ_TYPES
    tasks_todo = []
    for doc in corpus:
        for viz_type in viz_types:
            key = (doc["doc_id"], viz_type)
            if key not in done_ids:
                subtype = ""
                if viz_type == "diagram":
                    subtype = doc.get("diagram_subtype", "flowchart")
                elif viz_type == "chart":
                    subtype = doc.get("chart_subtype", "bar")
                tasks_todo.append((doc, viz_type, subtype))

    total_all = len(corpus) * len(VIZ_TYPES)
    print(f"[{model_id}] {len(tasks_todo)} remaining / {total_all} total, "
          f"{len(server_urls)} servers")

    if not tasks_todo:
        print(f"[{model_id}] All done.")
        return

    clients = [AsyncOpenAI(base_url=url, api_key="dummy") for url in server_urls]
    sem = asyncio.Semaphore(len(server_urls) * 3)  # 3 per server (reduced to avoid sidecar overload)
    file_lock = asyncio.Lock()
    counters = {"success": 0, "fail": 0}

    async def infer_one(idx: int, doc: dict, viz_type: str, subtype: str):
        client = clients[idx % len(clients)]
        doc_id = doc["doc_id"]

        async with sem:
            # Load doc text (sync, fast)
            # Limit to ~3000 tokens to leave room for output within 8192 context
            doc_text = load_doc_excerpts(
                [doc["doc_json_path"]],
                max_pages=8, chars_per_page=1500, max_total=10000
            )
            if not doc_text or len(doc_text.strip()) < 50:
                result = {"doc_id": doc_id, "model_id": model_id,
                          "viz_type": viz_type, "success": False,
                          "error": "Insufficient document text"}
                async with file_lock:
                    with open(log_path, "a") as f:
                        f.write(json.dumps(result, ensure_ascii=False) + "\n")
                counters["fail"] += 1
                return

            lang = doc.get("lang", "")
            system_prompt = get_system_prompt(viz_type, subtype, lang=lang)

            # Use specific chart query from gold structure (Issue 3 fix)
            if viz_type == "chart":
                query = make_specific_chart_query(doc_id, lang) or get_default_query("chart")
            else:
                query = get_default_query(viz_type)

            user_content = f"User query: {query}\n\nDocument source:\n{doc_text}"

            try:
                cfg = MODEL_CONFIGS.get(model_id, {})
                # max_tokens intentionally NOT set — let local vLLM use its
                # max_model_len default to avoid silent truncation.
                api_kwargs = dict(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.2,
                )
                # Only send enable_thinking for models that support toggle
                if cfg.get("thinking_toggle") is not None:
                    api_kwargs["extra_body"] = {
                        "chat_template_kwargs": {"enable_thinking": cfg["thinking_toggle"]}
                    }
                resp = await client.chat.completions.create(**api_kwargs)
                msg = resp.choices[0].message
                # Reasoning models put output in content after reasoning
                raw_output = msg.content or ""
            except Exception as e:
                raw_output = ""
                result = {"doc_id": doc_id, "model_id": model_id,
                          "viz_type": viz_type, "subtype": subtype,
                          "success": False, "error": f"API: {e}"}
                async with file_lock:
                    with open(log_path, "a") as f:
                        f.write(json.dumps(result, ensure_ascii=False) + "\n")
                counters["fail"] += 1
                return

        # Post-process (sync, CPU-bound — run in executor to avoid blocking)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, postprocess_and_save, doc_id, model_id, viz_type, subtype, raw_output
        )

        async with file_lock:
            with open(log_path, "a") as f:
                f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")

        if result["success"]:
            counters["success"] += 1
        else:
            counters["fail"] += 1

        done = counters["success"] + counters["fail"]
        if done % 50 == 0 or done == len(tasks_todo):
            print(f"  [{model_id}] {done}/{len(tasks_todo)} "
                  f"(ok={counters['success']}, fail={counters['fail']})", flush=True)

    # Launch all tasks
    t0 = time.time()
    aws = [infer_one(i, doc, vt, st) for i, (doc, vt, st) in enumerate(tasks_todo)]
    await asyncio.gather(*aws)

    elapsed = time.time() - t0
    print(f"[{model_id}] Done in {elapsed:.0f}s — "
          f"success={counters['success']}, fail={counters['fail']}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate model outputs")
    parser.add_argument("--model", choices=list(MODEL_CONFIGS.keys()))
    parser.add_argument("--ports", help="Comma-separated ports (overrides config)")
    parser.add_argument("--all-local", action="store_true")
    parser.add_argument("--max-docs", type=int, default=0)
    parser.add_argument("--viz-type", choices=VIZ_TYPES)
    args = parser.parse_args()

    corpus_path = os.path.join(DATA_DIR, "documents", "corpus.jsonl")
    with open(corpus_path, "r", encoding="utf-8") as f:
        corpus = [json.loads(line) for line in f if line.strip()]

    if args.max_docs > 0:
        corpus = corpus[:args.max_docs]

    models = []
    if args.model:
        models = [args.model]
    elif args.all_local:
        models = ["qwen397b", "qwen9b", "internvl3"]
    else:
        models = ["qwen397b"]

    print(f"Corpus: {len(corpus)} docs, Models: {models}")

    for model_id in models:
        config = MODEL_CONFIGS[model_id]

        # qwen397b: copy from gold
        if model_id == "qwen397b":
            print(f"\n[qwen397b] Copying gold → model_outputs...")
            for doc in corpus:
                copy_gold_as_model_output(doc)
            print(f"  Done.")
            continue

        # Determine server URLs
        if args.ports:
            ports = [int(p) for p in args.ports.split(",")]
        elif "ports" in config:
            ports = config["ports"]
        else:
            ports = [8000]

        server_urls = [f"http://localhost:{p}/v1" for p in ports]
        model_name = config["model"]

        print(f"\n[{model_id}] Servers: {ports}, Model: {model_name}")
        asyncio.run(run_async_inference(model_id, corpus, server_urls,
                                         model_name, args.max_docs,
                                         viz_type_filter=args.viz_type or ""))


if __name__ == "__main__":
    main()
