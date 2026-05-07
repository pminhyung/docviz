#!/usr/bin/env python3
"""Preflight: Compare Markdown vs Mermaid mindmap prompts for Claude Sonnet.

Generates Mermaid-format mindmaps for 3 test documents using the explicit
MINDMAP_MERMAID_SYSTEM_PROMPT, then compares structure metrics against:
  (a) Gold structures
  (b) Existing Markdown-format Sonnet outputs

Usage:
    python -m scripts.claude_preflight.mermaid_mindmap_preflight
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.claude_preflight.claude_client import call_text_generation
from scripts.config import DATA_DIR
from scripts.step3_generate_models import get_default_query
from scripts.utils.doc_loader import load_doc_excerpts
from scripts.utils.structure_extraction import extract_structure
from eval.metrics.structural import (
    node_coverage_f1,
    edge_precision_f1,
)
from examples.diagram.diagram_tools import MINDMAP_MERMAID_SYSTEM_PROMPT

# ── Config ────────────────────────────────────────────────────────────────
TEST_DOC_IDS = ["09a76cdd", "8834437a", "bbfed79d"]
OUTPUT_DIR = os.path.join(DATA_DIR, "claude_preflight", "mermaid_mindmap_test")
GOLD_DIR = os.path.join(DATA_DIR, "gold", "mindmap")
SONNET_MD_DIR = os.path.join(DATA_DIR, "model_outputs", "claude_sonnet_4_6", "mindmap")
CORPUS_PATH = os.path.join(DATA_DIR, "documents", "corpus.jsonl")


def _load_corpus_map() -> dict[str, dict]:
    """Load corpus as {doc_id: row}."""
    result = {}
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                result[row["doc_id"]] = row
    return result


def _load_structure(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "node_labels" in data and isinstance(data["node_labels"], list):
        data["node_labels"] = set(data["node_labels"])
    return data


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    corpus_map = _load_corpus_map()

    # Append language constraint (matching get_system_prompt logic)
    lang_suffix = {
        "en": "\n\nIMPORTANT: The source document is in English. ALL output labels MUST be in English.",
        "ko": "\n\nIMPORTANT: The source document is in Korean. ALL output labels MUST be in Korean.",
        "zh": "\n\nIMPORTANT: The source document is in Chinese. ALL output labels MUST be in Chinese.",
    }

    results = []

    for doc_id in TEST_DOC_IDS:
        doc = corpus_map.get(doc_id)
        if not doc:
            print(f"[SKIP] {doc_id}: not found in corpus")
            continue

        lang = doc.get("lang", "en")
        doc_text = load_doc_excerpts(
            [doc["doc_json_path"]],
            max_pages=8, chars_per_page=1500, max_total=10000,
        )
        if not doc_text or len(doc_text.strip()) < 50:
            print(f"[SKIP] {doc_id}: insufficient doc text")
            continue

        # Build prompt using the Mermaid system prompt
        system_prompt = MINDMAP_MERMAID_SYSTEM_PROMPT + lang_suffix.get(lang, "")
        query = get_default_query("mindmap")
        user_content = f"User query: {query}\n\nDocument source:\n{doc_text}"

        print(f"\n[GEN] {doc_id} (lang={lang}) ...", flush=True)
        t0 = time.time()
        resp = call_text_generation(user_content, system_prompt, timeout=240)
        elapsed = time.time() - t0
        print(f"  claude_ok={resp.ok} tokens={resp.output_tokens} "
              f"cost=${resp.cost_usd:.4f} time={elapsed:.1f}s")

        if not resp.ok:
            print(f"  ERROR: {resp.error}")
            results.append({
                "doc_id": doc_id, "ok": False, "error": resp.error,
            })
            continue

        raw = resp.text or ""

        # Save raw output
        src_path = os.path.join(OUTPUT_DIR, f"{doc_id}_source.txt")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(raw)
        print(f"  Saved: {src_path}")
        print(f"  Preview: {raw[:200]}")

        # Extract structure from the Mermaid output
        mermaid_struct = extract_structure(raw, "mindmap")
        struct_path = os.path.join(OUTPUT_DIR, f"{doc_id}_structure.json")
        with open(struct_path, "w", encoding="utf-8") as f:
            # Convert sets to lists for JSON
            save_struct = dict(mermaid_struct)
            if isinstance(save_struct.get("node_labels"), set):
                save_struct["node_labels"] = sorted(save_struct["node_labels"])
            json.dump(save_struct, f, ensure_ascii=False, indent=2, default=str)

        # Load gold structure
        gold_path = os.path.join(GOLD_DIR, f"{doc_id}_structure.json")
        gold_struct = _load_structure(gold_path)

        # Load existing Markdown Sonnet structure
        md_struct_path = os.path.join(SONNET_MD_DIR, f"{doc_id}_structure.json")
        md_struct = _load_structure(md_struct_path)

        rec = {
            "doc_id": doc_id,
            "ok": True,
            "cost_usd": resp.cost_usd,
            "output_tokens": resp.output_tokens,
            "duration_s": round(elapsed, 2),
        }

        # Mermaid stats
        rec["mermaid_nodes"] = mermaid_struct["stats"]["num_nodes"]
        rec["mermaid_edges"] = mermaid_struct["stats"]["num_edges"]
        rec["mermaid_node_labels"] = len(mermaid_struct.get("node_labels", set()))

        # Compare Mermaid vs Gold
        if gold_struct:
            rec["gold_nodes"] = gold_struct["stats"]["num_nodes"]
            rec["gold_edges"] = gold_struct["stats"]["num_edges"]
            rec["gold_node_labels"] = len(gold_struct.get("node_labels", set()))

            nf1 = node_coverage_f1(gold_struct, mermaid_struct)
            rec["mermaid_vs_gold_node_f1"] = nf1["f1"]
            rec["mermaid_vs_gold_node_prec"] = nf1["precision"]
            rec["mermaid_vs_gold_node_rec"] = nf1["recall"]

            ef1 = edge_precision_f1(gold_struct, mermaid_struct)
            rec["mermaid_vs_gold_edge_f1"] = ef1["f1"]

        # Compare existing Markdown vs Gold (baseline)
        if md_struct and gold_struct:
            rec["md_nodes"] = md_struct["stats"]["num_nodes"]
            rec["md_edges"] = md_struct["stats"]["num_edges"]
            rec["md_node_labels"] = len(md_struct.get("node_labels", set()))

            nf1_md = node_coverage_f1(gold_struct, md_struct)
            rec["md_vs_gold_node_f1"] = nf1_md["f1"]
            rec["md_vs_gold_node_prec"] = nf1_md["precision"]
            rec["md_vs_gold_node_rec"] = nf1_md["recall"]

            ef1_md = edge_precision_f1(gold_struct, md_struct)
            rec["md_vs_gold_edge_f1"] = ef1_md["f1"]

        results.append(rec)

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("MERMAID MINDMAP PREFLIGHT RESULTS")
    print("=" * 80)

    for rec in results:
        if not rec.get("ok"):
            print(f"\n{rec['doc_id']}: FAILED — {rec.get('error', 'unknown')}")
            continue

        doc_id = rec["doc_id"]
        print(f"\n--- {doc_id} ---")
        print(f"  Gold:    nodes={rec.get('gold_nodes','?')}  "
              f"edges={rec.get('gold_edges','?')}  "
              f"labels={rec.get('gold_node_labels','?')}")
        print(f"  Mermaid: nodes={rec['mermaid_nodes']}  "
              f"edges={rec['mermaid_edges']}  "
              f"labels={rec['mermaid_node_labels']}")
        print(f"  Md(old): nodes={rec.get('md_nodes','?')}  "
              f"edges={rec.get('md_edges','?')}  "
              f"labels={rec.get('md_node_labels','?')}")
        print()
        print(f"  Mermaid vs Gold:  node_f1={rec.get('mermaid_vs_gold_node_f1','?'):.4f}  "
              f"prec={rec.get('mermaid_vs_gold_node_prec','?'):.4f}  "
              f"rec={rec.get('mermaid_vs_gold_node_rec','?'):.4f}  "
              f"edge_f1={rec.get('mermaid_vs_gold_edge_f1','?'):.4f}")
        print(f"  Md vs Gold:      node_f1={rec.get('md_vs_gold_node_f1','?'):.4f}  "
              f"prec={rec.get('md_vs_gold_node_prec','?'):.4f}  "
              f"rec={rec.get('md_vs_gold_node_rec','?'):.4f}  "
              f"edge_f1={rec.get('md_vs_gold_edge_f1','?'):.4f}")
        print(f"  Cost: ${rec.get('cost_usd',0):.4f}  "
              f"Tokens: {rec.get('output_tokens',0)}  "
              f"Time: {rec.get('duration_s',0):.1f}s")

    # Averages
    ok_recs = [r for r in results if r.get("ok")]
    if ok_recs:
        print("\n" + "-" * 80)
        print("AVERAGES (n={})".format(len(ok_recs)))
        for key, label in [
            ("mermaid_vs_gold_node_f1", "Mermaid node_f1"),
            ("md_vs_gold_node_f1", "Markdown node_f1"),
            ("mermaid_vs_gold_edge_f1", "Mermaid edge_f1"),
            ("md_vs_gold_edge_f1", "Markdown edge_f1"),
        ]:
            vals = [r[key] for r in ok_recs if key in r]
            if vals:
                avg = sum(vals) / len(vals)
                print(f"  {label:25s}: {avg:.4f}")

    # Save full results as JSONL
    log_path = os.path.join(OUTPUT_DIR, "results.jsonl")
    with open(log_path, "w", encoding="utf-8") as f:
        for rec in results:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    print(f"\nResults saved: {log_path}")


if __name__ == "__main__":
    main()
