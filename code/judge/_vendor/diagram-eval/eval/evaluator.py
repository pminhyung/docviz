from __future__ import annotations
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Union

from pydantic import BaseModel, Field

from .graph import DiagramGraph
from utils.structured_llm import StructuredLLM, StructuredMLLM


# ============================================================================
# Graph Extraction Models
# ============================================================================

class NodeSpec(BaseModel):
    """Specification for a single node in the graph."""
    id: Optional[str] = Field(default=None, description="Optional identifier for the node.")
    text: str = Field(description="Textual content for the node.")


class EdgeSpec(BaseModel):
    """Specification for a single edge in the graph."""
    source: str = Field(description="Identifier of the source node.")
    target: str = Field(description="Identifier of the target node.")


class GraphSpec(BaseModel):
    """Complete graph specification with nodes and edges."""
    nodes: List[NodeSpec]
    edges: List[EdgeSpec] = Field(default_factory=list)


# ============================================================================
# Node Alignment Models
# ============================================================================

class NodeMatch(BaseModel):
    """Single alignment entry returned by the LLM."""
    source_id: str = Field(description="Node ID from the generated graph (Graph A).")
    target_id: str = Field(description="Node ID from the reference graph (Graph B).")
    reason: Optional[str] = Field(
        default=None, description="Short justification for the proposed match."
    )


class NodeAlignmentResponse(BaseModel):
    matches: List[NodeMatch] = Field(default_factory=list)


# ============================================================================
# Result Classes
# ============================================================================

@dataclass
class AlignmentScores:
    precision: float
    recall: float
    f1: float


@dataclass
class NodeAlignmentResult:
    matches: Dict[str, str]
    scores: AlignmentScores


@dataclass
class PathAlignmentResult:
    matched_paths: Set[Tuple[str, str]]
    scores: AlignmentScores


@dataclass
class EvaluationResult:
    node_alignment: NodeAlignmentResult
    path_alignment: PathAlignmentResult


# ============================================================================
# Main Evaluator Class
# ============================================================================

class DiagramEvaluator:
    """
    Evaluates generated diagrams by comparing their graphs against a reference.
    
    Supports:
    - Text-based graph extraction using StructuredLLM
    - Image-based graph extraction using StructuredMLLM (vision model)
    - Graph alignment and scoring
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        *,
        similarity_threshold: float = 0.55,
        verbose: bool = False,
    ):
        """
        Configure evaluator from unified config file.
        
        Args:
            config_path: Path to unified config file (e.g., configs/llm_config.yaml)
                        If None, uses heuristic-only evaluation
            similarity_threshold: Threshold for heuristic node matching
            verbose: Enable verbose logging
        """
        self._similarity_threshold = similarity_threshold
        self._verbose = verbose
        
        # Initialize LLMs from config if provided
        if config_path:
            self._text_graph_llm = StructuredLLM(config_path, GraphSpec, config_section="text_graph_extraction")
            self._image_graph_mllm = StructuredMLLM(config_path, GraphSpec, config_section="image_graph_extraction")
            self._alignment_llm = StructuredLLM(config_path, NodeAlignmentResponse, config_section="node_alignment")
        else:
            self._text_graph_llm = None
            self._image_graph_mllm = None
            self._alignment_llm = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    
    def evaluate(
        self,
        generated: Union[DiagramGraph, str, Path],
        reference: Union[DiagramGraph, str, Path],
    ) -> EvaluationResult:
        """
        Compute node and path alignment metrics between generated and reference.
        
        Args:
            generated: Generated graph (DiagramGraph, text file path, or image file path)
            reference: Reference graph (DiagramGraph, text file path, or image file path)
        
        Returns:
            EvaluationResult with node and path alignment scores
        """
        # Convert inputs to DiagramGraph if needed
        graph_a = self._to_diagram_graph(generated, "generated")
        graph_b = self._to_diagram_graph(reference, "reference")
        
        # Perform alignment and scoring
        matches = self._align_nodes(graph_a, graph_b)
        node_scores = self._compute_node_scores(matches, graph_a, graph_b)
        path_result = self._score_paths(matches, graph_a, graph_b)
        
        return EvaluationResult(
            node_alignment=NodeAlignmentResult(matches=matches, scores=node_scores),
            path_alignment=path_result,
        )

    # ------------------------------------------------------------------ #
    # Graph Extraction
    # ------------------------------------------------------------------ #
    
    def _to_diagram_graph(
        self,
        source: Union[DiagramGraph, str, Path],
        label: str
    ) -> DiagramGraph:
        """Convert various input formats to DiagramGraph."""
        # Already a graph
        if isinstance(source, DiagramGraph):
            return source
        
        # Convert to Path
        if isinstance(source, str):
            source = Path(source)
        
        if not source.exists():
            raise FileNotFoundError(f"{label} file not found: {source}")
        
        # Determine file type and extract graph
        suffix = source.suffix.lower()
        
        if suffix == ".txt":
            # Text file - extract graph from text
            return self._extract_graph_from_text(source)
        elif suffix in [".png", ".jpg", ".jpeg"]:
            # Image file - extract graph from image
            return self._extract_graph_from_image(source)
        elif suffix == ".json":
            # JSON graph file
            import json
            with open(source, "r", encoding="utf-8") as f:
                data = json.load(f)
            return DiagramGraph.from_dict(data)
        else:
            raise ValueError(f"Unsupported file format for {label}: {suffix}")
    
    def _extract_graph_from_text(self, text_path: Path) -> DiagramGraph:
        """Extract graph from text file using StructuredLLM."""
        if not self._text_graph_llm:
            raise ValueError("text_graph_llm is required for text-based graph extraction")
        
        # Read text
        with open(text_path, "r", encoding="utf-8") as f:
            text = f.read()
        
        # Build prompt
        prompt = self._build_text_graph_prompt(text)
        
        # Query LLM
        response = self._text_graph_llm.query(prompt, max_retries=2)
        
        # Convert to DiagramGraph
        if isinstance(response, dict):
            spec = GraphSpec.model_validate(response)
        else:
            spec = response
        
        return self._spec_to_graph(spec, prefix="T")
    
    def _extract_graph_from_image(self, image_path: Path) -> DiagramGraph:
        """Extract graph from image file using StructuredMLLM (vision model)."""
        if not self._image_graph_mllm:
            raise ValueError("image_graph_mllm is required for image-based graph extraction")
        
        # Step 1: Extract nodes from image
        nodes_prompt = self._build_image_nodes_prompt()
        nodes_response = self._image_graph_mllm.query_with_image(
            nodes_prompt,
            image_path,
            max_retries=2
        )
        
        if isinstance(nodes_response, dict):
            nodes_spec = GraphSpec.model_validate(nodes_response)
        else:
            nodes_spec = nodes_response
        
        # Step 2: Extract edges given the nodes
        if nodes_spec.nodes:
            edges_prompt = self._build_image_edges_prompt(nodes_spec.nodes)
            edges_response = self._image_graph_mllm.query_with_image(
                edges_prompt,
                image_path,
                max_retries=2
            )
            
            if isinstance(edges_response, dict):
                full_spec = GraphSpec.model_validate(edges_response)
            else:
                full_spec = edges_response
            
            # Combine nodes from step 1 with edges from step 2
            final_spec = GraphSpec(
                nodes=nodes_spec.nodes,
                edges=full_spec.edges
            )
        else:
            final_spec = nodes_spec
        
        return self._spec_to_graph(final_spec, prefix="D")
    
    def _spec_to_graph(self, spec: GraphSpec, prefix: str = "N") -> DiagramGraph:
        """Convert GraphSpec to DiagramGraph."""
        graph = DiagramGraph(prefix=prefix)
        id_map: Dict[str, str] = {}
        
        # Add nodes
        for node in spec.nodes:
            created = graph.add_node(node.text, node_id=node.id, dedupe=False)
            id_map[node.id or created.node_id] = created.node_id
        
        # Add edges
        for edge in spec.edges:
            src = id_map.get(edge.source)
            tgt = id_map.get(edge.target)
            if src and tgt and src != tgt:
                graph.add_edge(src, tgt)
        
        return graph
    
    # ------------------------------------------------------------------ #
    # Prompts
    # ------------------------------------------------------------------ #
    
    def _build_text_graph_prompt(self, text: str) -> str:
        """Build prompt for extracting graph from text."""
        return (
            "You are analyzing a research paper text to extract its logical structure as a directed graph.\n"
            "Return JSON containing two arrays: 'nodes' and 'edges'.\n"
            "Each node must have fields 'id' (string identifier) and 'text' (descriptive content).\n"
            "Each edge must have fields 'source' and 'target' referencing node IDs.\n"
            "Focus on the key concepts, components, and their relationships described in the text.\n"
            "Only include edges when the text implies a directional relationship (e.g., flow, dependency, causality).\n\n"
            f"Text:\n{text}"
        )
    
    def _build_image_nodes_prompt(self) -> str:
        """Build prompt for extracting nodes from diagram image."""
        return (
            "You are analyzing a research diagram image to extract all visible components and text boxes.\n"
            "Identify every distinct element, box, or component in the diagram.\n"
            "Return JSON with a 'nodes' array. Each node should have:\n"
            "- 'id': A unique identifier (e.g., 'node1', 'node2', etc.)\n"
            "- 'text': The text content or description of that component\n\n"
            "Include all visible text, labels, and component names.\n"
            "Also include 'edges' as an empty array for now (we'll extract edges in the next step)."
        )
    
    def _build_image_edges_prompt(self, nodes: List[NodeSpec]) -> str:
        """Build prompt for extracting edges given nodes."""
        node_list = "\n".join([f"- {node.id}: {node.text}" for node in nodes])
        
        return (
            "You are analyzing a research diagram image to extract all connections (arrows, lines) between components.\n"
            "The following nodes have been identified:\n\n"
            f"{node_list}\n\n"
            "Return JSON with 'nodes' (copy the list above) and 'edges' arrays.\n"
            "Each edge should have:\n"
            "- 'source': The ID of the source node\n"
            "- 'target': The ID of the target node\n\n"
            "Only include edges where you can clearly see a directional connection (arrow) in the diagram.\n"
            "Use the exact node IDs from the list above. Do not create new nodes."
        )

    # ------------------------------------------------------------------ #
    # Node alignment helpers
    # ------------------------------------------------------------------ #
    
    def _align_nodes(self, graph_a: DiagramGraph, graph_b: DiagramGraph) -> Dict[str, str]:
        """Determine best node correspondences using the LLM or fallback heuristic."""
        matches: Dict[str, str] = {}

        if self._alignment_llm:
            try:
                matches = self._align_nodes_with_llm(graph_a, graph_b)
            except Exception as exc:
                if self._verbose:
                    print(f"[DiagramEvaluator] LLM alignment failed: {exc}")

        if not matches:
            matches = self._align_nodes_by_similarity(graph_a, graph_b)

        return matches

    def _align_nodes_with_llm(
        self, graph_a: DiagramGraph, graph_b: DiagramGraph
    ) -> Dict[str, str]:
        """Ask the LLM to produce node pairings and filter invalid suggestions."""
        prompt = self._build_alignment_prompt(graph_a, graph_b)
        response = self._alignment_llm.query(prompt, max_retries=2)

        valid_sources = set(graph_a.node_ids())
        valid_targets = set(graph_b.node_ids())
        matches: Dict[str, str] = {}
        used_targets: Set[str] = set()
        
        # Handle both dict and Pydantic model responses
        if isinstance(response, dict):
            matches_list = response.get("matches", [])
        else:
            matches_list = response.matches
        
        for item in matches_list:
            if isinstance(item, dict):
                source_id = item.get("source_id")
                target_id = item.get("target_id")
            else:
                source_id = item.source_id
                target_id = item.target_id
            
            if source_id in matches:
                continue
            if target_id in used_targets:
                continue
            if source_id not in valid_sources:
                continue
            if target_id not in valid_targets:
                continue
            matches[source_id] = target_id
            used_targets.add(target_id)
        
        return matches

    def _build_alignment_prompt(self, graph_a: DiagramGraph, graph_b: DiagramGraph) -> str:
        """Craft the textual instructions used for LLM-based alignment."""
        lines = [
            "You match nodes between a generated diagram (Graph A) and a reference (Graph B).",
            "Only match IDs that clearly describe the same concept.",
            "Return JSON with field 'matches', each item containing 'source_id', 'target_id', and 'reason'.",
            "Every ID must come from the provided lists. Do not invent new IDs.",
            "",
            "Graph A nodes:",
        ]
        for node in graph_a.nodes:
            lines.append(f"- {node.node_id}: {node.text}")

        lines.append("")
        lines.append("Graph B nodes:")
        for node in graph_b.nodes:
            lines.append(f"- {node.node_id}: {node.text}")

        lines.append("")
        lines.append(
            "Only include a pair when the textual descriptions refer to the same concept."
        )
        return "\n".join(lines)

    def _align_nodes_by_similarity(
        self, graph_a: DiagramGraph, graph_b: DiagramGraph
    ) -> Dict[str, str]:
        """Align nodes greedily using token coverage when LLM support is unavailable."""
        matches: Dict[str, str] = {}
        used_targets: Set[str] = set()

        for src_node in graph_a.nodes:
            best_target = None
            best_score = 0.0
            for tgt_node in graph_b.nodes:
                if tgt_node.node_id in used_targets:
                    continue
                score = _token_coverage(src_node.text, tgt_node.text)
                if score > best_score:
                    best_score, best_target = score, tgt_node.node_id
            if best_target and best_score >= self._similarity_threshold:
                matches[src_node.node_id] = best_target
                used_targets.add(best_target)
        return matches

    def _compute_node_scores(
        self, matches: Dict[str, str], graph_a: DiagramGraph, graph_b: DiagramGraph
    ) -> AlignmentScores:
        """Calculate precision, recall, and F1 for node matching."""
        matched = len(matches)
        total_a = max(len(graph_a.nodes), 1)
        total_b = max(len(graph_b.nodes), 1)

        precision = matched / total_a
        recall = matched / total_b
        f1 = _f1_score(precision, recall)
        return AlignmentScores(precision=precision, recall=recall, f1=f1)

    # ------------------------------------------------------------------ #
    # Path scoring
    # ------------------------------------------------------------------ #
    
    def _score_paths(
        self, matches: Dict[str, str], graph_a: DiagramGraph, graph_b: DiagramGraph
    ) -> PathAlignmentResult:
        """Evaluate path-level precision, recall, and F1 using translated matches."""
        if not matches:
            scores = AlignmentScores(precision=0.0, recall=0.0, f1=0.0)
            return PathAlignmentResult(matched_paths=set(), scores=scores)

        graph_a_paths = graph_a.compute_paths()
        translated_paths: Set[Tuple[str, str]] = set()
        for src, dst in graph_a_paths:
            if src in matches and dst in matches:
                translated_paths.add((matches[src], matches[dst]))

        graph_b_paths = graph_b.compute_paths()
        common_paths = translated_paths.intersection(graph_b_paths)

        precision = _safe_div(len(common_paths), len(translated_paths))
        recall = _safe_div(len(common_paths), len(graph_b_paths))
        f1 = _f1_score(precision, recall)

        return PathAlignmentResult(
            matched_paths=common_paths,
            scores=AlignmentScores(precision=precision, recall=recall, f1=f1),
        )


# ---------------------------------------------------------------------- #
# Utility helpers
# ---------------------------------------------------------------------- #

def _token_coverage(text_a: str, text_b: str) -> float:
    """Compute asymmetric token coverage similarity between two strings."""
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)

    if not tokens_a or not tokens_b:
        return 0.0

    overlap = tokens_a.intersection(tokens_b)
    if not overlap:
        return 0.0

    coverage_a = len(overlap) / len(tokens_a)
    coverage_b = len(overlap) / len(tokens_b)
    return max(coverage_a, coverage_b)


def _tokenize(text: str) -> Set[str]:
    """Lowercase whitespace tokenisation helper."""
    return {token for token in text.lower().split() if token}


def _safe_div(numerator: int, denominator: int) -> float:
    """Perform safe division returning 0.0 when denominator is zero."""
    return float(numerator) / float(denominator) if denominator else 0.0


def _f1_score(precision: float, recall: float) -> float:
    """Compute harmonic mean while guarding zero cases."""
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


__all__ = [
    "DiagramEvaluator",
    "EvaluationResult",
    "NodeAlignmentResult",
    "PathAlignmentResult",
    "AlignmentScores",
    "NodeAlignmentResponse",
]
