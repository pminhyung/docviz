from __future__ import annotations
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import argparse
import json
from typing import Iterable

from generate import DiagramGenerationWorkflow


def _cli(argv: Iterable[str] | None = None) -> int:
    """
    CLI entry point for diagram generation workflow.
    
    Generates diagram PNG from text using Nano Banana API.
    Input: text file ({arxiv_id}_text.txt)
    Output: PNG diagram ({arxiv_id}_generated.png)
    """
    parser = argparse.ArgumentParser(
        description="Generate a diagram PNG from text using Nano Banana API."
    )
    parser.add_argument(
        "text_file",
        type=Path,
        help="Path to the text file (e.g., {arxiv_id}_text.txt)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/llm_config.yaml"),
        help="Path to unified configuration file (default: configs/llm_config.yaml)."
    )
    parser.add_argument(
        "--output-png",
        type=Path,
        help="Output path for generated PNG. If not specified, saves to same directory as input with _generated.png suffix."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory. If specified, saves as {arxiv_id}_generated.png"
    )
    parser.add_argument(
        "--metadata-json",
        type=Path,
        help="Optional path to store generation metadata."
    )
    parser.add_argument(
        "--use-planner",
        action="store_true",
        help="Enable layout planner to create a structured plan before generation (focuses on methodology)."
    )
    parser.add_argument(
        "--style-reference",
        type=Path,
        help="Optional path to a reference diagram image for visual style guidance."
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    # Read text
    text_content = args.text_file.read_text(encoding="utf-8")

    # Determine output path
    if args.output_png:
        output_path = args.output_png
    elif args.output_dir:
        arxiv_id = args.text_file.stem.replace("_text", "")
        output_path = args.output_dir / f"{arxiv_id}_generated.png"
    else:
        output_path = args.text_file.parent / f"{args.text_file.stem.replace('_text', '')}_generated.png"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize workflow and generate
    workflow = DiagramGenerationWorkflow(
        config_path=args.config,
        use_planner=args.use_planner,
    )

    result = workflow.generate(
        paper_context=text_content,
        style_reference_image=args.style_reference,
    )

    # Save PNG (Nano Banana returns PNG directly)
    output_path.write_bytes(result.image_data)
    print(f"✓ PNG saved to {output_path}")

    # Save metadata if requested
    if args.metadata_json:
        args.metadata_json.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "text_file": str(args.text_file),
            "output_png": str(output_path),
            "used_planner": args.use_planner,
            "style_reference": str(args.style_reference) if args.style_reference else None,
        }
        if hasattr(result, 'image_url') and result.image_url:
            metadata["image_url"] = result.image_url
        if result.plan:
            metadata["plan"] = {
                "key_components": result.plan.key_components,
                "relationships": result.plan.relationships,
                "layout_structure": result.plan.layout_structure,
            }
        
        args.metadata_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"✓ Metadata saved to {args.metadata_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())