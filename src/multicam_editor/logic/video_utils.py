"""Video and audio helper functions.

This module contains utility functions for working with video files.

Primary implementation uses FFmpeg for video splitting (instant stream-copy,
preserves audio, memory-safe). Falls back to OpenCV if FFmpeg unavailable
(slower, no audio preservation).
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import List, Optional, Tuple

import cv2

logger = logging.getLogger(__name__)


def _is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system."""
    try:
        from ..utils.ffmpeg import is_ffmpeg_available
        return is_ffmpeg_available()
    except ImportError:
        # Fallback: try running ffmpeg directly
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False


def _get_ffmpeg_path() -> str:
    """Get path to ffmpeg executable."""
    try:
        from ..utils.ffmpeg import get_ffmpeg_path
        return get_ffmpeg_path() or "ffmpeg"
    except ImportError:
        return "ffmpeg"


def extract_audio(video_path: str, output_audio_path: str) -> None:
    """
    Extract the audio track from a video file.

    This implementation is a stub.  It exists to satisfy callers but
    performs no work because audio extraction requires external
    dependencies (e.g. FFmpeg) that are not available in this runtime.
    """
    logging.debug("extract_audio called for %s → %s (no-op)", video_path, output_audio_path)
    return None


def get_video_duration(video_path: str) -> Optional[float]:
    """
    Return the duration of a video in seconds.

    Uses OpenCV to probe the frame count and frame rate.  If either
    value cannot be determined the function returns ``None``.
    """
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if fps and fps > 0.0 and frames and frames > 0:
            return float(frames / fps)
    except Exception:
        pass
    return None


def split_video(input_path: str, split_ms: int) -> List[str]:
    """
    Physically split a video file into two segments at ``split_ms``.

    Parameters
    ----------
    input_path: str
        Absolute path to the source video file.  The file must exist.
    split_ms: int
        Millisecond offset at which to cut the video.

    Returns
    -------
    list[str]
        Two filenames corresponding to the left and right segments.  If
        splitting fails, an empty list is returned.

    Notes
    -----
    Uses FFmpeg stream-copy for instant splitting when available (preserves
    audio, memory-safe). Falls back to OpenCV if FFmpeg is not installed
    (slower, no audio preservation).
    """
    if not os.path.isfile(input_path):
        logger.warning("split_video: input file does not exist: %s", input_path)
        return []
    
    split_ms = max(0, int(split_ms))
    
    # Try FFmpeg first (instant, preserves audio)
    if _is_ffmpeg_available():
        return _split_video_ffmpeg(input_path, split_ms)
    else:
        logger.warning("split_video: FFmpeg not available, falling back to CV2 (no audio)")
        return _split_video_cv2(input_path, split_ms)


def _split_video_ffmpeg(input_path: str, split_ms: int) -> List[str]:
    """
    Split video using FFmpeg stream-copy (instant, preserves audio).
    
    Uses -c copy for instant splitting without re-encoding.
    """
    ffmpeg = _get_ffmpeg_path()
    split_sec = split_ms / 1000.0
    
    base, ext = os.path.splitext(os.path.basename(input_path))
    directory = os.path.dirname(input_path) or os.getcwd()
    
    def unique_path(suffix: str) -> str:
        candidate = os.path.join(directory, f"{base}{suffix}{ext}")
        idx = 1
        while os.path.exists(candidate):
            candidate = os.path.join(directory, f"{base}{suffix}_{idx}{ext}")
            idx += 1
        return candidate
    
    left_path = unique_path("_part1")
    right_path = unique_path("_part2")
    
    try:
        # Part 1: from start to split point
        cmd_left = [
            ffmpeg,
            "-y",  # Overwrite output
            "-i", input_path,
            "-t", str(split_sec),  # Duration from start
            "-c", "copy",  # Stream copy (instant)
            "-avoid_negative_ts", "make_zero",
            left_path,
        ]
        result_left = subprocess.run(
            cmd_left,
            capture_output=True,
            timeout=300,  # 5 min timeout
        )
        if result_left.returncode != 0:
            logger.error("split_video FFmpeg part1 failed: %s", result_left.stderr.decode()[:500])
            return []
        
        # Part 2: from split point to end
        cmd_right = [
            ffmpeg,
            "-y",
            "-ss", str(split_sec),  # Seek to split point
            "-i", input_path,
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            right_path,
        ]
        result_right = subprocess.run(
            cmd_right,
            capture_output=True,
            timeout=300,
        )
        if result_right.returncode != 0:
            logger.error("split_video FFmpeg part2 failed: %s", result_right.stderr.decode()[:500])
            # Cleanup part1 if part2 failed
            if os.path.exists(left_path):
                os.remove(left_path)
            return []
        
        # Verify outputs exist and have content
        outputs: List[str] = []
        for path in (left_path, right_path):
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                outputs.append(path)
            elif os.path.isfile(path):
                os.remove(path)
        
        logger.info("split_video (FFmpeg): created segments %s", outputs)
        return outputs
        
    except subprocess.TimeoutExpired:
        logger.error("split_video: FFmpeg timeout splitting %s", input_path)
        return []
    except Exception as exc:
        logger.exception("split_video FFmpeg error: %s", exc)
        return []


def _split_video_cv2(input_path: str, split_ms: int) -> List[str]:
    """
    Fallback: Split video using OpenCV (slower, no audio preservation).
    
    WARNING: Loads all frames into memory - can cause OOM on large videos.
    """
    try:
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            logger.warning("split_video CV2: failed to open video %s", input_path)
            return []
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0.0 or total_frames <= 0:
            logger.warning("split_video CV2: invalid fps or frame count for %s", input_path)
            cap.release()
            return []
        
        frame_split = int((split_ms / 1000.0) * fps)
        frame_split = max(1, min(frame_split, total_frames - 1))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        
        base, ext = os.path.splitext(os.path.basename(input_path))
        directory = os.path.dirname(input_path) or os.getcwd()
        
        def unique_path(suffix: str) -> str:
            candidate = os.path.join(directory, f"{base}{suffix}{ext}")
            idx = 1
            while os.path.exists(candidate):
                candidate = os.path.join(directory, f"{base}{suffix}_{idx}{ext}")
                idx += 1
            return candidate
        
        left_path = unique_path("_part1")
        right_path = unique_path("_part2")
        writer_left = cv2.VideoWriter(left_path, fourcc, fps, (width, height))
        writer_right = cv2.VideoWriter(right_path, fourcc, fps, (width, height))
        
        frame_idx = 0
        ok, frame = cap.read()
        while ok:
            if frame_idx < frame_split:
                writer_left.write(frame)
            else:
                writer_right.write(frame)
            frame_idx += 1
            ok, frame = cap.read()
        
        writer_left.release()
        writer_right.release()
        cap.release()
        
        # Verify outputs
        outputs: List[str] = []
        for path in (left_path, right_path):
            if os.path.isfile(path):
                try:
                    if os.path.getsize(path) > 0:
                        outputs.append(path)
                    else:
                        os.remove(path)
                except Exception:
                    pass
        
        logger.info("split_video (CV2): created segments %s", outputs)
        return outputs
        
    except Exception as exc:
        logger.exception("split_video CV2 error: %s", exc)
        return []

