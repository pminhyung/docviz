#!/usr/bin/env python3
"""
Input preparation pipeline for diagram evaluation.

This script orchestrates two stages:
1. Crawl papers from arXiv (download PDFs and LaTeX sources)
2. Extract text and diagrams from PDFs

Note: Graph conversion is now integrated into the evaluation workflow (evaluate.py).
The evaluator automatically converts text/images to graphs as needed.

Output structure:
    output_dir/
        crawled/
            {arxiv_id}/
                {arxiv_id}.pdf              # Downloaded PDF
                {arxiv_id}.tar.gz           # LaTeX source
        extracted/
            {arxiv_id}/
                {arxiv_id}_text.txt         # Extracted text
                {arxiv_id}_diagrams/        # Extracted diagrams (always PNG)
                    figure_overview.png
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Iterable, List
import sys

sys.path.append(str(Path(__file__).parent.parent))

from utils.crawl_paper import crawl_papers
from utils.extract_text_diagram_from_paper import extract_overview_diagrams_in_folder


logger = logging.getLogger("prepare_inputs")


# ============================================================================
# Stage 1: Paper Crawling
# ============================================================================

def stage1_crawl_papers(
    paper_list: Path,
    output_dir: Path,
    max_workers: int = 4,
) -> List[dict]:
    """
    Stage 1: Crawl papers from arXiv.
    
    Args:
        paper_list: JSON file with paper titles
        output_dir: Directory for crawled papers
        max_workers: Number of concurrent workers
    
    Returns:
        List of crawl results
    """
    logger.info("=" * 60)
    logger.info("STAGE 1: Crawling papers from arXiv")
    logger.info("=" * 60)
    
    crawl_dir = output_dir / "crawled"
    metadata_file = crawl_dir / "metadata.json"
    
    results = crawl_papers(
        paper_list=paper_list,
        output_dir=crawl_dir,
        max_workers=max_workers,
        metadata_file=metadata_file,
    )
    
    success_count = sum(1 for r in results if r.get("status") == "success")
    logger.info(f"Stage 1 complete: {success_count}/{len(results)} papers crawled successfully")
    
    return results


# ============================================================================
# Stage 2: Text and Diagram Extraction
# ============================================================================

def stage2_extract_text_and_diagrams(
    crawled_dir: Path,
    output_dir: Path,
    llm_config: Path,
    max_workers: int = 4,
) -> List[dict]:
    """
    Stage 2: Extract text and diagrams from PDFs.
    
    Args:
        crawled_dir: Directory containing crawled papers
        output_dir: Directory for extracted content
        llm_config: LLM config for diagram selection
        max_workers: Number of concurrent workers
    
    Returns:
        List of extraction results
    """
    logger.info("=" * 60)
    logger.info("STAGE 2: Extracting text and diagrams from PDFs")
    logger.info("=" * 60)
    
    extracted_dir = output_dir / "extracted"
    
    results = extract_overview_diagrams_in_folder(
        input_path=crawled_dir,
        output_dir=extracted_dir,
        config_path=llm_config,
        max_workers=max_workers,
    )
    
    success_count = sum(1 for r in results if r.get("status") == "success")
    logger.info(f"Stage 2 complete: {success_count}/{len(results)} papers extracted successfully")
    
    return results


# ============================================================================
# Main Pipeline
# ============================================================================

def run_pipeline(
    paper_list: Path,
    output_dir: Path,
    diagram_eval_config: Path,
    max_workers: int = 4,
    skip_crawl: bool = False,
    skip_extract: bool = False,
) -> dict:
    """
    Run the input preparation pipeline.
    
    Args:
        paper_list: JSON file with paper titles
        output_dir: Base output directory
        diagram_eval_config: LLM config for diagram selection
        max_workers: Number of concurrent workers
        skip_crawl: Skip stage 1 (crawling)
        skip_extract: Skip stage 2 (extraction)
    
    Returns:
        Dictionary with results from all stages
    """
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {
        "stage1_crawl": [],
        "stage2_extract": [],
    }
    
    # Stage 1: Crawl papers
    if not skip_crawl:
        results["stage1_crawl"] = stage1_crawl_papers(
            paper_list=paper_list,
            output_dir=output_dir,
            max_workers=max_workers,
        )
    else:
        logger.info("Skipping Stage 1: Crawling")
    
    # Stage 2: Extract text and diagrams
    if not skip_extract:
        crawled_dir = output_dir / "crawled"
        results["stage2_extract"] = stage2_extract_text_and_diagrams(
            crawled_dir=crawled_dir,
            output_dir=output_dir,
            llm_config=diagram_eval_config,
            max_workers=max_workers,
        )
    else:
        logger.info("Skipping Stage 2: Extraction")
    
    return results


# ============================================================================
# CLI
# ============================================================================

def _configure_logging(log_dir: Path) -> None:
    """Configure logging handlers."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "prepare_inputs.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger.info(f"Logs will be written to {log_file}")


def _cli(argv: Iterable[str] | None = None) -> int:
    """CLI entry point for the input preparation pipeline."""
    parser = argparse.ArgumentParser(
        description="Prepare inputs: crawl papers and extract text/diagrams. "
                    "Graph conversion is now integrated into evaluate.py."
    )
    
    # Input/Output
    parser.add_argument(
        "--paper-list",
        type=Path,
        default=Path("test/input/paper_list.json"),
        help="JSON file with paper titles (format: [{\"title\": \"...\"}, ...])."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("test/output"),
        help="Base output directory for all stages (default: test/output)."
    )
    
    # LLM Configurations
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/llm_config.yaml"),
        help="Unified LLM configuration file (default: configs/llm_config.yaml)."
    )
    
    # Processing Options
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Number of concurrent workers (default: 4)."
    )
    
    # Stage Control
    parser.add_argument(
        "--skip-crawl",
        action="store_true",
        help="Skip Stage 1 (crawling papers)."
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Skip Stage 2 (extracting text and diagrams)."
    )
    
    # Output Options
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional: Path to write summary JSON."
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs"),
        help="Directory for log files (default: logs)."
    )
    
    args = parser.parse_args(list(argv) if argv is not None else None)
    _configure_logging(args.log_dir)
    
    logger.info("=" * 60)
    logger.info("DIAGRAM EVALUATION INPUT PREPARATION PIPELINE")
    logger.info("=" * 60)
    logger.info("Note: Graph conversion is now integrated into evaluate.py")
    logger.info("=" * 60)
    
    # Run pipeline
    results = run_pipeline(
        paper_list=args.paper_list,
        output_dir=args.output_dir,
        diagram_eval_config=args.config,
        max_workers=args.max_workers,
        skip_crawl=args.skip_crawl,
        skip_extract=args.skip_extract,
    )
    
    # Save summary
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.summary_json, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Summary written to {args.summary_json}")
    
    # Print statistics
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 60)
    
    if results["stage1_crawl"]:
        crawl_success = sum(1 for r in results["stage1_crawl"] if r.get("status") == "success")
        logger.info(f"Stage 1 (Crawl): {crawl_success}/{len(results['stage1_crawl'])} succeeded")
    
    if results["stage2_extract"]:
        extract_success = sum(1 for r in results["stage2_extract"] if r.get("status") == "success")
        logger.info(f"Stage 2 (Extract): {extract_success}/{len(results['stage2_extract'])} succeeded")
    
    logger.info("=" * 60)
    logger.info("Next step: Use script/evaluate.py to evaluate diagrams")
    logger.info("Graph conversion happens automatically during evaluation")
    logger.info("=" * 60)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
