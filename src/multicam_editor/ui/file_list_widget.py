# file: ui/file_list_widget.py
from __future__ import annotations

import os
from typing import Iterable, List, Tuple

from PySide6.QtCore import Qt, QModelIndex, QMimeData, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem, QKeyEvent
from PySide6.QtWidgets import QListView, QVBoxLayout, QWidget

# Use a relative import to ensure we access the utils module within the
# ``multicam_editor`` package rather than relying on sys.path state.
from ..utils import file_utils
from ..utils.ffprobe import probe, ProbeResult


class FileListWidget(QWidget):
    """Media list with drag & drop, de-dup, and a hard video cap.

    Emits:
        filesAdded(list[str])
        videoCountChanged(int)
        currentPathChanged(str)
    """

    filesAdded = Signal(list)
    videoCountChanged = Signal(int)
    currentPathChanged = Signal(str)
    # Signals for removal - MainWindow handles Project sync via RemoveClipsCommand
    removalRequested = Signal(str)  # path to remove
    removeAllRequested = Signal()   # remove all videos

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self._view = QListView(self)
        self._view.setModel(self._model)
        self._view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._view.setUniformItemSizes(True)
        self._view.selectionModel().currentChanged.connect(self._on_current_changed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)

        # State
        self._path_set: set[str] = set()
        self._video_count: int = 0
        self._cap: int | None = None  # set by MainWindow; None = unlimited
        self._sync_status: dict[str, bool] = {}  # path -> synced (True=🟢, False=🔴)
        self._sync_mode_enabled: bool = False  # Only show sync dots when enabled

        # DnD
        self.setAcceptDrops(True)

    # ------------------------ Public API ------------------------
    def set_video_cap(self, cap: int | None) -> None:
        self._cap = cap

    def set_sync_mode_enabled(self, enabled: bool) -> None:
        """Enable/disable sync status indicators in the file list.
        
        When disabled, no sync dots appear next to files.
        When enabled, sync status dots (🔴/🟢) are shown.
        """
        if self._sync_mode_enabled == enabled:
            return
        self._sync_mode_enabled = enabled
        # Refresh all items to show/hide sync indicators
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item:
                path = item.data(Qt.ItemDataRole.UserRole)
                is_result = item.data(Qt.ItemDataRole.UserRole + 1)
                if path and not is_result:
                    base_text = item.data(Qt.ItemDataRole.UserRole + 2)
                    if base_text:
                        if enabled:
                            synced = self._sync_status.get(path, False)
                            indicator = "🟢" if synced else "🔴"
                            item.setText(f"{indicator} {base_text}")
                        else:
                            item.setText(base_text)

    def is_sync_mode_enabled(self) -> bool:
        """Return whether sync mode is currently enabled."""
        return self._sync_mode_enabled

    def add_files(
        self, paths: List[str], *, cap_remaining: int | None = None
    ) -> tuple[list[str], list[str], list[str]]:
        """Add files with type filter, de-dup, and optional cap.
        Returns: (added, skipped_duplicates, skipped_not_video)
        """
        added: list[str] = []
        skipped_dup: list[str] = []
        skipped_not_video: list[str] = []

        videos, non_videos = file_utils.split_by_type(paths)
        skipped_not_video.extend(non_videos)

        remaining = (
            cap_remaining
            if cap_remaining is not None
            else (max(0, (self._cap or 1_000_000) - self._video_count))
        )

        for p in videos:
            if remaining <= 0:
                break
            if p in self._path_set:
                skipped_dup.append(p)
                continue
            self._append_item(p)
            added.append(p)
            remaining -= 1

        if added:
            self.filesAdded.emit(added)
            self.videoCountChanged.emit(self._video_count)
        return added, skipped_dup, skipped_not_video

    def video_count(self) -> int:
        return self._video_count

    def all_paths(self) -> list[str]:
        paths: list[str] = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item is not None:
                p = item.data(Qt.ItemDataRole.UserRole)
                if p:
                    paths.append(p)
        return paths

    def set_sync_status(self, path: str, synced: bool) -> None:
        """Update sync status indicator for a file (🔴 not synced → 🟢 synced)."""
        if path not in self._path_set:
            return
        
        self._sync_status[path] = synced
        indicator = "🟢" if synced else "🔴"
        
        # Find and update the item
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                # Get base text (without indicator)
                base_text = item.data(Qt.ItemDataRole.UserRole + 2)
                if base_text:
                    item.setText(f"{indicator} {base_text}")
                break

    def set_all_synced(self, synced: bool = True) -> None:
        """Update sync status for all files at once."""
        for path in self._path_set:
            self.set_sync_status(path, synced)

    def all_synced(self) -> bool:
        """Return True if all files have been synced."""
        if not self._sync_status:
            return False
        return all(self._sync_status.values())

    def reorder_to_paths(self, new_order: list[str]) -> None:
        """Rebuild the list to match new_order; ignores paths not present.
        (Why) Keep list ↔ timeline in sync until model is added (Prompt 3a).
        """
        if not new_order:
            return
        current = set(self._path_set)
        filtered = [p for p in new_order if p in current]
        if not filtered:
            return
        self._model.removeRows(0, self._model.rowCount())
        self._path_set.clear()
        self._video_count = 0
        for p in filtered:
            self._append_item(p)
        self.videoCountChanged.emit(self._video_count)

    def sync_from_paths(self, paths: list[str]) -> None:
        """Rebuild the list to exactly match given paths (for undo/redo sync).

        Unlike reorder_to_paths, this allows adding new paths not currently present.
        """
        self._model.removeRows(0, self._model.rowCount())
        self._path_set.clear()
        self._video_count = 0
        for p in paths:
            self._append_item(p)
        self.videoCountChanged.emit(self._video_count)

    def selected_path(self) -> str | None:
        idx: QModelIndex = self._view.currentIndex()
        if not idx.isValid():
            return None
        item = self._model.itemFromIndex(idx)
        return item.data(Qt.ItemDataRole.UserRole)

    def select_path(self, path: str) -> None:
        """Programmatically select the row for `path` and focus it."""
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item is None:
                continue
            if item.data(Qt.ItemDataRole.UserRole) == path:
                idx = item.index()
                self._view.setCurrentIndex(idx)
                self._view.scrollTo(idx)
                return

    def add_result_file(self, path: str, label: str = "🎬 Final Output") -> None:
        """Add a result file to the list without counting against video cap.

        This is used for auto-loading exported/merged videos for preview
        without affecting the 10-video import limit.

        Args:
            path: Absolute path to the result video file
            label: Display label prefix (default: "🎬 Final Output")
        """
        if not path or path in self._path_set:
            return

        base = file_utils.safe_basename(path)
        display_text = f"{label}: {base}"

        # Probe for metadata
        result = probe(path)
        if not result.error and result.duration_ms > 0:
            secs = result.duration_ms // 1000
            mins, secs = divmod(secs, 60)
            display_text = f"{label}: {base}  [{mins}:{secs:02d}]"

        item = QStandardItem(display_text)
        item.setEditable(False)
        item.setToolTip(f"Result: {path}")
        item.setData(path, Qt.ItemDataRole.UserRole)
        # Mark as result (non-counting) via a custom role
        item.setData(True, Qt.ItemDataRole.UserRole + 1)
        self._model.appendRow(item)
        self._path_set.add(path)
        # Note: _video_count NOT incremented - this doesn't count against cap

    # ------------------------ Drag & Drop ------------------------
    def dragEnterEvent(self, e):  # type: ignore[override]
        if self._has_supported_urls(e.mimeData()):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):  # type: ignore[override]
        if self._has_supported_urls(e.mimeData()):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):  # type: ignore[override]
        urls = [u.toLocalFile() for u in e.mimeData().urls()] if e.mimeData().hasUrls() else []
        if not urls:
            e.ignore()
            return
        normed = file_utils.normalize_paths(urls)
        remaining = None
        if self._cap is not None:
            remaining = max(0, self._cap - self._video_count)
        self.add_files(normed, cap_remaining=remaining)
        e.acceptProposedAction()

    # ------------------------ Internals ------------------------
    def _append_item(self, abs_path: str) -> None:
        base = file_utils.safe_basename(abs_path)
        display_text = base

        # Probe for metadata (cached, fast on repeat)
        result = probe(abs_path)
        if result.error:
            # Bad file - show error indicator but still add
            display_text = f"{base}  [Error: {result.error[:30]}]"
            tooltip = f"{abs_path}\n\nError: {result.error}"
        else:
            # Build metadata string: duration, resolution, fps
            parts = []
            if result.duration_ms > 0:
                secs = result.duration_ms // 1000
                mins, secs = divmod(secs, 60)
                parts.append(f"{mins}:{secs:02d}")
            if result.resolution_str():
                parts.append(result.resolution_str())
            if result.fps:
                parts.append(f"{result.fps:.0f}fps")

            if parts:
                display_text = f"{base}  [{' | '.join(parts)}]"
            tooltip = abs_path
            if result.video_codec:
                tooltip += f"\nCodec: {result.video_codec}"
            if result.audio_codec:
                tooltip += f" / {result.audio_codec}"

        # Only show sync indicator if sync mode is enabled
        if self._sync_mode_enabled:
            sync_indicator = "🔴"  # Not synced initially
            display_with_status = f"{sync_indicator} {display_text}"
        else:
            display_with_status = display_text

        item = QStandardItem(display_with_status)
        item.setEditable(False)
        item.setToolTip(tooltip)
        item.setData(abs_path, Qt.ItemDataRole.UserRole)
        item.setData(display_text, Qt.ItemDataRole.UserRole + 2)  # Store base text
        self._model.appendRow(item)
        self._path_set.add(abs_path)
        self._sync_status[abs_path] = False  # Not synced initially
        self._video_count += 1

    @staticmethod
    def _has_supported_urls(m: QMimeData) -> bool:
        if not m.hasUrls():
            return False
        for u in m.urls():
            if not u.isLocalFile():
                continue
            if file_utils.is_video(u.toLocalFile()):
                return True
        return False

    def _on_current_changed(self, cur: QModelIndex, _prev: QModelIndex) -> None:
        if cur.isValid():
            item = self._model.itemFromIndex(cur)
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                self.currentPathChanged.emit(path)

    # ------------------------ Keyboard Events ------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Delete/Backspace to remove selected items."""
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_selected()
            event.accept()
        else:
            super().keyPressEvent(event)

    def remove_selected(self) -> bool:
        """Request removal of selected item via signal.

        MainWindow handles the actual removal via RemoveClipsCommand
        to ensure Project model stays in sync with undo support.

        Returns True if a removal was requested, False if nothing selected.
        """
        idx = self._view.currentIndex()
        if not idx.isValid():
            return False

        item = self._model.itemFromIndex(idx)
        if item is None:
            return False

        path = item.data(Qt.ItemDataRole.UserRole)
        is_result = item.data(Qt.ItemDataRole.UserRole + 1)

        if not path:
            return False

        # Result files can be removed directly (not in Project)
        if is_result:
            self._do_remove_path(path)
            return True

        # Emit signal for MainWindow to handle via RemoveClipsCommand
        self.removalRequested.emit(path)
        return True

    def remove_all(self) -> None:
        """Request removal of all videos via signal.

        MainWindow handles via RemoveClipsCommand for proper undo support.
        Result files are excluded from Project removal.
        """
        self.removeAllRequested.emit()

    def _do_remove_path(self, path: str) -> bool:
        """Internal: Actually remove a path from the UI.

        Called by MainWindow after Project sync, or directly for result files.
        Returns True if removed, False if not found.
        """
        if path not in self._path_set:
            return False

        # Find and remove the item
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                is_result = item.data(Qt.ItemDataRole.UserRole + 1)
                self._model.removeRow(row)
                self._path_set.discard(path)
                if not is_result:
                    self._video_count = max(0, self._video_count - 1)
                    self.videoCountChanged.emit(self._video_count)

                # Select next item
                new_count = self._model.rowCount()
                if new_count > 0:
                    new_row = min(row, new_count - 1)
                    self._view.setCurrentIndex(self._model.index(new_row, 0))
                return True
        return False

    def get_all_video_paths(self) -> list[str]:
        """Return paths of all non-result videos in the list."""
        paths: list[str] = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item is not None:
                is_result = item.data(Qt.ItemDataRole.UserRole + 1)
                if not is_result:
                    p = item.data(Qt.ItemDataRole.UserRole)
                    if p:
                        paths.append(p)
        return paths
