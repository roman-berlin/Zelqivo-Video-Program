# file: ui/file_list_widget.py
from __future__ import annotations

import os
from typing import Iterable, List, Tuple

from PyQt6.QtCore import Qt, QModelIndex, QMimeData, pyqtSignal
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import QListView, QVBoxLayout, QWidget

# Use a relative import to ensure we access the utils module within the
# ``multicam_editor`` package rather than relying on sys.path state.
from ..utils import file_utils


class FileListWidget(QWidget):
    """Media list with drag & drop, de-dup, and a hard video cap.

    Emits:
        filesAdded(list[str])
        videoCountChanged(int)
        currentPathChanged(str)
    """

    filesAdded = pyqtSignal(list)
    videoCountChanged = pyqtSignal(int)
    currentPathChanged = pyqtSignal(str)

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

        # DnD
        self.setAcceptDrops(True)

    # ------------------------ Public API ------------------------
    def set_video_cap(self, cap: int | None) -> None:
        self._cap = cap

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
        item = QStandardItem(base)
        item.setEditable(False)
        item.setToolTip(abs_path)
        item.setData(abs_path, Qt.ItemDataRole.UserRole)
        self._model.appendRow(item)
        self._path_set.add(abs_path)
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