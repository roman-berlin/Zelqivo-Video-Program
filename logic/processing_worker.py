"""Worker class to run the processing pipeline on a separate thread."""

from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

# Import ProcessingSignals via an absolute path. Using ``..`` to ascend above
# the package root breaks when running the application with ``python main.py``.
from utils.signals import ProcessingSignals
from .processing_pipeline import ProcessingPipeline


class ProcessingWorker(QObject):
    """
    Worker running the processing pipeline in a separate thread.

    It forwards progress, finished and error signals from the internal
    ProcessingPipeline to its own signals so the UI can update safely.
    """

    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        input_files: List[str],
        external_audio: Optional[str] = None,
        resolution: str = "1080p",
    ) -> None:
        super().__init__()
        self.input_files = input_files
        self.external_audio = external_audio
        self.resolution = resolution

    def run(self) -> None:
        """
        Execute the processing pipeline and forward emitted signals.

        This method is intended to be called when the QThread starts.
        """
        pipeline = ProcessingPipeline(self.input_files, ProcessingSignals())
        # forward pipeline signals to our own signals
        pipeline.signals.progress.connect(self.progress.emit)
        pipeline.signals.finished.connect(self.finished.emit)
        pipeline.signals.error.connect(self.error.emit)
        try:
            pipeline.run(external_audio=self.external_audio, resolution=self.resolution)
        except Exception as exc:
            # propagate unexpected errors
            self.error.emit(str(exc))
