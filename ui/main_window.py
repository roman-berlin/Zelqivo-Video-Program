from __future__ import annotations

import os
import shutil
from typing import Optional

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from logic.processing_worker import ProcessingWorker
from ui.file_list_widget import FileListWidget
from ui.video_preview import VideoPreviewWidget


class MainWindow(QMainWindow):
    """Top-level window wiring UI to the background processing worker."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MultiCamEditor — Active Speaker Video Merger")
        self.resize(1100, 700)

        self._thread: Optional[QThread] = None
        self._worker: Optional[ProcessingWorker] = None
        self._last_output_path: str = ""

        # --- Left: file list
        self.file_list = FileListWidget(self)
        self.file_list.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        # --- Right: video preview
        self.preview = VideoPreviewWidget(self)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # --- Buttons
        self.add_button = QPushButton("Add Files")
        self.start_button = QPushButton("Start Processing")
        self.save_button = QPushButton("Save Merged Video")
        self.save_button.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.progress.setTextVisible(True)

        # Layouts
        right_col = QVBoxLayout()
        right_col.addWidget(self.preview)

        left_col = QVBoxLayout()
        left_col.addWidget(QLabel("Files"))
        left_col.addWidget(self.file_list)

        center = QHBoxLayout()
        center.addLayout(left_col, 1)
        center.addLayout(right_col, 2)

        bottom = QHBoxLayout()
        bottom.addWidget(self.add_button)
        bottom.addStretch(1)
        bottom.addWidget(self.start_button)
        bottom.addWidget(self.save_button)

        root = QVBoxLayout()
        root.addLayout(center, 1)
        root.addWidget(self.progress)
        root.addLayout(bottom)

        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

        # Signals
        self.add_button.clicked.connect(self._on_add_files_clicked)
        self.start_button.clicked.connect(self._on_start_clicked)
        self.save_button.clicked.connect(self._on_save_clicked)
        self.file_list.currentTextChanged.connect(self._on_file_selected)

        # UX: disable start until at least one file is present
        self._update_start_enabled()

    # ----------------------------
    # UI actions
    # ----------------------------

    def _update_start_enabled(self) -> None:
        self.start_button.setEnabled(self.file_list.count() > 0)

    def _on_add_files_clicked(self) -> None:
        filters = "Media files (*.mp4 *.avi *.mov *.wav *.mp3);;All files (*)"
        files, _ = QFileDialog.getOpenFileNames(self, "Add media files", "", filters)
        for path in files:
            self.file_list.add_path(path)
        self._update_start_enabled()
        if files:
            self.preview.load(files[0])

    def _on_file_selected(self, path: str) -> None:
        if path:
            self.preview.load(path)

    def _on_start_clicked(self) -> None:
        self._start_processing(
            input_files=self.file_list.get_file_paths(),
            external_audio=None,
            resolution="1080p",
        )

    def _on_save_clicked(self) -> None:
        if not self._last_output_path or not os.path.exists(self._last_output_path):
            QMessageBox.information(
                self, "Nothing to save", "There is no merged video to save yet."
            )
            return
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save merged video", "merged.mp4", "MP4 Video (*.mp4)"
        )
        if not out_path:
            return
        try:
            shutil.copyfile(self._last_output_path, out_path)
            QMessageBox.information(self, "Saved", f"Saved to:\n{out_path}")
        except Exception as exc:  # why: provide feedback instead of silent failure
            QMessageBox.critical(self, "Save failed", str(exc))

    # ----------------------------
    # Background processing
    # ----------------------------

    def _start_processing(
        self, input_files: list[str], external_audio: Optional[str], resolution: str
    ) -> None:
        if self._thread is not None:
            QMessageBox.warning(self, "Busy", "Processing is already running.")
            return
        if not input_files:
            QMessageBox.information(self, "No input", "Please add at least one media file.")
            return

        self.progress.setValue(0)
        self.save_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self._last_output_path = ""

        self._thread = QThread(self)
        self._worker = ProcessingWorker(input_files, external_audio, resolution)
        self._worker.moveToThread(self._thread)

        # Wire signals
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)

        # Ensure cleanup
        self._worker.finished.connect(self._cleanup_thread)
        self._worker.error.connect(self._cleanup_thread)
        self._thread.finished.connect(self._thread.deleteLater)  # why: avoid leaks

        self._thread.start()

    def _cleanup_thread(self, *_: object) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self.start_button.setEnabled(True)

    def _on_worker_finished(self, output_path: str) -> None:
        self._last_output_path = output_path or ""
        if self._last_output_path and os.path.exists(self._last_output_path):
            self.save_button.setEnabled(True)
            QMessageBox.information(self, "Done", "Processing finished successfully.")
        else:
            self.save_button.setEnabled(False)
            QMessageBox.warning(
                self,
                "Processing Result",
                "Processing finished but no output video was produced.",
            )

    def _on_worker_error(self, message: str) -> None:
        """Display an error message if the worker encounters an exception."""
        self.start_button.setEnabled(True)
        QMessageBox.critical(self, "Processing Error", message)