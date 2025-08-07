"""File utility functions."""

import os
from typing import Iterable

VIDEO_EXTENSIONS: Iterable[str] = {".mp4", ".avi", ".mov"}
AUDIO_EXTENSIONS: Iterable[str] = {".wav", ".mp3"}


def is_supported_video_file(path: str) -> bool:
    """Return True if the file has a supported video extension."""
    _, ext = os.path.splitext(path.lower())
    return ext in VIDEO_EXTENSIONS


def is_supported_audio_file(path: str) -> bool:
    """Return True if the file has a supported audio extension."""
    _, ext = os.path.splitext(path.lower())
    return ext in AUDIO_EXTENSIONS
