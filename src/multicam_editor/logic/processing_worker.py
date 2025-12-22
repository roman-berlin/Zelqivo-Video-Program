"""Worker class to run the processing pipeline on a separate thread."""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ..utils.signals import ProcessingSignals
from .processing_pipeline import ProcessingPipeline, PipelineProgress

logger = logging.getLogger(__name__)


class ProcessingWorker(QObject):
    """Run the processing pipeline inside a QThread.

    Signals:
        progress(int): Overall progress 0-100.
        stage(str, int, str, float): Stage name, stage percent, message, eta_seconds.
        finished(str): Output path on success.
        error(str): Error message on failure.

    Usage:
        worker = ProcessingWorker(files)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.start()
        # To cancel:
        worker.cancel()
    """

    progress = pyqtSignal(int)
    stage = pyqtSignal(str, int, str, float)  # stage_name, stage_percent, message, eta_seconds
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        input_files: List[str],
        external_audio: Optional[str] = None,
        resolution: str = "1080p",
        output_path: Optional[str] = None,
        speaker_switching_enabled: bool = True,
        camera_speaker_mapping: Optional[dict[int, str]] = None,
    ) -> None:
        super().__init__()
        self.input_files = input_files
        self.external_audio = external_audio
        self.resolution = resolution
        self.output_path = output_path
        self.speaker_switching_enabled = speaker_switching_enabled
        self.camera_speaker_mapping = camera_speaker_mapping or {}
        self._pipeline: Optional[ProcessingPipeline] = None

    def cancel(self) -> None:
        """Cancel the running pipeline."""
        logger.info("Worker cancellation requested")
        if self._pipeline:
            self._pipeline.cancel()

    def _on_progress_callback(self, progress: PipelineProgress) -> None:
        """Handle detailed progress from pipeline."""
        eta = progress.eta_seconds if progress.eta_seconds is not None else -1.0
        self.stage.emit(
            progress.stage_name,
            progress.stage_percent,
            progress.message,
            eta,
        )

    def run(self) -> None:
        """Execute the processing pipeline and forward emitted signals."""
        signals = ProcessingSignals()
        signals.progress.connect(self.progress.emit)
        signals.finished.connect(self.finished.emit)
        signals.error.connect(self.error.emit)

        try:
            # Convert camera_speaker_mapping to speaker_to_camera_map for pipeline
            # Note: V1 ENERGY mode ignores mapping (speaker_id == camera_id)
            speaker_to_camera = None
            if self.camera_speaker_mapping:
                # Mapping format: {camera_id: speaker_name} -> not used in V1
                logger.debug("camera_speaker_mapping provided: %s (ignored in ENERGY mode)",
                           self.camera_speaker_mapping)

            self._pipeline = ProcessingPipeline(
                self.input_files,
                signals,
                progress_callback=self._on_progress_callback,
                speaker_switching_enabled=self.speaker_switching_enabled,
                speaker_to_camera_map=speaker_to_camera,
            )
            result = self._pipeline.run(
                external_audio=self.external_audio,
                resolution=self.resolution,
                output_path=self.output_path,
            )

            if result.cancelled:
                logger.info("Pipeline was cancelled")
            elif not result.success:
                logger.error("Pipeline failed: %s", result.error)

        except ValueError as ve:
            # Pipeline validation error (e.g., < 2 files)
            logger.error("Pipeline validation error: %s", ve)
            self.error.emit(str(ve))
        except Exception as exc:
            logger.error("Pipeline exception: %s", exc, exc_info=True)
            self.error.emit(str(exc))
        finally:
            self._pipeline = None


class ProcessingThread(QThread):
    """Convenience wrapper that manages QThread lifecycle.

    Usage:
        thread = ProcessingThread(files, external_audio, resolution)
        thread.progress.connect(on_progress)
        thread.finished_with_path.connect(on_finished)
        thread.error.connect(on_error)
        thread.start()
        # To cancel:
        thread.cancel()
    """

    progress = pyqtSignal(int)
    stage = pyqtSignal(str, int, str, float)  # stage_name, stage_percent, message, eta_seconds
    finished_with_path = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        input_files: List[str],
        external_audio: Optional[str] = None,
        resolution: str = "1080p",
        output_path: Optional[str] = None,
        speaker_switching_enabled: bool = True,
        camera_speaker_mapping: Optional[dict[int, str]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.input_files = input_files
        self.external_audio = external_audio
        self.resolution = resolution
        self.output_path = output_path
        self.speaker_switching_enabled = speaker_switching_enabled
        self.camera_speaker_mapping = camera_speaker_mapping or {}
        self._worker: Optional[ProcessingWorker] = None

    def cancel(self) -> None:
        """Cancel the processing."""
        if self._worker:
            self._worker.cancel()

    def run(self) -> None:
        """Thread entry point - creates and runs worker."""
        self._worker = ProcessingWorker(
            self.input_files,
            self.external_audio,
            self.resolution,
            self.output_path,
            self.speaker_switching_enabled,
            self.camera_speaker_mapping,
        )

        # Connect worker signals to thread signals
        self._worker.progress.connect(self.progress.emit)
        self._worker.stage.connect(self.stage.emit)
        self._worker.finished.connect(self.finished_with_path.emit)
        self._worker.error.connect(self.error.emit)

        # Run the worker
        self._worker.run()
        self._worker = None
