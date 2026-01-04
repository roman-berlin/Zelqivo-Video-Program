# file: ui/loading_dialog.py
"""Loading dialog with progress bar for video file loading."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LoadingDialog(QDialog):
    """Modern loading dialog with progress bar for video loading.
    
    Features a themed design matching the app's dark/light theme,
    progress percentage, current file label, and cancel button.
    """
    
    cancelled = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, title: str = "Loading Videos"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setWindowFlags(
            Qt.WindowType.Dialog 
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        
        self._cancelled = False
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the UI with modern styling."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title label
        self.label_title = QLabel("Loading Videos")
        self.label_title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #1976d2;
            }
        """)
        self.label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label_title)

        # Current file label
        self.label_current = QLabel("Preparing...")
        self.label_current.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #757575;
            }
        """)
        self.label_current.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_current.setWordWrap(True)
        layout.addWidget(self.label_current)

        # Progress bar with modern styling
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setMinimumHeight(24)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 12px;
                background-color: #e0e0e0;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                border-radius: 12px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #1976d2,
                    stop: 1 #42a5f5
                );
            }
        """)
        layout.addWidget(self.progress_bar)

        # Count label (e.g., "3 of 10 files")
        self.label_count = QLabel("")
        self.label_count.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #9e9e9e;
            }
        """)
        self.label_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label_count)

        # Cancel button
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f5;
                border: 1px solid #bdbdbd;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 12px;
                color: #424242;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #bdbdbd;
            }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(self.btn_cancel, alignment=Qt.AlignmentFlag.AlignCenter)

        # Dialog styling
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
            }
        """)

    def set_progress(self, current: int, total: int, filename: str = "") -> None:
        """Update the progress display.
        
        Args:
            current: Current item number (1-indexed)
            total: Total number of items
            filename: Current file being processed
        """
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
            self.label_count.setText(f"{current} of {total} files")
        
        if filename:
            # Show just the filename, not full path
            import os
            basename = os.path.basename(filename)
            # Truncate if too long
            if len(basename) > 50:
                basename = basename[:25] + "..." + basename[-22:]
            self.label_current.setText(f"Loading: {basename}")

    def is_cancelled(self) -> bool:
        """Check if the user cancelled the operation."""
        return self._cancelled

    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        self._cancelled = True
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("Cancelling...")
        self.cancelled.emit()

    def complete(self) -> None:
        """Mark loading as complete and close dialog."""
        self.progress_bar.setValue(100)
        self.label_current.setText("Complete!")
        QTimer.singleShot(300, self.accept)


class LoadingDialogDark(LoadingDialog):
    """Dark-themed variant of the loading dialog."""

    def _init_ui(self) -> None:
        """Initialize with dark theme styling."""
        super()._init_ui()
        
        # Override styles for dark theme
        self.label_title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #64b5f6;
            }
        """)
        
        self.label_current.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #9e9e9e;
            }
        """)
        
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 12px;
                background-color: #3c3c3c;
                text-align: center;
                font-weight: bold;
                color: #e0e0e0;
            }
            QProgressBar::chunk {
                border-radius: 12px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #1976d2,
                    stop: 1 #42a5f5
                );
            }
        """)
        
        self.label_count.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #757575;
            }
        """)
        
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 12px;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #555555;
            }
        """)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 12px;
            }
        """)
