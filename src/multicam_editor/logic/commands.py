"""
Undo/Redo command infrastructure using QUndoCommand pattern.

This module provides base classes for implementing undoable operations
in the application. Commands should be self-contained and reversible,
capturing all necessary state to perform and reverse their operations.
"""

from __future__ import annotations
from typing import Optional, Any
from PySide6.QtGui import QUndoCommand


class UndoableCommand(QUndoCommand):
    """Base class for undoable operations.

    Subclasses should implement redo() and undo() to perform and reverse
    their operations. The redo() method is called when the command is first
    pushed onto the undo stack and when redoing after an undo.

    Example:
        class SplitCommand(UndoableCommand):
            def __init__(self, project, clip_id, split_ms):
                super().__init__("Split Clip")
                self.project = project
                self.clip_id = clip_id
                self.split_ms = split_ms
                self.left_id = None
                self.right_id = None

            def redo(self):
                result = self.project.split_clip_by_id(self.clip_id, self.split_ms)
                if result:
                    self.left_id, self.right_id = result[0].id, result[1].id

            def undo(self):
                # Merge left and right clips back into original
                self.project.merge_clips(self.left_id, self.right_id, self.clip_id)
    """

    def __init__(self, text: str = "", parent: Optional[QUndoCommand] = None):
        """Initialize an undoable command.

        Args:
            text: Description shown in undo/redo menu (e.g., "Split Clip")
            parent: Parent command for command composition (optional)
        """
        super().__init__(text, parent)
        self._first_redo = True

    def redo(self) -> None:
        """Perform the operation.

        This is called both when the command is first executed (pushed)
        and when redoing after an undo. Subclasses must implement this.

        The default implementation does nothing.
        """
        pass

    def undo(self) -> None:
        """Reverse the operation.

        This is called when undoing the command. Must restore the exact
        state that existed before redo() was called.

        The default implementation does nothing.
        """
        pass

    def id(self) -> int:
        """Return command ID for merging consecutive similar commands.

        Commands with the same ID can be merged if mergeWith() returns True.
        Default is -1 (no merging).

        Override to enable command merging for similar operations.
        """
        return -1

    def mergeWith(self, other: QUndoCommand) -> bool:
        """Merge this command with another of the same type.

        Called when a command with the same id() is pushed onto the stack.
        If this returns True, the other command is discarded and this
        command represents both operations.

        Useful for merging consecutive operations like slider adjustments.

        Args:
            other: Another command to potentially merge with

        Returns:
            True if commands were merged, False otherwise
        """
        return False


class TrimCommand(UndoableCommand):
    """Command for trimming a clip with automatic coalescing.

    Multiple trim operations on the same clip are automatically merged
    into a single undo operation via mergeWith().
    """

    def __init__(self, project: Any, path: str, old_in: int, old_out: int,
                 new_in: int, new_out: int, refresh_callback: Optional[Any] = None):
        """Initialize trim command.

        Args:
            project: Project instance
            path: File path of clip to trim (using path-based API for now)
            old_in: Previous in_ms value
            old_out: Previous out_ms value
            new_in: New in_ms value
            new_out: New out_ms value
            refresh_callback: Optional callback to refresh UI after trim
        """
        super().__init__(f"Trim Clip")
        self.project = project
        self.path = path
        self.old_in = old_in
        self.old_out = old_out
        self.new_in = new_in
        self.new_out = new_out
        self.refresh_callback = refresh_callback

    def redo(self) -> None:
        """Apply the trim."""
        self.project.set_trim_by_path(self.path, self.new_in, self.new_out)
        if self.refresh_callback and callable(self.refresh_callback):
            self.refresh_callback()

    def undo(self) -> None:
        """Restore previous trim values."""
        self.project.set_trim_by_path(self.path, self.old_in, self.old_out)
        if self.refresh_callback and callable(self.refresh_callback):
            self.refresh_callback()

    def id(self) -> int:
        """Return command ID to enable merging of consecutive trims."""
        # Use a unique ID for trim commands
        return 1

    def mergeWith(self, other: QUndoCommand) -> bool:
        """Merge consecutive trim operations on the same clip.

        When user adjusts trim slider, we want to merge all the intermediate
        adjustments into a single undo operation.
        """
        if not isinstance(other, TrimCommand):
            return False

        # Only merge if same clip
        if other.path != self.path:
            return False

        # Update our new values to include the other command's changes
        self.new_in = other.new_in
        self.new_out = other.new_out
        return True


class SplitCommand(UndoableCommand):
    """Command for splitting a clip with undo support.

    Splits a clip at a specific position, creating two new clips.
    Undo merges them back into the original clip with selection restored.
    """

    def __init__(self, project: Any, path: str, split_ms: int,
                 refresh_callback: Optional[Any] = None,
                 adapter: Optional[Any] = None):
        """Initialize split command.

        Args:
            project: Project instance
            path: File path of clip to split
            split_ms: Position in milliseconds to split at
            refresh_callback: Optional callback to refresh UI after split/merge
            adapter: Optional TimelineAdapter for selection restoration
        """
        super().__init__("Split Clip")
        self.project = project
        self.path = path
        self.split_ms = split_ms
        self.refresh_callback = refresh_callback
        self.adapter = adapter
        # Store IDs and data, not object references
        self.original_clip_id: Optional[str] = None
        self.original_in_ms: int = 0
        self.original_out_ms: Optional[int] = None
        self.original_duration_ms: int = 0
        self.original_index: int = 0
        self.left_clip_id: Optional[str] = None
        self.right_clip_id: Optional[str] = None
        # Store left/right clip objects for first redo
        self.left_clip: Optional[Any] = None
        self.right_clip: Optional[Any] = None

    def redo(self) -> None:
        """Perform the split."""
        from ..core.project import Clip

        if self.left_clip_id is None:
            # First time: find original clip, store its data, then split
            clips = self.project.clips()
            for i, clip in enumerate(clips):
                if clip.path == self.path:
                    self.original_clip_id = clip.id
                    self.original_in_ms = clip.in_ms
                    self.original_out_ms = clip.out_ms
                    self.original_duration_ms = clip.duration_ms
                    self.original_index = i
                    break

            result = self.project.split_clip_by_path(self.path, self.split_ms)
            if result:
                self.left_clip, self.right_clip = result
                self.left_clip_id = self.left_clip.id
                self.right_clip_id = self.right_clip.id
        else:
            # Redo after undo: replace original with left and right
            clips = self.project.clips()
            new_clips = []
            for clip in clips:
                if clip.id == self.original_clip_id:
                    # Recreate left and right clips with stored IDs
                    left = Clip(
                        id=self.left_clip_id,
                        path=self.path,
                        in_ms=self.original_in_ms,
                        out_ms=self.split_ms,
                        duration_ms=self.original_duration_ms
                    )
                    right = Clip(
                        id=self.right_clip_id,
                        path=self.path,
                        in_ms=self.split_ms,
                        out_ms=self.original_out_ms,
                        duration_ms=self.original_duration_ms
                    )
                    new_clips.append(left)
                    new_clips.append(right)
                    self.left_clip = left
                    self.right_clip = right
                else:
                    new_clips.append(clip)
            self.project.set_clips(new_clips)

        # Refresh UI
        if self.refresh_callback and callable(self.refresh_callback):
            self.refresh_callback()

        # Select left clip after split/redo
        if self.adapter and self.left_clip:
            self._select_clip(self.left_clip)

    def undo(self) -> None:
        """Merge the split clips back together, restore selection."""
        if not self.left_clip_id or not self.right_clip_id:
            return

        from ..core.project import Clip

        # Recreate original clip with its original ID
        original = Clip(
            id=self.original_clip_id,
            path=self.path,
            in_ms=self.original_in_ms,
            out_ms=self.original_out_ms,
            duration_ms=self.original_duration_ms
        )

        # Find and replace left+right with original
        clips = self.project.clips()
        new_clips = []
        skip_next = False
        for i, clip in enumerate(clips):
            if skip_next:
                skip_next = False
                continue
            if clip.id == self.left_clip_id:
                new_clips.append(original)
                # Skip right clip if it follows
                if i + 1 < len(clips) and clips[i + 1].id == self.right_clip_id:
                    skip_next = True
            elif clip.id == self.right_clip_id:
                # Right without left preceding (edge case)
                if not any(c.id == self.original_clip_id for c in new_clips):
                    new_clips.append(original)
            else:
                new_clips.append(clip)

        self.project.set_clips(new_clips)

        # Refresh UI
        if self.refresh_callback and callable(self.refresh_callback):
            self.refresh_callback()

        # Restore selection to original clip
        if self.adapter:
            self._select_clip(original)

    def _select_clip(self, clip: Any) -> None:
        """Select the given clip in the timeline."""
        if not self.adapter:
            return
        try:
            clips = self.project.clips()
            idx = next((i for i, c in enumerate(clips) if c.id == clip.id), 0)
            if hasattr(self.adapter, "_make_key"):
                key = self.adapter._make_key(clip, idx)
                self.adapter.select_and_scroll_by_key(key)
        except Exception:
            pass


class AddClipsCommand(UndoableCommand):
    """Command for adding clips to the project.

    This command captures the paths of clips being added and stores the
    actual Clip objects that were created, allowing proper undo/redo.
    """

    def __init__(self, project: Any, paths: list[str], refresh_callback: Optional[Any] = None):
        """Initialize add clips command.

        Args:
            project: Project instance
            paths: List of file paths to add
            refresh_callback: Optional callback to refresh UI after add/remove
        """
        count = len(paths)
        text = f"Add {count} Clip{'s' if count != 1 else ''}"
        super().__init__(text)
        self.project = project
        self.paths = paths
        self.refresh_callback = refresh_callback
        self.added_clips: list = []  # Store actual Clip objects that were added
        self.insertion_index: int = -1  # Track where clips were added

    def redo(self) -> None:
        """Add clips to project."""
        if not self.added_clips:
            # First time: actually add the clips
            start_count = len(self.project.clips())
            for path in self.paths:
                clip = self.project.add_path(path)
                if clip is not None:
                    self.added_clips.append(clip)
            self.insertion_index = start_count
        else:
            # Redo: restore the clips at their original position
            current_clips = self.project.clips()
            # Insert at the original position
            for i, clip in enumerate(self.added_clips):
                current_clips.insert(self.insertion_index + i, clip)
            self.project.set_clips(current_clips)

        # Refresh UI if callback provided
        if self.refresh_callback and callable(self.refresh_callback):
            self.refresh_callback()

    def undo(self) -> None:
        """Remove the added clips from project."""
        if not self.added_clips:
            return

        # Get current clips and remove the ones we added
        current_clips = self.project.clips()
        clips_to_keep = [c for c in current_clips if c not in self.added_clips]
        self.project.set_clips(clips_to_keep)

        # Refresh UI if callback provided
        if self.refresh_callback and callable(self.refresh_callback):
            self.refresh_callback()


class RemoveClipsCommand(UndoableCommand):
    """Command for removing clips from the project.

    This command stores the clips being removed along with their positions,
    allowing them to be restored in the correct order.
    """

    def __init__(self, project: Any, clip_ids: list[str], refresh_callback: Optional[Any] = None):
        """Initialize remove clips command.

        Args:
            project: Project instance
            clip_ids: List of clip IDs to remove
            refresh_callback: Optional callback to refresh UI after add/remove
        """
        count = len(clip_ids)
        text = f"Remove {count} Clip{'s' if count != 1 else ''}"
        super().__init__(text)
        self.project = project
        self.clip_ids = clip_ids
        self.refresh_callback = refresh_callback
        self.removed_clips: list = []  # Store (index, clip) tuples

    def redo(self) -> None:
        """Remove clips from project."""
        current_clips = self.project.clips()

        if not self.removed_clips:
            # First time: find and store the clips with their indices
            for clip_id in self.clip_ids:
                for i, clip in enumerate(current_clips):
                    if clip.id == clip_id:
                        self.removed_clips.append((i, clip))
                        break

        # Remove the clips
        clips_to_keep = [c for c in current_clips
                        if c.id not in self.clip_ids]
        self.project.set_clips(clips_to_keep)

        # Refresh UI if callback provided
        if self.refresh_callback and callable(self.refresh_callback):
            self.refresh_callback()

    def undo(self) -> None:
        """Restore the removed clips at their original positions."""
        if not self.removed_clips:
            return

        current_clips = self.project.clips()

        # Sort by original index to maintain proper order
        sorted_removed = sorted(self.removed_clips, key=lambda x: x[0])

        # Insert clips back at their original positions
        for original_index, clip in sorted_removed:
            current_clips.insert(original_index, clip)

        self.project.set_clips(current_clips)

        # Refresh UI if callback provided
        if self.refresh_callback and callable(self.refresh_callback):
            self.refresh_callback()


class ReorderClipsCommand(UndoableCommand):
    """Command for reordering clips via drag-and-drop.

    This command stores the old and new order as lists of clip IDs,
    allowing undo/redo of reorder operations.
    """

    def __init__(self, project: Any, old_order: list[str], new_order: list[str],
                 refresh_callback: Optional[Any] = None):
        """Initialize reorder clips command.

        Args:
            project: Project instance
            old_order: List of clip IDs in original order
            new_order: List of clip IDs in new order
            refresh_callback: Optional callback to refresh UI after reorder
        """
        super().__init__("Reorder Clips")
        self.project = project
        self.old_order = old_order
        self.new_order = new_order
        self.refresh_callback = refresh_callback

    def redo(self) -> None:
        """Apply the new order."""
        self._apply_order(self.new_order)

    def undo(self) -> None:
        """Restore the old order."""
        self._apply_order(self.old_order)

    def _apply_order(self, clip_ids: list[str]) -> None:
        """Apply a specific order of clip IDs to the project.

        Args:
            clip_ids: List of clip IDs in desired order
        """
        current_clips = self.project.clips()

        # Build mapping from ID to Clip
        id_to_clip = {clip.id: clip for clip in current_clips}

        # Build new clips list in specified order
        new_clips = []
        for clip_id in clip_ids:
            clip = id_to_clip.get(clip_id)
            if clip is not None:
                new_clips.append(clip)

        # Apply new order to project
        self.project.set_clips(new_clips)

        # Refresh UI if callback provided
        if self.refresh_callback and callable(self.refresh_callback):
            self.refresh_callback()
