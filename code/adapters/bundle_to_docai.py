"""Bundle → docai-format JSON conversion.

The docviz/agent server's `/v2/run` endpoint accepts a list of JSON file
paths via the `doc_json_paths` field. The agent's DocumentLoader recognizes
the dict-of-pages format `{"1": "...", "2": "...", ...}` directly, so we
serialize each source doc in the bundle as ITS OWN such file (one doc per
file). This preserves the multi-document structure expected by the rest of
the agent pipeline:

  - `DOC_STEP_PROMPT` (`agent/config/training_prompts.py`) expects 2+
    documents and asks for a per-doc summary that "starts each with the
    document name."
  - `doc_contexts` (`run_agent_v2.py:380`) iterates `multi_docs` and emits
    one `File N: <filename>\n<snippet>` block per document.
  - `filelist` (`run_agent_v2.py:519`) shows the agent
    `Document1-<file>, Document2-<file>, ...` so tool args
    `document_number=[1]`, `[2]`, etc. drill into specific source docs via
    `search` and `ReadFullDocument`.

The earlier `single_doc=True` + concat-as-pages serialization collapsed the
bundle into one synthetic document with N "pages", which defeated all three
of the above and let the agent rationalize skipping `search` / `RFD` because
the Step-1 doc summary already covered everything from the 80K-truncated
concat.

Why one page per source doc (not chunked):
  - The on-prem Qwen3.5-397B-A17B-FP8 vLLM endpoints serve max_model_len=131072
    (128K tokens). Even bundles totaling ~40-50K chars per source doc fit with
    headroom across all paths.
  - One-page-per-doc preserves a clean doc_id ↔ file boundary for SAO and
    keeps the agent's `document_number` semantics aligned with source docs.

The `page_to_doc_id` map is keyed by `str(doc_idx)` (the 1-based index of
the source doc in the bundle, which is the same as the `document_number`
the agent uses). SAO post-processing in viz_output_mapper falls back to
`page_<n>` when a key is missing, so this keying is the simplest form
that the existing mapper can consume.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

from code.pipelines.base import Bundle


_SLUG_DROP = re.compile(r"[^A-Za-z0-9가-힣\s_-]")
_SLUG_SPACE = re.compile(r"\s+")


def _slug(title: str, maxlen: int = 60) -> str:
    """Lowercased, dash-joined, alphanumeric-only slug of a doc title.

    Used to put the source doc's title into the on-disk filename so the
    agent's filelist (which is derived from filenames) carries human
    readable per-doc identifiers like
    `Document2-arxiv_03_01_attention-is-all-you-need`.
    """
    s = _SLUG_DROP.sub("", title or "")
    s = _SLUG_SPACE.sub("-", s.strip())
    s = s.strip("-").lower()
    return s[:maxlen] if s else "untitled"


def write_bundle_as_docai(
    bundle: Bundle,
    out_dir: str | os.PathLike[str] | None = None,
) -> Tuple[List[str], Dict[str, str]]:
    """Persist one docai JSON file per source doc and return (paths, page_to_doc_id).

    Each source doc in ``bundle.docs`` is written to its own JSON file in
    the dict-of-pages format with a single page (page 1) holding
    ``"Title: <doc.title>\\n\\n<doc.content>"``. The agent will see this
    as N distinct documents with sensible per-doc filenames.

    Filename pattern: ``{bundle_id}_{doc_idx:02d}_{slug(title)}.json``
    (1-based ``doc_idx``).

    Returns:
        Tuple of (paths, page_to_doc_id):
        - paths: list of N file paths, one per source doc, in bundle order.
        - page_to_doc_id: ``{str(doc_idx): doc.doc_id}`` for SAO mapping.

    The returned ``page_to_doc_id`` is also stashed in
    ``bundle.metadata["page_to_doc_id"]`` so downstream SAO post-processing
    can use it without re-parsing.

    If ``out_dir`` is None, a per-bundle subdirectory is created under
    ``$TMPDIR`` and the caller is responsible for cleanup.
    """
    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix=f"bundle_{bundle.bundle_id}_"))
    else:
        out_dir = Path(out_dir) / bundle.bundle_id
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: List[str] = []
    page_to_doc_id: Dict[str, str] = {}

    for idx, doc in enumerate(bundle.docs, start=1):
        page_to_doc_id[str(idx)] = doc.doc_id
        # Page 1 of this file carries the title + content of one source doc.
        page_text = f"Title: {doc.title}\n\n{doc.content}"
        docai_dict: Dict[str, str] = {"1": page_text}

        fname = f"{bundle.bundle_id}_{idx:02d}_{_slug(doc.title)}.json"
        path = out_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(docai_dict, f, ensure_ascii=False, indent=2)
        paths.append(str(path))

    bundle.metadata["page_to_doc_id"] = page_to_doc_id
    return paths, page_to_doc_id


def bundle_to_docai_dict(bundle: Bundle) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Legacy single-file serializer — concats all docs as pages of ONE file.

    Retained for the rare backward-compat path; new code should use
    ``write_bundle_as_docai`` (N files). The single-file form collapses N
    source docs into one synthetic document and breaks the per-doc
    structure that ``search`` / ``ReadFullDocument`` rely on; see this
    module's docstring for the failure mode.
    """
    docai: Dict[str, str] = {}
    page_to_doc_id: Dict[str, str] = {}
    for idx, doc in enumerate(bundle.docs, start=1):
        page_key = str(idx)
        page_text = f"Passage [{idx}]\nTitle: {doc.title}\n\n{doc.content}"
        docai[page_key] = page_text
        page_to_doc_id[page_key] = doc.doc_id
    return docai, page_to_doc_id
