"""Placeholder widget for previewing the merged video output."""

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt


class VideoPreviewWidget(QWidget):
    """Widget that would display the merged video in a future version."""

    def __init__(self) -> None:
        super().__init__()
        self.label = QLabel("Video preview not available.")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)

    def load_video(self, file_path: str) -> None:
        """
        Load a video for previewing. Currently just updates the label.
        """
        self.label.setText(f"Preview would load: {file_path}")
