"""
Timeline View (Time Machine UI - Phase II)

Provides paginated execution timeline with filtering.

UI REQUIREMENTS:
- Paginated execution timeline
- Filter by intent, model, trust domain, status
- ExecutionId always visible
- Parent/child lineage indicators
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from intentusnet.phase2.timemachine.api.core import (
    TimeMachineAPI,
    TimelineEntry,
    TimelineFilter,
    PaginationParams,
    SortOrder,
    VerificationStatus,
)


# ===========================================================================
# Timeline View State
# ===========================================================================


class LineageIndicator(Enum):
    """Indicator for parent/child relationships."""
    ROOT = "root"  # No parent
    CHILD = "child"  # Has parent
    PARENT = "parent"  # Has children
    BOTH = "both"  # Has parent and children


@dataclass
class TimelineViewEntry:
    """
    A single entry in the timeline view with UI-specific state.

    Attributes:
        entry: The underlying timeline entry
        lineage: Lineage indicator
        is_selected: Whether this entry is selected
        is_expanded: Whether this entry is expanded
        depth: Nesting depth for lineage display
    """
    entry: TimelineEntry
    lineage: LineageIndicator
    is_selected: bool = False
    is_expanded: bool = False
    depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry": self.entry.to_dict(),
            "lineage": self.lineage.value,
            "isSelected": self.is_selected,
            "isExpanded": self.is_expanded,
            "depth": self.depth,
        }


@dataclass
class TimelineViewState:
    """
    State for the timeline view.

    Attributes:
        entries: List of timeline entries with UI state
        total_count: Total number of matching executions
        current_page: Current page number (0-indexed)
        page_size: Number of entries per page
        filter: Current filter parameters
        sort_order: Current sort order
        selected_execution_id: Currently selected execution
        loading: Whether data is being loaded
        error: Error message if loading failed
    """
    entries: List[TimelineViewEntry]
    total_count: int
    current_page: int
    page_size: int
    filter: TimelineFilter
    sort_order: SortOrder
    selected_execution_id: Optional[str] = None
    loading: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "totalCount": self.total_count,
            "currentPage": self.current_page,
            "pageSize": self.page_size,
            "filter": self.filter.to_dict(),
            "sortOrder": self.sort_order.value,
            "selectedExecutionId": self.selected_execution_id,
            "loading": self.loading,
            "error": self.error,
        }

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        if self.page_size == 0:
            return 0
        return (self.total_count + self.page_size - 1) // self.page_size

    @property
    def has_next_page(self) -> bool:
        """Check if there is a next page."""
        return self.current_page < self.total_pages - 1

    @property
    def has_previous_page(self) -> bool:
        """Check if there is a previous page."""
        return self.current_page > 0


# ===========================================================================
# Timeline View
# ===========================================================================


class TimelineView:
    """
    Timeline view controller for the Time Machine UI.

    Provides:
    - Paginated execution timeline
    - Filter by intent, model, trust domain, status
    - ExecutionId always visible
    - Parent/child lineage indicators
    """

    def __init__(self, api: TimeMachineAPI):
        """
        Initialize the timeline view.

        Args:
            api: Time Machine API instance
        """
        self._api = api
        self._state: Optional[TimelineViewState] = None

    @property
    def state(self) -> Optional[TimelineViewState]:
        """Get current view state."""
        return self._state

    def load(
        self,
        filter_params: Optional[TimelineFilter] = None,
        page: int = 0,
        page_size: int = 50,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> TimelineViewState:
        """
        Load the timeline view.

        Args:
            filter_params: Filter parameters
            page: Page number (0-indexed)
            page_size: Number of entries per page
            sort_order: Sort order

        Returns:
            TimelineViewState with loaded data
        """
        filter_params = filter_params or TimelineFilter()

        # Create pagination
        pagination = PaginationParams(
            offset=page * page_size,
            limit=page_size,
            sort_order=sort_order,
        )

        try:
            # Query API
            entries, total_count = self._api.query_timeline(
                filter_params=filter_params,
                pagination=pagination,
            )

            # Convert to view entries with lineage indicators
            view_entries: List[TimelineViewEntry] = []
            for entry in entries:
                lineage = self._compute_lineage(entry)
                view_entries.append(TimelineViewEntry(
                    entry=entry,
                    lineage=lineage,
                ))

            self._state = TimelineViewState(
                entries=view_entries,
                total_count=total_count,
                current_page=page,
                page_size=page_size,
                filter=filter_params,
                sort_order=sort_order,
            )

        except Exception as e:
            self._state = TimelineViewState(
                entries=[],
                total_count=0,
                current_page=page,
                page_size=page_size,
                filter=filter_params,
                sort_order=sort_order,
                error=str(e),
            )

        return self._state

    def _compute_lineage(self, entry: TimelineEntry) -> LineageIndicator:
        """Compute lineage indicator for an entry."""
        has_parent = entry.has_parent
        has_children = entry.has_children

        if has_parent and has_children:
            return LineageIndicator.BOTH
        elif has_parent:
            return LineageIndicator.CHILD
        elif has_children:
            return LineageIndicator.PARENT
        else:
            return LineageIndicator.ROOT

    def next_page(self) -> Optional[TimelineViewState]:
        """Load the next page."""
        if self._state is None or not self._state.has_next_page:
            return self._state

        return self.load(
            filter_params=self._state.filter,
            page=self._state.current_page + 1,
            page_size=self._state.page_size,
            sort_order=self._state.sort_order,
        )

    def previous_page(self) -> Optional[TimelineViewState]:
        """Load the previous page."""
        if self._state is None or not self._state.has_previous_page:
            return self._state

        return self.load(
            filter_params=self._state.filter,
            page=self._state.current_page - 1,
            page_size=self._state.page_size,
            sort_order=self._state.sort_order,
        )

    def select_execution(self, execution_id: str) -> None:
        """Select an execution in the timeline."""
        if self._state is None:
            return

        self._state.selected_execution_id = execution_id

        for entry in self._state.entries:
            entry.is_selected = entry.entry.execution_id == execution_id

    def apply_filter(
        self,
        intent_names: Optional[Set[str]] = None,
        gateway_ids: Optional[Set[str]] = None,
        status: Optional[Set[VerificationStatus]] = None,
        has_parent: Optional[bool] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> TimelineViewState:
        """
        Apply filter and reload.

        Args:
            intent_names: Filter by intent names
            gateway_ids: Filter by gateway IDs
            status: Filter by verification status
            has_parent: Filter by parent existence
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Updated TimelineViewState
        """
        filter_params = TimelineFilter(
            intent_names=intent_names,
            gateway_ids=gateway_ids,
            status=status,
            has_parent=has_parent,
            start_time=start_time,
            end_time=end_time,
        )

        page_size = self._state.page_size if self._state else 50
        sort_order = self._state.sort_order if self._state else SortOrder.DESC

        return self.load(
            filter_params=filter_params,
            page=0,  # Reset to first page on filter change
            page_size=page_size,
            sort_order=sort_order,
        )

    def clear_filter(self) -> TimelineViewState:
        """Clear all filters and reload."""
        return self.apply_filter()

    def toggle_sort_order(self) -> TimelineViewState:
        """Toggle sort order and reload."""
        if self._state is None:
            return self.load()

        new_order = (
            SortOrder.ASC
            if self._state.sort_order == SortOrder.DESC
            else SortOrder.DESC
        )

        return self.load(
            filter_params=self._state.filter,
            page=self._state.current_page,
            page_size=self._state.page_size,
            sort_order=new_order,
        )

    def get_filter_options(self) -> Dict[str, List[str]]:
        """
        Get available filter options based on current data.

        Returns:
            Dict of filter name to available values
        """
        # In production, this would query the API for distinct values
        intent_names: Set[str] = set()
        gateway_ids: Set[str] = set()

        if self._state:
            for entry in self._state.entries:
                intent_names.add(entry.entry.intent_name)
                gateway_ids.add(entry.entry.gateway_id)

        return {
            "intentNames": sorted(intent_names),
            "gatewayIds": sorted(gateway_ids),
            "status": [s.value for s in VerificationStatus],
        }
