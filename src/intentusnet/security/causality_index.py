"""
Security Kernel v2.1 — Causality Graph with Segmented Storage

Tracks the derivation chain of every execution so that a forensic investigator
can answer "what caused what?" without scanning the full WAL.

Execution ID derivation
-----------------------
Child IDs are cryptographically derived from their parent:

    child_id = SHA-256(parent_id + ":" + agent_id + ":" + str(step_seq))

Root executions (no parent) use:

    root_id = SHA-256("ROOT:" + agent_id + ":" + nonce)

This means the lineage is verifiable: given a leaf node and its declared
ancestors you can recompute every ID and detect any tampering.

Storage layout
--------------
Nodes are stored in segments of ``segment_size`` (default 1000) so that a
large causality graph does not become one monolithic allocation.  A lightweight
in-memory index maps ``execution_id → (segment_index, position)`` for O(1)
lookup, and a children index maps ``parent_id → [child_ids]`` for O(|children|)
child enumeration.

Thread safety
-------------
All public methods acquire the instance lock.
"""

from __future__ import annotations

import hashlib
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# ExecutionNode
# ---------------------------------------------------------------------------

@dataclass
class ExecutionNode:
    """
    One node in the causality graph.

    ``execution_id`` — derivation-based SHA-256 hex digest (64 chars).
    ``parent_id``    — execution_id of the direct parent; None for root nodes.
    ``depth``        — 0 for root nodes, parent.depth + 1 for children.
    ``step_seq``     — caller-assigned monotonic step number within the parent's
                       execution scope.  Used in ID derivation so two children
                       of the same parent at different steps produce different IDs.
    """
    execution_id: str
    agent_id:     str
    step_seq:     int
    depth:        int
    timestamp:    float = field(default_factory=time.time)
    parent_id:    Optional[str] = None
    metadata:     Dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# CausalityIndex
# ---------------------------------------------------------------------------

class CausalityIndex:
    """
    Thread-safe segmented causality graph.

    All nodes are kept in memory.  Persistence to disk is a Phase 7 concern
    (the WAL sampler will snapshot segments).

    Parameters
    ----------
    segment_size
        Number of nodes per segment (default 1000).  Tune this based on
        expected graph density and available memory.
    """

    _SENTINEL_ROOT = "ROOT"

    def __init__(self, segment_size: int = 1000) -> None:
        self._segment_size = segment_size

        # Segmented node store: List[segment], each segment = List[ExecutionNode]
        self._segments: List[List[ExecutionNode]] = [[]]

        # Primary index: execution_id → (segment_idx, position_within_segment)
        self._index: Dict[str, Tuple[int, int]] = {}

        # Children index: parent_id → [execution_id, ...]
        self._children: Dict[str, List[str]] = {}

        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Derivation helpers (class-level, no state)
    # ------------------------------------------------------------------

    @staticmethod
    def derive_execution_id(parent_id: str, agent_id: str, step_seq: int) -> str:
        """
        Deterministic child execution ID derived from its parent and position.

        Identical inputs always produce the identical output, enabling
        offline verification of lineage without access to the running index.
        """
        raw = f"{parent_id}:{agent_id}:{step_seq}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def derive_root_id(agent_id: str, nonce: str) -> str:
        """
        Root execution ID (no parent).

        ``nonce`` should be unique per root execution — e.g. a UUID4 or a
        wall-clock timestamp string.  It is the caller's responsibility to
        supply a sufficiently unguessable nonce.
        """
        raw = f"ROOT:{agent_id}:{nonce}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_node(self, node: ExecutionNode) -> None:
        """
        Insert a node into the causality graph.

        Raises ``ValueError`` if a node with the same execution_id already
        exists (each ID must be unique within one index instance).
        """
        with self._lock:
            if node.execution_id in self._index:
                raise ValueError(
                    f"Execution ID already indexed: {node.execution_id[:16]}…"
                )

            current_segment = self._segments[-1]
            if len(current_segment) >= self._segment_size:
                self._segments.append([])
                current_segment = self._segments[-1]

            seg_idx = len(self._segments) - 1
            pos     = len(current_segment)
            current_segment.append(node)
            self._index[node.execution_id] = (seg_idx, pos)

            if node.parent_id is not None:
                if node.parent_id not in self._children:
                    self._children[node.parent_id] = []
                self._children[node.parent_id].append(node.execution_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_node(self, execution_id: str) -> Optional[ExecutionNode]:
        """Return the node for ``execution_id``, or None if not found."""
        with self._lock:
            loc = self._index.get(execution_id)
            if loc is None:
                return None
            seg_idx, pos = loc
            return self._segments[seg_idx][pos]

    def get_children(self, execution_id: str) -> List[ExecutionNode]:
        """Return all direct children of ``execution_id`` in insertion order."""
        with self._lock:
            child_ids = list(self._children.get(execution_id, []))
            result = []
            for cid in child_ids:
                loc = self._index.get(cid)
                if loc is not None:
                    seg_idx, pos = loc
                    result.append(self._segments[seg_idx][pos])
            return result

    def get_lineage(self, execution_id: str) -> List[ExecutionNode]:
        """
        Return the full ancestor chain from the root down to (and including)
        the given execution_id.

        Returns an empty list if the execution_id is not found.
        Raises ``RuntimeError`` if a cycle is detected (should never happen
        with derivation-based IDs, but guard defensively).
        """
        with self._lock:
            chain: List[ExecutionNode] = []
            visited: set = set()
            current_id: Optional[str] = execution_id

            while current_id is not None:
                if current_id in visited:
                    raise RuntimeError(
                        f"Cycle detected in causality graph at {current_id[:16]}…"
                    )
                visited.add(current_id)
                loc = self._index.get(current_id)
                if loc is None:
                    break
                seg_idx, pos = loc
                node = self._segments[seg_idx][pos]
                chain.append(node)
                current_id = node.parent_id

            # Reverse so list is root → leaf
            chain.reverse()
            return chain

    def has_node(self, execution_id: str) -> bool:
        with self._lock:
            return execution_id in self._index

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        with self._lock:
            return len(self._index)

    @property
    def segment_count(self) -> int:
        with self._lock:
            return len(self._segments)

    def segment_sizes(self) -> List[int]:
        """Return the number of nodes in each segment."""
        with self._lock:
            return [len(seg) for seg in self._segments]
