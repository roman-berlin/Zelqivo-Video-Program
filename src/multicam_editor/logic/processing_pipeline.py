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
from .active_speaker import ActiveSpeakerDetector, SpeakerSegment
from .decision_engine import DecisionEngine, CutSegment
from .qa_artifacts import QAArtifactExporter
from .video_merger import SegmentRenderer, CutDefinition, concatenate_segments

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


@dataclass
class PipelineResult:
    """Result of pipeline execution."""
    success: bool
    output_path: str = ""
    error: str = ""
    cancelled: bool = False


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
        pipeline = ProcessingPipeline(input_files, signals)
        pipeline.run(external_audio, resolution)
        # To cancel from another thread:
        pipeline.cancel()
    """

    def __init__(
        self,
        input_files: List[str],
        signals: ProcessingSignals,
        progress_callback: Optional[Callable[[PipelineProgress], None]] = None,
    ) -> None:
        if len(input_files) < 2:
            raise ValueError("At least 2 input files required")
        self.input_files = input_files
        self.signals = signals
        self.progress_callback = progress_callback

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
        """Remove all temp files created during pipeline."""
        for path in self._temp_files:
            if os.path.isfile(path):
                try:
                    os.remove(path)
                    logger.debug("Cleaned up: %s", path)
                except Exception as e:
                    logger.debug("Cleanup failed for %s: %s", path, e)
        self._temp_files.clear()

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

        # ETA calculation
        elapsed = time.time() - self._pipeline_start_time
        eta_seconds = None
        if overall_percent > 5 and elapsed > 1:
            eta_seconds = (elapsed / overall_percent) * (100 - overall_percent)

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

        # Start QA artifact collection
        self._qa_exporter.start_run()

        try:
            # Stage 1: Probe all input files
            if not self._stage_probe():
                return PipelineResult(success=False, cancelled=self._cancelled,
                                     error="Probe stage failed")

            if self._check_cancelled():
                return PipelineResult(success=False, cancelled=True)

            # Stage 2: Align cameras (auto-sync by audio)
            self._stage_align()

            if self._check_cancelled():
                return PipelineResult(success=False, cancelled=True)

            # Stage 3: Diarize (speaker detection)
            if not self._stage_diarize():
                return PipelineResult(success=False, cancelled=self._cancelled,
                                     error="Diarization stage failed")

            if self._check_cancelled():
                return PipelineResult(success=False, cancelled=True)

            # Stage 3: Decision engine - generate cut plan
            if not self._stage_decision():
                return PipelineResult(success=False, cancelled=self._cancelled,
                                     error="Decision stage failed")

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
            return PipelineResult(success=True, output_path=final_path)

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
        """Run speaker diarization on first video's audio."""
        self._advance_stage(PipelineStage.DIARIZE)

        # Use first video as reference for diarization
        # In production, this would extract audio and analyze all tracks
        detector = ActiveSpeakerDetector()

        try:
            # Stub: diarize using first video path as reference
            # Real implementation would extract audio track first
            self._emit_progress(50, "Analyzing speaker activity...")

            num_cameras = len(self.input_files)
            self._speaker_segments = detector.detect(
                self.input_files[0],  # Use as audio reference
                num_channels=num_cameras,
            )

            # Record for QA artifacts
            self._qa_exporter.set_diarization(self._speaker_segments)

            self._emit_progress(100, f"Found {len(self._speaker_segments)} speaker segments")
            logger.info("Diarization complete: %d segments", len(self._speaker_segments))
            return True

        except Exception as e:
            logger.error("Diarization failed: %s", e, exc_info=True)
            self.signals.error.emit(f"Diarization failed: {e}")
            return False

    def _stage_decision(self) -> bool:
        """Generate cut plan from speaker segments."""
        self._advance_stage(PipelineStage.DECISION)

        # Get total duration from probe results
        total_duration_ms = max(r.duration_ms for r in self._probe_results)

        self._emit_progress(50, "Generating cut plan...")

        # Read settings for decision engine
        settings = QSettings("MultiCamEditor", "MultiCamEditor")
        min_switch_interval_ms = settings.value("decision_engine/min_switch_interval_ms", 1500, type=int)
        min_speech_ms = settings.value("decision_engine/min_speech_ms", 600, type=int)
        bg_short_remark_ms = settings.value("decision_engine/bg_short_remark_ms", 500, type=int)

        engine = DecisionEngine(
            min_switch_interval_ms=min_switch_interval_ms,
            min_speech_ms=min_speech_ms,
            bg_short_remark_ms=bg_short_remark_ms,
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
        """Sync external audio to video reference."""
        self._advance_stage(PipelineStage.SYNC)

        from .audio_sync import sync_external_audio

        self._emit_progress(50, "Synchronizing external audio...")

        # Use first video as reference
        result = sync_external_audio(
            external_audio=external_audio,
            reference_audio=self.input_files[0],
        )

        if result is None or result.status == "failed":
            error_msg = result.message if result else "Sync failed"
            logger.error("Audio sync failed: %s", error_msg)
            self._qa_exporter.set_sync_info(offset_ms=0, success=False, message=error_msg)
            self.signals.error.emit(f"Audio sync failed: {error_msg}")
            self._emit_progress(100, "Sync failed, continuing without external audio")
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
        """Render cut segments to temp files."""
        self._advance_stage(PipelineStage.RENDER)

        if not self._cut_plan:
            logger.warning("No cuts to render")
            self._emit_progress(100, "No cuts to render")
            return []

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
            ))

        # Create renderer with temp output directory
        output_dir = tempfile.mkdtemp(prefix="multicam_render_")
        self._temp_files.append(output_dir)  # Track for cleanup

        self._segment_renderer = SegmentRenderer(output_dir)

        def on_render_progress(rendered: int, total: int) -> None:
            if total > 0:
                percent = int(rendered * 100 / total)
                self._emit_progress(percent, f"Rendering segment {rendered}/{total}")

        result = self._segment_renderer.render_segments(cuts, on_progress=on_render_progress)
        self._segment_renderer = None

        if result.cancelled:
            logger.info("Render cancelled")
            return None

        if not result.success:
            logger.error("Render failed: %s", result.error)
            self.signals.error.emit(f"Render failed: {result.error}")
            return None

        # Track segment paths for cleanup
        self._temp_files.extend(result.segment_paths)

        self._emit_progress(100, f"Rendered {len(result.segment_paths)} segments")
        logger.info("Render complete: %d segments", len(result.segment_paths))
        return result.segment_paths

    def _stage_concat(
        self, segment_paths: List[str], output_path: Optional[str]
    ) -> Optional[str]:
        """Concatenate rendered segments into final output, optionally replacing audio."""
        self._advance_stage(PipelineStage.CONCAT)

        if not segment_paths:
            logger.warning("No segments to concatenate")
            self._emit_progress(100, "No segments to concatenate")
            return None

        # Generate output path if not provided
        if not output_path:
            output_dir = os.path.dirname(self.input_files[0])
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_dir, f"multicam_output_{timestamp}.mp4")

        self._emit_progress(30, f"Concatenating {len(segment_paths)} segments...")

        # If we have synced external audio, concat to temp first then replace audio
        synced_audio = getattr(self, "_synced_audio_path", None)
        if synced_audio and os.path.isfile(synced_audio):
            # Concat to temp file first
            temp_concat_path = output_path.replace(".mp4", "_temp_video.mp4")
            result_path = concatenate_segments(segment_paths, temp_concat_path)
            if not result_path:
                logger.error("Concatenation failed")
                self.signals.error.emit("Failed to concatenate segments")
                return None

            self._temp_files.append(temp_concat_path)
            self._emit_progress(70, "Replacing audio with external audio...")

            # Replace audio track with synced external audio
            final_path = self._replace_audio_track(temp_concat_path, synced_audio, output_path)
            if final_path:
                self._emit_progress(100, "Audio replaced successfully")
                logger.info("Concat + audio replace complete: %s", final_path)
                self._cleanup()
                return final_path
            else:
                # Fallback: use video without external audio
                logger.warning("Audio replace failed, using original audio")
                self._emit_progress(100, "Using original audio (replace failed)")
                import shutil
                try:
                    shutil.move(temp_concat_path, output_path)
                    self._cleanup()
                    return output_path
                except Exception as e:
                    logger.error("Failed to move temp file: %s", e)
                    self._cleanup()
                    return None
        else:
            # No external audio - just concatenate normally
            self._emit_progress(50, f"Concatenating {len(segment_paths)} segments...")
            result_path = concatenate_segments(segment_paths, output_path)

            if result_path:
                self._emit_progress(100, "Concatenation complete")
                logger.info("Concat complete: %s", result_path)
                self._cleanup()
                return result_path

            logger.error("Concatenation failed")
            self.signals.error.emit("Failed to concatenate segments")
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
