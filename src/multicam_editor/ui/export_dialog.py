"""Export dialog for exporting timeline with presets and progress tracking."""

from __future__ import annotations

import logging
import os
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..utils.ffmpeg import FFmpegProcess, is_ffmpeg_available

logger = logging.getLogger(__name__)


class ExportWorker(QThread):
    """Worker thread for exporting video with ffmpeg."""

    progress = Signal(int)  # 0-100
    finished_ok = Signal(str)  # output_path
    error = Signal(str)  # error message

    def __init__(
        self,
        input_path: str,
        output_path: str,
        resolution: str,
        bitrate: str,
        parent=None,
    ):
        super().__init__(parent)
        self._input_path = input_path
        self._output_path = output_path
        self._resolution = resolution
        self._bitrate = bitrate
        self._ffmpeg_proc: Optional[FFmpegProcess] = None
        self._cancelled = False

    def run(self) -> None:
        """Run the export operation."""
        try:
            # Build ffmpeg arguments
            args = self._build_export_args()

            # Create FFmpeg process
            self._ffmpeg_proc = FFmpegProcess(args, self._output_path)

            # Run (blocking)
            result = self._ffmpeg_proc.run()

            if self._cancelled:
                self.error.emit("Export cancelled")
                return

            if result.success:
                self.progress.emit(100)
                self.finished_ok.emit(self._output_path)
            else:
                err_msg = result.error or "Unknown error"
                if result.cancelled:
                    err_msg = "Export cancelled"
                self.error.emit(err_msg)

        except Exception as e:
            logger.error(f"Export error: {e}", exc_info=True)
            self.error.emit(str(e))

    def cancel(self) -> None:
        """Cancel the export operation."""
        self._cancelled = True
        if self._ffmpeg_proc:
            self._ffmpeg_proc.cancel()

    def _build_export_args(self) -> list[str]:
        """Build ffmpeg command arguments for export."""
        args = [
            "ffmpeg",
            "-y",  # Overwrite
            "-i", self._input_path,
        ]

        # Resolution scaling
        if self._resolution == "1080p":
            args.extend(["-vf", "scale=-2:1080"])
        elif self._resolution == "720p":
            args.extend(["-vf", "scale=-2:720"])
        elif self._resolution == "480p":
            args.extend(["-vf", "scale=-2:480"])
        # "Original" or "Source" = no scaling

        # Video codec and bitrate
        args.extend(["-c:v", "libx264", "-preset", "fast"])
        if self._bitrate != "auto":
            args.extend(["-b:v", self._bitrate])

        # Audio codec
        args.extend(["-c:a", "aac", "-b:a", "192k"])

        args.append(self._output_path)
        return args


class ExportDialog(QDialog):
    """Dialog for exporting the processed video with presets."""

    def __init__(self, input_path: str, parent=None):
        super().__init__(parent)
        self._input_path = input_path
        self._output_path: Optional[str] = None
        self._worker: Optional[ExportWorker] = None

        self.setWindowTitle("Export Video")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Source file info
        info_label = QLabel(f"Source: {os.path.basename(self._input_path)}", self)
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray;")
        layout.addWidget(info_label)

        # Form for presets
        form = QFormLayout()
        form.setSpacing(8)

        # Resolution preset
        self.combo_resolution = QComboBox(self)
        self.combo_resolution.setObjectName("comboResolution")
        self.combo_resolution.addItems(["1080p", "720p", "480p", "Source"])
        self.combo_resolution.setCurrentText("1080p")
        form.addRow("Resolution:", self.combo_resolution)

        # Bitrate preset
        self.combo_bitrate = QComboBox(self)
        self.combo_bitrate.setObjectName("comboBitrate")
        self.combo_bitrate.addItems([
            "auto",
            "5000k (High)",
            "3000k (Medium)",
            "1500k (Low)",
        ])
        self.combo_bitrate.setCurrentText("auto")
        form.addRow("Video Bitrate:", self.combo_bitrate)

        layout.addLayout(form)

        # Destination picker
        dest_layout = QHBoxLayout()
        dest_layout.setSpacing(8)

        self.txt_destination = QLineEdit(self)
        self.txt_destination.setObjectName("txtDestination")
        self.txt_destination.setPlaceholderText("Choose destination...")
        self.txt_destination.setReadOnly(True)
        dest_layout.addWidget(self.txt_destination, 1)

        self.btn_browse = QPushButton("Browse...", self)
        self.btn_browse.setObjectName("btnBrowse")
        self.btn_browse.clicked.connect(self._on_browse_clicked)
        dest_layout.addWidget(self.btn_browse)

        layout.addLayout(dest_layout)

        # Progress section (initially hidden)
        self.lbl_status = QLabel("", self)
        self.lbl_status.setObjectName("lblStatus")
        self.lbl_status.setVisible(False)
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)

        self.btn_export = QPushButton("Export", self)
        self.btn_export.setObjectName("btnExport")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._on_export_clicked)
        button_layout.addWidget(self.btn_export)

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        button_layout.addWidget(self.btn_cancel)

        layout.addLayout(button_layout)

        # Check ffmpeg availability
        if not is_ffmpeg_available():
            self.lbl_status.setText("Error: ffmpeg not found on system")
            self.lbl_status.setStyleSheet("color: red;")
            self.lbl_status.setVisible(True)
            self.btn_export.setEnabled(False)

    def _on_browse_clicked(self) -> None:
        """Open file dialog to choose destination."""
        default_name = "exported_video.mp4"
        if hasattr(self.parent(), "settings"):
            last_dir = self.parent().settings.value("export/last_dir", os.path.expanduser("~"))
        else:
            last_dir = os.path.expanduser("~")

        default_path = os.path.join(last_dir, default_name)

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Video",
            default_path,
            "Video Files (*.mp4 *.mov *.avi);;All Files (*)",
        )

        if path:
            self._output_path = path
            self.txt_destination.setText(path)
            self.btn_export.setEnabled(True)

            # Save directory for next time
            if hasattr(self.parent(), "settings"):
                self.parent().settings.setValue("export/last_dir", os.path.dirname(path))

    def _on_export_clicked(self) -> None:
        """Start the export operation."""
        if not self._output_path:
            return

        # Disable controls during export
        self.combo_resolution.setEnabled(False)
        self.combo_bitrate.setEnabled(False)
        self.btn_browse.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_cancel.setText("Cancel Export")

        # Show status
        self.lbl_status.setText("Exporting... This may take a while.")
        self.lbl_status.setStyleSheet("color: blue;")
        self.lbl_status.setVisible(True)

        # Get preset values
        resolution = self.combo_resolution.currentText()
        bitrate_text = self.combo_bitrate.currentText()
        bitrate = bitrate_text.split()[0]  # Extract "5000k" from "5000k (High)"

        # Create and start worker
        self._worker = ExportWorker(
            self._input_path,
            self._output_path,
            resolution,
            bitrate,
            self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished_ok)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_cancel_clicked(self) -> None:
        """Handle cancel button click."""
        if self._worker and self._worker.isRunning():
            # Cancel export
            self.lbl_status.setText("Cancelling export...")
            self.lbl_status.setStyleSheet("color: orange;")
            self.btn_cancel.setEnabled(False)
            self._worker.cancel()
            self._worker.wait(5000)  # Wait up to 5 seconds
            self.reject()
        else:
            # Just close dialog
            self.reject()

    def _on_progress(self, percent: int) -> None:
        """Update progress display."""
        self.lbl_status.setText(f"Exporting... {percent}%")

    def _on_finished_ok(self, output_path: str) -> None:
        """Handle successful export completion."""
        self.lbl_status.setText(f"Export complete: {os.path.basename(output_path)}")
        self.lbl_status.setStyleSheet("color: green;")
        self.btn_cancel.setText("Close")
        self.btn_cancel.setEnabled(True)

        # Store output path for later use
        self._output_path = output_path

        # Auto-close after 1 second
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1000, self.accept)

    def _on_error(self, error_msg: str) -> None:
        """Handle export error."""
        self.lbl_status.setText(f"Export failed: {error_msg}")
        self.lbl_status.setStyleSheet("color: red;")
        self.btn_cancel.setText("Close")
        self.btn_cancel.setEnabled(True)

        # Re-enable controls so user can try again
        self.combo_resolution.setEnabled(True)
        self.combo_bitrate.setEnabled(True)
        self.btn_browse.setEnabled(True)
        self.btn_export.setEnabled(True)

    def closeEvent(self, event) -> None:
        """Handle close event - cancel export if running."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)
        event.accept()

    def get_output_path(self) -> Optional[str]:
        """Get the output path after successful export."""
        return self._output_path
