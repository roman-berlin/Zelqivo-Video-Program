from __future__ import annotations
import os
from typing import List

from PyQt6.QtCore import Qt, QSettings, QTimer
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
from ui.trim_panel import TrimPanel
from ui.timeline.timeline import TimelineScene, TimelineView
from ui.timeline.adapter import TimelineAdapter
from logic.project_state import Project

VIDEO_CAP = 10


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MultiCamEditor")
        self.resize(1280, 800)
        self.settings = QSettings("MultiCamEditor", "MultiCamEditor")
        self.project = Project(max_videos=VIDEO_CAP)
        self._current_path: str | None = None

        self._init_ui()
        self._connect_signals()
        self._refresh_counter()

    # --- UI setup ---
    def _init_ui(self) -> None:
        central = QWidget(self)
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)

        # Left: file list + controls
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

        # Right: preview + trim panel + timeline
        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        lbl_prev = QLabel("Preview", right)
        lbl_prev.setObjectName("lblPreview")
        self.preview = VideoPreview(right)
        self.preview.setObjectName("videoPreview")
        right_layout.addWidget(lbl_prev)
        right_layout.addWidget(self.preview, 1)

        # Trim panel (read-only in 4.1)
        self.trim_panel = TrimPanel(right)
        right_layout.addWidget(self.trim_panel)

        line = QFrame(right)
        line.setFrameShape(QFrame.Shape.HLine)
        right_layout.addWidget(line)

        lbl_tl = QLabel("Timeline", right)
        lbl_tl.setObjectName("lblTimeline")
        right_layout.addWidget(lbl_tl)

        self.timeline_scene = TimelineScene(self)
        self.timeline_view = TimelineView(self.timeline_scene, right)
        self.timeline_view.setMinimumHeight(120)
        right_layout.addWidget(self.timeline_view, 0)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([420, 860])
        self.setCentralWidget(central)
        self.statusBar().showMessage("")

        # Adapter bridges model ↔ view
        self.timeline_adapter = TimelineAdapter(self.project, self.timeline_scene)
        # ensure timeline starts scrolled fully left
        QTimer.singleShot(0, self._scroll_timeline_left)

    # --- Signals ---
    def _connect_signals(self) -> None:
        # list → preview + select in scene
        self.file_list.currentPathChanged.connect(self.preview.set_source)
        self.file_list.currentPathChanged.connect(self.timeline_scene.select_by_path)
        self.file_list.currentPathChanged.connect(self._on_current_path_changed)

        # timeline selection → mirror to list (drives preview when clicking squares)
        if hasattr(self.timeline_scene, "selectionChanged"):
            self.timeline_scene.selectionChanged.connect(self._on_scene_selection_changed)

        # preview → TrimPanel population when duration becomes known
        if hasattr(self.preview, "durationKnown"):
            try:
                self.preview.durationKnown.connect(self._on_preview_duration_known)
            except Exception:
                pass

        # scene reorder → adapter
        if hasattr(self.timeline_scene, "requestReorder"):
            try:
                self.timeline_scene.requestReorder.connect(self.timeline_adapter.on_request_reorder)
            except Exception:
                pass

        # file list changes
        self.file_list.filesAdded.connect(self._on_files_added)
        self.file_list.videoCountChanged.connect(self._refresh_counter)

        # buttons
        self.btn_add.clicked.connect(self.on_add_files)

    # --- Actions ---
    def on_add_files(self) -> None:
        last_dir = self.settings.value("last_dir", os.path.expanduser("~"))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add video files", last_dir, file_utils.dialog_filter_videos()
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
        if skipped_dup:
            self._toast(f"Skipped {len(skipped_dup)} duplicate file(s).")
        if len(videos) > len(added) + len(skipped_dup):
            skipped_by_cap = len(videos) - len(added) - len(skipped_dup)
            if skipped_by_cap > 0:
                self._toast(f"Reached 10-video cap. Skipped {skipped_by_cap} file(s).")
        self._refresh_counter()

    # --- Handlers ---
    def _on_files_added(self, paths: List[str]) -> None:
        if not paths:
            return
        self.settings.setValue("last_dir", os.path.dirname(paths[-1]))
        _actually_added = self.timeline_adapter.add_paths(paths)
        self._refresh_counter()
        # keep the view anchored to the left after adding clips
        QTimer.singleShot(0, self._scroll_timeline_left)

    def _on_scene_selection_changed(self) -> None:
        """Mirror timeline selection to file list to drive preview.
        Why: selecting in the list emits currentPathChanged → preview.set_source.
        """
        sel = self.timeline_scene.selectedItems()
        if not sel:
            return
        item = sel[0]
        path = getattr(item, "path", None)
        if path:
            self.file_list.select_path(path)

    # --- Helpers ---
    def _refresh_counter(self, *_args) -> None:
        count = self.file_list.video_count()
        self.lbl_counter.setText(f"Videos: {count}/{VIDEO_CAP}")
        self.btn_add.setEnabled(count < VIDEO_CAP)

    def _toast(self, message: str, timeout_ms: int = 4000) -> None:
        self.statusBar().showMessage(message, timeout_ms)

    def _scroll_timeline_left(self) -> None:
        """Anchor timeline view to the far left (after layout/scene updates)."""
        try:
            hbar = self.timeline_view.horizontalScrollBar()
            if hbar is not None:
                hbar.setValue(hbar.minimum())
        except Exception:
            pass

    # --- TrimPanel wiring ---
    def _on_current_path_changed(self, path: str) -> None:
        self._current_path = path
        # Immediate path display; duration/in/out fill when known
        if getattr(self, "trim_panel", None):
            try:
                self.trim_panel.load(path, 0, 0, 0)
            except Exception:
                pass

    def _on_preview_duration_known(self, duration_ms: int) -> None:
        path = self._current_path
        if not path:
            return
        in_ms = 0
        out_ms = int(duration_ms)
        try:
            for c in getattr(self.project.video, "clips", []):
                if getattr(c, "path", None) == path:
                    in_ms = int(getattr(c, "in_ms", 0) or 0)
                    out_val = getattr(c, "out_ms", None)
                    out_ms = int(out_val) if (out_val is not None and int(out_val) > 0) else int(duration_ms)
                    break
        except Exception:
            pass
        if hasattr(self, "trim_panel") and self.trim_panel is not None:
            self.trim_panel.load(path, int(duration_ms), int(in_ms), int(out_ms))
