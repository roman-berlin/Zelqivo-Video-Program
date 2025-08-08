"""High‑level orchestration of the video processing workflow."""

import time
from typing import List, Optional

from ..utils.signals import ProcessingSignals


class ProcessingPipeline:
    """Pipeline that merges multiple videos based on active speaker detection."""

    def __init__(self, input_files: List[str], signals: ProcessingSignals) -> None:
        self.input_files = input_files
        self.signals = signals

    def run(self, external_audio: Optional[str] = None, resolution: str = "1080p") -> None:
        """
        Execute the processing pipeline.

        The current stub simulates progress updates and emits a finished signal
        when complete. In a real implementation this would perform audio/video
        processing and periodically emit progress between 0 and 100.
        """
        # Simulate work by emitting progress in steps
        for percent in range(0, 101, 20):
            time.sleep(0.5)  # simulate expensive computation
            self.signals.progress.emit(percent)
        # When processing is complete, emit the output path (placeholder here)
        dummy_output_path = ""  # replace with real output path when implemented
        self.signals.finished.emit(dummy_output_path)
