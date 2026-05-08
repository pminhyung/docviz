"""
JSON Document Loader

Loads documents from JSON file paths and converts them to the
multi_docs format expected by the base module.
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union


class DocumentFormat(Enum):
    """Supported JSON document formats"""
    DICT = "dict"       # {"1": "content...", "2": "content..."}
    ARRAY = "array"     # [{"page": 1, "content": "..."}, ...]
    DOCAI = "docai"     # {"outputs": [{"html_parsed": {...}}]}
    AUTO = "auto"       # Auto-detect format


@dataclass
class LoadedDocument:
    """A loaded document with metadata"""
    filename: str
    pages: List[Dict[str, Any]]
    raw_data: Any
    format_detected: DocumentFormat
    total_pages: int
    total_chars: int
    image_dir: Optional[str] = None  # Path to image directory for docai format


class DocumentLoader:
    """
    Loads documents from JSON file paths.

    Supports two JSON formats:

    Format 1 (dict):
    {
        "1": "Page 1 content...",
        "2": "Page 2 content..."
    }

    Format 2 (array):
    [
        {"page": 1, "content": "..."},
        {"page": 2, "content": "..."}
    ]

    Converts to multi_docs format:
    [[
        {"Index": 1, "filename": "doc.pdf", "page": 1, "content": "..."},
        {"Index": 2, "filename": "doc.pdf", "page": 2, "content": "..."},
    ]]

    Usage:
        loader = DocumentLoader()
        multi_docs, filenames = loader.load_documents(
            doc_json_paths=["/path/to/doc1.json"],
            single_doc=True
        )
    """

    def __init__(self, format_hint: DocumentFormat = DocumentFormat.AUTO):
        """
        Initialize the loader.

        Args:
            format_hint: Hint for expected JSON format
        """
        self.format_hint = format_hint
        self._loaded_docs: List[LoadedDocument] = []

    def load_single_document(
        self,
        json_path: str,
        doc_index: int = 1,
        image_dir: Optional[str] = None
    ) -> LoadedDocument:
        """
        Load a single document from a JSON file.

        Args:
            json_path: Path to the JSON file
            doc_index: Document index (1-based)
            image_dir: Optional path to image directory (for docai format)

        Returns:
            LoadedDocument with parsed content
        """
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {json_path}")

        # Extract filename from path
        filename = path.stem
        if path.suffix == ".json":
            # Try to get a more descriptive name
            filename = path.name

        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        # Detect format and parse
        doc_format, pages, detected_filename = self._parse_document(raw_data, filename, doc_index)

        # Use detected filename if available (from docai format)
        if detected_filename:
            filename = detected_filename

        # Calculate stats
        total_chars = sum(len(p.get("content", "")) for p in pages)

        doc = LoadedDocument(
            filename=filename,
            pages=pages,
            raw_data=raw_data,
            format_detected=doc_format,
            total_pages=len(pages),
            total_chars=total_chars,
            image_dir=image_dir,
        )

        self._loaded_docs.append(doc)
        return doc

    def _parse_document(
        self,
        data: Any,
        filename: str,
        doc_index: int
    ) -> Tuple[DocumentFormat, List[Dict[str, Any]], Optional[str]]:
        """
        Parse document data based on format.

        Args:
            data: The JSON data
            filename: The document filename
            doc_index: Document index (1-based)

        Returns:
            Tuple of (format, pages list, detected_filename or None)
        """
        pages = []
        detected_filename = None

        if isinstance(data, dict):
            # Check for docai format: {"outputs": [{"html_parsed": {...}}]}
            if "outputs" in data and isinstance(data.get("outputs"), list):
                return self._parse_docai_format(data, filename, doc_index)

            # Format 1: {"1": "content...", "2": "content..."}
            # Check if keys are page numbers
            if all(self._is_page_key(k) for k in data.keys()):
                doc_format = DocumentFormat.DICT

                # Sort by page number and convert
                sorted_items = sorted(
                    data.items(),
                    key=lambda x: int(x[0]) if x[0].isdigit() else 0
                )

                for idx, (page_str, content) in enumerate(sorted_items, start=1):
                    pages.append({
                        "Index": idx,
                        "filename": filename,
                        "page": int(page_str) if page_str.isdigit() else idx,
                        "content": str(content) if content else "",
                    })
            else:
                # Unknown dict format, treat as single page
                doc_format = DocumentFormat.DICT
                pages.append({
                    "Index": 1,
                    "filename": filename,
                    "page": 1,
                    "content": json.dumps(data, ensure_ascii=False),
                })

        elif isinstance(data, list):
            # Format 2: [{"page": 1, "content": "..."}, ...]
            doc_format = DocumentFormat.ARRAY

            for idx, item in enumerate(data, start=1):
                if isinstance(item, dict):
                    page_num = item.get("page", idx)
                    content = item.get("content", item.get("text", ""))

                    # If content is not found, serialize the whole item
                    if not content and item:
                        content = json.dumps(item, ensure_ascii=False)

                    pages.append({
                        "Index": idx,
                        "filename": filename,
                        "page": int(page_num) if isinstance(page_num, (int, str)) else idx,
                        "content": str(content),
                    })
                else:
                    # Plain string in array
                    pages.append({
                        "Index": idx,
                        "filename": filename,
                        "page": idx,
                        "content": str(item),
                    })

        else:
            # Single string content
            doc_format = DocumentFormat.DICT
            pages.append({
                "Index": 1,
                "filename": filename,
                "page": 1,
                "content": str(data),
            })

        return doc_format, pages, detected_filename

    def _parse_docai_format(
        self,
        data: Dict[str, Any],
        filename: str,
        doc_index: int
    ) -> Tuple[DocumentFormat, List[Dict[str, Any]], Optional[str]]:
        """
        Parse docai JSON format.

        Docai format:
        {
            "id": "uuid",
            "outputs": [{
                "file_name": "original.pdf",
                "html_parsed": {
                    "1": ["text1", "text2", ...],
                    "2": ["text3", ...]
                },
                "list_parsed": {...}  # alternative
            }]
        }

        Args:
            data: The docai JSON data
            filename: Fallback filename
            doc_index: Document index (1-based)

        Returns:
            Tuple of (format, pages list, detected_filename)
        """
        pages = []
        detected_filename = None

        outputs = data.get("outputs", [])
        if not outputs:
            # Empty outputs, return single empty page
            return DocumentFormat.DOCAI, [{
                "Index": 1,
                "filename": filename,
                "page": 1,
                "content": "",
            }], None

        # Use first output
        output = outputs[0]

        # Get original filename
        detected_filename = output.get("file_name", filename)

        # Prefer html_parsed, fallback to list_parsed
        parsed_data = output.get("html_parsed") or output.get("list_parsed") or {}

        if not parsed_data:
            # No parsed data available
            return DocumentFormat.DOCAI, [{
                "Index": 1,
                "filename": detected_filename,
                "page": 1,
                "content": "",
            }], detected_filename

        # Sort page numbers and process
        page_numbers = sorted(
            [int(k) for k in parsed_data.keys() if k.isdigit()],
            key=int
        )

        for idx, page_num in enumerate(page_numbers, start=1):
            page_key = str(page_num)
            page_content = parsed_data.get(page_key, [])

            # Join text array with double newlines
            if isinstance(page_content, list):
                content = "\n\n".join(str(item) for item in page_content if item)
            else:
                content = str(page_content) if page_content else ""

            pages.append({
                "Index": idx,
                "filename": detected_filename,
                "page": page_num,
                "content": content,
            })

        if not pages:
            # No pages found, return empty page
            pages.append({
                "Index": 1,
                "filename": detected_filename,
                "page": 1,
                "content": "",
            })

        return DocumentFormat.DOCAI, pages, detected_filename

    def _is_page_key(self, key: str) -> bool:
        """Check if a key looks like a page number"""
        if isinstance(key, int):
            return True
        if isinstance(key, str):
            return key.isdigit() or key.startswith("page") or key.startswith("p")
        return False

    def load_documents(
        self,
        doc_json_paths: List[str],
        single_doc: bool = True,
        image_dirs: Optional[List[str]] = None
    ) -> Tuple[List[List[Dict[str, Any]]], List[str], Optional[List[str]]]:
        """
        Load documents and return in multi_docs format.

        Args:
            doc_json_paths: List of paths to JSON document files
            single_doc: Whether this is single-doc mode
            image_dirs: Optional list of image directory paths (parallel to doc_json_paths)

        Returns:
            Tuple of (multi_docs, filenames, image_dirs_out)
        """
        multi_docs = []
        filenames = []
        image_dirs_out = []

        for idx, path in enumerate(doc_json_paths, start=1):
            image_dir = None
            if image_dirs and idx <= len(image_dirs):
                image_dir = image_dirs[idx - 1]

            doc = self.load_single_document(path, doc_index=idx, image_dir=image_dir)
            multi_docs.append(doc.pages)
            filenames.append(doc.filename)
            image_dirs_out.append(doc.image_dir)

            if single_doc and idx >= 1:
                break  # Only load first doc in single-doc mode

        return multi_docs, filenames, image_dirs_out if any(image_dirs_out) else None

    def get_document_summary(
        self,
        multi_docs: List[List[Dict[str, Any]]],
        max_chars_per_page: int = 1000
    ) -> str:
        """
        Get a summary of loaded documents for the doc step.

        Args:
            multi_docs: The loaded documents
            max_chars_per_page: Max characters to show per page

        Returns:
            Summary string
        """
        parts = []

        for doc_idx, pages in enumerate(multi_docs, start=1):
            if not pages:
                continue

            filename = pages[0].get("filename", f"Document {doc_idx}")
            parts.append(f"\n\nDocument {doc_idx}: {filename}")
            parts.append(f"Total pages: {len(pages)}")

            for page in pages:
                content = page.get("content", "")
                if len(content) > max_chars_per_page:
                    content = content[:max_chars_per_page] + "..."

                parts.append(f"\n[Page {page.get('page', '?')}]")
                parts.append(content)

        return "\n".join(parts)

    def convert_to_base_format(
        self,
        multi_docs: List[List[Dict[str, Any]]],
        filenames: List[str]
    ) -> Dict[str, Any]:
        """
        Convert loaded documents to the format expected by base module's process_document.

        This mimics the structure returned by reading parquet files.

        Args:
            multi_docs: Loaded documents
            filenames: List of filenames

        Returns:
            Dictionary mimicking parquet row format
        """
        file_data = {}

        for idx, (pages, filename) in enumerate(zip(multi_docs, filenames), start=1):
            # Convert pages to dict format {page_num: content}
            text_dict = {
                str(page.get("page", i)): page.get("content", "")
                for i, page in enumerate(pages, start=1)
            }

            if idx == 1:
                file_data["filename_1_origin"] = filename
                file_data["file_1_text_dict"] = text_dict
            elif idx == 2:
                file_data["filename_2_origin"] = filename
                file_data["file_2_text_dict"] = text_dict

        return file_data

    @property
    def loaded_documents(self) -> List[LoadedDocument]:
        """Get all loaded documents"""
        return self._loaded_docs

    def clear(self) -> None:
        """Clear loaded documents"""
        self._loaded_docs.clear()


def load_document_from_json(
    json_path: str,
    doc_index: int = 1,
    image_dir: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    """
    Convenience function to load a single document.

    Args:
        json_path: Path to JSON file
        doc_index: Document index
        image_dir: Optional path to image directory

    Returns:
        Tuple of (pages list, filename, image_dir)
    """
    loader = DocumentLoader()
    doc = loader.load_single_document(json_path, doc_index, image_dir=image_dir)
    return doc.pages, doc.filename, doc.image_dir
