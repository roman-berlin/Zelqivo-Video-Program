"""Video segment rendering and merging module.

Provides functionality to render video segments (cuts) to temp files
with stream-copy when possible, and support for cancellation/cleanup.
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Callable

from ..utils.ffmpeg import (
    FFmpegProcess,
    FFmpegResult,
    build_concat_args,
    build_segment_with_effects_args,
    build_segment_with_qa_overlay_args,
    build_trim_args,
    create_concat_list,
    get_temp_output_path,
    has_effects,
    is_ffmpeg_available,
    select_h264_encoder,
)


logger = logging.getLogger(__name__)


@dataclass
class CutDefinition:
    """Definition of a single cut/segment to render.

    Effects (Prompt 8.1):
        fade_in_ms: Duration of fade-in (0 = disabled)
        fade_out_ms: Duration of fade-out (0 = disabled)
        grayscale: Apply grayscale filter
        speed: Playback speed (1.0 = normal)

    QA Overlay (Prompt 5):
        qa_overlay: Enable QA overlay burn-in
        speaker_id: Active speaker ID for overlay
        camera_index: Active camera index for overlay
    """

    source_path: str
    start_ms: int
    end_ms: int
    cut_index: int = 0
    # Effects (Prompt 8.1)
    fade_in_ms: int = 0
    fade_out_ms: int = 0
    grayscale: bool = False
    speed: float = 1.0
    # QA Overlay (Prompt 5)
    qa_overlay: bool = False
    speaker_id: int = 0
    camera_index: int = 0


@dataclass
class RenderResult:
    """Result of segment rendering."""

    success: bool
    segment_paths: List[str] = field(default_factory=list)
    error: Optional[str] = None
    cancelled: bool = False
    rendered_count: int = 0
    total_count: int = 0


class SegmentRenderer:
    """Renders video segments with cancellation support.

    Usage:
        renderer = SegmentRenderer()
        result = renderer.render_segments(cuts, on_progress)
        # To cancel from another thread:
        renderer.cancel()
    """

    def __init__(self, output_dir: Optional[str] = None):
        """Initialize the segment renderer.

        Args:
            output_dir: Directory for temp segments. Uses system temp if None.
        """
        self._output_dir = output_dir or tempfile.gettempdir()
        self._cancelled = False
        self._current_process: Optional[FFmpegProcess] = None
        self._rendered_segments: List[str] = []

    def render_segments(
        self,
        cuts: List[CutDefinition],
        on_progress: Optional[Callable[[int, int], None]] = None,
        try_stream_copy: bool = False,  # Re-encode by default to avoid black frames at cut points
    ) -> RenderResult:
        """Render all cuts to temp mp4 segments.

        Args:
            cuts: List of cut definitions to render
            on_progress: Callback(rendered_count, total) for progress updates
            try_stream_copy: If True, try stream copy first, fallback to re-encode

        Returns:
            RenderResult with segment paths and status
        """
        if not cuts:
            return RenderResult(success=True, total_count=0)

        if not is_ffmpeg_available():
            return RenderResult(
                success=False,
                error="ffmpeg not found. Please install ffmpeg.",
                total_count=len(cuts),
            )

        self._cancelled = False
        self._rendered_segments = []
        total = len(cuts)

        logger.info("Rendering %d segments...", total)

        for i, cut in enumerate(cuts):
            if self._cancelled:
                self._cleanup_segments()
                return RenderResult(
                    success=False,
                    cancelled=True,
                    error="Cancelled by user",
                    rendered_count=i,
                    total_count=total,
                )

            # Validate cut
            if cut.end_ms <= cut.start_ms:
                logger.warning("Skipping invalid cut %d: end <= start", i)
                continue

            if not os.path.isfile(cut.source_path):
                logger.error("Source file not found: %s", cut.source_path)
                self._cleanup_segments()
                return RenderResult(
                    success=False,
                    error=f"Source file not found: {cut.source_path}",
                    segment_paths=self._rendered_segments,
                    rendered_count=i,
                    total_count=total,
                )

            # Generate output path
            output_path = self._get_segment_path(cut.cut_index)

            # Try stream copy first
            result = self._render_segment(cut, output_path, copy_codec=try_stream_copy)

            # If stream copy failed, try re-encode
            if not result.success and try_stream_copy and not result.cancelled:
                logger.info("Stream copy failed for cut %d, re-encoding...", i)
                result = self._render_segment(cut, output_path, copy_codec=False)

            if result.cancelled:
                self._cleanup_segments()
                return RenderResult(
                    success=False,
                    cancelled=True,
                    error="Cancelled by user",
                    rendered_count=i,
                    total_count=total,
                )

            if not result.success:
                logger.error("Failed to render cut %d: %s", i, result.error)
                self._cleanup_segments()
                return RenderResult(
                    success=False,
                    error=f"Failed to render cut {i}: {result.error}",
                    rendered_count=i,
                    total_count=total,
                )

            self._rendered_segments.append(output_path)
            logger.info("Rendered segment %d/%d: %s", i + 1, total, output_path)

            if on_progress:
                on_progress(i + 1, total)

        return RenderResult(
            success=True,
            segment_paths=self._rendered_segments.copy(),
            rendered_count=len(self._rendered_segments),
            total_count=total,
        )

    def _render_segment(
        self, cut: CutDefinition, output_path: str, copy_codec: bool
    ) -> FFmpegResult:
        """Render a single segment.

        Args:
            cut: Cut definition
            output_path: Where to write the segment
            copy_codec: Whether to use stream copy

        Returns:
            FFmpegResult from the ffmpeg process
        """
        # Check if effects require re-encoding
        use_effects = has_effects(
            fade_in_ms=cut.fade_in_ms,
            fade_out_ms=cut.fade_out_ms,
            grayscale=cut.grayscale,
            speed=cut.speed,
        )

        # QA overlay requires re-encoding with drawtext filter
        if cut.qa_overlay:
            logger.debug(
                "Rendering segment %d with QA overlay: speaker=%d, camera=%d",
                cut.cut_index, cut.speaker_id, cut.camera_index
            )
            args = build_segment_with_qa_overlay_args(
                input_path=cut.source_path,
                output_path=output_path,
                start_ms=cut.start_ms,
                end_ms=cut.end_ms,
                speaker_id=cut.speaker_id,
                camera_index=cut.camera_index,
                fade_in_ms=cut.fade_in_ms,
                fade_out_ms=cut.fade_out_ms,
                grayscale=cut.grayscale,
                speed=cut.speed,
            )
        elif use_effects:
            # Effects require re-encoding
            args = build_segment_with_effects_args(
                input_path=cut.source_path,
                output_path=output_path,
                start_ms=cut.start_ms,
                end_ms=cut.end_ms,
                fade_in_ms=cut.fade_in_ms,
                fade_out_ms=cut.fade_out_ms,
                grayscale=cut.grayscale,
                speed=cut.speed,
            )
        else:
            args = build_trim_args(
                input_path=cut.source_path,
                output_path=output_path,
                start_ms=cut.start_ms,
                end_ms=cut.end_ms,
                copy_codec=copy_codec,
            )

        self._current_process = FFmpegProcess(args, output_path)
        result = self._current_process.run()
        self._current_process = None

        return result

    def _get_segment_path(self, index: int) -> str:
        """Generate a unique path for a segment."""
        return os.path.join(
            self._output_dir,
            f"multicam_seg_{index:04d}_{os.getpid()}.mp4",
        )

    def cancel(self) -> None:
        """Cancel rendering and cleanup partial files."""
        logger.info("Cancelling segment rendering...")
        self._cancelled = True
        if self._current_process:
            self._current_process.cancel()
        self._cleanup_segments()

    def _cleanup_segments(self) -> None:
        """Remove all rendered segments (used on cancel/error)."""
        for path in self._rendered_segments:
            if os.path.isfile(path):
                try:
                    os.remove(path)
                    logger.debug("Cleaned up segment: %s", path)
                except Exception as e:
                    logger.debug("Failed to cleanup %s: %s", path, e)
        self._rendered_segments = []

    def cleanup(self) -> None:
        """Public method to cleanup all rendered segments."""
        self._cleanup_segments()


def render_cuts(
    cuts: List[CutDefinition],
    output_dir: Optional[str] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> RenderResult:
    """Convenience function to render cuts without managing renderer instance.

    Args:
        cuts: List of cut definitions
        output_dir: Directory for output. Uses temp dir if None.
        on_progress: Progress callback(rendered, total)

    Returns:
        RenderResult with segment paths
    """
    renderer = SegmentRenderer(output_dir)
    return renderer.render_segments(cuts, on_progress)


def merge_videos(
    segment_definitions: List[dict],
    input_video_paths: List[str],
    output_path: str,
    resolution: str = "1080p",
    aligned_audio_path: Optional[str] = None,
) -> Optional[str]:
    """Merge videos according to segment definitions.

    Args:
        segment_definitions: List of dicts with keys:
            - video_index: Index into input_video_paths
            - start_ms: Start time in ms
            - end_ms: End time in ms
        input_video_paths: List of source video paths
        output_path: Where to write final merged video
        resolution: Target resolution (unused for now)
        aligned_audio_path: Optional external audio to use

    Returns:
        Output path on success, None on failure
    """
    # Convert segment definitions to CutDefinition objects
    cuts = []
    for i, seg in enumerate(segment_definitions):
        video_idx = seg.get("video_index", 0)
        if video_idx >= len(input_video_paths):
            logger.error("Invalid video_index %d in segment %d", video_idx, i)
            return None

        cuts.append(
            CutDefinition(
                source_path=input_video_paths[video_idx],
                start_ms=int(seg.get("start_ms", 0)),
                end_ms=int(seg.get("end_ms", 0)),
                cut_index=i,
            )
        )

    # Render segments
    result = render_cuts(cuts)
    if not result.success:
        logger.error("Failed to render segments: %s", result.error)
        return None

    # Single segment: just copy/rename to output
    if len(result.segment_paths) == 1:
        import shutil
        try:
            shutil.copy2(result.segment_paths[0], output_path)
            os.remove(result.segment_paths[0])
            return output_path
        except Exception as e:
            logger.error("Failed to copy single segment: %s", e)
            return None

    # Multiple segments: concatenate
    concat_result = concatenate_segments(result.segment_paths, output_path)

    # Cleanup temp segments
    for seg in result.segment_paths:
        try:
            os.remove(seg)
        except Exception:
            pass

    return concat_result


def concatenate_segments(
    segment_paths: List[str],
    output_path: str,
    output_quality: str = "1080p",
) -> Optional[str]:
    """Concatenate multiple video segments into a single mp4.

    Uses ffmpeg concat demuxer for fast stream-copy concatenation.
    Falls back to re-encode if concat fails.

    Args:
        segment_paths: List of segment file paths (must be compatible codecs)
        output_path: Where to write the final merged video
        output_quality: Target quality (unused for stream copy)

    Returns:
        output_path on success, None on failure
    """
    if not segment_paths:
        logger.warning("No segments to concatenate")
        return None

    # Single segment: just copy (no ffmpeg needed)
    if len(segment_paths) == 1:
        import shutil
        try:
            shutil.copy2(segment_paths[0], output_path)
            return output_path
        except Exception as e:
            logger.error("Failed to copy single segment: %s", e)
            return None

    # Multiple segments require ffmpeg
    if not is_ffmpeg_available():
        logger.error("ffmpeg not available for concatenation")
        return None

    logger.info("Concatenating %d segments to %s", len(segment_paths), output_path)

    # Create concat list file
    concat_list_path = get_temp_output_path(suffix=".txt")
    try:
        create_concat_list(segment_paths, concat_list_path)

        # Build and run concat command
        args = build_concat_args(segment_paths, output_path, concat_list_path)
        proc = FFmpegProcess(args, output_path)
        result = proc.run()

        if result.success:
            logger.info("Concatenation successful: %s", output_path)
            return output_path

        # Stream copy concat failed, try re-encode
        logger.warning("Stream copy concat failed, re-encoding...")
        encoder, quality_args = select_h264_encoder()
        args_reencode = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c:v", encoder,
            *quality_args,
            "-c:a", "aac",
            output_path,
        ]
        proc2 = FFmpegProcess(args_reencode, output_path)
        result2 = proc2.run()

        if result2.success:
            logger.info("Re-encode concatenation successful: %s", output_path)
            return output_path

        logger.error("Concatenation failed: %s", result2.error)
        return None

    finally:
        # Cleanup concat list file
        if os.path.isfile(concat_list_path):
            try:
                os.remove(concat_list_path)
            except Exception:
                pass


def render_single_pass(
    cuts: List[CutDefinition],
    output_path: str,
    resolution: str = "1080p",
    fps: float = 30.0,
) -> RenderResult:
    """Render all cuts in a single FFmpeg pass using filter_complex.

    This eliminates black frames at segment boundaries by:
    - Decoding each source file continuously (no seeking per segment)
    - Using trim filter for frame-accurate extraction
    - Using concat filter for seamless joining
    - Single CFR encode output

    Args:
        cuts: List of CutDefinition objects to render
        output_path: Where to write the final video (no audio)
        resolution: Target resolution ("1080p" or "720p")
        fps: Target frame rate

    Returns:
        RenderResult with success status and output path
    """
    from ..utils.ffmpeg import build_single_pass_filter_complex_args

    if not cuts:
        logger.warning("render_single_pass: no cuts provided")
        return RenderResult(success=True, segment_paths=[], total_count=0)

    if not is_ffmpeg_available():
        return RenderResult(
            success=False,
            error="ffmpeg not found. Please install ffmpeg.",
            total_count=len(cuts),
        )

    # Validate all source files exist
    for i, cut in enumerate(cuts):
        if not os.path.isfile(cut.source_path):
            logger.error("Source file not found for cut %d: %s", i, cut.source_path)
            return RenderResult(
                success=False,
                error=f"Source file not found: {cut.source_path}",
                total_count=len(cuts),
            )

    # Log segment summary
    logger.info("Single-pass render starting: %d segments to %s", len(cuts), output_path)
    for i, cut in enumerate(cuts):
        logger.info(
            "  Cut %d: %s [%d-%d ms] (camera %d)",
            i, os.path.basename(cut.source_path), cut.start_ms, cut.end_ms,
            getattr(cut, 'camera_index', 0)
        )

    # Build FFmpeg args (returns tuple with filter script path for cleanup)
    args, filter_script_path = build_single_pass_filter_complex_args(
        cuts=cuts,
        output_path=output_path,
        resolution=resolution,
        fps=fps,
    )

    if not args:
        return RenderResult(
            success=False,
            error="Failed to build filter_complex arguments",
            total_count=len(cuts),
        )

    try:
        # Run FFmpeg
        proc = FFmpegProcess(args, output_path)
        result = proc.run()

        if result.cancelled:
            logger.info("Single-pass render cancelled")
            return RenderResult(
                success=False,
                cancelled=True,
                error="Cancelled by user",
                total_count=len(cuts),
            )

        if not result.success:
            logger.error("Single-pass render failed: %s", result.error)
            return RenderResult(
                success=False,
                error=f"Single-pass render failed: {result.error}",
                total_count=len(cuts),
            )

        logger.info("Single-pass render complete: %s", output_path)
        return RenderResult(
            success=True,
            segment_paths=[output_path],  # Single output file
            rendered_count=len(cuts),
            total_count=len(cuts),
        )
    finally:
        # Clean up the filter script temp file
        if filter_script_path and os.path.isfile(filter_script_path):
            try:
                os.remove(filter_script_path)
                logger.debug("Cleaned up filter script: %s", filter_script_path)
            except Exception as e:
                logger.debug("Failed to cleanup filter script %s: %s", filter_script_path, e)

