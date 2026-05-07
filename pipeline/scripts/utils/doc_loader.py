"""Document excerpt loader — standalone copy of eval.core.load_doc_excerpts.

Avoids importing eval.core which depends on doc_agent_v2.
"""
import json
import os
from typing import List


def load_doc_excerpts(
    doc_paths: List[str],
    max_pages: int = 15,
    chars_per_page: int = 3000,
    max_total: int = 40000,
) -> str:
    """Load document excerpts from docai JSON files. Supports multiple docs."""
    doc_text = ""
    for doc_idx, path in enumerate(doc_paths):
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                raw = json.load(f)
            hp = raw.get("outputs", [{}])[0].get("html_parsed", {})
            fname = raw.get("outputs", [{}])[0].get("file_name", f"Document {doc_idx + 1}")
            doc_text += f"\n=== Document {doc_idx + 1}: {fname} ===\n"
            for pg in sorted(hp.keys(), key=lambda x: int(x) if x.isdigit() else 0)[:max_pages]:
                content = hp[pg]
                if isinstance(content, list):
                    content = "\n".join(str(x) for x in content)
                doc_text += f"\n[p.{pg}] {str(content)[:chars_per_page]}\n"
                if len(doc_text) > max_total:
                    break
        except Exception:
            pass
    return doc_text
