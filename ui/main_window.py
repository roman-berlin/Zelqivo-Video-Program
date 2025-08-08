"""Main window for the Active Speaker Video Merger application.

This module defines the ``MainWindow`` class which inherits from
``QMainWindow``. It sets up the high‑level layout: a list for
uploading video and audio files, buttons to start processing and save
the resulting video, a progress bar to report progress and a preview
area. At this stage, the widgets are placeholders and do not
implement any real processing logic.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QProgressBar, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt

from .file_list_widget import FileListWidget
from .video_preview import VideoPreviewWidget
from ..utils.signals import ProcessingSignals


class MainWindow(QMainWindow):
    """The main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Active Speaker Video Merger")
        self.resize(800, 600)
        self.signals = ProcessingSignals()
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Initialise and arrange widgets in the main window."""
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        self.file_list_widget = FileListWidget()
        layout.addWidget(self.file_list_widget)
        self.start_button = QPushButton("Start Processing")
        layout.addWidget(self.start_button)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        self.preview_widget = VideoPreviewWidget()
        layout.addWidget(self.preview_widget)
        self.save_button = QPushButton("Save Merged Video")
        self.save_button.setEnabled(False)
        layout.addWidget(self.save_button)
        self.setCentralWidget(central_widget)

    def _connect_signals(self) -> None:
        """Connect UI events to their handlers."""
        self.start_button.clicked.connect(self._start_processing)
        self.save_button.clicked.connect(self._save_video)
        self.signals.progress.connect(self.progress_bar.setValue)
        self.signals.finished.connect(self._on_processing_finished)

    def _start_processing(self) -> None:
        """Placeholder handler for the Start button."""
        QMessageBox.information(
            self,
            "Not Implemented",
            "Processing logic is not yet implemented. This button will start the processing pipeline.",
        )

    def _save_video(self) -> None:
        """Prompt the user to save the merged video to a chosen location."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Merged Video", "", "MP4 Video (*.mp4)"
        )
        if file_path:
            QMessageBox.information(
                self,
                "Save Location",
                f"Selected path: {file_path}\nSaving functionality not implemented yet.",
            )

    def _on_processing_finished(self, output_path: str) -> None:
        """Handle completion of the processing pipeline."""
        self.save_button.setEnabled(True)
        self.preview_widget.load_video(output_path)
