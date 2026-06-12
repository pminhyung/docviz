from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List

import sys
sys.path.append(str(Path(__file__).parent.parent))

from utils import MetadataManager, PaperCrawler


def _configure_logging(log_dir: Path) -> None:
    """(log_dir: Path) -> None: Configure shared logging handlers for crawl scripts."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "crawl.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger(__name__).info("Logs will be written to %s", log_file)


def crawl_papers(
    paper_list: Path,
    output_dir: Path,
    *,
    max_workers: int = 4,
    metadata_file: Path | None = None,
) -> List[dict]:
    """(paper_list: Path, output_dir: Path, max_workers: int=4, metadata_file: Optional[Path]=None) -> List[dict]: Run the crawler and update metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = metadata_file or (output_dir / "metadata.json")

    crawler = PaperCrawler(str(paper_list), str(output_dir))
    metadata = MetadataManager(str(metadata_path))

    papers = crawler.load_papers()
    logger = logging.getLogger("crawl_paper")
    logger.info("Loaded %d paper entries.", len(papers))

    results: List[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(crawler.process_single_paper_crawl, item): item for item in papers}
        for future in as_completed(future_map):
            original = future_map[future]
            processed = future.result()

            results.append(processed)
            if processed.get("status") == "success":
                metadata.add_paper(processed)
            logger.info("Processed '%s' -> status=%s", processed.get("title"), processed.get("status"))

    return results


def _cli(argv: Iterable[str] | None = None) -> int:
    """(argv: Optional[Iterable[str]]) -> int: CLI wrapper for crawling papers and printing JSON summaries."""
    parser = argparse.ArgumentParser(description="Crawl paper metadata, LaTeX sources, and PDFs from arXiv.")
    parser.add_argument("--paper-list", type=Path, default=Path("test/input/paper_list.json"), help="Path to a JSON file containing paper titles (format: [{\"title\": \"...\"}, ...]).")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("test/output/crawled"),
        help="Directory used to store crawl artefacts (default: test/output/crawled).",
    )
    parser.add_argument("--max-workers", type=int, default=4, help="Number of concurrent worker threads.")
    parser.add_argument("--metadata-file", type=Path, default=Path("test/output/crawled/metadata.json"), help="Optional path for the aggregated metadata JSON.")
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs"),
        help="Directory where crawl logs will be written (default: logs).",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)
    _configure_logging(args.log_dir)

    results = crawl_papers(
        paper_list=args.paper_list,
        output_dir=args.output_dir,
        max_workers=args.max_workers,
        metadata_file=args.metadata_file,
    )

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
