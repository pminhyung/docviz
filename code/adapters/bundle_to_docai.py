"""Bundle → docai-format JSON conversion.

The docviz/agent server's `/v2/run` endpoint takes a `doc_json_path` pointing
at a JSON file. The agent's document_loader (agent/core/document_loader.py)
recognizes the dict-of-pages format `{"1": "...", "2": "...", ...}` directly,
so we serialize each Bundle as a single such file with one page per source
document.

Concat convention (LongBench-style multi-doc context):

    Page N corresponds to docs[N-1]. Each page text is:

        Passage [N]
        Title: <doc.title>

        <doc.content>

The Bundle's docs[i].doc_id is preserved in `Bundle.metadata["page_to_doc_id"]`
so SAO post-processing can map the agent's citations / page references back to
the original doc_id.

Why one page per doc (not chunked):
  - The Qwen3.6-27B vLLM endpoints serve max_model_len=131072 (128K tokens).
    Even the largest expected bundle (10-K MD&A + Risk = ~20K chars per Doc,
    2 Docs = ~40K chars ≈ ~10K tokens) fits with comfortable headroom.
  - One-page-per-doc preserves a clean doc_id boundary for SAO.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Tuple

from code.pipelines.base import Bundle


def bundle_to_docai_dict(bundle: Bundle) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Serialize a Bundle into the docai dict-of-pages format.

    Returns:
        (docai_dict, page_to_doc_id)
        - docai_dict: {"1": "...passage 1 text...", "2": "...", ...}
        - page_to_doc_id: {"1": doc_id_1, "2": doc_id_2, ...}
    """
    docai: Dict[str, str] = {}
    page_to_doc_id: Dict[str, str] = {}

    for idx, doc in enumerate(bundle.docs, start=1):
        page_key = str(idx)
        page_text = (
            f"Passage [{idx}]\n"
            f"Title: {doc.title}\n\n"
            f"{doc.content}"
        )
        docai[page_key] = page_text
        page_to_doc_id[page_key] = doc.doc_id

    return docai, page_to_doc_id


def write_bundle_as_docai(
    bundle: Bundle,
    out_dir: str | os.PathLike[str] | None = None,
) -> Tuple[str, Dict[str, str]]:
    """Persist the docai JSON for a Bundle and return (path, page_to_doc_id).

    If out_dir is None, a temporary file under $TMPDIR is created and its path
    returned. The caller is responsible for cleanup.

    The returned page_to_doc_id is also written into bundle.metadata under
    the key "page_to_doc_id" so downstream SAO post-processing can rely on it
    without re-parsing the JSON.
    """
    docai, page_to_doc_id = bundle_to_docai_dict(bundle)

    if out_dir is None:
        fd, path = tempfile.mkstemp(prefix=f"bundle_{bundle.bundle_id}_", suffix=".json")
        os.close(fd)
    else:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = str(out_dir / f"{bundle.bundle_id}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(docai, f, ensure_ascii=False, indent=2)

    bundle.metadata["page_to_doc_id"] = page_to_doc_id
    return path, page_to_doc_id
