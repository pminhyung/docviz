from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import pypdf
import requests
from bs4 import BeautifulSoup


class PaperCrawler:
    """Crawl arXiv metadata, PDFs, and LaTeX sources for configured papers."""

    def __init__(self, paper_list_dir: str, output_dir: str):
        """(paper_list_dir: str, output_dir: str) -> None: Configure crawler directories and request session."""
        self.paper_list_dir = Path(paper_list_dir)
        self.output_dir = Path(output_dir)
        self.raw_dir = self.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(exist_ok=True)

        self.logger = logging.getLogger("PaperCrawler")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                )
            }
        )

        self.last_request_time = 0.0
        self.min_request_interval = 5.0

    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """(title1: str, title2: str) -> float: Compute F1-based word-overlap similarity considering both precision and recall."""
        def tokenize(text: str) -> List[str]:
            text = text.lower()
            text = re.sub(r"[^\w\s]", "", text)
            return text.split()

        tokens1 = tokenize(title1)
        tokens2 = tokenize(title2)

        if not tokens1 or not tokens2:
            return 0.0

        counts1 = Counter(tokens1)
        counts2 = Counter(tokens2)

        # Calculate intersection (common words)
        intersection_score = 0
        for word in counts1.keys() & counts2.keys():
            intersection_score += min(counts1[word], counts2[word])

        # Calculate precision: intersection / tokens1
        precision = intersection_score / len(tokens1) if tokens1 else 0.0
        
        # Calculate recall: intersection / tokens2  
        recall = intersection_score / len(tokens2) if tokens2 else 0.0
        
        # Calculate F1 score: harmonic mean of precision and recall
        if precision + recall == 0:
            return 0.0
        
        f1_score = 2 * (precision * recall) / (precision + recall)
        return f1_score * 100

    def _respect_rate_limit(self) -> None:
        """() -> None: Enforce minimum delay between HTTP requests."""
        current_time = time.time()
        elapsed = current_time - self.last_request_time

        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            self.logger.debug("Rate limiting: sleeping for %.2f seconds", sleep_time)
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def load_papers(self) -> List[Dict]:
        """() -> List[Dict]: Load paper descriptions from the configured JSON file."""
        self.logger.info("Loading papers from %s", self.paper_list_dir)
        
        with open(self.paper_list_dir, "r") as f:
            papers = json.load(f)
        
        if not isinstance(papers, list):
            papers = [papers]
        
        self.logger.info("Loaded %d paper entries from %s", len(papers), self.paper_list_dir)
        return papers

    def search_arxiv_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """(title: str) -> Optional[Dict[str, Any]]: Search arXiv and return matching arXiv ID and authors."""
        clean_title = re.sub(r"\$.*?\$", "", title)
        clean_title = re.sub(r"\s+", " ", clean_title).strip()

        search_term = clean_title
        encoded_query = urllib.parse.quote_plus(search_term)
        search_url = (
            f"https://arxiv.org/search/?query={encoded_query}&searchtype=title&source=header&start=0&max_results=10"
        )

        self._respect_rate_limit()

        response = self.session.get(search_url, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "lxml")

        results = soup.select("li.arxiv-result")
        top_results = results[:5]

        best_match_id = None
        best_match_authors = []
        best_score = 0.0
        best_title = ""

        for result in top_results:
            # Extract title - handle both old and new HTML structures
            title_tag = result.select_one("p.title")
            if not title_tag:
                continue
            
            # Get text from all children (handles span-wrapped titles)
            result_title = title_tag.get_text(separator=" ", strip=True)
            
            
            # Calculate similarity
            similarity = self._calculate_title_similarity(clean_title, result_title)
            # print(f"result_title: {result_title} clean_title: {clean_title} similarity: {similarity}")

            # Extract arXiv ID
            id_tag = result.select_one("p.list-title a")
            if id_tag:
                href = id_tag.get("href", "")
                match = re.search(r"/abs/([0-9]+\.[0-9]+)", href)
                arxiv_id = match.group(1) if match else None
            else:
                arxiv_id = None

            if not arxiv_id:
                continue

            # Extract authors
            authors_tag = result.select_one("p.authors")
            authors = []
            if authors_tag:
                author_links = authors_tag.select("a")
                authors = [a.get_text(strip=True) for a in author_links]

            # Track best match
            if similarity > best_score:
                best_score = similarity
                best_match_id = arxiv_id
                best_match_authors = authors
                best_title = result_title

        if best_score >= 70.0:
            self.logger.info("Matched: '%s' -> arXiv:%s (%.1f%%)", best_title, best_match_id, best_score)
            return {"arxiv_id": best_match_id, "authors": best_match_authors}

        self.logger.warning("No match found for '%s' (best: %.1f%%)", title, best_score)
        return None

    def download_latex_source(self, arxiv_id: str) -> str:
        """(arxiv_id: str) -> str: Download LaTeX source tarball for a specific arXiv paper."""
        paper_raw_dir = self.raw_dir / arxiv_id
        paper_raw_dir.mkdir(parents=True, exist_ok=True)
        source_url = f"https://arxiv.org/e-print/{arxiv_id}"
        output_path = paper_raw_dir / f"{arxiv_id}.tar.gz"

        if output_path.exists():
            self.logger.info("Source already downloaded for %s: %s", arxiv_id, output_path)
            return str(output_path)

        self.logger.info("Downloading source for %s to %s", arxiv_id, output_path)
        self._respect_rate_limit()
        
        response = requests.get(source_url, stream=True, timeout=30)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        self.logger.info("Successfully downloaded source to: %s", output_path)
        return str(output_path)

    def download_pdf(self, arxiv_id: str) -> str:
        """(arxiv_id: str) -> str: Download and truncate PDF to first pages for a paper."""
        paper_raw_dir = self.raw_dir / arxiv_id
        paper_raw_dir.mkdir(parents=True, exist_ok=True)
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        output_path = paper_raw_dir / f"{arxiv_id}.pdf"

        if output_path.exists():
            self.logger.info("Truncated PDF already exists for %s: %s", arxiv_id, output_path)
            return str(output_path)

        self.logger.info("Downloading PDF for %s from %s", arxiv_id, pdf_url)
        self._respect_rate_limit()
        
        response = requests.get(pdf_url, stream=True, timeout=60)
        response.raise_for_status()

        pdf_data = io.BytesIO(response.content)
        reader = pypdf.PdfReader(pdf_data)
        writer = pypdf.PdfWriter()

        num_pages_to_keep = min(len(reader.pages), 8)
        if num_pages_to_keep < len(reader.pages):
            self.logger.info(
                "Truncating PDF for %s from %d to %d pages.",
                arxiv_id,
                len(reader.pages),
                num_pages_to_keep,
            )
        else:
            self.logger.info("PDF for %s has %d pages (<= 8). Keeping all.", arxiv_id, len(reader.pages))

        for i in range(num_pages_to_keep):
            writer.add_page(reader.pages[i])

        with open(output_path, "wb") as f:
            writer.write(f)

        self.logger.info("Successfully saved truncated PDF to: %s", output_path)
        return str(output_path)

    def process_single_paper_crawl(self, paper_info: Dict) -> Dict:
        """(paper_info: Dict) -> Dict: Search, download, and record artefacts for a single paper entry."""
        paper_output = paper_info.copy()
        title = paper_output.get("title")
        if not title:
            self.logger.warning("Paper entry missing title. Skipping.")
            paper_output["status"] = "failed"
            return paper_output

        # Search for paper and get arxiv_id + authors
        search_result = self.search_arxiv_by_title(title)
        
        if not search_result:
            self.logger.warning("Could not find paper on arXiv with title '%s'", title)
            paper_output["status"] = "failed"
            return paper_output

        arxiv_id = search_result["arxiv_id"]
        authors = search_result["authors"]
        
        paper_output["arxiv_id"] = arxiv_id
        paper_output["authors"] = authors

        # Download both LaTeX source and PDF
        latex_source_path = self.download_latex_source(arxiv_id)
        pdf_path = self.download_pdf(arxiv_id)
        
        paper_output["latex_source_path"] = latex_source_path
        paper_output["pdf_path"] = pdf_path
        paper_output["status"] = "success"

        return paper_output
