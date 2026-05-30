"""Document source mode for the SFT pipeline.

The ir-shim branch supports two top-level modes, controlled by the
``HERMES_DOC_SOURCE`` environment variable:

  - ``HERMES_DOC_SOURCE=local`` (default): Mode A. The agent reads
    pre-parsed JSON artifacts from disk via ``file_mapping.json`` and
    the sft_pipeline selector ranks pages locally. No IR / parser HTTP
    calls. SFT-only path; production master does not have this mode.
  - ``HERMES_DOC_SOURCE=remote``: Mode B. The agent runs the same
    end-to-end IR flow as production master. The SFT top-level
    script (``exaone/sft_gen/upload_to_ir.py``) uploads each raw file
    to the Dev Files API first to obtain a fid, then injects the fid
    into the per-task attachment table so the agent loop sees the
    same shape it would in production.

The previous env name ``HERMES_DOC_SHIM`` is no longer read — callers
must migrate to ``HERMES_DOC_SOURCE``. The rename is intentional: the
old name described an implementation detail ("we are bypassing IR"),
the new name describes the policy ("where do documents come from").

See ``exaone/docqa_tools/_policy.md`` for the full background on why
both modes exist and how they map onto the production flow.
"""

from __future__ import annotations

import os


def doc_source() -> str:
    """Return ``"local"`` or ``"remote"``. Default: ``"local"``."""
    raw = os.getenv("HERMES_DOC_SOURCE", "local").strip().lower()
    if raw in ("local", "remote"):
        return raw
    # Unknown value → default to local (safer for SFT batches that
    # forget to set the env). The shim helpers log a warning on first
    # use if you want to surface this.
    return "local"


def is_local_mode() -> bool:
    """Mode A: pre-parsed JSON + sft_pipeline selector. SFT-only."""
    return doc_source() == "local"


def is_remote_mode() -> bool:
    """Mode B: production-parity IR/parser flow."""
    return doc_source() == "remote"
