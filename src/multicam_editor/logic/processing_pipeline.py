"""High‑level orchestration of the video processing workflow."""

from __future__ import annotations

import time
from typing import List, Optional

# Import the ProcessingSignals class from our package's utils module via a
# relative import.  This avoids relying on the Python path outside of the
# package context, which can break when the package is installed.
from ..utils.signals import ProcessingSignals


class ProcessingPipeline:
    """Pipeline that merges multiple videos based on active speaker detection."""

    def __init__(self, input_files: List[str], signals: ProcessingSignals) -> None:
        self.input_files = input_files
        self.signals = signals  # why: allow UI to subscribe without tight coupling

    def run(self, external_audio: Optional[str] = None, resolution: str = "1080p") -> None:
        """Simulate work and emit progress/finished."""
        for percent in range(0, 101, 20):
            time.sleep(0.4)
            self.signals.progress.emit(percent)
        # No real output yet — emit empty string to indicate "no file"
        self.signals.finished.emit("")