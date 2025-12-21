# file: utils/file_utils.py
from __future__ import annotations
import os
from typing import Iterable, List, Tuple

# Extensions - common video formats supported by ffmpeg/OpenCV
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".flv", ".wmv"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a"}


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def is_audio(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in AUDIO_EXTS


# Back-compat aliases expected by utils/__init__.py
is_supported_video_file = is_video
is_supported_audio_file = is_audio


def normalize_paths(paths: Iterable[str]) -> List[str]:
    """Normalize to absolute paths; preserve order; de-dup."""
    seen: set[str] = set()
    out: List[str] = []
    for p in paths:
        if not p:
            continue
        ap = os.path.normpath(os.path.abspath(p))
        if ap not in seen:
            seen.add(ap)
            out.append(ap)
    return out


def dialog_filter_videos() -> str:
    return "Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.m4v *.flv *.wmv)"


def split_by_type(paths: Iterable[str]) -> Tuple[List[str], List[str]]:
    normed = normalize_paths(paths)
    vids = [p for p in normed if is_video(p)]
    non = [p for p in normed if not is_video(p)]
    return vids, non


def safe_basename(path: str) -> str:
    try:
        return os.path.basename(path)
    except Exception:
        return path
