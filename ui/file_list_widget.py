# file: ui/file_list_widget.py
from __future__ import annotations
import os
from typing import List, Tuple
from PyQt6.QtCore import pyqtSignal, Qt, QModelIndex, QMimeData
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import QWidget, QListView, QVBoxLayout

from utils import file_utils


class FileListWidget(QWidget):
    """List of media files with drag-and-drop and de-dup.

    Emits:
        - filesAdded(list[str]): absolute paths that were added (videos only in Prompt 1)
        - videoCountChanged(int): number of video items currently in the list
        - currentPathChanged(str): path of the newly selected item
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
        self._view.selectionModel().currentChanged.connect(self._on_current_changed)
        self._view.setUniformItemSizes(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)

        # DnD
        self.setAcceptDrops(True)

        # State
        self._path_set: set[str] = set()
        self._video_count: int = 0

    # --- Public API ---
    def add_files(self, paths: List[str], *, cap_remaining: int | None = None) -> Tuple[List[str], List[str], List[str]]:
        """Add files to the list.
        Returns (added, skipped_duplicates, skipped_not_video).
        If cap_remaining is provided, at most that many **videos** will be added.
        """
        added: List[str] = []
        skipped_dup: List[str] = []
        skipped_not_video: List[str] = []

        videos, non_videos = file_utils.split_by_type(paths)
        skipped_not_video.extend(non_videos)

        remaining = cap_remaining if cap_remaining is not None else len(videos)
        for p in videos:
            if p in self._path_set:
                skipped_dup.append(p)
                continue
            if remaining <= 0:
                break
            self._append_item(p)
            added.append(p)
            remaining -= 1

        if added:
            self.filesAdded.emit(added)
            self.videoCountChanged.emit(self._video_count)
        return added, skipped_dup, skipped_not_video

    def video_count(self) -> int:
        return self._video_count

    def selected_path(self) -> str | None:
        idx: QModelIndex = self._view.currentIndex()
        if not idx.isValid():
            return None
        item = self._model.itemFromIndex(idx)
        return item.data(Qt.ItemDataRole.UserRole)

    # --- DnD ---
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
        # Caller (MainWindow) will handle cap; here we add without cap
        self.add_files(normed)
        e.acceptProposedAction()

    # --- Internal ---
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