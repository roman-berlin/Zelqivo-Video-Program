"""Progress dialog for video processing pipeline."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class ProcessingProgressDialog(QDialog):
    """Dialog showing processing progress with cancel button.

    Displays:
    - Current stage name and message
    - Overall progress bar with ETA
    - Cancel button

    Signals:
        cancelRequested: Emitted when user clicks Cancel.
    """

    cancelRequested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Processing Videos")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._cancelled = False
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Stage label
        self.lbl_stage = QLabel("Initializing...", self)
        self.lbl_stage.setObjectName("lblStage")
        self.lbl_stage.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.lbl_stage)

        # Message label
        self.lbl_message = QLabel("", self)
        self.lbl_message.setObjectName("lblMessage")
        self.lbl_message.setWordWrap(True)
        layout.addWidget(self.lbl_message)

        # Overall progress bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # ETA label
        self.lbl_eta = QLabel("", self)
        self.lbl_eta.setObjectName("lblEta")
        self.lbl_eta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_eta)

        # Cancel button
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self.btn_cancel, alignment=Qt.AlignmentFlag.AlignCenter)

    def _on_cancel_clicked(self) -> None:
        """Handle cancel button click."""
        self._cancelled = True
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Cancelling...")
        self.lbl_message.setText("Cancellation requested, please wait...")
        self.cancelRequested.emit()

    def update_progress(self, percent: int) -> None:
        """Update the overall progress bar."""
        self.progress_bar.setValue(percent)

    def update_stage(self, stage_name: str, stage_percent: int, message: str) -> None:
        """Update stage information."""
        self.lbl_stage.setText(f"Stage: {stage_name}")
        self.lbl_message.setText(message)

    def update_eta(self, eta_seconds: Optional[float]) -> None:
        """Update ETA display.

        Args:
            eta_seconds: Estimated time remaining in seconds.
                - None: Show "Estimating..."
                - <= 0: Hide ETA
                - > 0: Show formatted ETA (mm:ss)
        """
        if eta_seconds is None:
            self.lbl_eta.setText("Estimating...")
            return

        if eta_seconds <= 0:
            self.lbl_eta.setText("")
            return

        # Format as mm:ss for consistency
        if eta_seconds < 60:
            eta_text = f"ETA: 00:{int(eta_seconds):02d}"
        elif eta_seconds < 3600:
            minutes = int(eta_seconds // 60)
            seconds = int(eta_seconds % 60)
            eta_text = f"ETA: {minutes:02d}:{seconds:02d}"
        else:
            hours = int(eta_seconds // 3600)
            minutes = int((eta_seconds % 3600) // 60)
            eta_text = f"ETA: {hours}h {minutes:02d}m"

        self.lbl_eta.setText(eta_text)

    def set_finished(self, success: bool, message: str = "") -> None:
        """Show finished state."""
        self._cancelled = False
        if success:
            self.lbl_stage.setText("Complete!")
            self.lbl_message.setText(message or "Processing finished successfully.")
            self.progress_bar.setValue(100)
        else:
            self.lbl_stage.setText("Failed")
            self.lbl_message.setText(message or "Processing failed.")

        self.lbl_eta.setText("")
        self.btn_cancel.setText("Close")
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self.accept)

    def set_cancelled(self) -> None:
        """Show cancelled state."""
        self.lbl_stage.setText("Cancelled")
        self.lbl_message.setText("Processing was cancelled.")
        self.lbl_eta.setText("")
        self.btn_cancel.setText("Close")
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self.accept)

    def closeEvent(self, event) -> None:
        """Handle close event - emit cancel if still processing."""
        if not self._cancelled and self.btn_cancel.text() == "Cancel":
            self._on_cancel_clicked()
            event.ignore()
        else:
            event.accept()
