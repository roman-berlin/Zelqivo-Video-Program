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
from .settings_dialog import SettingsDialog
from .export_dialog import ExportDialog
from .theme import apply_theme
# Import internal components using relative imports to avoid relying on sys.path
from .trim_panel import TrimPanel
from .timeline.timeline import TimelineScene, TimelineView
from .timeline.adapter import TimelineAdapter
# Use the core project implementation for clip management and splitting.
from ..core.project import Project
# Import undo/redo commands
from ..logic.commands import AddClipsCommand, ReorderClipsCommand, TrimCommand
from ..logic.processing_worker import ProcessingThread
from .progress_dialog import ProcessingProgressDialog


VIDEO_CAP = 10
MIN_VIDEOS_FOR_PROCESS = 2


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
        self._init_menu()
        self._connect_signals()
        self._refresh_counter()

        # Apply saved theme on startup
        self._apply_startup_theme()

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
        self.btn_add.setToolTip("Add video files (up to 10)")
        self.btn_process = QPushButton("Process", ctrl_row)
        self.btn_process.setObjectName("btnProcess")
        self.btn_process.setEnabled(False)  # Enabled when >=2 videos
        self.btn_process.setToolTip("Process videos with auto-switching (requires 2+ videos)")
        self.lbl_counter = QLabel("Videos: 0/10", ctrl_row)
        self.lbl_counter.setObjectName("lblCounter")
        ctrl_lay.addWidget(self.btn_add)
        ctrl_lay.addWidget(self.btn_process)
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

        # A/B comparison preview header with toggle
        preview_header = QWidget(right)
        preview_header_layout = QHBoxLayout(preview_header)
        preview_header_layout.setContentsMargins(0, 0, 0, 0)

        lbl_prev = QLabel("Preview", preview_header)
        lbl_prev.setObjectName("lblPreview")
        preview_header_layout.addWidget(lbl_prev)
        preview_header_layout.addStretch(1)

        self.btn_toggle_ab = QPushButton("A/B Compare", preview_header)
        self.btn_toggle_ab.setObjectName("btnToggleAB")
        self.btn_toggle_ab.setCheckable(True)
        self.btn_toggle_ab.setChecked(False)
        self.btn_toggle_ab.setToolTip("Compare original vs auto-switched result side-by-side")
        self.btn_toggle_ab.clicked.connect(self._toggle_ab_mode)
        preview_header_layout.addWidget(self.btn_toggle_ab)

        right_layout.addWidget(preview_header)

        # Preview container (single or dual)
        self.preview_container = QWidget(right)
        self.preview_layout = QHBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_layout.setSpacing(4)

        # Primary preview (A - original)
        preview_a_widget = QWidget(self.preview_container)
        preview_a_layout = QVBoxLayout(preview_a_widget)
        preview_a_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_preview_a = QLabel("Original", preview_a_widget)
        self.lbl_preview_a.setObjectName("lblPreviewA")
        self.lbl_preview_a.setVisible(False)
        preview_a_layout.addWidget(self.lbl_preview_a)

        self.preview = VideoPreview(preview_a_widget)
        self.preview.setObjectName("videoPreview")
        preview_a_layout.addWidget(self.preview, 1)
        self.preview_layout.addWidget(preview_a_widget, 1)

        # Secondary preview (B - auto-switch result)
        preview_b_widget = QWidget(self.preview_container)
        preview_b_layout = QVBoxLayout(preview_b_widget)
        preview_b_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_preview_b = QLabel("Auto-Switch", preview_b_widget)
        self.lbl_preview_b.setObjectName("lblPreviewB")
        preview_b_layout.addWidget(self.lbl_preview_b)

        self.preview_b = VideoPreview(preview_b_widget)
        self.preview_b.setObjectName("videoPreviewB")
        preview_b_layout.addWidget(self.preview_b, 1)
        self.preview_layout.addWidget(preview_b_widget, 1)

        # Start with B hidden
        preview_b_widget.setVisible(False)
        self._ab_mode = False
        self._result_path: str | None = None

        right_layout.addWidget(self.preview_container, 1)

        # Sync timer for A/B playheads (50ms interval)
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(50)
        self._sync_timer.timeout.connect(self._sync_playheads)

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

    def _init_menu(self) -> None:
        """Initialize menu bar with File and View menus."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        # Export action
        self.action_export = QAction("&Export...", self)
        self.action_export.setObjectName("actionExport")
        self.action_export.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export.setEnabled(False)  # Enabled after processing
        self.action_export.triggered.connect(self._show_export_dialog)
        file_menu.addAction(self.action_export)

        file_menu.addSeparator()

        settings_action = QAction("&Settings...", self)
        settings_action.triggered.connect(self._show_settings_dialog)
        file_menu.addAction(settings_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # Theme toggle action
        self.action_toggle_theme = QAction("&Dark Mode", self)
        self.action_toggle_theme.setObjectName("actionToggleDarkMode")
        self.action_toggle_theme.setCheckable(True)
        self.action_toggle_theme.setShortcut(QKeySequence("Ctrl+D"))

        # Load theme setting and set checkbox
        current_theme = self.settings.value("appearance/theme", "light", type=str)
        self.action_toggle_theme.setChecked(current_theme == "dark")

        self.action_toggle_theme.triggered.connect(self._toggle_theme)
        view_menu.addAction(self.action_toggle_theme)

    def _toggle_theme(self) -> None:
        """Toggle between light and dark themes."""
        is_dark = self.action_toggle_theme.isChecked()
        theme = "dark" if is_dark else "light"

        # Save theme setting
        self.settings.setValue("appearance/theme", theme)

        # Apply theme to app
        app = self.window().parentWidget()
        if app is None:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
        if app:
            apply_theme(app, theme)

        self._toast(f"{'Dark' if is_dark else 'Light'} mode enabled", 2000)

    def _apply_startup_theme(self) -> None:
        """Apply saved theme on application startup."""
        theme = self.settings.value("appearance/theme", "light", type=str)
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            apply_theme(app, theme)

    def _show_settings_dialog(self) -> None:
        """Show the settings dialog."""
        dialog = SettingsDialog(self)
        dialog.exec()

    def _show_export_dialog(self) -> None:
        """Show the export dialog for the processed video."""
        if not self._result_path or not os.path.exists(self._result_path):
            self._toast("No processed video available to export")
            return

        dialog = ExportDialog(self._result_path, self)
        if dialog.exec():
            output_path = dialog.get_output_path()
            if output_path and os.path.exists(output_path):
                self._toast(f"Exported: {os.path.basename(output_path)}")

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
        if hasattr(self.timeline_scene, "orderChanged"):
            try:
                self.timeline_scene.orderChanged.connect(self.timeline_adapter.on_request_reorder)
            except Exception:
                logger.warning("Failed to connect timeline_scene.orderChanged signal", exc_info=True)

        # cut marker click → preview seek
        if hasattr(self.timeline_scene, "cutMarkerClicked"):
            try:
                self.timeline_scene.cutMarkerClicked.connect(self._on_cut_marker_clicked)
            except Exception:
                logger.warning("Failed to connect timeline_scene.cutMarkerClicked signal", exc_info=True)

        # file list changes
        self.file_list.filesAdded.connect(self._on_files_added)
        self.file_list.videoCountChanged.connect(self._refresh_counter)

        # buttons
        self.btn_add.clicked.connect(self.on_add_files)
        self.btn_process.clicked.connect(self.on_process_videos)

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

    def _on_cut_marker_clicked(self, timestamp_ms: int) -> None:
        """Seek preview to cut marker timestamp when clicked."""
        try:
            if hasattr(self, "preview") and self.preview:
                self.preview.seek_ms(timestamp_ms)
                self._toast(f"Seek to {timestamp_ms}ms", 2000)
        except Exception:
            logger.debug(f"Failed to seek to cut marker at {timestamp_ms}ms", exc_info=True)

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
                paths = [clip.path for clip in clips]
                self.file_list.sync_from_paths(paths)
            except Exception:
                logger.debug("Failed to sync file list with project", exc_info=True)

        # Update counter and button state
        self._refresh_counter()

    def _refresh_counter(self, *_args) -> None:
        count = self.file_list.video_count()
        self.lbl_counter.setText(f"Videos: {count}/{VIDEO_CAP}")
        self.btn_add.setEnabled(count < VIDEO_CAP)
        self.btn_process.setEnabled(count >= MIN_VIDEOS_FOR_PROCESS)

    # --- Processing ---
    def on_process_videos(self) -> None:
        """Start the video processing pipeline."""
        clips = self.project.clips()
        paths = [clip.path for clip in clips]

        if len(paths) < MIN_VIDEOS_FOR_PROCESS:
            self._toast(f"Need at least {MIN_VIDEOS_FOR_PROCESS} videos to process.")
            return

        # Read output quality from settings
        quality = self.settings.value("output/quality", "1080p", type=str)

        # Create and show progress dialog
        self._progress_dialog = ProcessingProgressDialog(self)

        # Create processing thread
        self._processing_thread = ProcessingThread(
            input_files=paths,
            external_audio=None,
            resolution=quality,
            parent=self,
        )

        # Connect signals
        self._processing_thread.progress.connect(self._on_processing_progress)
        self._processing_thread.stage.connect(self._on_processing_stage)
        self._processing_thread.finished_with_path.connect(self._on_processing_finished)
        self._processing_thread.error.connect(self._on_processing_error)
        self._processing_thread.finished.connect(self._on_thread_finished)
        self._progress_dialog.cancelRequested.connect(self._on_cancel_processing)

        # Start processing
        self._processing_thread.start()
        self._progress_dialog.show()

    def _on_processing_progress(self, percent: int) -> None:
        """Update progress dialog with overall progress."""
        if hasattr(self, "_progress_dialog") and self._progress_dialog:
            self._progress_dialog.update_progress(percent)

    def _on_processing_stage(self, stage_name: str, stage_percent: int, message: str) -> None:
        """Update progress dialog with stage info."""
        if hasattr(self, "_progress_dialog") and self._progress_dialog:
            self._progress_dialog.update_stage(stage_name, stage_percent, message)

    def _on_processing_finished(self, output_path: str) -> None:
        """Handle successful processing completion."""
        if hasattr(self, "_progress_dialog") and self._progress_dialog:
            self._progress_dialog.set_finished(True, f"Output: {output_path}")
        self._toast(f"Processing complete: {os.path.basename(output_path)}")

        # Store result path for A/B comparison and export
        self._result_path = output_path
        self.btn_toggle_ab.setEnabled(True)
        self.action_export.setEnabled(True)

    def _on_processing_error(self, error_msg: str) -> None:
        """Handle processing error."""
        if hasattr(self, "_progress_dialog") and self._progress_dialog:
            if "Cancelled" in error_msg:
                self._progress_dialog.set_cancelled()
            else:
                self._progress_dialog.set_finished(False, error_msg)
        else:
            self._toast(f"Processing failed: {error_msg}")

    def _on_cancel_processing(self) -> None:
        """Cancel the processing thread."""
        if hasattr(self, "_processing_thread") and self._processing_thread:
            self._processing_thread.cancel()

    def _on_thread_finished(self) -> None:
        """Cleanup after thread finishes."""
        self._processing_thread = None

    def _toast(self, message: str, timeout_ms: int = 4000) -> None:
        self.statusBar().showMessage(message, timeout_ms)

    def _toggle_ab_mode(self) -> None:
        """Toggle A/B comparison mode."""
        self._ab_mode = self.btn_toggle_ab.isChecked()

        # Get preview B widget (second widget in layout)
        preview_b_widget = self.preview_layout.itemAt(1).widget()

        if self._ab_mode:
            # Enable A/B mode
            if not self._result_path or not os.path.exists(self._result_path):
                self._toast("No result video available for comparison")
                self.btn_toggle_ab.setChecked(False)
                self._ab_mode = False
                return

            # Show labels and B preview
            self.lbl_preview_a.setVisible(True)
            preview_b_widget.setVisible(True)

            # Load result in preview B
            self.preview_b.set_source(self._result_path)

            # Start sync timer
            self._sync_timer.start()
            self._toast("A/B comparison enabled - playheads synced within 50ms", 3000)
        else:
            # Disable A/B mode
            self.lbl_preview_a.setVisible(False)
            preview_b_widget.setVisible(False)

            # Stop sync timer
            self._sync_timer.stop()
            self._toast("A/B comparison disabled", 2000)

    def _sync_playheads(self) -> None:
        """Sync playhead positions between A and B previews (≤50ms tolerance)."""
        if not self._ab_mode:
            return

        try:
            # Get current positions
            pos_a = self.preview.current_position_ms()
            pos_b = self.preview_b.current_position_ms()

            # Calculate drift
            drift = abs(pos_a - pos_b)

            # Sync if drift exceeds 50ms threshold
            if drift > 50:
                # Sync B to A (A is master)
                self.preview_b.seek_ms(pos_a)
        except Exception:
            logger.debug("Failed to sync playheads", exc_info=True)

    def _scroll_timeline_left(self) -> None:
        """Anchor timeline view to the far left after layout/scene updates."""
        try:
            hbar = self.timeline_view.horizontalScrollBar()
            if hbar is not None:
                hbar.setValue(hbar.minimum())
        except Exception:
            pass
