# file: ui/main_window.py
from __future__ import annotations
import os
from typing import List
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QSplitter,
    QPushButton,
    QFileDialog,
)

from utils import file_utils
from .file_list_widget import FileListWidget
from .video_preview import VideoPreview

VIDEO_CAP = 10


class MainWindow(QMainWindow):
    """Wires FileList ↔ Preview and adds Prompt 1 controls (Add button, counter, cap)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MultiCamEditor")
        self.resize(1200, 720)
        self.settings = QSettings("MultiCamEditor", "MultiCamEditor")
        self._init_ui()
        self._connect_signals()
        self._refresh_counter()

    # --- UI
    def _init_ui(self) -> None:
        central = QWidget(self)
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)

        # Left: File list and controls
        left = QWidget(splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Controls row
        ctrl_row = QWidget(left)
        ctrl_lay = QHBoxLayout(ctrl_row)
        ctrl_lay.setContentsMargins(0, 0, 0, 0)
        self.btn_add = QPushButton("Add Files…", ctrl_row)
        self.btn_add.setObjectName("btnAddFiles")
        self.lbl_counter = QLabel("Videos: 0/10", ctrl_row)
        self.lbl_counter.setObjectName("lblCounter")
        ctrl_lay.addWidget(self.btn_add)
        ctrl_lay.addStretch(1)
        ctrl_lay.addWidget(self.lbl_counter)

        lbl = QLabel("Media Files", left)
        lbl.setObjectName("lblMediaFiles")
        self.file_list = FileListWidget(left)
        self.file_list.setObjectName("fileList")

        left_layout.addWidget(ctrl_row)
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
        splitter.setSizes([420, 780])
        self.setCentralWidget(central)

        # Status bar for non-blocking notices
        self.statusBar().showMessage("")

    # --- Signals
    def _connect_signals(self) -> None:
        self.file_list.currentPathChanged.connect(self.preview.set_source)
        self.file_list.filesAdded.connect(self._on_files_added)
        self.file_list.videoCountChanged.connect(self._refresh_counter)
        self.btn_add.clicked.connect(self.on_add_files)

    # --- Actions
    def on_add_files(self) -> None:
        last_dir = self.settings.value("last_dir", os.path.expanduser("~"))
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add video files",
            last_dir,
            file_utils.dialog_filter_videos(),
        )
        if not files:
            return

        videos, _non_videos = file_utils.split_by_type(files)  # filter strictly to videos
        if not videos:
            self._toast("No supported video files selected.")
            return

        remaining = max(0, VIDEO_CAP - self.file_list.video_count())
        if remaining <= 0:
            self._toast("Video limit reached (10/10). Remove some to add more.")
            return

        added, skipped_dup, _skipped_not_video = self.file_list.add_files(
            videos, cap_remaining=remaining
        )

        if added:
            # Persist the directory of the last added file
            self.settings.setValue("last_dir", os.path.dirname(added[-1]))

        # Notices
        if skipped_dup:
            self._toast(f"Skipped {len(skipped_dup)} duplicate file(s).")
        if len(videos) > len(added) + len(skipped_dup):
            skipped_by_cap = len(videos) - len(added) - len(skipped_dup)
            if skipped_by_cap > 0:
                self._toast(f"Reached 10-video cap. Skipped {skipped_by_cap} file(s).")

        self._refresh_counter()

    # --- Helpers
    def _refresh_counter(self, *_args) -> None:
        count = self.file_list.video_count()
        self.lbl_counter.setText(f"Videos: {count}/{VIDEO_CAP}")
        self.btn_add.setEnabled(count < VIDEO_CAP)

    def _on_files_added(self, paths: List[str]) -> None:
        if paths:
            self.settings.setValue("last_dir", os.path.dirname(paths[-1]))
        self._refresh_counter()

    def _toast(self, message: str, timeout_ms: int = 4000) -> None:
        # Non-blocking, auto-clearing status message
        self.statusBar().showMessage(message, timeout_ms)