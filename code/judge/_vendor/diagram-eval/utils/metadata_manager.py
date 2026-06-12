from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class MetadataManager:
    """Thread-safe metadata store for crawled papers."""

    def __init__(self, metadata_file: str):
        """(metadata_file: str) -> None: Initialise metadata storage and load existing entries."""
        self.metadata_file = Path(metadata_file)
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger("MetadataManager")
        self.lock = threading.RLock()
        self.load_metadata()

    def load_metadata(self) -> None:
        """() -> None: Load metadata JSON into memory."""
        with self.lock:
            if self.metadata_file.exists():
                with open(self.metadata_file, "r") as f:
                    self.metadata = json.load(f)
                self.logger.info(
                    "Loaded metadata for %d papers from %s",
                    len(self.metadata),
                    self.metadata_file,
                )
            else:
                self.logger.info("Metadata file %s does not exist, starting with empty metadata", self.metadata_file)
                self.metadata = {}

    def save_metadata(self) -> None:
        """() -> None: Persist current metadata to disk."""
        with self.lock:
            with open(self.metadata_file, "w") as f:
                json.dump(self.metadata, f, indent=2)
            self.logger.debug(
                "Saved metadata for %d papers to %s", len(self.metadata), self.metadata_file
            )

    def _convert_to_relative_path(self, path_value: Optional[str]) -> Optional[str]:
        """(path_value: Optional[str]) -> Optional[str]: Convert absolute paths to relative paths."""
        if path_value and os.path.isabs(path_value):
            base_dir = self.metadata_file.parent
            return os.path.relpath(path_value, base_dir)
        return path_value

    def add_paper(self, paper_info: Dict) -> None:
        """(paper_info: Dict) -> None: Insert or update metadata entry for a paper."""
        arxiv_id = paper_info.get("arxiv_id")
        if not arxiv_id:
            self.logger.warning("Cannot add paper without arXiv ID")
            return

        with self.lock:
            new_data: Dict[str, Any] = {
                "arxiv_id": arxiv_id,
                "title": paper_info.get("title", "Unknown Title"),
                "authors": paper_info.get("authors", []),
                "status": paper_info.get("status", "unknown"),
                "last_updated": time.time(),
            }

            # Handle path fields
            source_path = paper_info.get("latex_source_path")
            if source_path:
                new_data["latex_source_path"] = self._convert_to_relative_path(source_path)
            else:
                new_data["latex_source_path"] = None

            pdf_path = paper_info.get("pdf_path")
            if pdf_path:
                new_data["pdf_path"] = self._convert_to_relative_path(pdf_path)
            else:
                new_data["pdf_path"] = None

            if arxiv_id not in self.metadata:
                self.metadata[arxiv_id] = new_data
                self.logger.info("Added new paper to metadata: %s (%s)", new_data["title"], arxiv_id)
            else:
                self.metadata[arxiv_id].update(new_data)
                self.logger.info("Updated existing paper in metadata: %s (%s)", new_data["title"], arxiv_id)

            self.save_metadata()

    def get_paper(self, arxiv_id: str) -> Optional[Dict]:
        """(arxiv_id: str) -> Optional[Dict]: Retrieve a single paper record."""
        with self.lock:
            return self.metadata.get(arxiv_id)

    def get_all_papers(self) -> List[Dict]:
        """() -> List[Dict]: Return a copy of all paper records."""
        with self.lock:
            return [p.copy() for p in self.metadata.values()]

    def get_papers_by_status(self, status: str) -> List[Dict]:
        """(status: str) -> List[Dict]: Fetch all papers matching a given status."""
        with self.lock:
            papers = [p.copy() for p in self.metadata.values() if p.get("status") == status]
        self.logger.info("Found %d papers with status '%s'", len(papers), status)
        return papers
