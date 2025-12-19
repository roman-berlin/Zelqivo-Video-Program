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
    else:
        args.extend(["-c:v", "libx264", "-c:a", "aac"])

    args.append(output_path)
    return args


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
