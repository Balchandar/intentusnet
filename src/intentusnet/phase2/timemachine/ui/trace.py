"""
Trace Viewer (Time Machine UI - Phase II)

Provides deterministic tree rendering of execution traces.

UI REQUIREMENTS:
- Deterministic tree rendering
- Collapsible nodes
- Timing per node
- Hash-based identity per node
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ===========================================================================
# Trace Node
# ===========================================================================


@dataclass
class TraceNode:
    """
    A node in the trace tree.

    Attributes:
        node_id: Hash-based unique identifier
        node_type: Type of trace event
        name: Human-readable name
        start_time: When the node started
        end_time: When the node ended
        duration_ms: Duration in milliseconds
        payload: Node payload data
        children: Child nodes
        depth: Depth in the tree
        is_collapsed: Whether node is collapsed in UI
        is_selected: Whether node is selected
    """
    node_id: str
    node_type: str
    name: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[float] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    children: List["TraceNode"] = field(default_factory=list)
    depth: int = 0
    is_collapsed: bool = False
    is_selected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodeId": self.node_id,
            "nodeType": self.node_type,
            "name": self.name,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "durationMs": self.duration_ms,
            "payload": self.payload,
            "children": [c.to_dict() for c in self.children],
            "depth": self.depth,
            "isCollapsed": self.is_collapsed,
            "isSelected": self.is_selected,
        }

    @property
    def has_children(self) -> bool:
        """Check if node has children."""
        return len(self.children) > 0

    @property
    def child_count(self) -> int:
        """Get total descendant count."""
        count = len(self.children)
        for child in self.children:
            count += child.child_count
        return count


# ===========================================================================
# Trace View State
# ===========================================================================


@dataclass
class TraceViewState:
    """
    State for the trace viewer.

    Attributes:
        execution_id: Execution being viewed
        root_nodes: Top-level trace nodes
        selected_node_id: Currently selected node
        expanded_node_ids: Set of expanded node IDs
        total_duration_ms: Total trace duration
        node_count: Total number of nodes
        loading: Whether trace is loading
        error: Error message if loading failed
    """
    execution_id: str
    root_nodes: List[TraceNode]
    selected_node_id: Optional[str] = None
    expanded_node_ids: set = field(default_factory=set)
    total_duration_ms: Optional[float] = None
    node_count: int = 0
    loading: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "rootNodes": [n.to_dict() for n in self.root_nodes],
            "selectedNodeId": self.selected_node_id,
            "expandedNodeIds": list(self.expanded_node_ids),
            "totalDurationMs": self.total_duration_ms,
            "nodeCount": self.node_count,
            "loading": self.loading,
            "error": self.error,
        }


# ===========================================================================
# Trace Viewer
# ===========================================================================


class TraceViewer:
    """
    Trace viewer controller for the Time Machine UI.

    Provides:
    - Deterministic tree rendering
    - Collapsible nodes
    - Timing per node
    - Hash-based identity per node
    """

    def __init__(self):
        """Initialize the trace viewer."""
        self._state: Optional[TraceViewState] = None

    @property
    def state(self) -> Optional[TraceViewState]:
        """Get current view state."""
        return self._state

    def load_trace(
        self,
        execution_id: str,
        trace_data: List[Dict[str, Any]],
    ) -> TraceViewState:
        """
        Load and parse trace data.

        Args:
            execution_id: Execution ID
            trace_data: Raw trace data

        Returns:
            TraceViewState
        """
        try:
            # Parse trace into tree
            root_nodes = self._build_trace_tree(trace_data)

            # Calculate total duration
            total_duration = self._calculate_total_duration(root_nodes)

            # Count nodes
            node_count = self._count_nodes(root_nodes)

            self._state = TraceViewState(
                execution_id=execution_id,
                root_nodes=root_nodes,
                total_duration_ms=total_duration,
                node_count=node_count,
            )

        except Exception as e:
            self._state = TraceViewState(
                execution_id=execution_id,
                root_nodes=[],
                error=str(e),
            )

        return self._state

    def _build_trace_tree(
        self,
        trace_data: List[Dict[str, Any]],
        depth: int = 0,
    ) -> List[TraceNode]:
        """Build trace tree from raw data."""
        nodes: List[TraceNode] = []

        for item in trace_data:
            # Generate deterministic node ID from content
            node_id = self._compute_node_id(item)

            # Extract timing
            start_time = item.get("startTime") or item.get("timestamp")
            end_time = item.get("endTime")
            duration_ms = item.get("durationMs")

            if duration_ms is None and start_time and end_time:
                duration_ms = self._compute_duration(start_time, end_time)

            # Build children recursively
            children_data = item.get("children", [])
            children = self._build_trace_tree(children_data, depth + 1)

            node = TraceNode(
                node_id=node_id,
                node_type=item.get("type", "unknown"),
                name=item.get("name", item.get("type", "unnamed")),
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                payload={k: v for k, v in item.items() if k not in [
                    "children", "type", "name", "startTime", "endTime", "durationMs"
                ]},
                children=children,
                depth=depth,
            )
            nodes.append(node)

        return nodes

    def _compute_node_id(self, item: Dict[str, Any]) -> str:
        """
        Compute deterministic hash-based node ID.

        The ID is based on the node's content, ensuring
        consistent identification across renders.
        """
        # Create canonical representation (exclude children for uniqueness)
        content = {k: v for k, v in item.items() if k != "children"}
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def _compute_duration(self, start: str, end: str) -> float:
        """Compute duration in milliseconds between two ISO timestamps."""
        try:
            from dateutil.parser import isoparse

            start_dt = isoparse(start)
            end_dt = isoparse(end)
            delta = end_dt - start_dt
            return delta.total_seconds() * 1000
        except Exception:
            return 0.0

    def _calculate_total_duration(self, nodes: List[TraceNode]) -> Optional[float]:
        """Calculate total duration across all root nodes."""
        if not nodes:
            return None

        total = 0.0
        for node in nodes:
            if node.duration_ms:
                total += node.duration_ms
            # Recursively add children
            child_total = self._calculate_total_duration(node.children)
            if child_total:
                total += child_total

        return total if total > 0 else None

    def _count_nodes(self, nodes: List[TraceNode]) -> int:
        """Count total number of nodes in tree."""
        count = len(nodes)
        for node in nodes:
            count += self._count_nodes(node.children)
        return count

    def toggle_node(self, node_id: str) -> None:
        """Toggle node collapsed state."""
        if self._state is None:
            return

        if node_id in self._state.expanded_node_ids:
            self._state.expanded_node_ids.remove(node_id)
        else:
            self._state.expanded_node_ids.add(node_id)

        # Update node state
        self._update_node_collapsed(self._state.root_nodes, node_id)

    def _update_node_collapsed(
        self,
        nodes: List[TraceNode],
        target_id: str,
    ) -> None:
        """Update collapsed state for a node."""
        for node in nodes:
            if node.node_id == target_id:
                node.is_collapsed = not node.is_collapsed
            self._update_node_collapsed(node.children, target_id)

    def select_node(self, node_id: str) -> None:
        """Select a node."""
        if self._state is None:
            return

        self._state.selected_node_id = node_id
        self._update_node_selected(self._state.root_nodes, node_id)

    def _update_node_selected(
        self,
        nodes: List[TraceNode],
        target_id: str,
    ) -> None:
        """Update selected state for nodes."""
        for node in nodes:
            node.is_selected = node.node_id == target_id
            self._update_node_selected(node.children, target_id)

    def expand_all(self) -> None:
        """Expand all nodes."""
        if self._state is None:
            return

        self._set_all_collapsed(self._state.root_nodes, False)

    def collapse_all(self) -> None:
        """Collapse all nodes."""
        if self._state is None:
            return

        self._set_all_collapsed(self._state.root_nodes, True)

    def _set_all_collapsed(
        self,
        nodes: List[TraceNode],
        collapsed: bool,
    ) -> None:
        """Set collapsed state for all nodes."""
        for node in nodes:
            node.is_collapsed = collapsed
            self._set_all_collapsed(node.children, collapsed)

    def get_node_path(self, node_id: str) -> List[str]:
        """Get path from root to a node."""
        path: List[str] = []
        self._find_node_path(self._state.root_nodes if self._state else [], node_id, path)
        return path

    def _find_node_path(
        self,
        nodes: List[TraceNode],
        target_id: str,
        path: List[str],
    ) -> bool:
        """Recursively find path to a node."""
        for node in nodes:
            if node.node_id == target_id:
                path.append(node.node_id)
                return True
            if self._find_node_path(node.children, target_id, path):
                path.insert(0, node.node_id)
                return True
        return False

    def get_flattened_nodes(
        self,
        include_collapsed: bool = False,
    ) -> List[TraceNode]:
        """
        Get flattened list of nodes for rendering.

        Args:
            include_collapsed: Whether to include children of collapsed nodes

        Returns:
            Flattened list of visible nodes
        """
        if self._state is None:
            return []

        result: List[TraceNode] = []
        self._flatten_nodes(
            self._state.root_nodes,
            result,
            include_collapsed,
        )
        return result

    def _flatten_nodes(
        self,
        nodes: List[TraceNode],
        result: List[TraceNode],
        include_collapsed: bool,
    ) -> None:
        """Recursively flatten nodes."""
        for node in nodes:
            result.append(node)
            if include_collapsed or not node.is_collapsed:
                self._flatten_nodes(node.children, result, include_collapsed)
