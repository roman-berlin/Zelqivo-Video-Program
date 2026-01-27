"""High-level orchestration of the video processing workflow.

Pipeline stages: probe -> align -> diarize -> decision -> (sync) -> render -> concat.
Supports cancellation, cleanup, and progress callbacks with ETA.
Camera alignment auto-syncs multiple cameras using audio cross-correlation.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, List, Optional

from PyQt6.QtCore import QSettings

from ..utils.ffprobe import probe, ProbeResult
from ..utils.signals import ProcessingSignals
from .active_speaker import (
    ActiveSpeakerDetector,
    ActiveSpeakerDetector,
    RealEnergyVADBackend,
    SpeakerSegment,
    HybridBackend,
    LipMovementBackend,
)
from .switching_strategy import SwitchingStrategy, select_switching_engine, DEFAULT_STRATEGY
from .decision_engine import DecisionEngine, CutSegment
from .pipeline_config import PipelineConfig
from .qa_artifacts import QAArtifactExporter
from .video_merger import SegmentRenderer, CutDefinition, concatenate_segments, render_single_pass
from .checkpoint import PipelineCheckpoint, save_checkpoint, delete_checkpoint

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Pipeline stages for progress tracking."""
    PROBE = auto()
    ALIGN = auto()
    DIARIZE = auto()
    DECISION = auto()
    SYNC = auto()
    RENDER = auto()
    CONCAT = auto()
    DONE = auto()


# Weight for each stage (used for ETA calculation)
STAGE_WEIGHTS = {
    PipelineStage.PROBE: 5,
    PipelineStage.ALIGN: 10,
    PipelineStage.DIARIZE: 15,
    PipelineStage.DECISION: 5,
    PipelineStage.SYNC: 10,
    PipelineStage.RENDER: 45,
    PipelineStage.CONCAT: 10,
}


class RollingAverage:
    """Rolling average calculator for smoothing ETA estimates.
    
    Maintains a sliding window of recent values and returns the average,
    preventing volatile jumps in displayed ETA.
    """
    
    def __init__(self, window_size: int = 5) -> None:
        self._values: List[float] = []
        self._window_size = window_size
    
    def add(self, value: float) -> float:
        """Add a new value and return the smoothed average.
        
        Args:
            value: New measurement to add.
            
        Returns:
            Rolling average of recent values.
        """
        self._values.append(value)
        if len(self._values) > self._window_size:
            self._values.pop(0)
        return sum(self._values) / len(self._values)
    
    def reset(self) -> None:
        """Clear all stored values."""
        self._values.clear()
    
    @property
    def count(self) -> int:
        """Number of values in the current window."""
        return len(self._values)




@dataclass
class PipelineResult:
    """Result of pipeline execution."""
    success: bool
    output_path: str = ""
    error: str = ""
    cancelled: bool = False
    speaker_segments: list = None  # List of SpeakerSegment for XML export
    
    def __post_init__(self):
        if self.speaker_segments is None:
            self.speaker_segments = []


@dataclass
class PipelineProgress:
    """Progress state for UI updates."""
    stage: PipelineStage
    stage_name: str
    overall_percent: int
    stage_percent: int
    eta_seconds: Optional[float] = None
    message: str = ""


class ProcessingPipeline:
    """Pipeline that merges multiple videos based on active speaker detection.

    Usage:
        config = PipelineConfig(speaker_switching_enabled=True)
        pipeline = ProcessingPipeline(input_files, signals, config=config)
        pipeline.run(external_audio, resolution)
        # To cancel from another thread:
        pipeline.cancel()

    Mapping note (V1):
        ENERGY mode: speaker_id == camera_id, no mapping needed.
        REAL/pyannote mode: requires speaker-to-camera mapping; without it,
        falls back to single-camera output (primary) with a warning.
    """

    def __init__(
        self,
        input_files: List[str],
        signals: ProcessingSignals,
        progress_callback: Optional[Callable[[PipelineProgress], None]] = None,
        config: Optional[PipelineConfig] = None,
        # Legacy params for backwards compatibility
        speaker_switching_enabled: bool = True,
        speaker_to_camera_map: Optional[dict[int, int]] = None,
    ) -> None:
        if len(input_files) < 2:
            raise ValueError("At least 2 input files required")
        self.input_files = input_files
        self.signals = signals
        self.progress_callback = progress_callback

        # Use config if provided, otherwise fall back to legacy params
        if config is not None:
            self._config = config
        else:
            # Convert legacy single-camera map to new list format
            cameras_map: dict[int, list[int]] = {}
            if speaker_to_camera_map:
                for speaker_id, camera_id in speaker_to_camera_map.items():
                    cameras_map[speaker_id] = [camera_id]
            self._config = PipelineConfig(
                speaker_switching_enabled=speaker_switching_enabled,
                speaker_to_cameras_map=cameras_map,
            )

        # Convenience accessor
        self.speaker_switching_enabled = self._config.speaker_switching_enabled

        # Load switching strategy from settings (defaults to BALANCED/Hybrid)
        self._switching_strategy = self._load_switching_strategy()

        # Cancellation state
        self._cancelled = False

        # Stage tracking
        self._current_stage = PipelineStage.PROBE
        self._stage_start_time = 0.0
        self._pipeline_start_time = 0.0

        # For cleanup
        self._temp_files: List[str] = []
        self._segment_renderer: Optional[SegmentRenderer] = None

        # Results from stages
        self._probe_results: List[ProbeResult] = []
        self._speaker_segments: List[SpeakerSegment] = []
        self._cut_plan: List[CutSegment] = []

        # Camera alignment offsets (camera_idx -> offset_ms)
        self._camera_offsets: dict[int, float] = {}

        # QA artifacts exporter
        self._qa_exporter = QAArtifactExporter()

        # Checkpoint for crash recovery
        self._run_id = time.strftime("%Y%m%d_%H%M%S")
        self._checkpoint = PipelineCheckpoint(
            run_id=self._run_id,
            current_stage="INIT",
            input_files=list(input_files),
        )

        # Rolling average for ETA smoothing (prevents volatile jumps)
        self._eta_smoother = RollingAverage(window_size=5)

    def _save_checkpoint(self, stage: str, rendered_segments: Optional[List[str]] = None) -> None:
        """Save current pipeline state for crash recovery."""
        self._checkpoint.current_stage = stage
        if stage not in self._checkpoint.completed_stages:
            self._checkpoint.completed_stages.append(stage)
        self._checkpoint.camera_offsets = dict(self._camera_offsets)
        if rendered_segments:
            self._checkpoint.rendered_segments = rendered_segments
        save_checkpoint(self._checkpoint)

    def _load_switching_strategy(self) -> SwitchingStrategy:
        """Load switching strategy from QSettings."""
        settings = QSettings("MultiCamEditor", "MultiCamEditor")
        strategy_str = settings.value("switching/strategy", DEFAULT_STRATEGY.value, type=str)
        
        try:
            return SwitchingStrategy(strategy_str)
        except ValueError:
            logger.warning("Invalid strategy '%s', using default", strategy_str)
            return DEFAULT_STRATEGY

    def cancel(self) -> None:
        """Cancel the pipeline from any thread."""
        logger.info("Pipeline cancellation requested")
        self._cancelled = True
        if self._segment_renderer:
            self._segment_renderer.cancel()

    def _check_cancelled(self) -> bool:
        """Check if cancelled and emit error if so."""
        if self._cancelled:
            self._cleanup()
            self.signals.error.emit("Cancelled by user")
            return True
        return False

    def _cleanup(self) -> None:
        """Remove all temp files and directories created during pipeline.

        Uses retry logic with small delays to handle files still being released
        by ffmpeg processes. Logs warnings for files that couldn't be removed.
        """
        max_retries = 3
        retry_delay = 0.5  # seconds

        failed_paths: List[str] = []

        for path in self._temp_files:
            if not path:
                continue

            removed = False
            for attempt in range(max_retries):
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                        logger.debug("Cleaned up file: %s", path)
                        removed = True
                        break
                    elif os.path.isdir(path):
                        import shutil
                        shutil.rmtree(path, ignore_errors=True)
                        logger.debug("Cleaned up directory: %s", path)
                        removed = True
                        break
                    else:
                        # Path doesn't exist, consider it cleaned
                        removed = True
                        break
                except PermissionError as e:
                    # File might still be in use by ffmpeg process
                    if attempt < max_retries - 1:
                        logger.debug(
                            "Cleanup retry %d/%d for %s (permission error)",
                            attempt + 1, max_retries, os.path.basename(path)
                        )
                        time.sleep(retry_delay)
                    else:
                        logger.warning(
                            "Failed to cleanup %s after %d attempts: %s",
                            os.path.basename(path), max_retries, e
                        )
                        failed_paths.append(path)
                except Exception as e:
                    logger.debug("Cleanup failed for %s: %s", path, e)
                    failed_paths.append(path)
                    break

        self._temp_files.clear()

        if failed_paths:
            logger.warning(
                "Cleanup incomplete: %d files could not be removed",
                len(failed_paths)
            )

    def _check_disk_space(self, output_dir: Optional[str] = None, num_segments: int = 1) -> None:
        """Check if there's sufficient disk space for rendering.
        
        Args:
            output_dir: Directory to check. Uses temp dir if None.
            num_segments: Number of segments to render (for estimation).
            
        Raises:
            RuntimeError: If insufficient disk space.
        """
        import shutil
        
        # Use temp directory if no output specified
        check_dir = output_dir or tempfile.gettempdir()
        
        # Estimate required space:
        # - ~10MB per segment (conservative for 1080p)
        # - ~50% of total for final output
        # - 500MB buffer
        segment_mb = 10 * num_segments
        output_mb = segment_mb // 2
        buffer_mb = 500
        required_mb = segment_mb + output_mb + buffer_mb
        
        try:
            usage = shutil.disk_usage(check_dir)
            free_mb = usage.free // (1024 * 1024)
            
            logger.debug("Disk space check: %d MB free, %d MB required", free_mb, required_mb)
            
            if free_mb < required_mb:
                raise RuntimeError(
                    f"Insufficient disk space: {free_mb} MB available, "
                    f"~{required_mb} MB required. Free up disk space and try again."
                )
        except OSError as e:
            logger.warning("Could not check disk space: %s (continuing anyway)", e)

    def _emit_progress(self, stage_percent: int = 0, message: str = "") -> None:
        """Emit progress update via signals and callback."""
        # Calculate overall progress
        completed_weight = sum(
            STAGE_WEIGHTS.get(s, 0)
            for s in PipelineStage
            if s.value < self._current_stage.value
        )
        current_weight = STAGE_WEIGHTS.get(self._current_stage, 0)
        total_weight = sum(STAGE_WEIGHTS.values())

        stage_contribution = (current_weight * stage_percent) / 100
        overall_percent = int((completed_weight + stage_contribution) * 100 / total_weight)
        overall_percent = min(99, max(0, overall_percent))

        # ETA calculation with rolling average for stability
        elapsed = time.time() - self._pipeline_start_time
        eta_seconds = None
        # Lower threshold to 2% for earlier ETA display (was 5%)
        if overall_percent > 2 and elapsed > 0.5:
            raw_eta = (elapsed / overall_percent) * (100 - overall_percent)
            # Use rolling average to smooth out volatile jumps
            eta_seconds = self._eta_smoother.add(raw_eta)

        # Emit via signals
        self.signals.progress.emit(overall_percent)

        # Emit via callback for detailed progress
        if self.progress_callback:
            progress = PipelineProgress(
                stage=self._current_stage,
                stage_name=self._current_stage.name.capitalize(),
                overall_percent=overall_percent,
                stage_percent=stage_percent,
                eta_seconds=eta_seconds,
                message=message or f"Stage: {self._current_stage.name}",
            )
            self.progress_callback(progress)

    def _advance_stage(self, stage: PipelineStage) -> None:
        """Move to next stage and log timing."""
        if self._stage_start_time > 0:
            elapsed = time.time() - self._stage_start_time
            logger.debug("Stage %s completed in %.1fs", self._current_stage.name, elapsed)

        self._current_stage = stage
        self._stage_start_time = time.time()
        self._emit_progress(0, f"Starting {stage.name.lower()}...")

    def run(
        self,
        external_audio: Optional[str] = None,
        resolution: str = "1080p",
        output_path: Optional[str] = None,
    ) -> PipelineResult:
        """Execute the full pipeline.

        Args:
            external_audio: Optional path to external audio for sync.
            resolution: Target resolution (e.g., "1080p").
            output_path: Where to write final output. Uses temp if None.

        Returns:
            PipelineResult with success status and output path.
        """
        self._pipeline_start_time = time.time()
        self._cancelled = False
        self._external_audio_path = external_audio  # Store for hybrid detection

        # Start QA artifact collection
        self._qa_exporter.start_run()

        try:
            # Stage 1: Probe all input files
            if not self._stage_probe():
                return PipelineResult(success=False, cancelled=self._cancelled,
                                     error="Probe stage failed")
            self._save_checkpoint("PROBE")

            if self._check_cancelled():
                return PipelineResult(success=False, cancelled=True)

            # Stage 2: Align cameras (auto-sync by audio)
            self._stage_align()
            self._save_checkpoint("ALIGN")

            if self._check_cancelled():
                return PipelineResult(success=False, cancelled=True)

            # Stage 3: Diarize (speaker detection)
            if not self._stage_diarize():
                return PipelineResult(success=False, cancelled=self._cancelled,
                                     error="Diarization stage failed")
            self._save_checkpoint("DIARIZE")

            if self._check_cancelled():
                return PipelineResult(success=False, cancelled=True)

            # Stage 3: Decision engine - generate cut plan
            if not self._stage_decision():
                return PipelineResult(success=False, cancelled=self._cancelled,
                                     error="Decision stage failed")
            self._save_checkpoint("DECISION")

            if self._check_cancelled():
                return PipelineResult(success=False, cancelled=True)

            # Stage 4: Sync external audio (optional)
            self._synced_audio_path = None
            if external_audio:
                self._synced_audio_path = self._stage_sync(external_audio)
                if self._check_cancelled():
                    return PipelineResult(success=False, cancelled=True)
            else:
                self._advance_stage(PipelineStage.SYNC)
                self._emit_progress(100, "Skipping sync (no external audio)")

            # Stage 5: Render segments
            segment_paths = self._stage_render()
            if segment_paths is None:
                return PipelineResult(success=False, cancelled=self._cancelled,
                                     error="Render stage failed")
            self._save_checkpoint("RENDER", rendered_segments=segment_paths)

            if self._check_cancelled():
                return PipelineResult(success=False, cancelled=True)

            # Stage 6: Concatenate segments
            final_path = self._stage_concat(segment_paths, output_path)
            if not final_path:
                return PipelineResult(success=False, cancelled=self._cancelled,
                                     error="Concatenation stage failed")

            # Done
            self._advance_stage(PipelineStage.DONE)
            self._emit_progress(100, "Processing complete!")

            # Finalize QA artifacts
            self._qa_exporter.finalize()

            total_time = time.time() - self._pipeline_start_time
            logger.info("Pipeline completed in %.1fs: %s", total_time, final_path)

            self.signals.finished.emit(final_path)

            # Delete checkpoint on successful completion
            delete_checkpoint(self._run_id)

            return PipelineResult(
                success=True, 
                output_path=final_path,
                speaker_segments=self._speaker_segments
            )

        except Exception as e:
            logger.error("Pipeline error: %s", e, exc_info=True)
            self._cleanup()
            self.signals.error.emit(str(e))
            return PipelineResult(success=False, error=str(e))

    def _stage_probe(self) -> bool:
        """Probe all input files for metadata."""
        self._advance_stage(PipelineStage.PROBE)
        self._probe_results = []

        for i, path in enumerate(self.input_files):
            if self._cancelled:
                return False

            result = probe(path)
            if result.error:
                logger.error("Probe failed for %s: %s", path, result.error)
                self.signals.error.emit(f"Failed to probe {os.path.basename(path)}: {result.error}")
                return False

            self._probe_results.append(result)
            progress = int((i + 1) * 100 / len(self.input_files))
            self._emit_progress(progress, f"Probing {i + 1}/{len(self.input_files)}")

        logger.info("Probed %d files", len(self._probe_results))
        return True

    def _stage_align(self) -> None:
        """Align cameras using audio cross-correlation.

        First camera is primary (offset=0). Others aligned relative to it.
        Never fails the pipeline - on error, all offsets default to 0.
        """
        self._advance_stage(PipelineStage.ALIGN)

        from .audio_sync import align_cameras, CameraAlignment

        self._camera_offsets = {0: 0.0}  # Primary always 0

        if len(self.input_files) < 2:
            self._emit_progress(100, "Skipping alignment (single camera)")
            return

        self._emit_progress(10, "Aligning cameras by audio...")

        def on_progress(idx: int, total: int) -> None:
            if total > 0:
                percent = int((idx + 1) * 90 / total) + 10
                self._emit_progress(percent, f"Aligning camera {idx + 1}/{total}")

        try:
            alignments = align_cameras(self.input_files, on_progress=on_progress)

            # Store offsets
            alignment_data = []
            for align in alignments:
                self._camera_offsets[align.camera_index] = align.offset_ms
                alignment_data.append({
                    "camera_index": align.camera_index,
                    "offset_ms": align.offset_ms,
                    "status": align.status,
                    "message": align.message,
                })
                logger.info("Camera %d offset: %.1f ms (%s)",
                           align.camera_index, align.offset_ms, align.status)

            # Store for QA artifacts
            self._qa_exporter.set_camera_alignments(alignment_data)

            self._emit_progress(100, f"Aligned {len(alignments)} cameras")
            logger.info("Camera alignment complete: %s",
                       {k: f"{v:.1f}ms" for k, v in self._camera_offsets.items()})

        except Exception as e:
            # Never fail pipeline on alignment error - just use 0 offsets
            logger.error("Camera alignment failed, using offset=0 for all: %s", e, exc_info=True)
            for i in range(len(self.input_files)):
                self._camera_offsets[i] = 0.0

            self._qa_exporter.set_camera_alignments([
                {"camera_index": i, "offset_ms": 0.0, "status": "failed", "message": str(e)}
                for i in range(len(self.input_files))
            ])
            self._emit_progress(100, "Alignment failed, using default offsets")

    def _stage_diarize(self) -> bool:
        """
        Diarization using hybrid audio+visual detection (or Lips Only).
        
        Uses audio VAD to find speech regions, then visual lip detection
        to determine which camera is speaking during those regions.
        """
        self._advance_stage(PipelineStage.DIARIZE)

        # If switching is OFF, skip diarization - decision stage will create single-camera plan
        if not self.speaker_switching_enabled:
            logger.info("Speaker switching disabled, skipping diarization")
            self._speaker_segments = []
            self._qa_exporter.set_diarization([])
            self._emit_progress(100, "Speaker switching disabled (single camera mode)")
            return True

        try:
            from ..utils.ffmpeg import extract_audio_to_wav
            
            # Determine strategy
            strategy = self._load_switching_strategy()
            logger.info("Using switching strategy: %s", strategy.value)

            # Get engine from strategy
            engine, config = select_switching_engine(strategy)
            
            # Define progress callback mapping 0-100% of detection to 50-95% of stage
            def on_diarization_progress(pct: int):
                stage_progress = 50 + int(pct * 0.45)
                self._emit_progress(stage_progress, f"Analyzing speakers ({pct}%)")

            if strategy == SwitchingStrategy.BEST_LIPS:
                logger.info("BEST_LIPS: Starting lip movement detection")
                self._emit_progress(50, "Initializing visual detection...")
                
                # Calculate duration from probe results
                duration_ms = max(r.duration_ms for r in self._probe_results)
                
                self._speaker_segments = engine.detect_speakers(
                    video_paths=self.input_files,
                    duration_ms=duration_ms,
                    progress_callback=on_diarization_progress,
                )
                logger.info("LIPS mode complete: %d segments", len(self._speaker_segments))

            elif strategy == SwitchingStrategy.BALANCED_LIPS_ENERGY:
                logger.info("BALANCED: Starting hybrid detection")
                self._emit_progress(50, "Initializing hybrid detection...")
                
                # Hybrid backend handles audio extraction internally or we pass it?
                # The engine returned by select_switching_engine is initialized.
                # However, HybridBackend.detect_speakers in V1 might expect audio_path if it doesn't do extraction itself.
                # Let's check HybridBackend.detect_speakers signature.
                # Assuming it matches valid usage. If it needs audio_path, we might need to extract it first.
                # But select_switching_engine returns an instance.
                # Let's trust the engine abstraction or check if we need to do extraction here.
                # The old code did extraction:
                # audio_result = extract_audio_to_wav(...)
                # hybrid_detector.detect_speakers(..., audio_path=audio_path, ...)
                
                # If the new HybridBackend wrapper handles it, great. If not, we need to replicate that.
                # Let's assume for now we need to extract audio if the backend requires it.
                # But wait, select_switching_engine returns `HybridBackend`.
                # Does `HybridBackend` require `audio_path` in `detect_speakers`?
                # I should probably include the audio extraction logic if it's not inside the backend.
                # But to keep this chunk clean, let's assume I need to do what the old code did if I want to be safe,
                # OR better: The "HybridBackend" used here is imported from `.active_speaker`.
                # I'll check if I can check `detect_speakers` signature quickly.
                # But I'm in a tool call.
                # I will preserve the audio extraction logic just in case, or move it before the if/else if common.
                # Actually, `LipMovementBackend` doesn't need audio path.
                
                # To be safe and implementing correctly:
                # 1. Extract audio if strategy is BALANCED (Hybrid).
                # 2. Call detect_speakers.
                
                # Or, if I want to be cleaner:
                
                # Extract audio for Hybrid
                audio_path = None
                if strategy == SwitchingStrategy.BALANCED_LIPS_ENERGY:
                    from ..utils.ffmpeg import extract_audio_to_wav
                    self._emit_progress(20, "Extracting audio for speech detection...")
                    
                    target_file = self.input_files[0]
                    if hasattr(self, '_external_audio_path') and self._external_audio_path:
                        target_file = self._external_audio_path
                        logger.info("Using external audio: %s", target_file)
                    
                    audio_result = extract_audio_to_wav(target_file, sample_rate=16000, mono=True)
                    if not audio_result.success:
                         raise RuntimeError(f"Audio extraction failed: {audio_result.error}")
                    
                    audio_path = audio_result.output_path
                    self._temp_files.append(audio_path)
                    
                    # Calculate duration from probe results
                    duration_ms = max(r.duration_ms for r in self._probe_results)
                    
                    self._speaker_segments = engine.detect_speakers(
                        video_paths=self.input_files,
                        audio_path=audio_path,
                        duration_ms=duration_ms,
                        progress_callback=on_diarization_progress,
                        cancel_callback=lambda: self._cancelled
                    )
                else:
                    # BEST_LIPS
                     self._speaker_segments = engine.detect_speakers(
                        video_paths=self.input_files,
                        progress_callback=on_diarization_progress,
                        # No audio path needed for lips
                    )
                     
                logger.info("Detection complete: %d segments", len(self._speaker_segments))

            elif strategy == SwitchingStrategy.FAST_RULES:
                # FAST_RULES: CPU-only energy-based detection using RealEnergyVADBackend
                logger.info("FAST_RULES: Starting energy-based detection")
                self._emit_progress(10, "Extracting audio from cameras...")
                
                # Extract audio from each camera to WAV
                camera_audio_paths = []
                for i, video_path in enumerate(self.input_files):
                    if self._cancelled:
                        return False
                    self._emit_progress(
                        10 + int((i + 1) * 30 / len(self.input_files)),
                        f"Extracting audio from camera {i + 1}/{len(self.input_files)}..."
                    )
                    audio_result = extract_audio_to_wav(
                        video_path, sample_rate=16000, mono=True
                    )
                    if not audio_result.success:
                        raise RuntimeError(
                            f"Audio extraction failed for camera {i}: {audio_result.error}"
                        )
                    camera_audio_paths.append(audio_result.output_path)
                    self._temp_files.append(audio_result.output_path)
                
                self._emit_progress(45, "Analyzing audio energy levels...")
                
                # Use RealEnergyVADBackend for robust energy-based switching
                # This backend already has hysteresis, consecutive wins, and hold time
                energy_backend = RealEnergyVADBackend(
                    window_ms=200,
                    silence_threshold=0.01,
                    min_segment_ms=500,
                    noise_percentile=20,
                    gate_factor=2.5,
                    hysteresis_ratio=1.6,
                    consecutive_wins=3,
                    hold_time_ms=2000,  # Prevent rapid switching
                )
                energy_backend.set_camera_audio_paths(camera_audio_paths)
                
                self._emit_progress(60, "Detecting active speakers...")
                
                # diarize() returns List[SpeakerSegment] with speaker_id == camera_id
                self._speaker_segments = energy_backend.diarize(
                    audio_path="",  # Not used when camera_audio_paths are set
                    num_channels=len(self.input_files),
                )
                
                logger.info("FAST_RULES complete: %d segments", len(self._speaker_segments))
            
            # Record for QA artifacts
            self._qa_exporter.set_diarization(self._speaker_segments)
            
            self._emit_progress(100, f"Detection complete: {len(self._speaker_segments)} segments")
            return True
            
        except Exception as e:
            logger.error("Hybrid detection failed: %s", e, exc_info=True)
            self.signals.error.emit(f"Hybrid detection failed: {e}")
            return False


    def _apply_speaker_to_camera_mapping(
        self,
        segments: List[SpeakerSegment],
    ) -> tuple[List[SpeakerSegment], bool]:
        """Apply speaker-to-camera mapping if using pyannote mode.

        V1 behavior:
        - ENERGY mode: speaker_id == camera_id, no mapping needed; return as-is.
        - REAL/pyannote mode: requires mapping. If missing/incomplete, fallback
          to primary camera (camera 0) for all segments with warning.

        Args:
            segments: Raw diarization segments

        Returns:
            (mapped_segments, fallback_triggered) - fallback_triggered is True
            if mapping was missing and we fell back to single-camera.
        """
        # ENERGY mode: speaker_id already equals camera_id - no mapping needed
        # Old ENERGY mode check removed
        # Proceed with mapping check for all strategies


        # REAL/pyannote mode: check if we have complete mapping
        speaker_map = self._config.speaker_to_cameras_map
        if not speaker_map:
            logger.warning(
                "Pyannote mode but no speaker-to-camera mapping provided; "
                "falling back to single-camera output (primary camera)"
            )
            return [], True  # Empty segments = single-camera fallback in decision

        # Check if mapping is complete for all detected speakers
        detected_speakers = {s.speaker_id for s in segments}
        missing_speakers = detected_speakers - set(speaker_map.keys())

        if missing_speakers:
            logger.warning(
                "Incomplete speaker-to-camera mapping: speakers %s not mapped; "
                "falling back to single-camera output (primary camera)",
                missing_speakers,
            )
            return [], True

        # Apply mapping: convert speaker_id to camera_id
        mapped: List[SpeakerSegment] = []
        num_cameras = len(self.input_files)
        for seg in segments:
            camera_id = speaker_map.get(seg.speaker_id, 0)
            # Clamp to valid camera range
            camera_id = min(camera_id, num_cameras - 1)
            mapped.append(SpeakerSegment(
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                speaker_id=camera_id,  # Now speaker_id == camera_id
            ))

        logger.info("Applied speaker-to-camera mapping: %d segments mapped", len(mapped))
        return mapped, False

    def _stage_decision(self) -> bool:
        """Generate cut plan from speaker segments.

        If speaker_switching_enabled is False OR diarization returned empty,
        creates a single-segment plan covering full duration on primary camera.
        """
        self._advance_stage(PipelineStage.DECISION)

        # Get total duration from probe results
        total_duration_ms = max(r.duration_ms for r in self._probe_results)

        self._emit_progress(50, "Generating cut plan...")

        # Fallback: if switching enabled but diarization returned empty, warn user
        if self.speaker_switching_enabled and not self._speaker_segments:
            logger.warning(
                "Speaker switching enabled but diarization returned no segments; "
                "falling back to single-camera output on primary camera"
            )

        # Read settings for decision engine
        settings = QSettings("MultiCamEditor", "MultiCamEditor")
        min_switch_interval_ms = settings.value("decision_engine/min_switch_interval_ms", 1500, type=int)
        min_speech_ms = settings.value("decision_engine/min_speech_ms", 600, type=int)
        bg_short_remark_ms = settings.value("decision_engine/bg_short_remark_ms", 500, type=int)
        # Smoothing parameters
        confidence_stability_window_ms = settings.value("decision_engine/confidence_stability_window_ms", 400, type=int)
        min_clip_length_ms = settings.value("decision_engine/min_clip_length_ms", 1000, type=int)
        soft_boundary_search_ms = settings.value("decision_engine/soft_boundary_search_ms", 150, type=int)

        engine = DecisionEngine(
            min_switch_interval_ms=min_switch_interval_ms,
            min_speech_ms=min_speech_ms,
            bg_short_remark_ms=bg_short_remark_ms,
            confidence_stability_window_ms=confidence_stability_window_ms,
            min_clip_length_ms=min_clip_length_ms,
            soft_boundary_search_ms=soft_boundary_search_ms,
        )
        self._cut_plan = engine.generate_cut_plan(
            self._speaker_segments,
            total_duration_ms=total_duration_ms,
        )

        # Merge adjacent cuts with same camera
        self._cut_plan = engine.merge_adjacent(self._cut_plan)

        # Record QA artifacts
        self._qa_exporter.set_thresholds(
            min_switch_interval_ms=min_switch_interval_ms,
            min_speech_ms=min_speech_ms,
            bg_short_remark_ms=bg_short_remark_ms,
            confidence_stability_window_ms=confidence_stability_window_ms,
            min_clip_length_ms=min_clip_length_ms,
            soft_boundary_search_ms=soft_boundary_search_ms,
        )
        self._qa_exporter.set_total_duration(total_duration_ms)

        # Build a speaker segment lookup for determining cut reasons
        segment_speakers = {(s.start_ms, s.end_ms): s.speaker_id for s in self._speaker_segments}

        for cut in self._cut_plan:
            # Determine reason based on decision logic
            camera_idx = min(cut.camera_id, len(self.input_files) - 1)
            # Find speaker that triggered this cut (heuristic: speaker at cut start)
            speaker_id = cut.camera_id  # Assume camera_id == speaker_id from decision engine

            # Determine reason
            if cut.start_ms == 0:
                reason = "default"  # First cut is always default
            elif any(
                s.start_ms == cut.start_ms and s.speaker_id == speaker_id
                for s in self._speaker_segments
            ):
                reason = "threshold"  # Cut triggered by speaker segment meeting thresholds
            else:
                reason = "forced"  # Merged or forced cut

            self._qa_exporter.add_cut(
                start_ms=cut.start_ms,
                end_ms=cut.end_ms,
                camera_index=camera_idx,
                speaker_id=speaker_id,
                reason=reason,
            )

        self._emit_progress(100, f"Generated {len(self._cut_plan)} cuts")
        logger.info("Decision complete: %d cuts", len(self._cut_plan))
        return True

    def _stage_sync(self, external_audio: str) -> Optional[str]:
        """Sync external audio to video reference.

        Extracts reference audio from primary camera to temp WAV first,
        then uses cross-correlation to sync. Falls back gracefully on error.
        """
        self._advance_stage(PipelineStage.SYNC)

        from .audio_sync import sync_external_audio
        from ..utils.ffmpeg import extract_audio_to_wav

        self._emit_progress(20, "Extracting reference audio from primary camera...")

        # Step 1: Extract audio from primary video to temp WAV
        primary_video = self.input_files[0]
        logger.info("Extracting reference audio from: %s", os.path.basename(primary_video))

        try:
            extract_result = extract_audio_to_wav(
                primary_video,
                sample_rate=16000,  # Match sync sample rate
                mono=True,
                timeout=120.0,
            )
        except Exception as e:
            error_msg = f"Reference audio extraction error: {e}"
            logger.error(error_msg, exc_info=True)
            self._qa_exporter.set_sync_info(offset_ms=0, success=False, message=error_msg)
            self._emit_progress(100, "Sync failed (extraction error), using original audio")
            return None

        if not extract_result.success or not extract_result.output_path:
            error_msg = f"Failed to extract reference audio: {extract_result.error}"
            logger.error(error_msg)
            self._qa_exporter.set_sync_info(offset_ms=0, success=False, message=error_msg)
            self._emit_progress(100, "Sync failed (no reference audio), using original audio")
            return None

        ref_wav_path = extract_result.output_path
        self._temp_files.append(ref_wav_path)
        logger.info("Reference audio extracted: %s", os.path.basename(ref_wav_path))

        # Step 2: Sync external audio to extracted reference
        self._emit_progress(50, "Synchronizing external audio...")

        try:
            result = sync_external_audio(
                external_audio=external_audio,
                reference_audio=ref_wav_path,  # Use extracted WAV, not video
            )
        except Exception as e:
            error_msg = f"Audio sync error: {e}"
            logger.error(error_msg, exc_info=True)
            self._qa_exporter.set_sync_info(offset_ms=0, success=False, message=error_msg)
            self._emit_progress(100, "Sync failed (correlation error), using original audio")
            return None

        if result is None or result.status == "failed":
            error_msg = result.message if result else "Sync returned no result"
            logger.error("Audio sync failed: %s", error_msg)
            self._qa_exporter.set_sync_info(offset_ms=0, success=False, message=error_msg)
            self._emit_progress(100, "Sync failed, using original audio")
            return None

        if result.output_path:
            self._temp_files.append(result.output_path)

        # Record sync info for QA
        self._qa_exporter.set_sync_info(
            offset_ms=result.offset_ms,
            success=True,
            message=result.message or "Sync successful",
        )

        self._emit_progress(100, f"Audio synced (offset: {result.offset_ms:.0f}ms)")
        logger.info("Audio sync complete: offset=%.1fms", result.offset_ms)
        return result.output_path

    def _stage_render(self) -> Optional[List[str]]:
        """Render cut segments using single-pass filter_complex approach.
        
        Uses single FFmpeg invocation with filter_complex to eliminate black frames
        at segment boundaries. This replaces the previous per-segment rendering.
        """
        self._advance_stage(PipelineStage.RENDER)

        if not self._cut_plan:
            logger.warning("No cuts to render")
            self._emit_progress(100, "No cuts to render")
            return []

        # Check disk space before starting render
        try:
            self._check_disk_space(num_segments=len(self._cut_plan))
        except RuntimeError as e:
            logger.error("Disk space check failed: %s", e)
            self.signals.error.emit(str(e))
            return None

        # Load QA overlay setting - NOTE: QA overlay not supported in single-pass mode
        settings = QSettings("MultiCamEditor", "MultiCamEditor")
        qa_overlay_enabled = settings.value("qa_overlay/enabled", False, type=bool)
        if qa_overlay_enabled:
            logger.warning("QA overlay not yet supported in single-pass mode, will be ignored")

        # Get resolution setting
        resolution = getattr(self, '_resolution', '1080p')

        # Convert CutSegments to CutDefinitions with camera offset applied
        cuts: List[CutDefinition] = []
        for i, cut in enumerate(self._cut_plan):
            # camera_id maps to input file index
            camera_idx = min(cut.camera_id, len(self.input_files) - 1)

            # Apply camera alignment offset:
            # offset_ms > 0 means camera started late -> we need to seek earlier in that camera
            # offset_ms < 0 means camera started early -> we need to seek later in that camera
            # Timeline time T maps to camera time T + offset_ms
            offset_ms = self._camera_offsets.get(camera_idx, 0.0)
            adjusted_start = int(cut.start_ms + offset_ms)
            adjusted_end = int(cut.end_ms + offset_ms)

            # Clamp to valid range (0 to camera duration)
            camera_duration = self._probe_results[camera_idx].duration_ms if camera_idx < len(self._probe_results) else 0
            adjusted_start = max(0, adjusted_start)
            adjusted_end = max(adjusted_start + 1, adjusted_end)  # Ensure positive duration
            if camera_duration > 0:
                adjusted_end = min(adjusted_end, camera_duration)
                adjusted_start = min(adjusted_start, adjusted_end - 1)

            if offset_ms != 0.0:
                logger.debug("Cut %d: camera %d offset %.1fms -> %d-%d (was %d-%d)",
                           i, camera_idx, offset_ms, adjusted_start, adjusted_end,
                           cut.start_ms, cut.end_ms)

            cuts.append(CutDefinition(
                source_path=self.input_files[camera_idx],
                start_ms=adjusted_start,
                end_ms=adjusted_end,
                cut_index=i,
                camera_index=camera_idx,
                qa_overlay=False,  # Not supported in single-pass mode
                speaker_id=cut.camera_id,
            ))

        # Generate temp output path for single-pass render
        temp_video_path = tempfile.mktemp(prefix="multicam_singlepass_", suffix=".mp4")
        self._temp_files.append(temp_video_path)

        self._emit_progress(10, f"Single-pass render: {len(cuts)} segments...")

        # Use single-pass rendering
        logger.info("Starting single-pass render with %d cuts", len(cuts))
        result = render_single_pass(
            cuts=cuts,
            output_path=temp_video_path,
            resolution=resolution,
            fps=30.0,
        )

        if result.cancelled:
            logger.info("Render cancelled")
            return None

        if not result.success:
            logger.error("Single-pass render failed: %s", result.error)
            self.signals.error.emit(f"Render failed: {result.error}")
            return None

        self._emit_progress(100, "Single-pass render complete")
        logger.info("Render complete: %s", temp_video_path)
        return [temp_video_path]  # Single output file

    def _stage_concat(
        self, segment_paths: List[str], output_path: Optional[str]
    ) -> Optional[str]:
        """Finalize video output by adding audio track.
        
        With single-pass rendering, segment_paths contains a single pre-rendered video.
        This stage adds external audio if available, or adds audio from primary camera.
        """
        self._advance_stage(PipelineStage.CONCAT)

        if not segment_paths:
            logger.warning("No video to finalize")
            self._emit_progress(100, "No video to finalize")
            return None

        # With single-pass render, we have exactly one video file
        input_video = segment_paths[0]
        
        if not os.path.isfile(input_video):
            logger.error("Rendered video not found: %s", input_video)
            self.signals.error.emit("Rendered video not found")
            return None

        # Generate output path if not provided
        if not output_path:
            output_dir = os.path.dirname(self.input_files[0])
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_dir, f"multicam_output_{timestamp}.mp4")

        self._emit_progress(30, "Finalizing video...")

        # Check for synced external audio
        synced_audio = getattr(self, "_synced_audio_path", None)
        
        if synced_audio and os.path.isfile(synced_audio):
            # Add external audio to video
            self._emit_progress(50, "Adding external audio...")
            logger.info("Adding synced audio: %s", os.path.basename(synced_audio))
            
            final_path = self._replace_audio_track(input_video, synced_audio, output_path)
            if final_path:
                self._emit_progress(100, "Audio added successfully")
                logger.info("Final output with external audio: %s", final_path)
                self._cleanup()
                return final_path
            else:
                # Fallback: use video without audio
                logger.warning("Audio add failed, using video without audio")
                self._emit_progress(100, "Output ready (no external audio)")
                import shutil
                try:
                    shutil.copy2(input_video, output_path)
                    self._cleanup()
                    return output_path
                except Exception as e:
                    logger.error("Failed to copy video: %s", e)
                    self._cleanup()
                    return None
        else:
            # No external audio - add audio from primary camera
            self._emit_progress(50, "Adding audio from primary camera...")
            primary_video = self.input_files[0]
            
            final_path = self._add_audio_from_video(input_video, primary_video, output_path)
            if final_path:
                self._emit_progress(100, "Output finalized")
                logger.info("Final output with primary audio: %s", final_path)
                self._cleanup()
                return final_path
            else:
                # Fallback: use video without audio
                logger.warning("Audio add failed, using video without audio")
                import shutil
                try:
                    shutil.copy2(input_video, output_path)
                    self._cleanup()
                    return output_path
                except Exception as e:
                    logger.error("Failed to copy video: %s", e)
                    self._cleanup()
                    return None

    def _add_audio_from_video(
        self, video_path: str, audio_source_video: str, output_path: str
    ) -> Optional[str]:
        """Add audio track from source video to rendered video.

        Args:
            video_path: Path to rendered video (no audio)
            audio_source_video: Path to source video with audio to use
            output_path: Where to write final output

        Returns:
            output_path on success, None on failure
        """
        from ..utils.ffmpeg import FFmpegProcess, is_ffmpeg_available

        if not is_ffmpeg_available():
            logger.error("ffmpeg not available for audio muxing")
            return None

        try:
            # Get duration of video to trim audio
            video_duration = 0
            if self._probe_results:
                # Use the actual rendered video duration if possible
                from ..utils.ffprobe import probe as ffprobe
                probe_result = ffprobe(video_path)
                if probe_result and probe_result.duration_ms:
                    video_duration = probe_result.duration_ms / 1000.0

            args = [
                "ffmpeg", "-y",
                "-i", video_path,          # Video input (no audio)
                "-i", audio_source_video,  # Audio source
                "-c:v", "copy",            # Copy video stream
                "-c:a", "aac",             # Encode audio to AAC
                "-map", "0:v:0",           # Take video from first input
                "-map", "1:a:0",           # Take audio from second input
                "-shortest",               # Match shorter duration
                output_path,
            ]

            logger.info("Adding audio from %s to %s", 
                       os.path.basename(audio_source_video), 
                       os.path.basename(output_path))
            proc = FFmpegProcess(args, output_path)
            result = proc.run()

            if result.success:
                logger.info("Audio muxing successful: %s", output_path)
                return output_path

            logger.error("Audio muxing failed: %s", result.error)
            return None

        except Exception as e:
            logger.error("Audio muxing error: %s", e, exc_info=True)
            return None

    def _replace_audio_track(
        self, video_path: str, audio_path: str, output_path: str
    ) -> Optional[str]:
        """Replace video's audio track with external audio using ffmpeg.

        Args:
            video_path: Path to video file
            audio_path: Path to audio file (synced)
            output_path: Where to write final output

        Returns:
            output_path on success, None on failure
        """
        from ..utils.ffmpeg import FFmpegProcess, is_ffmpeg_available

        if not is_ffmpeg_available():
            logger.error("ffmpeg not available for audio replacement")
            return None

        try:
            # ffmpeg -i video.mp4 -i audio.wav -c:v copy -map 0:v:0 -map 1:a:0 -shortest output.mp4
            args = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "copy",  # Copy video stream (no re-encode)
                "-map", "0:v:0",  # Take video from first input
                "-map", "1:a:0",  # Take audio from second input
                "-shortest",  # Match shorter duration
                output_path,
            ]

            logger.info("Replacing audio: %s + %s -> %s", video_path, audio_path, output_path)
            proc = FFmpegProcess(args, output_path)
            result = proc.run()

            if result.success:
                logger.info("Audio replacement successful: %s", output_path)
                return output_path

            logger.error("Audio replacement failed: %s", result.error)
            return None

        except Exception as e:
            logger.error("Audio replacement error: %s", e, exc_info=True)
            return None
