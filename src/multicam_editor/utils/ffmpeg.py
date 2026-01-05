# file: utils/ffmpeg.py
"""FFmpeg wrapper for video processing operations.

Provides helpers for encoding, trimming, concatenation with proper
subprocess management, cancellation support, and temp file cleanup.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Callable

logger = logging.getLogger(__name__)

_ffmpeg_path: Optional[str] = None
_ffmpeg_checked: bool = False


def _find_ffmpeg() -> Optional[str]:
    """Locate ffmpeg executable. Returns path or None if not found."""
    global _ffmpeg_path, _ffmpeg_checked
    if _ffmpeg_checked:
        return _ffmpeg_path
    _ffmpeg_checked = True

    # Check if ffmpeg is in PATH
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode == 0:
            _ffmpeg_path = "ffmpeg"
            return _ffmpeg_path
    except Exception:
        pass

    # Common Windows locations
    if os.name == "nt":
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            os.path.expanduser(r"~\ffmpeg\bin\ffmpeg.exe"),
        ]
        # Add WinGet installation paths (dynamic version folder)
        winget_base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
        if os.path.isdir(winget_base):
            for pkg_dir in os.listdir(winget_base):
                if pkg_dir.startswith("Gyan.FFmpeg"):
                    pkg_path = os.path.join(winget_base, pkg_dir)
                    # Search for ffmpeg.exe in the package
                    for root, dirs, files in os.walk(pkg_path):
                        if "ffmpeg.exe" in files:
                            common_paths.append(os.path.join(root, "ffmpeg.exe"))
                            break
        for p in common_paths:
            if os.path.isfile(p):
                _ffmpeg_path = p
                return _ffmpeg_path
    return None


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system."""
    return _find_ffmpeg() is not None


def get_ffmpeg_path() -> Optional[str]:
    """Get the path to ffmpeg executable."""
    return _find_ffmpeg()


def reset_ffmpeg_detection() -> None:
    """Reset ffmpeg path detection. Useful for testing."""
    global _ffmpeg_path, _ffmpeg_checked
    _ffmpeg_path = None
    _ffmpeg_checked = False


@dataclass
class FFmpegResult:
    """Result of an ffmpeg operation."""
    success: bool
    output_path: Optional[str] = None
    error: Optional[str] = None
    cancelled: bool = False


class FFmpegProcess:
    """Wrapper for running ffmpeg with cancellation support.

    Usage:
        proc = FFmpegProcess(args, output_path)
        result = proc.run()
        # or to cancel from another thread:
        proc.cancel()
    """

    def __init__(
        self,
        args: List[str],
        output_path: Optional[str] = None,
        on_progress: Optional[Callable[[float], None]] = None,
    ):
        """Initialize FFmpeg process.

        Args:
            args: Full ffmpeg command arguments (including 'ffmpeg')
            output_path: Expected output file path (for cleanup on cancel)
            on_progress: Optional callback for progress (0.0-1.0)
        """
        self._args = args
        self._output_path = output_path
        self._on_progress = on_progress
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False

    def run(self, timeout: Optional[float] = None) -> FFmpegResult:
        """Run the ffmpeg process. Blocks until complete or cancelled.

        Args:
            timeout: Optional timeout in seconds

        Returns:
            FFmpegResult with success status and any error message
        """
        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            return FFmpegResult(success=False, error="ffmpeg not found")

        # Replace 'ffmpeg' placeholder with actual path
        args = [ffmpeg if a == "ffmpeg" else a for a in self._args]

        try:
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            stdout, stderr = self._process.communicate(timeout=timeout)

            if self._cancelled:
                self._cleanup_output()
                return FFmpegResult(success=False, cancelled=True, error="Cancelled")

            if self._process.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace").strip()[-500:]
                return FFmpegResult(success=False, error=f"ffmpeg error: {err_msg}")

            return FFmpegResult(success=True, output_path=self._output_path)

        except subprocess.TimeoutExpired:
            self.cancel()
            return FFmpegResult(success=False, error="ffmpeg timeout")
        except Exception as e:
            logger.debug(f"ffmpeg error: {e}", exc_info=True)
            self._cleanup_output()
            return FFmpegResult(success=False, error=str(e))
        finally:
            self._process = None

    def cancel(self) -> None:
        """Cancel the running process and cleanup output file."""
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._cleanup_output()

    def _cleanup_output(self) -> None:
        """Remove partial output file if it exists."""
        if self._output_path and os.path.isfile(self._output_path):
            try:
                os.remove(self._output_path)
                logger.debug(f"Cleaned up partial output: {self._output_path}")
            except Exception as e:
                logger.debug(f"Failed to cleanup {self._output_path}: {e}")


def run_ffmpeg(
    args: List[str],
    output_path: Optional[str] = None,
    timeout: Optional[float] = None,
) -> FFmpegResult:
    """Run ffmpeg with given arguments. Simple blocking call.

    Args:
        args: Command arguments (use 'ffmpeg' as first element, will be replaced)
        output_path: Expected output path for cleanup on failure
        timeout: Optional timeout in seconds

    Returns:
        FFmpegResult with success status
    """
    proc = FFmpegProcess(args, output_path)
    return proc.run(timeout=timeout)


def get_temp_output_path(suffix: str = ".mp4") -> str:
    """Get a temporary file path for ffmpeg output.

    The file is NOT created - just returns a safe path.

    Args:
        suffix: File extension (default .mp4)

    Returns:
        Path to use for temporary output
    """
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="multicam_")
    os.close(fd)
    os.remove(path)  # We just want the path, ffmpeg will create
    return path


def extract_audio_to_wav(
    video_path: str,
    output_path: Optional[str] = None,
    sample_rate: int = 16000,
    mono: bool = True,
    timeout: float = 60.0,
) -> FFmpegResult:
    """Extract audio track from video to WAV file.

    Args:
        video_path: Path to source video
        output_path: Destination WAV path (auto-generated if None)
        sample_rate: Target sample rate in Hz (default 16000 for sync)
        mono: Convert to mono (default True)
        timeout: Max extraction time in seconds

    Returns:
        FFmpegResult with output_path on success
    """
    if not os.path.isfile(video_path):
        logger.error("extract_audio_to_wav: source not found: %s", video_path)
        return FFmpegResult(success=False, error=f"File not found: {video_path}")

    if output_path is None:
        output_path = get_temp_output_path(suffix=".wav")

    args = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",  # No video
        "-ar", str(sample_rate),
    ]

    if mono:
        args.extend(["-ac", "1"])

    args.extend(["-f", "wav", output_path])

    logger.info("Extracting audio: %s -> %s (sr=%d, mono=%s)",
                os.path.basename(video_path), os.path.basename(output_path),
                sample_rate, mono)

    proc = FFmpegProcess(args, output_path)
    result = proc.run(timeout=timeout)

    if result.success:
        logger.info("Audio extraction complete: %s", os.path.basename(output_path))
    else:
        logger.error("Audio extraction failed for %s: %s",
                     os.path.basename(video_path), result.error)

    return result


def build_trim_args(
    input_path: str,
    output_path: str,
    start_ms: int,
    end_ms: int,
    copy_codec: bool = True,
) -> List[str]:
    """Build ffmpeg arguments for trimming a video segment.

    Args:
        input_path: Source video path
        output_path: Destination path
        start_ms: Start time in milliseconds
        end_ms: End time in milliseconds
        copy_codec: If True, use stream copy (fast). If False, re-encode.

    Returns:
        List of ffmpeg arguments
    """
    start_sec = start_ms / 1000.0
    duration_sec = (end_ms - start_ms) / 1000.0

    args = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-ss", f"{start_sec:.3f}",
        "-i", input_path,
        "-t", f"{duration_sec:.3f}",
    ]

    if copy_codec:
        args.extend(["-c", "copy"])
        # For stream copy, avoid negative timestamps
        args.extend(["-avoid_negative_ts", "make_zero"])
    else:
        # Re-encode with proper timestamp handling to avoid black frames
        args.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "aac",
            # Reset timestamps to start at 0 - critical for seamless concat
            "-avoid_negative_ts", "make_zero",
            # Force constant frame rate to avoid VFR issues
            "-fps_mode", "cfr",
            # Consistent timebase for all segments
            "-video_track_timescale", "90000",
        ])

    args.append(output_path)
    return args


def build_segment_with_effects_args(
    input_path: str,
    output_path: str,
    start_ms: int,
    end_ms: int,
    fade_in_ms: int = 0,
    fade_out_ms: int = 0,
    grayscale: bool = False,
    speed: float = 1.0,
) -> List[str]:
    """Build ffmpeg arguments for trimming with effects applied.

    Effects require re-encoding, so stream copy is not used.

    Args:
        input_path: Source video path
        output_path: Destination path
        start_ms: Start time in milliseconds
        end_ms: End time in milliseconds
        fade_in_ms: Fade in duration in ms (0 = disabled)
        fade_out_ms: Fade out duration in ms (0 = disabled)
        grayscale: Apply grayscale filter
        speed: Playback speed multiplier (1.0 = normal)

    Returns:
        List of ffmpeg arguments
    """
    # Clamp speed to reasonable range
    speed = max(0.25, min(4.0, speed))

    start_sec = start_ms / 1000.0
    duration_sec = (end_ms - start_ms) / 1000.0

    # Build filter chains
    vfilters: List[str] = []
    afilters: List[str] = []

    # Speed filter (setpts for video, atempo for audio)
    if speed != 1.0:
        # setpts=PTS/speed makes video faster (speed>1) or slower (speed<1)
        vfilters.append(f"setpts=PTS/{speed}")
        # atempo only accepts 0.5-2.0, chain multiple for wider range
        if speed >= 0.5 and speed <= 2.0:
            afilters.append(f"atempo={speed}")
        elif speed < 0.5:
            # Chain two atempo filters for speeds < 0.5
            afilters.append(f"atempo={speed * 2}")
            afilters.append("atempo=0.5")
        else:
            # Chain two atempo filters for speeds > 2.0
            afilters.append(f"atempo={speed / 2}")
            afilters.append("atempo=2.0")

    # Grayscale
    if grayscale:
        vfilters.append("format=gray")

    # Calculate output duration after speed change for fades
    output_duration_sec = duration_sec / speed

    # Fade in (at start of clip)
    if fade_in_ms > 0:
        fade_in_sec = fade_in_ms / 1000.0
        vfilters.append(f"fade=t=in:st=0:d={fade_in_sec:.3f}")
        afilters.append(f"afade=t=in:st=0:d={fade_in_sec:.3f}")

    # Fade out (at end of clip, based on output duration)
    if fade_out_ms > 0:
        fade_out_sec = fade_out_ms / 1000.0
        fade_start = max(0, output_duration_sec - fade_out_sec)
        vfilters.append(f"fade=t=out:st={fade_start:.3f}:d={fade_out_sec:.3f}")
        afilters.append(f"afade=t=out:st={fade_start:.3f}:d={fade_out_sec:.3f}")

    args = [
        "ffmpeg",
        "-y",
        "-ss", f"{start_sec:.3f}",
        "-i", input_path,
        "-t", f"{duration_sec:.3f}",
    ]

    # Add video filter if any
    if vfilters:
        args.extend(["-vf", ",".join(vfilters)])

    # Add audio filter if any
    if afilters:
        args.extend(["-af", ",".join(afilters)])

    # Re-encode with proper timestamp handling to avoid black frames
    args.extend([
        "-c:v", "libx264",
        "-preset", "fast",
        "-c:a", "aac",
        # Reset timestamps to start at 0 - critical for seamless concat
        "-avoid_negative_ts", "make_zero",
        # Force constant frame rate to avoid VFR issues
        "-fps_mode", "cfr",
        # Consistent timebase for all segments
        "-video_track_timescale", "90000",
    ])
    args.append(output_path)

    return args


def has_effects(
    fade_in_ms: int = 0,
    fade_out_ms: int = 0,
    grayscale: bool = False,
    speed: float = 1.0,
) -> bool:
    """Check if any effects are enabled that require re-encoding."""
    return fade_in_ms > 0 or fade_out_ms > 0 or grayscale or speed != 1.0


def build_concat_args(
    input_paths: List[str],
    output_path: str,
    concat_list_path: str,
) -> List[str]:
    """Build ffmpeg arguments for concatenating videos.

    Note: Caller must create the concat list file with format:
        file '/path/to/video1.mp4'
        file '/path/to/video2.mp4'

    Args:
        input_paths: List of input video paths (for reference)
        output_path: Destination path
        concat_list_path: Path to concat list file

    Returns:
        List of ffmpeg arguments
    """
    return [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        output_path,
    ]


def create_concat_list(paths: List[str], list_path: str) -> None:
    """Create a concat list file for ffmpeg concat demuxer.

    Args:
        paths: List of video paths to concatenate
        list_path: Where to write the list file
    """
    with open(list_path, "w", encoding="utf-8") as f:
        for p in paths:
            # Escape single quotes in path
            escaped = p.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")


def build_qa_overlay_filter(
    speaker_id: int,
    camera_index: int,
    start_ms: int,
    end_ms: int,
) -> str:
    """Build drawtext filter for QA overlay burn-in.

    Displays: timecode | speaker_id | camera_index at top-left.

    Args:
        speaker_id: Current active speaker ID
        camera_index: Current active camera index
        start_ms: Segment start time (for static timecode reference)
        end_ms: Segment end time (unused, for future cut marker)

    Returns:
        Drawtext filter string for ffmpeg -vf
    """
    # Build static overlay text with timecode placeholder
    # %{pts\:hms} shows running timecode, offset by segment start
    start_sec = start_ms / 1000.0
    # Escape colons for drawtext
    text = f"TC\\: %{{pts\\:hms}} | SPK\\: {speaker_id} | CAM\\: {camera_index}"

    # drawtext filter with white text on semi-transparent black box
    return (
        f"drawtext=fontfile=:text='{text}':"
        f"x=10:y=10:fontsize=18:fontcolor=white:"
        f"box=1:boxcolor=black@0.6:boxborderw=5"
    )


def build_segment_with_qa_overlay_args(
    input_path: str,
    output_path: str,
    start_ms: int,
    end_ms: int,
    speaker_id: int,
    camera_index: int,
    fade_in_ms: int = 0,
    fade_out_ms: int = 0,
    grayscale: bool = False,
    speed: float = 1.0,
) -> List[str]:
    """Build ffmpeg args for segment with QA overlay burned in.

    Combines existing effects with drawtext overlay.

    Args:
        input_path: Source video path
        output_path: Destination path
        start_ms: Start time in milliseconds
        end_ms: End time in milliseconds
        speaker_id: Active speaker ID for overlay
        camera_index: Active camera index for overlay
        fade_in_ms: Fade in duration in ms (0 = disabled)
        fade_out_ms: Fade out duration in ms (0 = disabled)
        grayscale: Apply grayscale filter
        speed: Playback speed multiplier (1.0 = normal)

    Returns:
        List of ffmpeg arguments
    """
    speed = max(0.25, min(4.0, speed))
    start_sec = start_ms / 1000.0
    duration_sec = (end_ms - start_ms) / 1000.0

    vfilters: List[str] = []
    afilters: List[str] = []

    # Speed filter
    if speed != 1.0:
        vfilters.append(f"setpts=PTS/{speed}")
        if 0.5 <= speed <= 2.0:
            afilters.append(f"atempo={speed}")
        elif speed < 0.5:
            afilters.append(f"atempo={speed * 2}")
            afilters.append("atempo=0.5")
        else:
            afilters.append(f"atempo={speed / 2}")
            afilters.append("atempo=2.0")

    # Grayscale
    if grayscale:
        vfilters.append("format=gray")

    output_duration_sec = duration_sec / speed

    # Fades
    if fade_in_ms > 0:
        fade_in_sec = fade_in_ms / 1000.0
        vfilters.append(f"fade=t=in:st=0:d={fade_in_sec:.3f}")
        afilters.append(f"afade=t=in:st=0:d={fade_in_sec:.3f}")

    if fade_out_ms > 0:
        fade_out_sec = fade_out_ms / 1000.0
        fade_start = max(0, output_duration_sec - fade_out_sec)
        vfilters.append(f"fade=t=out:st={fade_start:.3f}:d={fade_out_sec:.3f}")
        afilters.append(f"afade=t=out:st={fade_start:.3f}:d={fade_out_sec:.3f}")

    # Add QA overlay last (on top of other effects)
    qa_filter = build_qa_overlay_filter(speaker_id, camera_index, start_ms, end_ms)
    vfilters.append(qa_filter)

    args = [
        "ffmpeg",
        "-y",
        "-ss", f"{start_sec:.3f}",
        "-i", input_path,
        "-t", f"{duration_sec:.3f}",
    ]

    if vfilters:
        args.extend(["-vf", ",".join(vfilters)])
    if afilters:
        args.extend(["-af", ",".join(afilters)])

    # Re-encode with proper timestamp handling to avoid black frames
    args.extend([
        "-c:v", "libx264",
        "-preset", "fast",
        "-c:a", "aac",
        # Reset timestamps to start at 0 - critical for seamless concat
        "-avoid_negative_ts", "make_zero",
        # Force constant frame rate to avoid VFR issues
        "-fps_mode", "cfr",
        # Consistent timebase for all segments
        "-video_track_timescale", "90000",
    ])
    args.append(output_path)

    return args


def build_single_pass_filter_complex_args(
    cuts: list,
    output_path: str,
    resolution: str = "1080p",
    fps: float = 30.0,
) -> list[str]:
    """Build FFmpeg args for single-pass multi-segment render using filter_complex.

    This approach eliminates black frames at segment boundaries by:
    1. Opening each unique source file once (continuous decoding)
    2. Using trim filter for frame-accurate segment extraction
    3. Using concat filter to join segments seamlessly
    4. Single CFR encode output

    Args:
        cuts: List of cut definitions with fields:
            - source_path: str - path to source video
            - start_ms: int - start time in milliseconds
            - end_ms: int - end time in milliseconds
            - camera_index: int (optional) - for logging
        output_path: Destination path for output video
        resolution: Target resolution ("1080p" or "720p")
        fps: Target frame rate (default 30.0)

    Returns:
        List of ffmpeg arguments ready for FFmpegProcess
    """
    if not cuts:
        logger.warning("build_single_pass_filter_complex_args: no cuts provided")
        return []

    # Determine output dimensions based on resolution
    if resolution == "720p":
        out_width, out_height = 1280, 720
    else:  # Default to 1080p
        out_width, out_height = 1920, 1080

    # Build unique input list - map source paths to input indices
    unique_sources: dict[str, int] = {}
    for cut in cuts:
        source_path = cut.source_path if hasattr(cut, 'source_path') else cut.get('source_path', '')
        if source_path and source_path not in unique_sources:
            unique_sources[source_path] = len(unique_sources)

    if not unique_sources:
        logger.error("No valid source paths in cuts")
        return []

    # Build input arguments
    args = ["ffmpeg", "-y"]
    for source_path in unique_sources.keys():
        args.extend(["-i", source_path])

    # Build filter_complex
    filter_parts = []
    segment_labels = []

    for i, cut in enumerate(cuts):
        # Get cut attributes (support both dataclass and dict)
        if hasattr(cut, 'source_path'):
            source_path = cut.source_path
            start_ms = cut.start_ms
            end_ms = cut.end_ms
            camera_idx = getattr(cut, 'camera_index', 0)
        else:
            source_path = cut.get('source_path', '')
            start_ms = cut.get('start_ms', 0)
            end_ms = cut.get('end_ms', 0)
            camera_idx = cut.get('camera_index', 0)

        input_idx = unique_sources.get(source_path, 0)
        start_sec = start_ms / 1000.0
        end_sec = end_ms / 1000.0
        duration_sec = end_sec - start_sec

        # Log segment details for debugging
        logger.info(
            "Single-pass segment %d: camera=%d, source=%s, start=%.3fs, end=%.3fs (duration=%.3fs)",
            i, camera_idx, Path(source_path).name, start_sec, end_sec, duration_sec
        )

        # Build filter chain for this segment:
        # 1. trim: extract time range
        # 2. setpts: reset timestamps to 0
        # 3. scale: resize to target resolution with aspect ratio preservation
        # 4. pad: add letterbox/pillarbox if needed
        # 5. setsar: force square pixels
        # 6. fps: ensure constant frame rate
        segment_label = f"v{i}"
        filter_chain = (
            f"[{input_idx}:v]"
            f"trim=start={start_sec:.3f}:end={end_sec:.3f},"
            f"setpts=PTS-STARTPTS,"
            f"scale={out_width}:{out_height}:force_original_aspect_ratio=decrease,"
            f"pad={out_width}:{out_height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,"
            f"fps={fps}"
            f"[{segment_label}]"
        )
        filter_parts.append(filter_chain)
        segment_labels.append(f"[{segment_label}]")

    # Build concat filter
    concat_inputs = "".join(segment_labels)
    concat_filter = f"{concat_inputs}concat=n={len(cuts)}:v=1:a=0[outv]"
    filter_parts.append(concat_filter)

    # Join all filter parts
    filter_complex = ";".join(filter_parts)

    # Build output arguments
    args.extend([
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",  # High quality
        "-pix_fmt", "yuv420p",
        "-fps_mode", "cfr",
        "-an",  # No audio (added separately)
        output_path,
    ])

    logger.info(
        "Single-pass render: %d segments from %d unique sources, output=%s",
        len(cuts), len(unique_sources), Path(output_path).name
    )

    return args
