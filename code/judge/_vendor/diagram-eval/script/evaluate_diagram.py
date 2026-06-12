from __future__ import annotations
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import argparse
import json
from dataclasses import asdict
from typing import Iterable

from eval.evaluator import DiagramEvaluator


def _generate_markdown_report(summary: dict, generated_path: Path, reference_path: Path) -> str:
    """Generate a readable Markdown report from evaluation results."""
    # Create ID to text mappings
    gen_id_to_text = {node['id']: node['text'] for node in summary['generated_graph']['nodes']}
    ref_id_to_text = {node['id']: node['text'] for node in summary['reference_graph']['nodes']}
    
    lines = [
        "# Diagram Evaluation Report",
        "",
        "## Input Files",
        f"- **Generated**: `{generated_path}`",
        f"- **Reference**: `{reference_path}`",
        "",
        "## Evaluation Scores",
        "",
        "### Node Alignment",
        f"- **Precision**: {summary['node_alignment']['scores']['precision']:.3f}",
        f"- **Recall**: {summary['node_alignment']['scores']['recall']:.3f}",
        f"- **F1 Score**: {summary['node_alignment']['scores']['f1']:.3f}",
        "",
        "### Path Alignment",
        f"- **Precision**: {summary['path_alignment']['scores']['precision']:.3f}",
        f"- **Recall**: {summary['path_alignment']['scores']['recall']:.3f}",
        f"- **F1 Score**: {summary['path_alignment']['scores']['f1']:.3f}",
        "",
        "## Generated Graph",
        "",
        "### Nodes",
        "",
    ]
    
    # Add generated nodes
    for node in summary['generated_graph']['nodes']:
        lines.append(f"- **{node['id']}**: {node['text']}")
    
    lines.extend([
        "",
        "### Edges",
        "",
    ])
    
    # Add generated edges with text
    if summary['generated_graph']['edges']:
        for edge in summary['generated_graph']['edges']:
            src_text = gen_id_to_text.get(edge['source'], edge['source'])
            tgt_text = gen_id_to_text.get(edge['target'], edge['target'])
            lines.append(f"- {src_text} → {tgt_text}")
    else:
        lines.append("*(No edges)*")
    
    lines.extend([
        "",
        "## Reference Graph",
        "",
        "### Nodes",
        "",
    ])
    
    # Add reference nodes
    for node in summary['reference_graph']['nodes']:
        lines.append(f"- **{node['id']}**: {node['text']}")
    
    lines.extend([
        "",
        "### Edges",
        "",
    ])
    
    # Add reference edges with text
    if summary['reference_graph']['edges']:
        for edge in summary['reference_graph']['edges']:
            src_text = ref_id_to_text.get(edge['source'], edge['source'])
            tgt_text = ref_id_to_text.get(edge['target'], edge['target'])
            lines.append(f"- {src_text} → {tgt_text}")
    else:
        lines.append("*(No edges)*")
    
    lines.extend([
        "",
        "## Node Alignment Matches",
        "",
    ])
    
    # Add node matches with text
    if summary['node_alignment']['matches']:
        lines.append("| Generated Node | Reference Node |")
        lines.append("|----------------|----------------|")
        for gen_id, ref_id in summary['node_alignment']['matches'].items():
            gen_text = gen_id_to_text.get(gen_id, gen_id)
            ref_text = ref_id_to_text.get(ref_id, ref_id)
            lines.append(f"| {gen_text} | {ref_text} |")
    else:
        lines.append("*(No matches)*")
    
    lines.extend([
        "",
        "## Path Alignment Matches",
        "",
    ])
    
    # Add path matches with text
    if summary['path_alignment']['matched_paths']:
        lines.append("| Source | Target |")
        lines.append("|--------|--------|")
        for path in summary['path_alignment']['matched_paths']:
            src_text = ref_id_to_text.get(path[0], path[0])
            tgt_text = ref_id_to_text.get(path[1], path[1])
            lines.append(f"| {src_text} | {tgt_text} |")
    else:
        lines.append("*(No matched paths)*")
    
    return "\n".join(lines)


def _format_result(result, generated_graph, reference_graph) -> dict:
    """Format evaluation result as dictionary with graph details."""
    node_scores = result.node_alignment.scores
    path_scores = result.path_alignment.scores
    
    # Format generated graph
    generated_nodes = [
        {"id": node.node_id, "text": node.text}
        for node in generated_graph.nodes
    ]
    generated_edges = [
        {"source": src, "target": tgt}
        for src, tgt in generated_graph.compute_paths()
    ]
    
    # Format reference graph
    reference_nodes = [
        {"id": node.node_id, "text": node.text}
        for node in reference_graph.nodes
    ]
    reference_edges = [
        {"source": src, "target": tgt}
        for src, tgt in reference_graph.compute_paths()
    ]
    
    return {
        "generated_graph": {
            "nodes": generated_nodes,
            "edges": generated_edges,
        },
        "reference_graph": {
            "nodes": reference_nodes,
            "edges": reference_edges,
        },
        "node_alignment": {
            "matches": result.node_alignment.matches,
            "scores": asdict(node_scores),
        },
        "path_alignment": {
            "matched_paths": [list(pair) for pair in sorted(result.path_alignment.matched_paths)],
            "scores": asdict(path_scores),
        },
    }


def _cli(argv: Iterable[str] | None = None) -> int:
    """
    CLI evaluator comparing generated diagrams with references.
    
    Supports:
    - Text references: {arxiv_id}_text.txt
    - Image references: figure_overview.png or {arxiv_id}_generated.png
    - Pre-computed graph JSON files
    """
    parser = argparse.ArgumentParser(
        description="Evaluate a generated diagram against a reference."
    )
    parser.add_argument(
        "generated",
        type=Path,
        help="Path to generated diagram (PNG or graph JSON)."
    )
    parser.add_argument(
        "reference",
        type=Path,
        help="Path to reference (text file, PNG, or graph JSON)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/llm_config.yaml"),
        help="Path to unified LLM configuration file (default: configs/llm_config.yaml)."
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Output path for evaluation metrics. If not specified, saves to same directory as generated with _metrics.json suffix."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory. If specified, saves as {arxiv_id}_metrics.json"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output."
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    # Create evaluator
    evaluator = DiagramEvaluator(
        config_path=str(args.config),
        verbose=args.verbose,
    )

    # Run evaluation
    if args.verbose:
        print(f"Evaluating:")
        print(f"  Generated: {args.generated}")
        print(f"  Reference: {args.reference}")
    
    # Get graphs and evaluate
    generated_graph = evaluator._to_diagram_graph(args.generated, "generated")
    reference_graph = evaluator._to_diagram_graph(args.reference, "reference")
    
    result = evaluator.evaluate(
        generated=generated_graph,
        reference=reference_graph,
    )
    
    summary = _format_result(result, generated_graph, reference_graph)
    
    # Add file paths to summary
    summary["generated_path"] = str(args.generated)
    summary["reference_path"] = str(args.reference)

    # Determine output path
    if args.output_json:
        output_path = args.output_json
    elif args.output_dir:
        arxiv_id = args.generated.stem.replace("_generated", "")
        output_path = args.output_dir / f"{arxiv_id}_metrics.json"
    else:
        output_path = args.generated.parent / f"{args.generated.stem}_metrics.json"
    
    # Save JSON results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"✓ Metrics saved to {output_path}")
    
    # Save Markdown report
    md_path = output_path.with_suffix('.md')
    markdown_report = _generate_markdown_report(summary, args.generated, args.reference)
    md_path.write_text(markdown_report, encoding="utf-8")
    print(f"✓ Report saved to {md_path}")

    # Print summary
    print(f"\nNode Alignment - P: {summary['node_alignment']['scores']['precision']:.3f}, "
          f"R: {summary['node_alignment']['scores']['recall']:.3f}, "
          f"F1: {summary['node_alignment']['scores']['f1']:.3f}")
    print(f"Path Alignment - P: {summary['path_alignment']['scores']['precision']:.3f}, "
          f"R: {summary['path_alignment']['scores']['recall']:.3f}, "
          f"F1: {summary['path_alignment']['scores']['f1']:.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())