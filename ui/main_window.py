# file: ui/main_window.py
from __future__ import annotations

import os
from typing import List

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from utils import file_utils
from .file_list_widget import FileListWidget
from .video_preview import VideoPreview
from ui.timeline.timeline import TimelineScene, TimelineView

VIDEO_CAP = 10


class MainWindow(QMainWindow):
    """Main window wiring file list ↔ preview ↔ timeline, with a 10-video cap."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MultiCamEditor")
        self.resize(1280, 800)
        self.settings = QSettings("MultiCamEditor", "MultiCamEditor")
        self._init_ui()
        self._connect_signals()
        self._refresh_counter()

    # ------------------------ UI ------------------------
    def _init_ui(self) -> None:
        central = QWidget(self)
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)

        # Left column: controls + file list
        left = QWidget(splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

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
        self.file_list.set_video_cap(VIDEO_CAP)

        left_layout.addWidget(ctrl_row)
        left_layout.addWidget(lbl)
        left_layout.addWidget(self.file_list, 1)

        # Right column: preview + timeline
        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        lbl_prev = QLabel("Preview", right)
        lbl_prev.setObjectName("lblPreview")
        self.preview = VideoPreview(right)
        self.preview.setObjectName("videoPreview")
        right_layout.addWidget(lbl_prev)
        right_layout.addWidget(self.preview, 1)

        # Separator + timeline header
        line = QFrame(right)
        line.setFrameShape(QFrame.Shape.HLine)
        right_layout.addWidget(line)
        lbl_tl = QLabel("Timeline", right)
        lbl_tl.setObjectName("lblTimeline")
        right_layout.addWidget(lbl_tl)

        # Timeline widgets
        self.timeline_scene = TimelineScene(self)
        self.timeline_view = TimelineView(self.timeline_scene, right)
        self.timeline_view.setMinimumHeight(120)
        right_layout.addWidget(self.timeline_view, 0)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([420, 860])
        self.setCentralWidget(central)

        # Status bar for non-blocking notices
        self.statusBar().showMessage("")

    # ------------------------ Signals ------------------------
    def _connect_signals(self) -> None:
        # file list → preview & timeline
        self.file_list.currentPathChanged.connect(self.preview.set_source)
        self.file_list.currentPathChanged.connect(self.timeline_scene.select_by_path)

        # DnD/button add → central handler
        self.file_list.filesAdded.connect(self._on_files_added)
        self.file_list.videoCountChanged.connect(self._refresh_counter)

        # timeline → list reorder + click-to-play
        self.timeline_scene.orderChanged.connect(self._on_timeline_order_changed)
        self.timeline_scene.selectionChanged.connect(self._on_timeline_selection_changed)

        # controls
        self.btn_add.clicked.connect(self.on_add_files)

    # ------------------------ Actions ------------------------
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

        videos, _ = file_utils.split_by_type(files)
        if not videos:
            self._toast("No supported video files selected.")
            return

        remaining = max(0, VIDEO_CAP - self.file_list.video_count())
        if remaining <= 0:
            self._toast("Video limit reached (10/10). Remove some to add more.")
            return

        added, skipped_dup, _ = self.file_list.add_files(videos, cap_remaining=remaining)
        # NOTE: Do not add to timeline here. _on_files_added handles it via filesAdded signal.

        if skipped_dup:
            self._toast(f"Skipped {len(skipped_dup)} duplicate file(s).")
        if len(videos) > len(added) + len(skipped_dup):
            skipped_by_cap = len(videos) - len(added) - len(skipped_dup)
            if skipped_by_cap > 0:
                self._toast(f"Reached 10-video cap. Skipped {skipped_by_cap} file(s).")

        self._refresh_counter()

    # ------------------------ Handlers ------------------------
    def _on_files_added(self, paths: List[str]) -> None:
        if not paths:
            return
        # Persist last dir and mirror into timeline once (fixes duplicate add)
        self.settings.setValue("last_dir", os.path.dirname(paths[-1]))
        titles = [os.path.basename(p) for p in paths]
        self.timeline_scene.add_clips(paths, titles, cap=VIDEO_CAP)
        self._refresh_counter()

    def _on_timeline_order_changed(self, ordered_paths: list[str]) -> None:
        self.file_list.reorder_to_paths(ordered_paths)

    def _on_timeline_selection_changed(self) -> None:
        # Click-to-play: selecting a clip selects the corresponding list row → updates preview
        sel = self.timeline_scene.selectedItems()
        if not sel:
            return
        item = sel[0]
        path = getattr(item, "path", None)
        if path:
            self.file_list.select_path(path)
            # currentPathChanged will trigger preview + timeline highlight

    # ------------------------ Helpers ------------------------
    def _refresh_counter(self, *_args) -> None:
        count = self.file_list.video_count()
        self.lbl_counter.setText(f"Videos: {count}/{VIDEO_CAP}")
        self.btn_add.setEnabled(count < VIDEO_CAP)

    def _toast(self, message: str, timeout_ms: int = 4000) -> None:
        self.statusBar().showMessage(message, timeout_ms)