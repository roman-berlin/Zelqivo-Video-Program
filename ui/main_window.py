from __future__ import annotations
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QSplitter,
)

from .file_list_widget import FileListWidget
from .video_preview import VideoPreview


class MainWindow(QMainWindow):
    """Bootstrap wiring only: file list ↔ preview."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MultiCamEditor")
        self.resize(1200, 720)
        self._init_ui()
        self._connect_signals()

    # --- UI
    def _init_ui(self) -> None:
        central = QWidget(self)
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)

        # Left: File list
        left = QWidget(splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("Media Files", left)
        lbl.setObjectName("lblMediaFiles")
        self.file_list = FileListWidget(left)
        self.file_list.setObjectName("fileList")
        left_layout.addWidget(lbl)
        left_layout.addWidget(self.file_list, 1)

        # Right: Preview
        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        lbl_prev = QLabel("Preview", right)
        lbl_prev.setObjectName("lblPreview")
        self.preview = VideoPreview(right)
        self.preview.setObjectName("videoPreview")
        right_layout.addWidget(lbl_prev)
        right_layout.addWidget(self.preview, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([380, 820])

        self.setCentralWidget(central)

    # --- Signals
    def _connect_signals(self) -> None:
        self.file_list.currentPathChanged.connect(self.preview.set_source)