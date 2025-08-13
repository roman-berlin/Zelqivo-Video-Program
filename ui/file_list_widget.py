# file: ui/file_list_widget.py
from __future__ import annotations
import os
from typing import List
from PyQt6.QtCore import pyqtSignal, QModelIndex
from PyQt6.QtWidgets import QWidget, QListView, QVBoxLayout
from PyQt6.QtGui import QStandardItemModel, QStandardItem


class FileListWidget(QWidget):
    """Minimal list that emits selected path; DnD/buttons arrive in later prompts."""

    currentPathChanged = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self._view = QListView(self)
        self._view.setModel(self._model)
        self._view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._view.selectionModel().currentChanged.connect(self._on_current_changed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)

    # --- Public API used by MainWindow/tests ---
    def add_paths_bootstrap(self, paths: List[str]) -> None:
        """Temporary helper for bootstrap/testing only.
        Real add/drag/drop arrives in Prompt 1.
        """
        for p in paths:
            item = QStandardItem(os.path.basename(p))
            item.setData(p)  # store full path in item data
            self._model.appendRow(item)

    def selected_path(self) -> str | None:
        idx: QModelIndex = self._view.currentIndex()
        if not idx.isValid():
            return None
        item = self._model.itemFromIndex(idx)
        return item.data()

    # --- Internal ---
    def _on_current_changed(self, cur: QModelIndex, _prev: QModelIndex) -> None:
        path = None
        if cur.isValid():
            item = self._model.itemFromIndex(cur)
            path = item.data()
        if path:
            self.currentPathChanged.emit(path)