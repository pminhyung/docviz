"""Shim image-metadata index over docai/out/.

Production note: in prod, image metadata + bytes come from the lgair
DOC_PARSER "Document Modality Analyze" endpoint per (fid, page). The shim
backs the same call surface by reading pre-parsed JSON dumps + cropped
PNG files that the docai pipeline already produced:

    /ex_disk2/mhpark/poc/docai/out/<category>/<short_fid>.json
        outputs[0].images[<page>] = {"results": [
            {"Category", "bbox", "caption", "description",
             "id", "images" (rel path), "request_type"}, ...
        ]}
    /ex_disk2/mhpark/poc/docai/out/img/<category>/<short_fid>/page_<page>_image<idx>.png

`file_mapping.json` (561 entries today) maps short_fid → {absolute_path,
relative_path, original_filename} for the raw PDF.

This module owns:
  - cached load of file_mapping.json (one read per process)
  - fid resolution: filename / original_filename → short_fid + parsing JSON path
  - image candidate enumeration for a (short_fid, optional page filter)
  - PNG path resolution + on-demand bytes load
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Iterable, NamedTuple

logger = logging.getLogger(__name__)


DOCAI_ROOT = Path(os.environ.get(
    "EXAONE_DOCAI_ROOT", "/ex_disk2/mhpark/poc/docai"
))
OUT_ROOT = DOCAI_ROOT / "out"
IMG_ROOT = OUT_ROOT / "img"
FILE_MAPPING_PATH = OUT_ROOT / "file_mapping.json"


class FidInfo(NamedTuple):
    short_fid: str
    category_dir: str       # e.g. "7_현대경제연구원"
    original_filename: str  # e.g. "(CEO 경영이슈) ...pdf"
    raw_pdf_path: Path
    parsing_json_path: Path


class ImageMeta(NamedTuple):
    short_fid: str
    page: int
    idx: int                # position in results array; same png_id may appear multiple times
    category: str
    bbox: list[int]         # [x1, y1, x2, y2] in original PDF page coords
    caption: str
    description: str
    png_id: str             # e.g. "<filename>_id_10_image0.png"
    png_path: Path          # absolute path on disk


# ─── file_mapping.json load (one-shot) ──────────────────────────────────────

_FILE_MAPPING: dict[str, dict] | None = None
_MAPPING_LOCK = threading.Lock()


def _load_file_mapping() -> dict[str, dict]:
    global _FILE_MAPPING
    if _FILE_MAPPING is not None:
        return _FILE_MAPPING
    with _MAPPING_LOCK:
        if _FILE_MAPPING is not None:
            return _FILE_MAPPING
        if not FILE_MAPPING_PATH.is_file():
            logger.warning("file_mapping.json not found at %s", FILE_MAPPING_PATH)
            _FILE_MAPPING = {}
        else:
            with open(FILE_MAPPING_PATH, "rb") as f:
                _FILE_MAPPING = json.load(f)
    return _FILE_MAPPING


# ─── fid resolution ─────────────────────────────────────────────────────────

# docqa_tools' handle_parse_web_and_doc derives a 12-digit fid from filename + first
# 1KB; that fid is NOT the same as the 8-char short_fid in docai/out. We map
# by original_filename, which IS stable across both layers.
_BY_FILENAME: dict[str, str] | None = None


def _filename_index() -> dict[str, str]:
    global _BY_FILENAME
    if _BY_FILENAME is not None:
        return _BY_FILENAME
    fm = _load_file_mapping()
    idx: dict[str, str] = {}
    for short_fid, info in fm.items():
        original = info.get("original_filename") or ""
        if original:
            idx[original] = short_fid
    _BY_FILENAME = idx
    return idx


def resolve_fid_by_filename(filename: str) -> FidInfo | None:
    """Map a doc filename (e.g. parse_web_and_doc's `filename`) → shim FidInfo."""
    short_fid = _filename_index().get(filename)
    if short_fid is None:
        return None
    info = _load_file_mapping().get(short_fid) or {}
    rel = info.get("relative_path") or ""
    category_dir = rel.split("/", 1)[0] if "/" in rel else ""
    abs_path = info.get("absolute_path") or ""
    raw_path = Path(abs_path) if abs_path else (OUT_ROOT / rel)
    parsing_json = OUT_ROOT / category_dir / f"{short_fid}.json"
    return FidInfo(
        short_fid=short_fid,
        category_dir=category_dir,
        original_filename=info.get("original_filename") or filename,
        raw_pdf_path=raw_path,
        parsing_json_path=parsing_json,
    )


# ─── per-doc parsing JSON cache ─────────────────────────────────────────────

_PARSED_CACHE: dict[str, dict] = {}
_PARSED_LOCK = threading.Lock()


def _load_parsing(short_fid: str, json_path: Path) -> dict:
    cached = _PARSED_CACHE.get(short_fid)
    if cached is not None:
        return cached
    with _PARSED_LOCK:
        cached = _PARSED_CACHE.get(short_fid)
        if cached is not None:
            return cached
        if not json_path.is_file():
            logger.warning("parsing JSON missing: %s", json_path)
            _PARSED_CACHE[short_fid] = {}
            return {}
        with open(json_path, "rb") as f:
            _PARSED_CACHE[short_fid] = json.load(f)
    return _PARSED_CACHE[short_fid]


# ─── image enumeration ─────────────────────────────────────────────────────

def list_images_for_fid(
    info: FidInfo,
    *,
    pages: Iterable[int] | None = None,
) -> list[ImageMeta]:
    """Enumerate ImageMeta entries for a fid, optionally filtered by page set.

    Pages with no images yield nothing. Missing JSON yields empty list.
    """
    parsed = _load_parsing(info.short_fid, info.parsing_json_path)
    outputs = parsed.get("outputs") or []
    if not outputs:
        return []
    images_by_page = (outputs[0] or {}).get("images") or {}

    page_filter: set[int] | None = None
    if pages is not None:
        page_filter = {int(p) for p in pages}

    out: list[ImageMeta] = []
    for page_key, page_block in images_by_page.items():
        try:
            page_int = int(page_key)
        except (TypeError, ValueError):
            continue
        if page_filter is not None and page_int not in page_filter:
            continue
        results = (page_block or {}).get("results") or []
        for idx, entry in enumerate(results):
            if not isinstance(entry, dict):
                continue
            rel_png = entry.get("images") or ""
            # rel_png is "../img/<cat>/<short_fid>/page_X_imageY.png" relative
            # to the parsing JSON's directory.
            png_path = (info.parsing_json_path.parent / rel_png).resolve()
            out.append(ImageMeta(
                short_fid=info.short_fid,
                page=page_int,
                idx=idx,
                category=str(entry.get("Category") or ""),
                bbox=list(entry.get("bbox") or []),
                caption=str(entry.get("caption") or ""),
                description=str(entry.get("description") or ""),
                png_id=str(entry.get("id") or ""),
                png_path=png_path,
            ))
    return out


def load_png_bytes(meta: ImageMeta) -> bytes | None:
    """Read PNG file bytes; returns None if missing."""
    if not meta.png_path.is_file():
        logger.warning("image PNG missing: %s", meta.png_path)
        return None
    return meta.png_path.read_bytes()
