"""Worker class to run the processing pipeline on a separate thread."""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from utils.signals import ProcessingSignals
from .processing_pipeline import ProcessingPipeline


class ProcessingWorker(QObject):
    """Run the processing pipeline inside a QThread."""

    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, input_files: List[str], external_audio: Optional[str], resolution: str) -> None:
        super().__init__()
        self.input_files = input_files
        self.external_audio = external_audio
        self.resolution = resolution

    def run(self) -> None:
        """Execute the processing pipeline and forward emitted signals."""
        pipeline = ProcessingPipeline(self.input_files, ProcessingSignals())
        pipeline.signals.progress.connect(self.progress.emit)
        pipeline.signals.finished.connect(self.finished.emit)
        pipeline.signals.error.connect(self.error.emit)
        try:
            pipeline.run(external_audio=self.external_audio, resolution=self.resolution)
        except Exception as exc:
            self.error.emit(str(exc))