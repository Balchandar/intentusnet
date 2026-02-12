"""
Diff Viewer (Time Machine UI - Phase II)

Provides structural diff visualization for execution comparison.

UI REQUIREMENTS:
- Input / output / trace / metadata diffs
- Structural diff for JSON & traces
- Hash-verified diff context only
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


# ===========================================================================
# Diff Types
# ===========================================================================


class DiffType(Enum):
    """Type of diff operation."""
    ADDED = "added"  # Value was added
    REMOVED = "removed"  # Value was removed
    CHANGED = "changed"  # Value was modified
    UNCHANGED = "unchanged"  # Value is the same


class DiffSection(Enum):
    """Sections that can be diffed."""
    INPUT = "input"
    OUTPUT = "output"
    TRACE = "trace"
    METADATA = "metadata"


# ===========================================================================
# Diff Entry
# ===========================================================================


@dataclass
class DiffEntry:
    """
    A single diff entry.

    Attributes:
        path: JSON path to the diffed element
        diff_type: Type of diff
        old_value: Original value (for REMOVED/CHANGED)
        new_value: New value (for ADDED/CHANGED)
        old_hash: Hash of old value
        new_hash: Hash of new value
    """
    path: str
    diff_type: DiffType
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "diffType": self.diff_type.value,
            "oldValue": self.old_value,
            "newValue": self.new_value,
            "oldHash": self.old_hash,
            "newHash": self.new_hash,
        }


# ===========================================================================
# Section Diff
# ===========================================================================


@dataclass
class SectionDiff:
    """
    Diff results for a single section.

    Attributes:
        section: Which section was diffed
        entries: List of diff entries
        old_section_hash: Hash of entire old section
        new_section_hash: Hash of entire new section
        is_identical: Whether sections are identical
        diff_count: Number of differences found
    """
    section: DiffSection
    entries: List[DiffEntry]
    old_section_hash: str
    new_section_hash: str
    is_identical: bool
    diff_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section": self.section.value,
            "entries": [e.to_dict() for e in self.entries],
            "oldSectionHash": self.old_section_hash,
            "newSectionHash": self.new_section_hash,
            "isIdentical": self.is_identical,
            "diffCount": self.diff_count,
        }


# ===========================================================================
# Diff Result
# ===========================================================================


@dataclass
class DiffResult:
    """
    Complete diff result between two executions.

    Attributes:
        old_execution_id: ID of the original execution
        new_execution_id: ID of the compared execution
        old_canonical_hash: Canonical hash of original
        new_canonical_hash: Canonical hash of compared
        section_diffs: Diffs per section
        total_diff_count: Total number of differences
        hash_verified: Whether both executions passed hash verification
    """
    old_execution_id: str
    new_execution_id: str
    old_canonical_hash: str
    new_canonical_hash: str
    section_diffs: Dict[str, SectionDiff]
    total_diff_count: int
    hash_verified: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "oldExecutionId": self.old_execution_id,
            "newExecutionId": self.new_execution_id,
            "oldCanonicalHash": self.old_canonical_hash,
            "newCanonicalHash": self.new_canonical_hash,
            "sectionDiffs": {k: v.to_dict() for k, v in self.section_diffs.items()},
            "totalDiffCount": self.total_diff_count,
            "hashVerified": self.hash_verified,
        }


# ===========================================================================
# Diff View State
# ===========================================================================


@dataclass
class DiffViewState:
    """
    State for the diff viewer.

    Attributes:
        old_execution_id: Original execution
        new_execution_id: Compared execution
        result: Diff result
        selected_section: Currently selected section
        show_unchanged: Whether to show unchanged entries
        loading: Whether diff is being computed
        error: Error message if diff failed
    """
    old_execution_id: Optional[str] = None
    new_execution_id: Optional[str] = None
    result: Optional[DiffResult] = None
    selected_section: DiffSection = DiffSection.INPUT
    show_unchanged: bool = False
    loading: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "oldExecutionId": self.old_execution_id,
            "newExecutionId": self.new_execution_id,
            "result": self.result.to_dict() if self.result else None,
            "selectedSection": self.selected_section.value,
            "showUnchanged": self.show_unchanged,
            "loading": self.loading,
            "error": self.error,
        }


# ===========================================================================
# Diff Viewer
# ===========================================================================


class DiffViewer:
    """
    Diff viewer controller for the Time Machine UI.

    Provides:
    - Input / output / trace / metadata diffs
    - Structural diff for JSON & traces
    - Hash-verified diff context only

    CRITICAL: Only shows diff if both executions have verified hashes.
    """

    def __init__(self):
        """Initialize the diff viewer."""
        self._state: Optional[DiffViewState] = None

    @property
    def state(self) -> Optional[DiffViewState]:
        """Get current view state."""
        return self._state

    def compute_diff(
        self,
        old_execution_id: str,
        new_execution_id: str,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any],
        old_hash_verified: bool,
        new_hash_verified: bool,
    ) -> DiffViewState:
        """
        Compute diff between two executions.

        CRITICAL: Both executions must have verified hashes.

        Args:
            old_execution_id: Original execution ID
            new_execution_id: Compared execution ID
            old_data: Original execution data
            new_data: Compared execution data
            old_hash_verified: Whether old hash was verified
            new_hash_verified: Whether new hash was verified

        Returns:
            DiffViewState with results
        """
        # Check hash verification
        hash_verified = old_hash_verified and new_hash_verified

        if not hash_verified:
            self._state = DiffViewState(
                old_execution_id=old_execution_id,
                new_execution_id=new_execution_id,
                error="Cannot compute diff: hash verification failed for one or both executions",
            )
            return self._state

        try:
            section_diffs: Dict[str, SectionDiff] = {}
            total_diff_count = 0

            # Diff each section
            for section in DiffSection:
                section_key = section.value
                old_section = old_data.get(section_key, {})
                new_section = new_data.get(section_key, {})

                section_diff = self._diff_section(
                    section,
                    old_section,
                    new_section,
                )
                section_diffs[section_key] = section_diff
                total_diff_count += section_diff.diff_count

            result = DiffResult(
                old_execution_id=old_execution_id,
                new_execution_id=new_execution_id,
                old_canonical_hash=old_data.get("canonicalHash", ""),
                new_canonical_hash=new_data.get("canonicalHash", ""),
                section_diffs=section_diffs,
                total_diff_count=total_diff_count,
                hash_verified=hash_verified,
            )

            self._state = DiffViewState(
                old_execution_id=old_execution_id,
                new_execution_id=new_execution_id,
                result=result,
            )

        except Exception as e:
            self._state = DiffViewState(
                old_execution_id=old_execution_id,
                new_execution_id=new_execution_id,
                error=str(e),
            )

        return self._state

    def _diff_section(
        self,
        section: DiffSection,
        old_value: Any,
        new_value: Any,
    ) -> SectionDiff:
        """Compute diff for a section."""
        old_hash = self._compute_hash(old_value)
        new_hash = self._compute_hash(new_value)

        is_identical = old_hash == new_hash

        entries: List[DiffEntry] = []
        if not is_identical:
            entries = self._diff_values("", old_value, new_value)

        return SectionDiff(
            section=section,
            entries=entries,
            old_section_hash=old_hash,
            new_section_hash=new_hash,
            is_identical=is_identical,
            diff_count=len([e for e in entries if e.diff_type != DiffType.UNCHANGED]),
        )

    def _diff_values(
        self,
        path: str,
        old_value: Any,
        new_value: Any,
    ) -> List[DiffEntry]:
        """Recursively diff two values."""
        entries: List[DiffEntry] = []

        # Handle None/missing values
        if old_value is None and new_value is not None:
            entries.append(DiffEntry(
                path=path or "/",
                diff_type=DiffType.ADDED,
                new_value=new_value,
                new_hash=self._compute_hash(new_value),
            ))
            return entries

        if old_value is not None and new_value is None:
            entries.append(DiffEntry(
                path=path or "/",
                diff_type=DiffType.REMOVED,
                old_value=old_value,
                old_hash=self._compute_hash(old_value),
            ))
            return entries

        if old_value is None and new_value is None:
            return entries

        # Handle different types
        if type(old_value) != type(new_value):
            entries.append(DiffEntry(
                path=path or "/",
                diff_type=DiffType.CHANGED,
                old_value=old_value,
                new_value=new_value,
                old_hash=self._compute_hash(old_value),
                new_hash=self._compute_hash(new_value),
            ))
            return entries

        # Handle dicts
        if isinstance(old_value, dict):
            all_keys = set(old_value.keys()) | set(new_value.keys())
            for key in sorted(all_keys):
                child_path = f"{path}/{key}" if path else f"/{key}"
                old_child = old_value.get(key)
                new_child = new_value.get(key)
                entries.extend(self._diff_values(child_path, old_child, new_child))
            return entries

        # Handle lists
        if isinstance(old_value, list):
            max_len = max(len(old_value), len(new_value))
            for i in range(max_len):
                child_path = f"{path}[{i}]"
                old_item = old_value[i] if i < len(old_value) else None
                new_item = new_value[i] if i < len(new_value) else None
                entries.extend(self._diff_values(child_path, old_item, new_item))
            return entries

        # Handle primitives
        if old_value == new_value:
            entries.append(DiffEntry(
                path=path or "/",
                diff_type=DiffType.UNCHANGED,
                old_value=old_value,
                new_value=new_value,
                old_hash=self._compute_hash(old_value),
                new_hash=self._compute_hash(new_value),
            ))
        else:
            entries.append(DiffEntry(
                path=path or "/",
                diff_type=DiffType.CHANGED,
                old_value=old_value,
                new_value=new_value,
                old_hash=self._compute_hash(old_value),
                new_hash=self._compute_hash(new_value),
            ))

        return entries

    def _compute_hash(self, value: Any) -> str:
        """Compute hash of a value."""
        if value is None:
            return "null"
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def select_section(self, section: DiffSection) -> None:
        """Select a section to view."""
        if self._state:
            self._state.selected_section = section

    def toggle_show_unchanged(self) -> None:
        """Toggle showing unchanged entries."""
        if self._state:
            self._state.show_unchanged = not self._state.show_unchanged

    def get_visible_entries(self) -> List[DiffEntry]:
        """
        Get visible diff entries based on current settings.

        Returns:
            List of diff entries to display
        """
        if self._state is None or self._state.result is None:
            return []

        section_key = self._state.selected_section.value
        section_diff = self._state.result.section_diffs.get(section_key)

        if section_diff is None:
            return []

        if self._state.show_unchanged:
            return section_diff.entries
        else:
            return [e for e in section_diff.entries if e.diff_type != DiffType.UNCHANGED]

    def get_summary(self) -> Optional[Dict[str, Any]]:
        """Get diff summary."""
        if self._state is None or self._state.result is None:
            return None

        result = self._state.result

        section_summaries = {}
        for section_key, section_diff in result.section_diffs.items():
            section_summaries[section_key] = {
                "isIdentical": section_diff.is_identical,
                "diffCount": section_diff.diff_count,
            }

        return {
            "oldExecutionId": result.old_execution_id,
            "newExecutionId": result.new_execution_id,
            "totalDiffCount": result.total_diff_count,
            "hashVerified": result.hash_verified,
            "sectionSummaries": section_summaries,
        }
