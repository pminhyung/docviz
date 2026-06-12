from __future__ import annotations
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class DiagramNode:
    """Represents a node in a diagram graph."""

    node_id: str
    text: str


class DiagramGraph:
    """A lightweight directed graph used for diagram evaluation."""

    def __init__(self, prefix: str = "N"):
        """(prefix: str='N') -> None: Prepare empty graph containers with an ID prefix."""
        self._prefix = prefix.upper()
        self._nodes: Dict[str, DiagramNode] = {}
        self._text_index: Dict[str, str] = {}
        self._edges: Set[Tuple[str, str]] = set()
        self._next_numeric_id = 1

    # --------------------------------------------------------------------- #
    # Node operations
    # --------------------------------------------------------------------- #
    def add_node(self, text: str, node_id: Optional[str] = None, dedupe: bool = True) -> DiagramNode:
        """(text: str, node_id: Optional[str]=None, dedupe: bool=True) -> DiagramNode: Insert a node and return the stored instance."""
        if not text or not text.strip():
            raise ValueError("Node text must be a non-empty string.")

        normalized_text = text.strip()
        if dedupe and normalized_text in self._text_index:
            return self._nodes[self._text_index[normalized_text]]

        resolved_id = node_id or self._generate_node_id()
        if resolved_id in self._nodes:
            raise ValueError(f"Node ID '{resolved_id}' already exists.")

        node = DiagramNode(node_id=resolved_id, text=normalized_text)
        self._nodes[resolved_id] = node
        if dedupe:
            self._text_index[normalized_text] = resolved_id
        return node

    def remove_node(self, node_id: str) -> None:
        """(node_id: str) -> None: Remove a node and all connected edges if it exists."""
        node = self._nodes.pop(node_id, None)
        if not node:
            return
        self._text_index = {text: nid for text, nid in self._text_index.items() if nid != node_id}
        self._edges = {edge for edge in self._edges if node_id not in edge}

    def get_node(self, node_id: str) -> Optional[DiagramNode]:
        """(node_id: str) -> Optional[DiagramNode]: Retrieve a node by ID or None when missing."""
        return self._nodes.get(node_id)

    def find_node_by_text(self, text: str) -> Optional[DiagramNode]:
        """(text: str) -> Optional[DiagramNode]: Find the first node whose text matches the provided string."""
        if not text:
            return None
        node_id = self._text_index.get(text.strip())
        return self._nodes.get(node_id) if node_id else None

    # --------------------------------------------------------------------- #
    # Edge operations
    # --------------------------------------------------------------------- #
    def add_edge(self, source_id: str, target_id: str) -> None:
        """(source_id: str, target_id: str) -> None: Create a directed edge between two stored node IDs."""
        if source_id == target_id:
            return
        if source_id not in self._nodes or target_id not in self._nodes:
            missing = [nid for nid in (source_id, target_id) if nid not in self._nodes]
            raise KeyError(f"Cannot add edge; missing node(s): {', '.join(missing)}")
        self._edges.add((source_id, target_id))

    def remove_edge(self, source_id: str, target_id: str) -> None:
        """(source_id: str, target_id: str) -> None: Remove a directed edge when present."""
        self._edges.discard((source_id, target_id))

    # --------------------------------------------------------------------- #
    # Inspection helpers
    # --------------------------------------------------------------------- #
    @property
    def nodes(self) -> List[DiagramNode]:
        """() -> List[DiagramNode]: Return a snapshot list of current nodes."""
        return list(self._nodes.values())

    @property
    def edges(self) -> Set[Tuple[str, str]]:
        """() -> Set[Tuple[str, str]]: Return a copy of the stored edge set."""
        return set(self._edges)

    def node_ids(self) -> List[str]:
        """() -> List[str]: Obtain all node identifiers in insertion order."""
        return list(self._nodes.keys())

    def adjacency(self) -> Dict[str, Set[str]]:
        """() -> Dict[str, Set[str]]: Build adjacency lists keyed by source ID."""
        adj: Dict[str, Set[str]] = {node_id: set() for node_id in self._nodes}
        for source, target in self._edges:
            adj[source].add(target)
        return adj

    # --------------------------------------------------------------------- #
    # Path utilities
    # --------------------------------------------------------------------- #
    def compute_paths(self) -> Set[Tuple[str, str]]:
        """() -> Set[Tuple[str, str]]: Produce all reachable source-target pairs via depth-first traversal."""
        adj = self.adjacency()
        reachable: Set[Tuple[str, str]] = set()

        for source in adj:
            visited: Set[str] = set()
            stack = list(adj[source])
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                reachable.add((source, current))
                stack.extend(adj.get(current, set()) - visited)
        return reachable

    # --------------------------------------------------------------------- #
    # Serialization helpers
    # --------------------------------------------------------------------- #
    def to_dict(self) -> Dict[str, Iterable]:
        """() -> Dict[str, Iterable]: Serialise nodes and edges into a JSON-friendly dictionary."""
        return {
            "nodes": [{"id": node.node_id, "text": node.text} for node in self.nodes],
            "edges": [{"source": src, "target": tgt} for src, tgt in sorted(self._edges)],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Iterable], prefix: str = "N") -> "DiagramGraph":
        """(payload: Dict[str, Iterable], prefix: str='N') -> DiagramGraph: Reconstruct a graph from serialised node and edge data."""
        graph = cls(prefix=prefix)
        for node_info in payload.get("nodes", []):
            graph.add_node(
                text=node_info["text"],
                node_id=node_info["id"],
                dedupe=False,
            )
        for edge_info in payload.get("edges", []):
            graph.add_edge(edge_info["source"], edge_info["target"])
        return graph

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _generate_node_id(self) -> str:
        """() -> str: Produce a new unique node identifier based on the configured prefix."""
        while True:
            candidate = f"{self._prefix}{self._next_numeric_id}"
            self._next_numeric_id += 1
            if candidate not in self._nodes:
                return candidate


__all__ = ["DiagramGraph", "DiagramNode"]
