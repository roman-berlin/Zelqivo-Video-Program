# file: ui/main_window.py
from __future__ import annotations
import logging
import os
import time
from typing import List

from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QUndoStack
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
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
from ..logic.processing_worker import ProcessingThread
from ..logic.commands import AddClipsCommand
from ..logic.preflight import check_preflight_warnings, format_warnings_for_display
from ..logic.preflight import (
    run_gpu_preflight_check, 
    GpuPreflightResult, 
    GpuPreflightStatus
)
from ..logic.switching_strategy import SwitchingStrategy
from ..logic.eta_estimation import (
    get_eta_display_text, 
    compute_eta_range, 
    should_warn_long_project,
    get_rtf_range
)
from .progress_dialog import ProcessingProgressDialog
from .loading_dialog import LoadingDialog
from .gpu_warning_dialog import show_gpu_warning_dialog
from PyQt6.QtWidgets import QMessageBox



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
        self.btn_add = QPushButton("Add Videos…", ctrl_row)
        self.btn_add.setObjectName("btnAddFiles")
        self.btn_add.setToolTip("Add 2 or more camera videos (MP4/MOV/AVI)")
        self.btn_process = QPushButton("Create Video", ctrl_row)
        self.btn_process.setObjectName("btnProcess")
        self.btn_process.setEnabled(False)  # Enabled when >=2 videos
        self.btn_process.setToolTip("Automatically sync and switch cameras")
        self.btn_remove_all = QPushButton("Remove All", ctrl_row)
        self.btn_remove_all.setObjectName("btnRemoveAll")
        self.btn_remove_all.setEnabled(False)  # Enabled when >0 videos
        self.btn_remove_all.setToolTip("Remove all videos from the list")
        self.lbl_counter = QLabel("Videos: 0/10", ctrl_row)
        self.lbl_counter.setObjectName("lblCounter")
        ctrl_lay.addWidget(self.btn_add)
        ctrl_lay.addWidget(self.btn_process)
        
        # ETA Label
        self.lbl_eta = QLabel("")
        self.lbl_eta.setObjectName("lblEta")
        self.lbl_eta.setStyleSheet("color: #2980b9; font-weight: bold; margin-left: 10px;")
        self.lbl_eta.setToolTip("Estimated time to process on your hardware")
        ctrl_lay.addWidget(self.lbl_eta)
        
        ctrl_lay.addWidget(self.btn_remove_all)
        ctrl_lay.addStretch(1)
        ctrl_lay.addWidget(self.lbl_counter)

        # Inline hint for "need 2+ videos"
        self.lbl_process_hint = QLabel("Add at least 2 videos to create a multicam edit.", left)
        self.lbl_process_hint.setObjectName("lblProcessHint")
        self.lbl_process_hint.setStyleSheet("color: gray; font-style: italic;")
        self.lbl_process_hint.setVisible(True)  # Visible initially

        lbl = QLabel("Videos", left)
        lbl.setObjectName("lblMediaFiles")
        self.file_list = FileListWidget(left)
        self.file_list.setObjectName("fileList")
        self.file_list.set_video_cap(VIDEO_CAP)

        left_layout.addWidget(ctrl_row)
        left_layout.addWidget(self.lbl_process_hint)
        left_layout.addWidget(lbl)
        left_layout.addWidget(self.file_list, 1)

        # --- Processing Options Group ---
        self._init_processing_options(left_layout)

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

        # A/B Compare button (hidden for V1, kept for future use)
        self.btn_toggle_ab = QPushButton("A/B Compare", preview_header)
        self.btn_toggle_ab.setObjectName("btnToggleAB")
        self.btn_toggle_ab.setCheckable(True)
        self.btn_toggle_ab.setChecked(False)
        self.btn_toggle_ab.setToolTip("Compare original vs auto-switched result side-by-side")
        self.btn_toggle_ab.clicked.connect(self._toggle_ab_mode)
        self.btn_toggle_ab.setVisible(False)  # V1: hide A/B comparison
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

        # Trim panel (hidden for V1 one-click workflow, backend kept for future use)
        self.trim_panel = TrimPanel(right)
        self.trim_panel.setVisible(False)  # V1: hide manual trim controls
        right_layout.addWidget(self.trim_panel)

        line = QFrame(right)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setVisible(False)  # V1: hide separator
        right_layout.addWidget(line)

        lbl_tl = QLabel("Timeline", right)
        lbl_tl.setObjectName("lblTimeline")
        lbl_tl.setVisible(False)  # V1: hide timeline label
        right_layout.addWidget(lbl_tl)

        self.timeline_scene = TimelineScene(self)
        self.timeline_view = TimelineView(self.timeline_scene, right)
        self.timeline_view.setMinimumHeight(120)
        self.timeline_view.setVisible(False)  # V1: hide timeline view
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

    def _init_processing_options(self, parent_layout: QVBoxLayout) -> None:
        """Initialize processing options group: speaker switching, external audio, mapping."""
        group = QGroupBox("Processing Options")
        group.setObjectName("groupProcessingOptions")
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        layout.setColumnStretch(1, 1)  # Value column expands

        row = 0

        # 1) External Audio checkbox (spans both columns)
        self.chk_external_audio = QCheckBox("Use external audio")
        self.chk_external_audio.setObjectName("chkExternalAudio")
        self.chk_external_audio.setToolTip("Replace camera audio with external audio file")
        self.chk_external_audio.setChecked(
            self.settings.value("processing/use_external_audio", False, type=bool)
        )
        self.chk_external_audio.toggled.connect(self._on_external_audio_toggled)
        layout.addWidget(self.chk_external_audio, row, 0, 1, 3)
        row += 1

        # Helper text under checkbox (smaller, grey)
        self.lbl_external_audio_hint = QLabel("External audio replaces camera audio in final video")
        self.lbl_external_audio_hint.setObjectName("lblExternalAudioHint")
        self.lbl_external_audio_hint.setStyleSheet("color: gray; font-size: 9pt;")
        self.lbl_external_audio_hint.setContentsMargins(20, 0, 0, 0)
        layout.addWidget(self.lbl_external_audio_hint, row, 0, 1, 3)
        row += 1

        # External audio file row: [Choose Audio...] button + filename value
        self.btn_add_external_audio = QPushButton("Choose Audio…")
        self.btn_add_external_audio.setObjectName("btnAddExternalAudio")
        self.btn_add_external_audio.setToolTip("Select external audio file (WAV, MP3, AAC, M4A)")
        self.btn_add_external_audio.setFixedWidth(120)
        self.btn_add_external_audio.clicked.connect(self._on_add_external_audio)
        layout.addWidget(self.btn_add_external_audio, row, 0)

        self.lbl_external_audio = QLabel("No audio selected")
        self.lbl_external_audio.setObjectName("lblExternalAudio")
        self.lbl_external_audio.setStyleSheet("color: gray;")
        # Don't load external_audio_path from settings - always start fresh
        self._external_audio_path: str | None = None
        layout.addWidget(self.lbl_external_audio, row, 1, 1, 2)
        row += 1

        self._update_external_audio_ui()

        # 2) Speaker mapping row: label "Speaker mapping" + value "Auto" + [Edit...] button
        lbl_mapping = QLabel("Speaker mapping")
        lbl_mapping.setObjectName("lblMappingLabel")
        layout.addWidget(lbl_mapping, row, 0)

        self.lbl_mapping_summary = QLabel("Auto")
        self.lbl_mapping_summary.setObjectName("lblMappingSummary")
        layout.addWidget(self.lbl_mapping_summary, row, 1)

        self.btn_edit_mapping = QPushButton("Edit…")
        self.btn_edit_mapping.setObjectName("btnEditMapping")
        self.btn_edit_mapping.setToolTip("Choose which speaker each camera should follow")
        self.btn_edit_mapping.setFixedWidth(80)
        self.btn_edit_mapping.clicked.connect(self._toggle_mapping_expanded)
        layout.addWidget(self.btn_edit_mapping, row, 2)
        row += 1

        # Mapping expanded section (hidden by default)
        self.mapping_container = QWidget()
        self.mapping_layout = QVBoxLayout(self.mapping_container)
        self.mapping_layout.setContentsMargins(20, 4, 0, 4)
        self.mapping_layout.setSpacing(4)
        self.mapping_container.setVisible(False)
        layout.addWidget(self.mapping_container, row, 0, 1, 3)
        row += 1

        # Placeholder label when no cameras
        self.lbl_no_cameras = QLabel("(Add videos to configure mapping)")
        self.lbl_no_cameras.setObjectName("lblNoCameras")
        self.lbl_no_cameras.setStyleSheet("color: gray; font-style: italic;")
        self.mapping_layout.addWidget(self.lbl_no_cameras)

        # Store mapping combos: {camera_index: QComboBox}
        self._camera_combos: dict[int, QComboBox] = {}
        self._available_speakers: list[str] = ["Auto (best effort)"]
        self._mapping_expanded: bool = False

        # Warning label (hidden by default)
        self.lbl_mapping_warning = QLabel("")
        self.lbl_mapping_warning.setObjectName("lblMappingWarning")
        self.lbl_mapping_warning.setStyleSheet("color: orange;")
        self.lbl_mapping_warning.setWordWrap(True)
        self.lbl_mapping_warning.setVisible(False)
        layout.addWidget(self.lbl_mapping_warning, row, 0, 1, 3)
        row += 1

        # 3) Output folder row: label + value + [Choose...] button
        lbl_output = QLabel("Output folder")
        lbl_output.setObjectName("lblOutputFolder")
        layout.addWidget(lbl_output, row, 0)

        # Don't persist output folder between sessions - always start fresh
        self._output_folder: str | None = None
        self.lbl_output_folder = QLabel("Please choose the output folder")
        self.lbl_output_folder.setObjectName("lblOutputFolderPath")
        self.lbl_output_folder.setStyleSheet("color: #e67e22; font-style: italic;")
        self.lbl_output_folder.setToolTip("Select an output folder before creating video")
        layout.addWidget(self.lbl_output_folder, row, 1)

        self.btn_choose_output_folder = QPushButton("Choose…")
        self.btn_choose_output_folder.setObjectName("btnChooseOutputFolder")
        self.btn_choose_output_folder.setToolTip("Select output folder for processed video")
        self.btn_choose_output_folder.setFixedWidth(80)
        self.btn_choose_output_folder.clicked.connect(self._on_choose_output_folder)
        layout.addWidget(self.btn_choose_output_folder, row, 2)
        row += 1

        parent_layout.addWidget(group)
        
        # 4) Generated Video section - hidden until render completes
        self.result_group = QGroupBox("Generated Video")
        self.result_group.setObjectName("groupResult")
        self.result_group.setVisible(False)
        result_layout = QHBoxLayout(self.result_group)
        result_layout.setContentsMargins(10, 8, 10, 8)
        
        self.lbl_result_file = QLabel("")
        self.lbl_result_file.setObjectName("lblResultFile")
        self.lbl_result_file.setStyleSheet("font-weight: bold;")
        result_layout.addWidget(self.lbl_result_file, 1)
        
        self.btn_play_result = QPushButton("▶ Play Video")
        self.btn_play_result.setObjectName("btnPlayResult")
        self.btn_play_result.setToolTip("Open the generated video in your default player")
        self.btn_play_result.setFixedWidth(110)
        self.btn_play_result.clicked.connect(self._on_play_result)
        result_layout.addWidget(self.btn_play_result)
        
        parent_layout.addWidget(self.result_group)

    def _on_external_audio_toggled(self, checked: bool) -> None:
        """Save external audio setting and update UI state."""
        self.settings.setValue("processing/use_external_audio", checked)
        self._update_external_audio_ui()
        logger.debug("External audio: %s", "enabled" if checked else "disabled")

    def _update_external_audio_ui(self) -> None:
        """Enable/disable external audio controls based on checkbox."""
        enabled = self.chk_external_audio.isChecked()
        self.btn_add_external_audio.setEnabled(enabled)
        self.lbl_external_audio.setEnabled(enabled)

    def _on_add_external_audio(self) -> None:
        """Open file dialog to select external audio file."""
        last_dir = self.settings.value("last_audio_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(
            self, "Select External Audio", last_dir,
            "Audio Files (*.wav *.mp3 *.aac *.m4a);;All Files (*.*)"
        )
        if not path:
            return
        if not os.path.isfile(path):
            self._toast("File not found")
            return
        self._external_audio_path = path
        self.settings.setValue("processing/external_audio_path", path)
        self.settings.setValue("last_audio_dir", os.path.dirname(path))
        self.lbl_external_audio.setText(os.path.basename(path))
        self.lbl_external_audio.setStyleSheet("")  # Normal color when file selected
        logger.info("External audio selected: %s", path)

    def _on_choose_output_folder(self) -> None:
        """Open folder dialog to select output folder."""
        start_dir = self._output_folder or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", start_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        if not folder:
            return
        self._output_folder = folder
        # Don't persist to settings - fresh start each session
        self.lbl_output_folder.setText(os.path.basename(folder))
        self.lbl_output_folder.setStyleSheet("")  # Remove warning style
        self.lbl_output_folder.setToolTip(folder)
        logger.info("Output folder selected: %s", folder)
        # Refresh button state since output folder is now set
        self._refresh_counter()

    def _refresh_camera_mapping_ui(self) -> None:
        """Rebuild camera mapping combos based on current file list."""
        # Clear old row widgets from the layout, but preserve lbl_no_cameras
        while self.mapping_layout.count() > 1:  # Keep first item (lbl_no_cameras)
            item = self.mapping_layout.takeAt(1)  # Remove from index 1 onwards
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self._camera_combos.clear()

        clips = self.project.clips()
        if not clips:
            self.lbl_no_cameras.setVisible(True)
            self.lbl_mapping_warning.setVisible(False)
            return

        self.lbl_no_cameras.setVisible(False)

        # Update available speakers based on camera count
        num_cameras = len(clips)
        self._available_speakers = ["Auto (best effort)"]
        # Add speaker options: at least 2, or match camera count if more
        num_speakers = max(2, num_cameras)
        for s in range(num_speakers):
            self._available_speakers.append(f"Speaker {s + 1}")

        # Create combo for each camera
        for i, clip in enumerate(clips):
            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(4)

            lbl = QLabel(f"Camera {i + 1}:")
            lbl.setMinimumWidth(70)
            row_lay.addWidget(lbl)

            combo = QComboBox()
            combo.setObjectName(f"comboCamera{i}")
            combo.addItems(self._available_speakers)
            # Load saved mapping
            saved = self.settings.value(f"processing/camera_{i}_speaker", "Auto (best effort)")
            idx = combo.findText(saved)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.currentTextChanged.connect(
                lambda text, cam=i: self._on_camera_mapping_changed(cam, text)
            )
            row_lay.addWidget(combo, 1)

            # Show filename hint
            hint = QLabel(os.path.basename(clip.path)[:20])
            hint.setStyleSheet("color: gray; font-size: 10px;")
            row_lay.addWidget(hint)

            self._camera_combos[i] = combo
            self.mapping_layout.addWidget(row)

        self._check_mapping_warnings()

    def _on_camera_mapping_changed(self, camera_index: int, speaker: str) -> None:
        """Save camera-to-speaker mapping."""
        self.settings.setValue(f"processing/camera_{camera_index}_speaker", speaker)
        logger.debug("Camera %d mapped to %s", camera_index, speaker)
        self._check_mapping_warnings()

    def _toggle_mapping_expanded(self) -> None:
        """Toggle speaker mapping section visibility."""
        self._mapping_expanded = not self._mapping_expanded
        self.mapping_container.setVisible(self._mapping_expanded)
        self.btn_edit_mapping.setText("Hide" if self._mapping_expanded else "Edit…")
        # Only show warning when expanded
        if self._mapping_expanded:
            self._check_mapping_warnings()
        else:
            self.lbl_mapping_warning.setVisible(False)

    def _check_mapping_warnings(self) -> None:
        """Show warning if user edited mapping and all cameras use auto-mapping.

        Only shown when mapping UI is expanded (user opted in to edit).
        """
        # Hide warning if mapping section is collapsed
        if not self._mapping_expanded:
            self.lbl_mapping_warning.setVisible(False)
            return
        if not self._camera_combos:
            self.lbl_mapping_warning.setVisible(False)
            return
        all_auto = all(
            combo.currentText() == "Auto (best effort)"
            for combo in self._camera_combos.values()
        )
        if all_auto and len(self._camera_combos) > 1:
            self.lbl_mapping_warning.setText(
                "Tip: For best results, map cameras to specific speakers."
            )
            self.lbl_mapping_warning.setVisible(True)
        else:
            self.lbl_mapping_warning.setVisible(False)

    def get_camera_speaker_mapping(self) -> dict[int, str]:
        """Return current camera-to-speaker mapping dict."""
        return {
            cam: combo.currentText()
            for cam, combo in self._camera_combos.items()
        }

    def _init_undo_toolbar(self) -> None:
        """Initialize undo/redo actions with keyboard shortcuts (hidden from UI)."""
        # Keep internal undo/redo functionality but hide from UI
        # Create undo action with Ctrl+Z shortcut (invisible - no toolbar/menu)
        self.action_undo = self.undo_stack.createUndoAction(self, "Undo")
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)  # Ctrl+Z
        self.action_undo.setObjectName("actionUndo")
        self.addAction(self.action_undo)  # Add to window for shortcut to work

        # Create redo action with Ctrl+Y (invisible - no toolbar/menu)
        self.action_redo = self.undo_stack.createRedoAction(self, "Redo")
        self.action_redo.setShortcuts([
            QKeySequence.StandardKey.Redo,
            QKeySequence("Ctrl+Y")
        ])
        self.action_redo.setObjectName("actionRedo")
        self.addAction(self.action_redo)  # Add to window for shortcut to work

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
                logger.debug("Failed to connect trim_panel.trimChanged signal", exc_info=True)

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
        self.file_list.videoCountChanged.connect(self._refresh_camera_mapping_ui)
        # Removal signals for proper Project sync
        self.file_list.removalRequested.connect(self._on_remove_video)
        self.file_list.removeAllRequested.connect(self._on_remove_all_videos)

        # buttons
        self.btn_add.clicked.connect(self.on_add_files)
        self.btn_process.clicked.connect(self.on_process_videos)
        self.btn_remove_all.clicked.connect(self.file_list.remove_all)

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
        
        # Show progress dialog for multiple files (3+)
        if len(videos) >= 3:
            self._add_files_with_progress(videos, remaining)
        else:
            # Quick add for 1-2 files
            added, skipped_dup, _ = self.file_list.add_files(videos, cap_remaining=remaining)
            self._handle_add_files_result(videos, added, skipped_dup)

    def _add_files_with_progress(self, videos: List[str], remaining: int) -> None:
        """Add files with a progress dialog for user feedback."""
        from PyQt6.QtWidgets import QApplication
        
        # Check current theme for dialog styling
        is_dark = self.settings.value("appearance/theme", "light", type=str) == "dark"
        dialog = LoadingDialog(self, "Loading Videos", dark_mode=is_dark)
        
        dialog.show()
        QApplication.processEvents()
        
        # Process files one by one with progress updates
        added: List[str] = []
        skipped_dup: List[str] = []
        total = min(len(videos), remaining)
        
        for i, video_path in enumerate(videos[:remaining]):
            if dialog.is_cancelled():
                break
            
            # Update progress
            dialog.set_progress(i + 1, total, video_path)
            QApplication.processEvents()
            
            # Add file (this does the probe)
            result = self.file_list.add_files([video_path], cap_remaining=1)
            if result[0]:  # added
                added.extend(result[0])
            if result[1]:  # duplicates
                skipped_dup.extend(result[1])
        
        dialog.complete()
        dialog.close()
        
        self._handle_add_files_result(videos, added, skipped_dup)

    def _handle_add_files_result(self, videos: List[str], added: List[str], skipped_dup: List[str]) -> None:
        """Handle the result of adding files and show appropriate messages."""
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

    def _on_remove_video(self, path: str) -> None:
        """Handle removal request for a single video.
        
        Uses RemoveClipsCommand for proper Project sync and undo support.
        """
        if not path:
            return

        # Find the clip with this path in the project
        clips = self.project.clips()
        clip_ids = [clip.id for clip in clips if clip.path == path]
        
        if not clip_ids:
            # Path not in project (shouldn't happen), just remove from UI
            self.file_list._do_remove_path(path)
            return
        
        # Use RemoveClipsCommand for undoable removal
        cmd = RemoveClipsCommand(
            self.project,
            clip_ids,
            refresh_callback=self._refresh_after_undo_redo
        )
        self.undo_stack.push(cmd)

    def _on_remove_all_videos(self) -> None:
        """Handle removal request for all videos.
        
        Uses RemoveClipsCommand for proper Project sync and undo support.
        """
        clips = self.project.clips()
        if not clips:
            return
        
        # Get all clip IDs
        clip_ids = [clip.id for clip in clips]
        
        # Use RemoveClipsCommand for undoable removal
        cmd = RemoveClipsCommand(
            self.project,
            clip_ids,
            refresh_callback=self._refresh_after_undo_redo
        )
        self.undo_stack.push(cmd)

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
        
        # Create Video requires: 2+ videos AND output folder selected
        has_enough_videos = count >= MIN_VIDEOS_FOR_PROCESS
        has_output_folder = self._output_folder is not None
        self.btn_process.setEnabled(has_enough_videos and has_output_folder)
        
        self.btn_remove_all.setEnabled(count > 0)
        # Show/hide inline hint based on video count
        self.lbl_process_hint.setVisible(count < MIN_VIDEOS_FOR_PROCESS)
        
        # Update ETA whenever counter refreshes (files added/removed)
        self._update_eta_label()

    def _update_eta_label(self) -> None:
        """Update ETA label based on current file duration and selected strategy."""
        clips = self.project.clips()
        if not clips:
            self.lbl_eta.setText("")
            return
            
        # Sum duration of all clips (assuming all are used? Pipeline usually uses all)
        # However, pipeline probe might update durations.
        # Project.clips() have duration if probed.
        total_seconds = sum(c.duration_ms for c in clips) / 1000.0
        
        # Get strategy from settings
        # Note: We need to load it same way as pipeline or settings dialog
        strategy_str = self.settings.value("switching/strategy", "balanced", type=str)
        try:
            strategy = SwitchingStrategy(strategy_str)
        except ValueError:
            strategy = SwitchingStrategy.BALANCED_LIPS_ENERGY
            
        # Check GPU availability (maybe cache this? detect_gpu is fastish but uses torch import)
        # We can detect once or just rely on eta_estimation (which calls detect_gpu if needed)
        # eta_estimation.detect_gpu caches? No.
        # But detect_gpu handles import error gracefully.
        from ..logic.preflight import detect_gpu
        gpu_available = detect_gpu()
        
        eta_text = get_eta_display_text(total_seconds, strategy, gpu_available)
        self.lbl_eta.setText(f"Est. Time: {eta_text}")
        
        # Color coding: optional
        # If very long, maybe make it orange?
        pass

    # --- Processing ---
    def _generate_output_path(self, input_paths: List[str]) -> str:
        """Generate deterministic, user-friendly output path.

        Format: multicam_YYYY-MM-DD_HH-MM.mp4
        Uses selected output folder or same folder as first input.
        """
        # Determine output folder
        if self._output_folder and os.path.isdir(self._output_folder):
            output_dir = self._output_folder
        else:
            # Fallback to same folder as first input
            output_dir = os.path.dirname(input_paths[0]) if input_paths else os.getcwd()

        # Generate user-friendly filename with date-time
        timestamp = time.strftime("%Y-%m-%d_%H-%M")
        filename = f"multicam_{timestamp}.mp4"
        output_path = os.path.join(output_dir, filename)

        # If file exists, add counter
        counter = 1
        base_path = output_path
        while os.path.exists(output_path):
            output_path = base_path.replace(".mp4", f"_{counter}.mp4")
            counter += 1

        logger.info("Output path: %s", output_path)
        return output_path

    def on_process_videos(self) -> None:
        """Start the video processing pipeline with preflight checks."""
        clips = self.project.clips()
        paths = [clip.path for clip in clips]

        if len(paths) < MIN_VIDEOS_FOR_PROCESS:
            self._toast(f"Need at least {MIN_VIDEOS_FOR_PROCESS} videos to process.")
            return

        # --- 1. GPU Preflight Check ---
        # Load current strategy
        strategy_str = self.settings.value("switching/strategy", "balanced", type=str)
        try:
            strategy = SwitchingStrategy(strategy_str)
        except ValueError:
            strategy = SwitchingStrategy.BALANCED_LIPS_ENERGY

        # Run check
        status = run_gpu_preflight_check(
            strategy,
            show_dialog_callback=lambda s, m: show_gpu_warning_dialog(s, m, self)
        )
        
        # Apply any strategy change from dialog (e.g. user chose "Switch to Fast")
        if status.final_strategy != strategy:
            logger.info("Strategy changed by preflight check: %s -> %s", strategy, status.final_strategy)
            self.settings.setValue("switching/strategy", status.final_strategy.value)
            strategy = status.final_strategy
            # Update UI if valid
            self._update_eta_label()

        # --- 2. Long Project Warning (CPU) ---
        # Re-check GPU status or use preflight result
        has_gpu = status.gpu_available
        total_seconds = sum(c.duration_ms for c in clips) / 1000.0
        
        if should_warn_long_project(total_seconds, strategy, has_gpu):
            reply = QMessageBox.question(
                self, 
                "Project Duration Warning",
                f"This project is {total_seconds/60:.0f} minutes long.\n"
                f"Processing with '{strategy.value}' on CPU may take a very long time.\n\n"
                "Do you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # --- 3. Existing preflight for files ---
        warnings = check_preflight_warnings(paths)
        if warnings:
            msg = format_warnings_for_display(warnings)
            reply = QMessageBox.warning(
                self,
                "Preflight Warnings",
                msg + "\n\nDo you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # --- 4. Start Processing ---
        
        # Speaker switching is always enabled (core feature of this app)
        speaker_switching_enabled = True
        use_external_audio = self.chk_external_audio.isChecked()

        # Get external audio path if enabled - validate it was actually selected
        external_audio: str | None = None
        if use_external_audio:
            if not self._external_audio_path:
                # User checked the box but never selected an audio file
                QMessageBox.warning(
                    self,
                    "External Audio Required",
                    "You checked 'Use external audio' but no audio file was selected.\n\n"
                    "Please either:\n"
                    "• Click 'Choose Audio...' to select an audio file, or\n"
                    "• Uncheck 'Use external audio' to proceed without it."
                )
                return
            elif os.path.isfile(self._external_audio_path):
                external_audio = self._external_audio_path
            else:
                # File was selected but no longer exists
                QMessageBox.warning(
                    self,
                    "External Audio Not Found",
                    f"The selected external audio file was not found:\n\n"
                    f"{self._external_audio_path}\n\n"
                    "Please select a different audio file or uncheck 'Use external audio'."
                )
                return

        # Get camera-to-speaker mapping
        camera_mapping = self.get_camera_speaker_mapping()

        # Read output quality from settings
        quality = self.settings.value("output/quality", "1080p", type=str)

        # Generate deterministic output path
        output_path = self._generate_output_path(paths)

        # Log processing configuration
        logger.info(
            "Processing: strategy=%s, external_audio=%s, cameras=%d, quality=%s, output=%s",
            strategy.value, external_audio is not None, len(paths), quality, output_path
        )

        # Create and show progress dialog
        self._progress_dialog = ProcessingProgressDialog(self)
        self._progress_dialog.set_output_path(output_path)

        # Create processing thread with all options
        self._processing_thread = ProcessingThread(
            input_files=paths,
            external_audio=external_audio,
            resolution=quality,
            output_path=output_path,
            speaker_switching_enabled=speaker_switching_enabled,
            camera_speaker_mapping=camera_mapping,
            parent=self,
        )

        # Wire up signals
        # Use intermediate handlers to update progress dialog properly
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

    def _on_processing_stage(self, stage_name: str, stage_percent: int, message: str, eta_seconds: float) -> None:
        """Update progress dialog with stage info and ETA."""
        if hasattr(self, "_progress_dialog") and self._progress_dialog:
            self._progress_dialog.update_stage(stage_name, stage_percent, message)
            # ETA < 0 means unknown/not yet computed
            self._progress_dialog.update_eta(eta_seconds if eta_seconds >= 0 else None)

    def _on_processing_finished(self, output_path: str) -> None:
        """Handle successful processing completion."""
        if hasattr(self, "_progress_dialog") and self._progress_dialog:
            self._progress_dialog.set_finished(True, f"Output: {output_path}")
        self._toast(f"Processing complete: {os.path.basename(output_path)}")

        # Store result path for A/B comparison and export
        self._result_path = output_path
        self.btn_toggle_ab.setEnabled(True)
        self.action_export.setEnabled(True)
        
        # Show result section with Play button
        if hasattr(self, "result_group") and hasattr(self, "lbl_result_file"):
            self.lbl_result_file.setText(os.path.basename(output_path))
            self.lbl_result_file.setToolTip(output_path)
            self.result_group.setVisible(True)

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

    def _on_play_result(self) -> None:
        """Open the generated video in the system's default player."""
        if not hasattr(self, "_result_path") or not self._result_path:
            self._toast("No video available to play")
            return
        if not os.path.exists(self._result_path):
            self._toast("Video file not found")
            return
        
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        
        url = QUrl.fromLocalFile(self._result_path)
        if QDesktopServices.openUrl(url):
            logger.info("Opened video: %s", self._result_path)
        else:
            self._toast("Failed to open video player")
            logger.warning("Failed to open video: %s", self._result_path)

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




