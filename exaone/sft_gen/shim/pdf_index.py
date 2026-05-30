"""PDF → pre-parsed JSON path lookup for the SFT shim.

The lookup uses ``<parsed_root>/file_mapping.json`` as the source of truth.
Each entry maps a JSON stem (UUID) to the original PDF (absolute_path,
relative_path, original_filename). The parsed JSON itself lives at
``<parsed_root>/<dirname(relative_path)>/<stem>.json``.

We invert that mapping into two lookup tables — by absolute path (after
normalization) and by basename — so the shim can resolve either flavor
of caller-supplied ``file_path``. Built lazily per process and cached.

Environment:
    EXAONE_PARSED_ROOT — root directory containing file_mapping.json and
        per-category subdirectories of parsed JSONs.
        Default: ``/ex_disk2/mhpark/poc/docai/out``
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


_DEFAULT_PARSED_ROOT = "/ex_disk2/mhpark/poc/docai/out"
_MAPPING_FILENAME = "file_mapping.json"


@dataclass(frozen=True)
class PdfEntry:
    """One PDF / parsed-JSON pair from file_mapping.json."""

    stem: str               # JSON UUID stem (e.g. "21573a84")
    raw_pdf_path: Path      # Absolute path to the raw PDF
    parsed_json_path: Path  # Absolute path to the parsed JSON
    original_filename: str  # Basename of the PDF


class _PdfIndex:
    """Process-local lookup tables built once per worker."""

    def __init__(self, parsed_root: Path):
        self.parsed_root = parsed_root
        self._by_abs_path: Dict[str, PdfEntry] = {}
        self._by_basename: Dict[str, PdfEntry] = {}

    def lookup(self, file_path: str) -> Optional[PdfEntry]:
        """Resolve a caller-supplied PDF path to its parsed JSON entry."""
        if not file_path:
            return None
        abs_key = _normalize_abs_path(file_path)
        entry = self._by_abs_path.get(abs_key)
        if entry is not None:
            return entry
        return self._by_basename.get(Path(file_path).name)


def _normalize_abs_path(path_str: str) -> str:
    """Collapse ``/./``, double slashes, and trailing slashes."""
    return str(Path(path_str).expanduser().resolve(strict=False))


def get_parsed_root() -> Path:
    return Path(os.getenv("EXAONE_PARSED_ROOT", _DEFAULT_PARSED_ROOT))


_INDEX: Optional[_PdfIndex] = None
_INDEX_LOCK = threading.Lock()


def _build_index() -> _PdfIndex:
    parsed_root = get_parsed_root()
    mapping_path = parsed_root / _MAPPING_FILENAME
    if not mapping_path.exists():
        raise FileNotFoundError(
            f"PDF index unavailable: {mapping_path} not found. "
            f"Set EXAONE_PARSED_ROOT to the directory containing "
            f"file_mapping.json."
        )

    with mapping_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"{mapping_path} must be a JSON object")

    index = _PdfIndex(parsed_root)
    dupes = 0
    missing_json = 0
    for stem, meta in raw.items():
        if not isinstance(meta, dict):
            continue
        rel = meta.get("relative_path") or ""
        abs_pdf = meta.get("absolute_path") or ""
        original = meta.get("original_filename") or (Path(rel).name if rel else "")
        if not rel or not abs_pdf or not original:
            continue
        json_path = parsed_root / Path(rel).parent / f"{stem}.json"
        if not json_path.exists():
            missing_json += 1
            continue
        entry = PdfEntry(
            stem=str(stem),
            raw_pdf_path=Path(_normalize_abs_path(abs_pdf)),
            parsed_json_path=json_path,
            original_filename=str(original),
        )
        abs_key = str(entry.raw_pdf_path)
        if abs_key in index._by_abs_path:
            dupes += 1
        index._by_abs_path[abs_key] = entry
        # basename collisions overwrite — last writer wins. Callers that
        # need disambiguation should pass the full path.
        index._by_basename[entry.original_filename] = entry

    logger.info(
        "PDF index built from %s: %d entries (%d duplicate paths, %d missing JSONs)",
        mapping_path, len(index._by_abs_path), dupes, missing_json,
    )
    return index


def get_index() -> _PdfIndex:
    """Return the process-local PDF index, building it on first call."""
    global _INDEX
    if _INDEX is None:
        with _INDEX_LOCK:
            if _INDEX is None:
                _INDEX = _build_index()
    return _INDEX


def reset_index() -> None:
    """Drop the cached index (test/debug only)."""
    global _INDEX
    with _INDEX_LOCK:
        _INDEX = None
