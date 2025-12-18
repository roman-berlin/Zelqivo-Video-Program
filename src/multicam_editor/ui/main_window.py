# file: ui/main_window.py
from __future__ import annotations
import logging
import os
from typing import List

from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QUndoStack
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Import helpers from the package's utils module.  Use a relative import to
# ensure the correct package context when this module is executed as part of
# ``multicam_editor.ui``.
from ..utils import file_utils
from .file_list_widget import FileListWidget
from .video_preview import VideoPreview
# Import internal components using relative imports to avoid relying on sys.path
from .trim_panel import TrimPanel
from .timeline.timeline import TimelineScene, TimelineView
from .timeline.adapter import TimelineAdapter
# Use the core project implementation for clip management and splitting.
from ..core.project import Project
# Import undo/redo commands
from ..logic.commands import AddClipsCommand, ReorderClipsCommand, TrimCommand


VIDEO_CAP = 10


class MainWindow(QMainWindow):
    """Main window: file list, preview + trim panel, and timeline."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MultiCamEditor")
        self.resize(1280, 800)
        self.settings = QSettings("MultiCamEditor", "MultiCamEditor")
        # Instantiate the core Project used by the timeline and trim panel.
        # Video cap is enforced at the FileListWidget level.
        self.project = Project()
        self._current_path: str | None = None

        # Initialize undo/redo stack
        self.undo_stack = QUndoStack(self)

        self._init_ui()
        self._init_undo_toolbar()
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

        # Trim panel
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

        # Adapter bridges model ↔ view (pass view so adapter can fit/scroll)
        self.timeline_adapter = TimelineAdapter(
            self.project,
            self.timeline_scene,
            self.timeline_view,
            undo_stack=self.undo_stack,
            refresh_callback=self._refresh_after_undo_redo
        )

        # Bind context for the TrimPanel so splitting works correctly.  Pass
        # the file list as well so that physical splits can be added back
        # into the left panel when ``split_video`` is invoked.  This wiring
        # is done here after the adapter, preview and file list widgets exist.
        self.trim_panel.bind_context(
            self.project,
            self.timeline_adapter,
            self.preview,
            self._toast,  # status_sink for displaying error messages
            self.file_list,
            self.undo_stack  # for undoable operations
        )

        # Ensure timeline starts scrolled fully left
        QTimer.singleShot(0, self._scroll_timeline_left)

    def _init_undo_toolbar(self) -> None:
        """Initialize undo/redo toolbar with actions and keyboard shortcuts."""
        toolbar = QToolBar("Edit", self)
        toolbar.setObjectName("editToolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        # Create undo action with Ctrl+Z shortcut
        self.action_undo = self.undo_stack.createUndoAction(self, "Undo")
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)  # Ctrl+Z
        self.action_undo.setObjectName("actionUndo")
        toolbar.addAction(self.action_undo)

        # Create redo action with Ctrl+Y (and Ctrl+Shift+Z)
        self.action_redo = self.undo_stack.createRedoAction(self, "Redo")
        self.action_redo.setShortcuts([
            QKeySequence.StandardKey.Redo,  # Ctrl+Y or Ctrl+Shift+Z depending on platform
            QKeySequence("Ctrl+Y")  # Explicit Ctrl+Y
        ])
        self.action_redo.setObjectName("actionRedo")
        toolbar.addAction(self.action_redo)

        # Actions are automatically disabled when stack is empty
        # and enabled when operations are available

    # --- Signals ---
    def _connect_signals(self) -> None:
        # list → preview + select in scene + remember current path
        self.file_list.currentPathChanged.connect(self.preview.set_source)
        self.file_list.currentPathChanged.connect(self.timeline_scene.select_by_path)
        self.file_list.currentPathChanged.connect(self._on_current_path_changed)

        # TrimPanel → persist trims in model, refresh overlay
        if getattr(self, "trim_panel", None):
            try:
                self.trim_panel.trimChanged.connect(self._on_trim_changed)
            except Exception:
                logger.warning("Failed to connect trim_panel.trimChanged signal", exc_info=True)

        # timeline selection → mirror to list (keeps preview in sync when clicking squares)
        if hasattr(self.timeline_scene, "selectionChanged"):
            self.timeline_scene.selectionChanged.connect(self._on_scene_selection_changed)

        # timeline clip activation (double‑click) → mirror to list and play
        if hasattr(self.timeline_scene, "clipActivated"):
            try:
                self.timeline_scene.clipActivated.connect(self._on_clip_activated)
            except Exception:
                logger.warning("Failed to connect timeline_scene.clipActivated signal", exc_info=True)

        # preview → when duration becomes known, load TrimPanel & overlay
        if hasattr(self.preview, "durationKnown"):
            try:
                self.preview.durationKnown.connect(self._on_preview_duration_known)
            except Exception:
                logger.warning("Failed to connect preview.durationKnown signal", exc_info=True)

        # scene reorder → adapter (only if your scene exposes this)
        if hasattr(self.timeline_scene, "requestReorder"):
            try:
                self.timeline_scene.requestReorder.connect(self.timeline_adapter.on_request_reorder)
            except Exception:
                logger.warning("Failed to connect timeline_scene.requestReorder signal", exc_info=True)

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

        # Use AddClipsCommand for undoable add operation
        cmd = AddClipsCommand(
            self.project,
            paths,
            refresh_callback=self._refresh_after_undo_redo
        )
        self.undo_stack.push(cmd)

        # keep the view anchored to the left after adding clips
        QTimer.singleShot(0, self._scroll_timeline_left)

    def _on_scene_selection_changed(self) -> None:
        """Mirror timeline selection to file list to drive preview."""
        sel = self.timeline_scene.selectedItems()
        if not sel:
            return
        item = sel[0]
        # Timeline items store a composite key in `.path` but the original source
        # path in `.source_path`.  Use the raw source path for file list selection
        # so that currentPathChanged emits and the preview loads.
        path = None
        if hasattr(item, "source_path"):
            path = getattr(item, "source_path", None)
        if not path:
            path = getattr(item, "path", None)
        if path:
            # This emits currentPathChanged → preview + trim panel load
            self.file_list.select_path(path)

    def _on_clip_activated(self, key: str) -> None:
        """Play the clip associated with the given timeline key.

        The key has the format "path|in-out|index".  We extract the source path
        (the part before the first pipe) and select it in the file list.  This
        emits currentPathChanged, causing the preview to load and play the video.
        """
        try:
            if not key:
                return
            # Extract the source path from the composite key
            path = key.split("|", 1)[0]
            if path:
                self.file_list.select_path(path)
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
        """Preview told us the duration of current _current_path."""
        path = getattr(self, "_current_path", None)
        if not path:
            return
        # model update + panel load + timeline overlay refresh
        try:
            self.project.set_duration_by_path(path, duration_ms)
        except Exception:
            logger.error(f"Failed to set duration for {path}", exc_info=True)
        in_ms, out_ms = self.project.get_trim_by_path(path)
        if hasattr(self, "trim_panel") and self.trim_panel is not None:
            self.trim_panel.load(path, int(duration_ms), int(in_ms), int(out_ms))
        if hasattr(self, "timeline_adapter"):
            try:
                self.timeline_adapter.update_trim_for_path(path)
            except Exception:
                logger.debug(f"Failed to update timeline trim for {path}", exc_info=True)

    def _on_trim_changed(self, path: str, in_ms: int, out_ms: int) -> None:
        """Persist trim in model and refresh timeline overlay using undoable command."""
        # Get old values before creating command
        old_in, old_out = self.project.get_trim_by_path(path)

        # Create and push trim command (automatically coalesces with previous trims)
        cmd = TrimCommand(
            self.project,
            path,
            old_in, old_out,
            in_ms, out_ms,
            refresh_callback=lambda: self.timeline_adapter.update_trim_for_path(path) if hasattr(self, "timeline_adapter") else None
        )
        self.undo_stack.push(cmd)

    # --- Helpers ---
    def _refresh_after_undo_redo(self) -> None:
        """Refresh UI after undo/redo operations.

        This callback is passed to undo commands to ensure timeline, file list,
        and counter all reflect the current Project state after add/remove.
        """
        # Refresh timeline from project
        if hasattr(self, "timeline_adapter"):
            self.timeline_adapter.refresh_from_project()

        # Sync file list with project clips
        clips = self.project.clips()
        if hasattr(self, "file_list"):
            try:
                self.file_list.clear()
                for clip in clips:
                    self.file_list.addItem(clip.display_title())
            except Exception:
                logger.debug("Failed to sync file list with project", exc_info=True)

        # Update counter and button state
        self._refresh_counter()

    def _refresh_counter(self, *_args) -> None:
        count = self.file_list.video_count()
        self.lbl_counter.setText(f"Videos: {count}/{VIDEO_CAP}")
        self.btn_add.setEnabled(count < VIDEO_CAP)

    def _toast(self, message: str, timeout_ms: int = 4000) -> None:
        self.statusBar().showMessage(message, timeout_ms)

    def _scroll_timeline_left(self) -> None:
        """Anchor timeline view to the far left after layout/scene updates."""
        try:
            hbar = self.timeline_view.horizontalScrollBar()
            if hbar is not None:
                hbar.setValue(hbar.minimum())
        except Exception:
            pass
