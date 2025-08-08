"""Main window for the Active Speaker Video Merger application."""

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QProgressBar,
    QFileDialog,
    QMessageBox,
)
from PyQt6.QtCore import QThread
from typing import Optional

from .file_list_widget import FileListWidget
from .video_preview import VideoPreviewWidget
# Avoid using relative imports that ascend above the package root. Absolute
# imports work whether the application is launched via ``python main.py`` or
# through ``python -m`` on the package. See README for details.
from utils.file_utils import is_supported_video_file, is_supported_audio_file
from logic.processing_worker import ProcessingWorker


class MainWindow(QMainWindow):
    """The main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Active Speaker Video Merger")
        self.resize(800, 600)
        self._setup_ui()
        self._connect_signals()
        # holders for threading
        self._thread: Optional[QThread] = None
        self._worker: Optional[ProcessingWorker] = None
        # attribute to store the output path when processing completes
        self.output_path: str = ""

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

    def _start_processing(self) -> None:
        """
        Handle the Start button by launching the processing pipeline in a worker thread.

        Files are gathered from the file list widget and separated into video and audio.
        A ProcessingWorker is created and moved to a QThread; its progress and finished
        signals are connected to update the UI safely. The start button remains disabled
        until processing completes or an error occurs.
        """
        # Retrieve file paths
        file_paths = self.file_list_widget.get_file_paths()
        if not file_paths:
            QMessageBox.information(
                self,
                "No Files Selected",
                "Please add at least one supported video file before starting processing.",
            )
            return

        video_paths = [p for p in file_paths if is_supported_video_file(p)]
        audio_paths = [p for p in file_paths if is_supported_audio_file(p)]

        if not video_paths:
            QMessageBox.information(
                self,
                "No Video Files",
                "At least one supported video file is required to start processing.",
            )
            return

        external_audio = audio_paths[0] if audio_paths else None

        # Disable the start button while processing
        self.start_button.setEnabled(False)
        self.save_button.setEnabled(False)

        # Create and configure thread and worker
        self._thread = QThread(self)
        self._worker = ProcessingWorker(video_paths, external_audio)
        self._worker.moveToThread(self._thread)

        # When the thread starts, invoke the worker's run method
        self._thread.started.connect(self._worker.run)
        # Connect worker signals to UI updates
        self._worker.progress.connect(self.progress_bar.setValue)
        self._worker.finished.connect(self._on_processing_finished)
        self._worker.error.connect(self._on_worker_error)
        # Ensure we stop the thread cleanly when done or error
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        # Start the thread
        self._thread.start()

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
        """
        Handle completion of the processing pipeline.

        Re-enables the Start button, stores the output path, and enables the Save button.
        If no output was produced, alerts the user instead.
        """
        self.start_button.setEnabled(True)
        self.output_path = output_path
        if output_path:
            self.save_button.setEnabled(True)
            self.preview_widget.load_video(output_path)
        else:
            self.save_button.setEnabled(False)
            QMessageBox.warning(
                self,
                "Processing Result",
                "Processing finished but no output video was produced.",
            )

    def _on_worker_error(self, message: str) -> None:
        """
        Display an error message if the worker encounters an exception.

        This slot is connected to the ProcessingWorker.error signal.
        """
        # re-enable the start button since processing has failed
        self.start_button.setEnabled(True)
        QMessageBox.critical(self, "Processing Error", message)
