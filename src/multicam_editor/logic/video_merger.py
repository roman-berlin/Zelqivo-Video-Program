"""Video merging module."""

from typing import List, Dict, Optional


def merge_videos(
    segment_definitions: List[Dict[str, float]],
    input_video_paths: List[str],
    output_path: str,
    resolution: str = "1080p",
    aligned_audio_path: Optional[str] = None,
) -> None:
    """
    Merge videos according to the given segment definitions (stub).
    Does nothing yet.
    """
    return None
