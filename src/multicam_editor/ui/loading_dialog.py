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
    
    Auto-detects light/dark theme from parent widget and applies
    appropriate styling.
    """
    
    cancelled = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, title: str = "Loading Videos", dark_mode: bool = False):
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
        self._dark_mode = dark_mode
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the UI with theme-aware styling."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Colors based on theme
        if self._dark_mode:
            title_color = "#64b5f6"
            text_color = "#9e9e9e"
            count_color = "#757575"
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
            text_color = "#757575"
            count_color = "#9e9e9e"
            bg_color = "#ffffff"
            border_color = "#e0e0e0"
            progress_bg = "#e0e0e0"
            progress_text = "#212121"
            btn_bg = "#f5f5f5"
            btn_border = "#bdbdbd"
            btn_text = "#424242"
            btn_hover = "#e0e0e0"

        # Title label
        self.label_title = QLabel("Loading Videos")
        self.label_title.setStyleSheet(f"""
            QLabel {{
                font-size: 16px;
                font-weight: bold;
                color: {title_color};
            }}
        """)
        self.label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label_title)

        # Current file label
        self.label_current = QLabel("Preparing...")
        self.label_current.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {text_color};
            }}
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

        # Count label (e.g., "3 of 10 files")
        self.label_count = QLabel("")
        self.label_count.setStyleSheet(f"""
            QLabel {{
                font-size: 11px;
                color: {count_color};
            }}
        """)
        self.label_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label_count)

        # Cancel button
        self.btn_cancel = QPushButton("Cancel")
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
        self.btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(self.btn_cancel, alignment=Qt.AlignmentFlag.AlignCenter)

        # Dialog styling
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 12px;
            }}
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
