"""Progress dialog for video processing pipeline."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)


class ProcessingProgressDialog(QDialog):
    """Modern themed dialog showing processing progress with cancel button.

    Displays:
    - Current stage name and message
    - Overall progress bar with ETA
    - Cancel button
    
    Auto-detects light/dark theme from settings.

    Signals:
        cancelRequested: Emitted when user clicks Cancel.
    """

    cancelRequested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Processing Videos")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.setWindowFlags(
            Qt.WindowType.Dialog 
            | Qt.WindowType.FramelessWindowHint
        )

        self._cancelled = False
        self._output_path: Optional[str] = None
        
        # Detect theme
        settings = QSettings("MultiCamEditor", "MultiCamEditor")
        self._dark_mode = settings.value("appearance/theme", "light", type=str) == "dark"
        
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Theme colors
        if self._dark_mode:
            title_color = "#64b5f6"
            text_color = "#9e9e9e"
            eta_color = "#757575"
            bg_color = "#2d2d2d"
            border_color = "#555555"
            progress_bg = "#3c3c3c"
            progress_text = "#e0e0e0"
            btn_bg = "#3c3c3c"
            btn_border = "#555555"
            btn_text = "#e0e0e0"
            btn_hover = "#4a4a4a"
        else:
            title_color = "#1976d2"
            text_color = "#424242"
            eta_color = "#9e9e9e"
            bg_color = "#ffffff"
            border_color = "#e0e0e0"
            progress_bg = "#e0e0e0"
            progress_text = "#212121"
            btn_bg = "#f5f5f5"
            btn_border = "#bdbdbd"
            btn_text = "#424242"
            btn_hover = "#e0e0e0"

        # Title/Stage label
        self.lbl_stage = QLabel("Processing Videos", self)
        self.lbl_stage.setObjectName("lblStage")
        self.lbl_stage.setStyleSheet(f"""
            QLabel {{
                font-size: 16px;
                font-weight: bold;
                color: {title_color};
            }}
        """)
        self.lbl_stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_stage)

        # Message label
        self.lbl_message = QLabel("Initializing...", self)
        self.lbl_message.setObjectName("lblMessage")
        self.lbl_message.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {text_color};
            }}
        """)
        self.lbl_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_message.setWordWrap(True)
        layout.addWidget(self.lbl_message)

        # Overall progress bar with modern styling
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setMinimumHeight(24)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 12px;
                background-color: {progress_bg};
                text-align: center;
                font-weight: bold;
                color: {progress_text};
            }}
            QProgressBar::chunk {{
                border-radius: 12px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #1976d2,
                    stop: 1 #42a5f5
                );
            }}
        """)
        layout.addWidget(self.progress_bar)

        # ETA label
        self.lbl_eta = QLabel("Estimating...", self)
        self.lbl_eta.setObjectName("lblEta")
        self.lbl_eta.setStyleSheet(f"""
            QLabel {{
                font-size: 11px;
                color: {eta_color};
            }}
        """)
        self.lbl_eta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_eta)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        # Open Output Folder button (hidden initially)
        self.btn_open_folder = QPushButton("Open Folder", self)
        self.btn_open_folder.setObjectName("btnOpenFolder")
        self.btn_open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_folder.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                border: 1px solid {btn_border};
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 12px;
                color: {btn_text};
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
            }}
            QPushButton:pressed {{
                background-color: {btn_border};
            }}
        """)
        self.btn_open_folder.clicked.connect(self._on_open_folder_clicked)
        self.btn_open_folder.setVisible(False)
        btn_row.addWidget(self.btn_open_folder)

        # Cancel/Close button
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                border: 1px solid {btn_border};
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 12px;
                color: {btn_text};
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
            }}
            QPushButton:pressed {{
                background-color: {btn_border};
            }}
        """)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_row.addWidget(self.btn_cancel)

        layout.addLayout(btn_row)

        # Dialog styling
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 12px;
            }}
        """)

    def _on_cancel_clicked(self) -> None:
        """Handle cancel button click."""
        self._cancelled = True
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Cancelling...")
        self.lbl_message.setText("Cleaning up resources... (this may take a moment)")
        # Set indeterminate progress (pulsing) to show activity
        self.progress_bar.setRange(0, 0)
        self.lbl_eta.setText("Terminating processes...")
        self.cancelRequested.emit()

    def update_progress(self, percent: int) -> None:
        """Update the overall progress bar."""
        self.progress_bar.setValue(percent)

    def update_stage(self, stage_name: str, stage_percent: int, message: str) -> None:
        """Update stage information."""
        self.lbl_stage.setText(stage_name)
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

    def set_output_path(self, path: str) -> None:
        """Store output path for Open Output Folder button."""
        self._output_path = path

    def set_finished(self, success: bool, message: str = "") -> None:
        """Show finished state."""
        self._cancelled = False
        self.progress_bar.setRange(0, 100) # Reset from indeterminate
        if success:
            self.lbl_stage.setText("✓ Complete!")
            self.lbl_message.setText(message or "Processing finished successfully.")
            self.progress_bar.setValue(100)
            # Show Open Output Folder button if we have a valid path
            if self._output_path and os.path.isfile(self._output_path):
                self.btn_open_folder.setVisible(True)
        else:
            self.lbl_stage.setText("✗ Failed")
            self.lbl_message.setText(message or "Processing failed.")

        self.lbl_eta.setText("")
        self.btn_cancel.setText("Close")
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self.accept)

    def set_cancelled(self) -> None:
        """Show cancelled state."""
        self.progress_bar.setRange(0, 100) # Reset from indeterminate
        self.lbl_stage.setText("Cancelled")
        self.lbl_message.setText("Processing was cancelled.")
        self.lbl_eta.setText("")
        self.btn_cancel.setText("Close")
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.clicked.disconnect()
        self.btn_cancel.clicked.connect(self.accept)

    def _on_open_folder_clicked(self) -> None:
        """Open the output folder in the system file browser."""
        if not self._output_path:
            return

        folder = os.path.dirname(self._output_path)
        if not os.path.isdir(folder):
            logger.warning("Output folder does not exist: %s", folder)
            return

        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.run(["open", folder], check=True)
            else:
                subprocess.run(["xdg-open", folder], check=True)
            logger.info("Opened output folder: %s", folder)
        except Exception as e:
            logger.error("Failed to open output folder: %s", e, exc_info=True)

    def closeEvent(self, event) -> None:
        """Handle close event - emit cancel if still processing."""
        if not self._cancelled and self.btn_cancel.text() == "Cancel":
            self._on_cancel_clicked()
            event.ignore()
        else:
            event.accept()
