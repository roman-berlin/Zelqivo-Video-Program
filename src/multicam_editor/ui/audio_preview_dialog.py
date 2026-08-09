"""Audio Preview Dialog for synchronized audio verification.

Shows a modern progress dialog while playing mixed audio from all cameras.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class AudioPreviewDialog(QDialog):
    """Dialog showing audio preview playback progress.
    
    Displays a countdown timer and progress bar while playing
    synchronized audio from all cameras for echo detection.
    """
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        duration_seconds: int = 8,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("🎵 Audio Preview")
        self.setModal(True)
        self.setFixedSize(400, 200)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )
        
        self.duration_seconds = duration_seconds
        self.elapsed_seconds = 0
        
        self._init_ui()
        self._start_timer()
    
    def _init_ui(self) -> None:
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # Title
        title = QLabel("🎧 Listening to Synchronized Audio")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Instructions
        instructions = QLabel(
            "Listen carefully for echoes or delays.\n"
            "If you hear echoes, cameras may need re-syncing."
        )
        instructions.setStyleSheet("color: #888; font-size: 10pt;")
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(self.duration_seconds * 10)  # 100ms steps
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Countdown label
        self.countdown_label = QLabel(f"{self.duration_seconds}s remaining")
        self.countdown_label.setStyleSheet("font-size: 12pt; font-weight: bold; color: #3498db;")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.countdown_label)
        
        # Stop button
        self.btn_stop = QPushButton("⏹ Stop Preview")
        self.btn_stop.clicked.connect(self.reject)
        layout.addWidget(self.btn_stop)
        
        layout.addStretch()
    
    def _start_timer(self) -> None:
        """Start the countdown timer."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_progress)
        self.timer.start(100)  # Update every 100ms
    
    def _update_progress(self) -> None:
        """Update progress bar and countdown."""
        self.elapsed_seconds += 0.1
        
        # Update progress bar
        progress_value = int(self.elapsed_seconds * 10)
        self.progress_bar.setValue(progress_value)
        
        # Update countdown
        remaining = max(0, self.duration_seconds - self.elapsed_seconds)
        self.countdown_label.setText(f"{remaining:.1f}s remaining")
        
        # Auto-close when done
        if self.elapsed_seconds >= self.duration_seconds:
            self.timer.stop()
            self.accept()
    
    def closeEvent(self, event) -> None:
        """Clean up timer on close."""
        if hasattr(self, 'timer'):
            self.timer.stop()
        super().closeEvent(event)
