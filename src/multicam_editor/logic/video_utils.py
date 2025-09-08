"""Video and audio helper functions.

This module contains utility functions for working with video files.  The
original stubs have been replaced with concrete implementations using
OpenCV so that the application can split videos on disk when the user
clicks the "Split at Playhead" button.  Audio tracks are not preserved
in the current implementation because the environment does not bundle
FFmpeg.  If audio preservation is required, consider using MoviePy or
FFmpeg when they are available at runtime.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

import cv2


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
        Millisecond offset at which to cut the video.  The value is
        clamped into the duration of the video; a cut at the very start
        or end will result in an empty segment which is discarded.

    Returns
    -------
    list[str]
        Two filenames corresponding to the left and right segments.  If
        splitting fails, an empty list is returned.  When the cut
        position is outside the valid range the function returns the
        original path in a single‐element list to signal no work was done.

    Notes
    -----
    The segments are saved in the same directory as the input file with
    ``_part1`` and ``_part2`` suffixes appended to the base name.  If
    names collide with existing files numeric suffixes are added until
    unique filenames are found.  Audio streams are not preserved; the
    output videos are silent.
    """
    logger = logging.getLogger(__name__)
    try:
        if not os.path.isfile(input_path):
            logger.warning("split_video: input file does not exist: %s", input_path)
            return []
        split_ms = max(0, int(split_ms))
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            logger.warning("split_video: failed to open video %s", input_path)
            return []
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0.0 or total_frames <= 0:
            logger.warning("split_video: invalid fps or frame count for %s", input_path)
            cap.release()
            return []
        frame_split = int((split_ms / 1000.0) * fps)
        frame_split = max(1, min(frame_split, total_frames - 1))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        # Use MPEG-4 part 2 codec for broad compatibility
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        base, ext = os.path.splitext(os.path.basename(input_path))
        directory = os.path.dirname(input_path) or os.getcwd()
        # Build unique output filenames
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
        # If one of the segments ended up empty, delete it and return only the other
        outputs: List[str] = []
        for path in (left_path, right_path):
            if os.path.isfile(path):
                # Check file size > 0 bytes
                try:
                    if os.path.getsize(path) > 0:
                        outputs.append(path)
                    else:
                        os.remove(path)
                except Exception:
                    pass
        logger.info("split_video: created segments %s", outputs)
        return outputs
    except Exception as exc:
        logger.exception("split_video: unexpected error splitting %s: %s", input_path, exc)
        return []
