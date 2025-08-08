"""High‑level orchestration of the video processing workflow."""

from typing import List, Optional

from ..utils.signals import ProcessingSignals


class ProcessingPipeline:
    """Pipeline that merges multiple videos based on active speaker detection."""

    def __init__(self, input_files: List[str], signals: ProcessingSignals) -> None:
        self.input_files = input_files
        self.signals = signals

    def run(self, external_audio: Optional[str] = None, resolution: str = "1080p") -> None:
        """
        Execute the processing pipeline (stub).

        The actual implementation will extract audio, perform active speaker
        detection, optionally synchronise external audio, merge the video
        segments and emit progress updates.
        """
        # Placeholder implementation
        self.signals.progress.emit(0)
        dummy_output_path = ""
        self.signals.finished.emit(dummy_output_path)
