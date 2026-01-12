# file: utils/ffprobe.py
"""FFprobe wrapper for extracting video metadata.

Provides cached probe function returning duration_ms, fps, resolution, streams.
Cache keyed by (path + mtime) for invalidation on file changes.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Tuple, List

logger = logging.getLogger(__name__)


@dataclass
class StreamInfo:
    """Info about a single stream (video or audio)."""
    codec_type: str  # "video" or "audio"
    codec_name: str
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    rotation: Optional[int] = None  # degrees (90, 180, 270) if present


@dataclass
class ProbeResult:
    """Complete metadata for a media file."""
    duration_ms: int
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    streams: Optional[List[StreamInfo]] = None
    error: Optional[str] = None
    rotation: Optional[int] = None  # degrees if rotation metadata present
    vfr_risk: bool = False  # True if avg_fps != r_fps (likely VFR)

    def resolution_str(self) -> str:
        """Return resolution as 'WxH' or empty string."""
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return ""

    def fps_str(self) -> str:
        """Return fps as string with 2 decimals or empty."""
        if self.fps:
            return f"{self.fps:.2f}"
        return ""


# Cache: (path, mtime) -> ProbeResult
_probe_cache: Dict[Tuple[str, float], ProbeResult] = {}

# Legacy cache for backward compat
_duration_cache: Dict[Tuple[str, float], int] = {}

_ffprobe_path: Optional[str] = None
_ffprobe_checked: bool = False


def _get_app_dir() -> Path:
    """Get the application directory (frozen or source)."""
    import sys
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        return Path(sys._MEIPASS)
    else:
        # Running from source - project root
        return Path(__file__).resolve().parent.parent.parent.parent


def _find_ffprobe() -> Optional[str]:
    """Locate ffprobe executable. Returns path or None if not found."""
    global _ffprobe_path, _ffprobe_checked
    if _ffprobe_checked:
        return _ffprobe_path
    _ffprobe_checked = True

    # 1. Check bundled location first (for frozen builds)
    bundled_path = _get_app_dir() / "tools" / "ffmpeg" / "ffprobe.exe"
    if bundled_path.is_file():
        _ffprobe_path = str(bundled_path)
        logger.info("Using bundled ffprobe: %s", _ffprobe_path)
        return _ffprobe_path

    # 2. Check if ffprobe is in PATH
    try:
        result = subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode == 0:
            _ffprobe_path = "ffprobe"
            return _ffprobe_path
    except Exception:
        pass
    # 3. Common Windows locations
    if os.name == "nt":
        common_paths = [
            r"C:\ffmpeg\bin\ffprobe.exe",
            r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
            os.path.expanduser(r"~\ffmpeg\bin\ffprobe.exe"),
        ]
        # Add WinGet installation paths (dynamic version folder)
        winget_base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
        if os.path.isdir(winget_base):
            for pkg_dir in os.listdir(winget_base):
                if pkg_dir.startswith("Gyan.FFmpeg"):
                    pkg_path = os.path.join(winget_base, pkg_dir)
                    # Search for ffprobe.exe in the package
                    for root, dirs, files in os.walk(pkg_path):
                        if "ffprobe.exe" in files:
                            common_paths.append(os.path.join(root, "ffprobe.exe"))
                            break
        for p in common_paths:
            if os.path.isfile(p):
                _ffprobe_path = p
                return _ffprobe_path
    return None


def _parse_fps(stream: dict) -> Optional[float]:
    """Parse fps from stream data (avg_frame_rate or r_frame_rate)."""
    for key in ("avg_frame_rate", "r_frame_rate"):
        val = stream.get(key, "")
        if val and "/" in val:
            try:
                num, den = val.split("/")
                if int(den) != 0:
                    return float(num) / float(den)
            except (ValueError, ZeroDivisionError):
                pass
    return None


def _parse_rotation(stream: dict) -> Optional[int]:
    """Extract rotation from stream side_data_list or tags."""
    # Check side_data_list (newer ffprobe)
    for side_data in stream.get("side_data_list", []):
        if side_data.get("side_data_type") == "Display Matrix":
            rot = side_data.get("rotation")
            if rot is not None:
                return int(rot)
    # Check tags (older format)
    tags = stream.get("tags", {})
    rot = tags.get("rotate") or tags.get("rotation")
    if rot:
        try:
            return int(rot)
        except (ValueError, TypeError):
            pass
    return None


def _check_vfr_risk(stream: dict) -> bool:
    """Check if video stream likely has variable frame rate.

    Compares avg_frame_rate vs r_frame_rate - significant difference indicates VFR.
    """
    avg_str = stream.get("avg_frame_rate", "")
    r_str = stream.get("r_frame_rate", "")
    if not avg_str or not r_str:
        return False

    def parse_rate(s: str) -> Optional[float]:
        if "/" in s:
            try:
                num, den = s.split("/")
                if int(den) != 0:
                    return float(num) / float(den)
            except (ValueError, ZeroDivisionError):
                pass
        return None

    avg_fps = parse_rate(avg_str)
    r_fps = parse_rate(r_str)
    if avg_fps is None or r_fps is None or r_fps == 0:
        return False

    # Significant difference (>5%) indicates VFR risk
    diff = abs(avg_fps - r_fps) / max(avg_fps, r_fps)
    return diff > 0.05


def _parse_streams(data: dict) -> Tuple[List[StreamInfo], Optional[StreamInfo], Optional[StreamInfo], Optional[int], bool]:
    """Parse streams from ffprobe JSON.

    Returns: (all_streams, first_video, first_audio, rotation, vfr_risk)
    """
    streams: List[StreamInfo] = []
    first_video: Optional[StreamInfo] = None
    first_audio: Optional[StreamInfo] = None
    rotation: Optional[int] = None
    vfr_risk: bool = False

    for s in data.get("streams", []):
        codec_type = s.get("codec_type", "")
        info = StreamInfo(
            codec_type=codec_type,
            codec_name=s.get("codec_name", "unknown"),
        )
        if codec_type == "video":
            info.width = s.get("width")
            info.height = s.get("height")
            info.fps = _parse_fps(s)
            info.rotation = _parse_rotation(s)
            if first_video is None:
                first_video = info
                rotation = info.rotation
                vfr_risk = _check_vfr_risk(s)
        elif codec_type == "audio":
            info.sample_rate = int(s["sample_rate"]) if s.get("sample_rate") else None
            info.channels = s.get("channels")
            if first_audio is None:
                first_audio = info
        streams.append(info)

    return streams, first_video, first_audio, rotation, vfr_risk


def probe(path: str) -> ProbeResult:
    """Probe media file for metadata. Returns cached result if available.

    Returns ProbeResult with error field set on failure (no exception raised).
    Thread-safe for reads; call from background thread for large batches.

    Args:
        path: Path to media file

    Returns:
        ProbeResult with metadata or error message
    """
    if not path:
        return ProbeResult(duration_ms=0, error="Empty path")

    if not os.path.isfile(path):
        return ProbeResult(duration_ms=0, error="File not found")

    # Cache key: (path, mtime)
    try:
        mtime = os.path.getmtime(path)
    except Exception:
        mtime = 0.0
    cache_key = (path, mtime)

    if cache_key in _probe_cache:
        return _probe_cache[cache_key]

    ffprobe = _find_ffprobe()
    if not ffprobe:
        return ProbeResult(duration_ms=0, error="ffprobe not found")

    try:
        cmd = [
            ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            path
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode != 0:
            err_msg = result.stderr.decode("utf-8", errors="replace").strip()[:200]
            return ProbeResult(duration_ms=0, error=f"ffprobe failed: {err_msg or 'unknown error'}")

        data = json.loads(result.stdout.decode("utf-8", errors="replace"))

        # Parse duration
        duration_str = data.get("format", {}).get("duration")
        if duration_str is None:
            return ProbeResult(duration_ms=0, error="No duration in file")
        duration_ms = int(float(duration_str) * 1000)

        # Parse streams
        streams, video, audio, rotation, vfr_risk = _parse_streams(data)

        probe_result = ProbeResult(
            duration_ms=duration_ms,
            width=video.width if video else None,
            height=video.height if video else None,
            fps=video.fps if video else None,
            video_codec=video.codec_name if video else None,
            audio_codec=audio.codec_name if audio else None,
            streams=streams,
            rotation=rotation,
            vfr_risk=vfr_risk,
        )

        _probe_cache[cache_key] = probe_result
        _duration_cache[cache_key] = duration_ms  # backward compat
        logger.debug(f"Probed {path}: {duration_ms}ms, {probe_result.resolution_str()}, {probe_result.fps_str()} fps")
        return probe_result

    except subprocess.TimeoutExpired:
        return ProbeResult(duration_ms=0, error="ffprobe timeout")
    except json.JSONDecodeError as e:
        return ProbeResult(duration_ms=0, error=f"Invalid JSON: {e}")
    except Exception as e:
        logger.debug(f"ffprobe error for {path}: {e}", exc_info=True)
        return ProbeResult(duration_ms=0, error=str(e))


def get_duration_ms(path: str) -> Optional[int]:
    """Get video duration in milliseconds using ffprobe.

    Returns cached result if available. Returns None on error.
    Backward-compatible wrapper around probe().

    Args:
        path: Path to video file

    Returns:
        Duration in milliseconds, or None if probe failed
    """
    result = probe(path)
    if result.error:
        return None
    return result.duration_ms


def is_ffprobe_available() -> bool:
    """Check if ffprobe is available on the system."""
    return _find_ffprobe() is not None


def has_audio_stream(path: str) -> bool:
    """Check if a media file has at least one audio stream.

    Args:
        path: Path to media file

    Returns:
        True if file has audio, False otherwise or on error
    """
    result = probe(path)
    if result.error or not result.streams:
        return False
    return any(s.codec_type == "audio" for s in result.streams)


def clear_cache() -> None:
    """Clear the probe cache. Useful for testing."""
    _probe_cache.clear()
    _duration_cache.clear()


def reset_ffprobe_detection() -> None:
    """Reset ffprobe path detection. Useful for testing."""
    global _ffprobe_path, _ffprobe_checked
    _ffprobe_path = None
    _ffprobe_checked = False
