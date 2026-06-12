from __future__ import annotations

import argparse
import io
import json
import logging
import re
import shutil
import tarfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional
import sys

sys.path.append(str(Path(__file__).parent.parent))

from PIL import Image
Image.MAX_IMAGE_PIXELS = 933120000

import fitz  # PyMuPDF
from pdf2image import convert_from_path
from utils.structured_llm import StructuredLLM
from pydantic import BaseModel


logger = logging.getLogger("extract_text_diagram_from_paper")


@dataclass
class FigureInfo:
    """Information about a figure extracted from LaTeX source."""
    image_path: Path  # Path to image file in source
    caption: str
    label: str
    figure_index: int


class DiagramEvaluationResponse(BaseModel):
    """Response model for diagram evaluation."""
    reasoning: str
    selected_diagram_index: int


def extract_text(pdf_path: Path, destination: Path) -> Path:
    """(pdf_path: Path, destination: Path) -> Path: Extract sequential text from a PDF and write to disk."""
    doc = fitz.open(str(pdf_path))
    destination.parent.mkdir(parents=True, exist_ok=True)

    with open(destination, "w", encoding="utf-8") as handle:
        for page_number in range(len(doc)):
            page = doc[page_number]
            text = page.get_text() or ""
            handle.write(f"--- Page {page_number + 1} ---\n")
            handle.write(text.strip())
            handle.write("\n\n")

    doc.close()
    return destination


@dataclass
class ConversionResult:
    """Information about files created during diagram to PNG conversion."""
    source_path: Path
    output_files: List[Path]
    dpi: int | None


def convert_diagram_to_png(
    diagram_path: Path | str,
    output_dir: Path | str,
    dpi: int = 400,
    prefix: str | None = None
) -> ConversionResult:
    """
    Convert diagram (PDF or PNG) to PNG format.
    - If input is PDF: render to PNG at specified DPI
    - If input is PNG: copy to output directory
    
    Args:
        diagram_path: Path to input diagram (PDF or PNG)
        output_dir: Directory where PNG files will be saved
        dpi: Rendering resolution for PDFs (default: 300)
        prefix: Filename prefix for generated images (default: stem of input file)
    
    Returns:
        ConversionResult with source path and list of output files
    """
    diagram_path = Path(diagram_path).expanduser().resolve()
    if not diagram_path.exists():
        raise FileNotFoundError(f"Diagram not found: {diagram_path}")

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = prefix or diagram_path.stem
    
    # Handle PNG files - just copy them
    if diagram_path.suffix.lower() in ['.png', '.jpg', '.jpeg']:
        output_path = output_dir / f"{prefix}.png"
        shutil.copy2(diagram_path, output_path)
        return ConversionResult(
            source_path=diagram_path,
            output_files=[output_path],
            dpi=None
        )
    
    # Handle PDF files - convert to PNG
    elif diagram_path.suffix.lower() == '.pdf':
        images = convert_from_path(str(diagram_path), dpi=dpi, use_cropbox=True)
        if not images:
            raise RuntimeError(f"No pages rendered from {diagram_path}")

        written: List[Path] = []
        for page_number, image in enumerate(images, start=1):
            if len(images) == 1:
                # Single page PDF - no page number suffix
                filename = f"{prefix}.png"
            else:
                # Multi-page PDF - add page number
                filename = f"{prefix}_page{page_number}.png"
            output_path = output_dir / filename
            image.save(output_path, format="PNG")
            written.append(output_path)

        return ConversionResult(
            source_path=diagram_path,
            output_files=written,
            dpi=dpi
        )
    
    else:
        raise ValueError(f"Unsupported file format: {diagram_path.suffix}. Supported: .pdf, .png, .jpg, .jpeg")




def unzip_latex_source(source_path: Path, extract_dir: Path) -> Path:
    """Unzip LaTeX source file (.tar.gz or .zip) to extraction directory."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    if source_path.suffix == '.gz' and source_path.stem.endswith('.tar'):
        # Handle .tar.gz files
        with tarfile.open(source_path, 'r:gz') as tar:
            tar.extractall(extract_dir)
            logger.info(f"Extracted {source_path} to {extract_dir}")
    elif source_path.suffix == '.zip':
        # Handle .zip files
        with zipfile.ZipFile(source_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
            logger.info(f"Extracted {source_path} to {extract_dir}")
    else:
        raise ValueError(f"Unsupported archive format: {source_path}")
    
    return extract_dir


def extract_figures_from_tex(tex_file: Path, source_root: Path) -> List[FigureInfo]:
    """Extract figure information from a .tex file."""
    figures = []
    
    try:
        with open(tex_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        logger.warning(f"Failed to read {tex_file}: {e}")
        return figures
    
    # Pattern to match \begin{figure}...\end{figure} blocks
    figure_pattern = re.compile(
        r'\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}',
        re.DOTALL | re.IGNORECASE
    )
    
    for idx, match in enumerate(figure_pattern.finditer(content), start=1):
        figure_content = match.group(1)
        
        # Extract caption
        caption_match = re.search(r'\\caption\{(.*?)\}', figure_content, re.DOTALL)
        caption = caption_match.group(1).strip() if caption_match else ""
        
        # Clean up caption (remove LaTeX commands)
        caption = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', caption)
        caption = re.sub(r'\\[a-zA-Z]+', '', caption)
        caption = caption.strip()
        
        # Extract label
        label_match = re.search(r'\\label\{(.*?)\}', figure_content)
        label = label_match.group(1).strip() if label_match else ""
        
        # Extract image file path(s)
        # Look for \includegraphics
        image_match = re.search(
            r'\\includegraphics(?:\[.*?\])?\{(.*?)\}',
            figure_content
        )
        
        if image_match:
            image_filename = image_match.group(1).strip()
            
            # Remove common LaTeX path prefixes
            image_filename = image_filename.replace('./', '')
            
            # Try to find the actual image file
            # Common extensions if not specified
            possible_extensions = ['', '.pdf', '.png', '.jpg', '.jpeg', '.eps']
            
            image_path = None
            for ext in possible_extensions:
                # Search in source root and subdirectories
                search_name = image_filename + ext
                candidates = list(source_root.rglob(search_name))
                if candidates:
                    image_path = candidates[0]
                    break
            
            if image_path and image_path.exists():
                figures.append(FigureInfo(
                    image_path=image_path,
                    caption=caption,
                    label=label,
                    figure_index=idx
                ))
                logger.debug(f"Found figure {idx}: {caption[:50]}... -> {image_path.name}")
            else:
                logger.debug(f"Image file not found for figure {idx}: {image_filename}")
    
    return figures


def scan_latex_for_figures(source_dir: Path) -> List[FigureInfo]:
    """Scan all .tex files in source directory for figures."""
    all_figures = []
    
    tex_files = list(source_dir.rglob("*.tex"))
    logger.info(f"Found {len(tex_files)} .tex files in {source_dir}")
    
    for tex_file in tex_files:
        figures = extract_figures_from_tex(tex_file, source_dir)
        all_figures.extend(figures)
    
    logger.info(f"Extracted {len(all_figures)} figures from LaTeX source")
    return all_figures


def evaluate_figure_captions(figures: List[FigureInfo], paper_text: str, config_path: Path) -> Optional[FigureInfo]:
    """Evaluate all figure captions at once using structured LLM to find the best overview diagram."""
    if not figures:
        return None
    
    # Load structured LLM configuration
    llm = StructuredLLM(str(config_path), DiagramEvaluationResponse, config_section="diagram_selection")
    
    # Prepare evaluation prompt with captions
    captions_text = "\n".join([
        f"Figure {i}: {fig.caption}"
        for i, fig in enumerate(figures)
    ])
    
    prompt = f"""
You are evaluating figures from a research paper to identify which one best represents an overview diagram of the entire paper.

Available figures and their captions:
{captions_text}

Please evaluate each figure caption and select the one that is most likely to be a diagram showing the architecture or methodology.

Negative keywords (having one or more means the figure MUST NOT be considered as a diagram):
- results
- metric & metrics
- example & examples
- sample & samples
- qualitative
- score & scores
- performance
- visualization
- analysis
- comparison of performance or results

Positive indicators (suggest it MAY BE a diagram):
- architecture
- comparison (of methods or approaches)
- framework
- pipeline 
- workflow
- method
- approach
- overview

The rule is: **if the caption has at least one negative keywords, it MUST NOT be considered as a diagram. For those captions without negative keywords, if the caption has one or more positive indicators, it may be considered as a diagram.**
I notice that you may raise some captions as candidates with negative keywords and without positive indicators. This is extremely wrong. Please be critical and strict.

If none of the figures appear to be diagrams, return -1 as the selected_diagram_index.

Please think step by step and respond with:
- reasoning: Your reasoning for the selection. You need to evaluate each caption one by one carefully and make a decision based on the positive and negative keywords.
- selected_diagram_index: The index (0-based) of the best overview diagram, or -1 if none are suitable
"""
    
    try:
        response = llm.query(prompt)
        
        # Handle both dict and Pydantic model responses
        if isinstance(response, dict):
            selected_index = response.get("selected_diagram_index", -1)
            reasoning = response.get("reasoning", "No reasoning provided")
        else:
            selected_index = response.selected_diagram_index
            reasoning = response.reasoning
        
        if selected_index == -1:
            logger.info("No suitable overview diagram found")
            return None
        elif 0 <= selected_index < len(figures):
            logger.info(f"Selected figure {selected_index}: {reasoning}")
            logger.info(f"Caption: {figures[selected_index].caption}")
            return figures[selected_index]
        else:
            logger.warning(f"Invalid figure index {selected_index}, returning None")
            return None
            
    except Exception as e:
        logger.error(f"Error evaluating figures: {e}")
        return None






def extract_overview_diagram_and_text(
    paper_dir: Path,
    output_dir: Path,
    config_path: Path,
    *,
    diagram_prefix: str = "figure"
) -> tuple[Path, Optional[Path]]:
    """
    Extract text from PDF and select the best overview diagram from LaTeX source.
    
    Args:
        paper_dir: Directory containing PDF and LaTeX source (e.g., crawled/2212.09748/)
        output_dir: Output directory for extracted text and diagram
        config_path: Path to LLM configuration file
        diagram_prefix: Prefix for output diagram filename
    
    Returns:
        Tuple of (text_path, diagram_path or None)
    """
    paper_dir = paper_dir.expanduser().resolve()
    if not paper_dir.exists():
        raise FileNotFoundError(f"Paper directory not found: {paper_dir}")
    
    # Find PDF file
    arxiv_id = paper_dir.name
    pdf_path = paper_dir / f"{arxiv_id}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Find LaTeX source file
    latex_source = paper_dir / f"{arxiv_id}.tar.gz"
    if not latex_source.exists():
        latex_source = paper_dir / f"{arxiv_id}.zip"
    if not latex_source.exists():
        logger.warning(f"No LaTeX source found in {paper_dir}")
        latex_source = None
    
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    text_path = output_dir / f"{arxiv_id}_text.txt"
    diagrams_dir = output_dir / f"{arxiv_id}_diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Extract text from PDF
    logger.info(f"Extracting text from {pdf_path}")
    extracted_text_path = extract_text(pdf_path, text_path)
    
    # Read paper text for evaluation
    with open(extracted_text_path, "r", encoding="utf-8") as f:
        paper_text = f.read()
    
    # Step 2: Extract figures from LaTeX source
    if not latex_source:
        logger.warning("No LaTeX source available, cannot extract diagrams")
        return extracted_text_path, None
    
    # Unzip LaTeX source
    temp_extract_dir = paper_dir / "temp_latex_extract"
    try:
        logger.info(f"Extracting LaTeX source from {latex_source}")
        unzip_latex_source(latex_source, temp_extract_dir)
        
        # Scan for figures
        figures = scan_latex_for_figures(temp_extract_dir)
        
        if not figures:
            logger.warning(f"No figures found in LaTeX source")
            return extracted_text_path, None
        
        # Step 3: Evaluate figures and select best overview diagram
        selected_figure = evaluate_figure_captions(figures, paper_text, config_path)
        
        if selected_figure:
            # Step 4: Convert selected diagram to PNG and save to output directory
            logger.info(f"Selected overview diagram: {selected_figure.caption}")
            
            try:
                # Convert diagram to PNG (handles PDF, PNG, JPG, etc.)
                conversion_result = convert_diagram_to_png(
                    diagram_path=selected_figure.image_path,
                    output_dir=diagrams_dir,
                    dpi=400,
                    prefix=f"{diagram_prefix}_overview"
                )
                
                # Use the first output file (should be the only one for single-page diagrams)
                output_diagram_path = conversion_result.output_files[0]
                logger.info(f"Converted and saved to: {output_diagram_path}")
                return extracted_text_path, output_diagram_path
                
            except Exception as e:
                logger.error(f"Failed to convert diagram to PNG: {e}")
                # Fallback: copy original file if conversion fails
                output_diagram_path = diagrams_dir / f"{diagram_prefix}_overview{selected_figure.image_path.suffix}"
                shutil.copy2(selected_figure.image_path, output_diagram_path)
                logger.warning(f"Used original format as fallback: {output_diagram_path}")
                return extracted_text_path, output_diagram_path
        else:
            logger.info("No suitable overview diagram found")
            return extracted_text_path, None
            
    finally:
        # Clean up temporary extraction directory
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir)
            logger.debug(f"Cleaned up temporary directory: {temp_extract_dir}")




def extract_overview_diagrams_in_folder(
    input_path: Path,
    output_dir: Path,
    config_path: Path,
    *,
    max_workers: int = 4,
    diagram_prefix: str = "figure",
) -> List[dict]:
    """
    Extract text and select best overview diagram from LaTeX source for each paper.
    
    Args:
        input_path: Directory containing paper subdirectories (e.g., crawled/)
        output_dir: Output directory for extracted text and diagrams
        config_path: Path to LLM configuration file
        max_workers: Number of concurrent workers
        diagram_prefix: Prefix for output diagram filename
    
    Returns:
        List of processing summaries
    """
    input_path = input_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find paper directories (subdirectories with arXiv ID pattern)
    paper_dirs = []
    if input_path.is_dir():
        for subdir in input_path.iterdir():
            if subdir.is_dir() and subdir.name.replace(".", "").isdigit():  # arXiv ID pattern
                paper_dirs.append(subdir)
        paper_dirs = sorted(paper_dirs)
    else:
        raise FileNotFoundError(f"Path not found: {input_path}")

    if not paper_dirs:
        logger.warning("No paper directories found under %s", input_path)
        return []

    max_workers = max(1, min(max_workers, len(paper_dirs)))

    def _process_paper(paper_dir: Path) -> dict:
        arxiv_id = paper_dir.name
        destination_dir = output_dir / arxiv_id
        
        try:
            text_path, diagram_path = extract_overview_diagram_and_text(
                paper_dir, destination_dir, config_path, diagram_prefix=diagram_prefix
            )
            
            return {
                "arxiv_id": arxiv_id,
                "paper_dir": str(paper_dir),
                "status": "success",
                "text": str(text_path),
                "overview_diagram": str(diagram_path) if diagram_path else None,
            }
        except Exception as exc:
            logger.exception("Failed to process %s: %s", paper_dir, exc)
            return {
                "arxiv_id": arxiv_id,
                "paper_dir": str(paper_dir),
                "status": "error",
                "error": str(exc)
            }

    summaries: List[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_process_paper, paper_dir): paper_dir for paper_dir in paper_dirs}
        for future in as_completed(future_map):
            paper_dir = future_map[future]
            summary = future.result()
            summaries.append(summary)

    return summaries


def _configure_logging(log_dir: Path) -> None:
    """(log_dir: Path) -> None: Configure shared logging handlers for extraction."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "extract_text_diagram_from_paper.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger.info("Logs will be written to %s", log_file)


def _cli(argv: Iterable[str] | None = None) -> int:
    """CLI helper to extract text from PDFs and select best overview diagram from LaTeX source."""
    parser = argparse.ArgumentParser(
        description="Extract text from PDFs and select the best overview diagram from LaTeX source using LLM evaluation."
    )
    parser.add_argument(
        "--input_path",
        type=Path,
        default=Path("test/output/crawled"),
        help="Directory containing paper subdirectories (e.g., crawled/2212.09748/ with PDF and LaTeX source)."
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=Path("test/output/extracted"),
        help="Directory where text and overview diagram will be stored."
    )
    parser.add_argument(
        "--diagram-prefix",
        type=str,
        default="figure",
        help="Filename prefix for extracted diagrams."
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Number of concurrent workers."
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=Path("configs/llm_config.yaml"),
        help="Path to unified LLM configuration file (default: configs/llm_config.yaml)."
    )
    parser.add_argument(
        "--metadata-json",
        type=Path,
        help="Optional path to write a summary JSON containing text and overview diagram locations.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs"),
        help="Directory where logs will be written (default: logs).",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)
    _configure_logging(args.log_dir)

    # Extract text and select best overview diagram
    summaries = extract_overview_diagrams_in_folder(
        args.input_path,
        args.output_dir,
        args.config_path,
        max_workers=args.max_workers,
        diagram_prefix=args.diagram_prefix,
    )

    if args.metadata_json:
        args.metadata_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.metadata_json, "w", encoding="utf-8") as file:
            json.dump(summaries, file, indent=2)
        logger.info("Summary metadata written to %s", args.metadata_json)

    print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
