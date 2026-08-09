"""Backend availability checker for optional dependencies.

Provides health check functionality for system diagnostics,
including ffmpeg/ffprobe validation and optional ML backend status.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BackendStatus:
    """Status of a backend/feature."""
    name: str
    available: bool
    error: Optional[str] = None
    path: Optional[str] = None  # For executables like ffmpeg


@dataclass
class HealthCheckResult:
    """Complete health check result for the system."""
    ready: bool  # True if basic features work
    ffmpeg_available: bool
    ffmpeg_path: Optional[str]
    ffprobe_available: bool
    ffprobe_path: Optional[str]
    backends: Dict[str, BackendStatus] = field(default_factory=dict)
    python_version: str = ""
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """Return human-readable status summary."""
        if self.ready:
            if all(b.available for b in self.backends.values()):
                return "Ready (all features)"
            return "Ready (basic features)"
        return "Not ready - missing required dependencies"


def check_backends() -> Dict[str, BackendStatus]:
    """
    Check which backends are available.

    Returns a dict with status for each backend:
    - core: Always available (Qt, numpy, ffmpeg-python)
    - audio_sync: Requires librosa, soundfile
    - pyannote: Requires pyannote.audio, torch
    - energy_vad: Always available (CPU-only)

    Example usage:
        >>> from multicam_editor.utils.backends import check_backends
        >>> status = check_backends()
        >>> for name, s in status.items():
        ...     print(f"{name}: {'OK' if s.available else s.error}")
    """
    results: Dict[str, BackendStatus] = {}

    # Core - always available if we got this far
    results["core"] = BackendStatus(
        name="Core (Qt, numpy, ffmpeg)",
        available=True,
    )

    # Energy VAD - always available (CPU-only)
    results["energy_vad"] = BackendStatus(
        name="Energy VAD (CPU speaker detection)",
        available=True,
    )

    # Audio sync (librosa, soundfile)
    try:
        from ..logic.audio_sync import is_audio_sync_available
        available, error = is_audio_sync_available()
        results["audio_sync"] = BackendStatus(
            name="Audio Sync (librosa, soundfile)",
            available=available,
            error=error,
        )
    except Exception as e:
        results["audio_sync"] = BackendStatus(
            name="Audio Sync (librosa, soundfile)",
            available=False,
            error=str(e),
        )

    # Pyannote (real AI diarization)
    try:
        from ..logic.active_speaker import PyannoteBackend
        available = PyannoteBackend.is_available()
        error = PyannoteBackend.get_error() if not available else None
        results["pyannote"] = BackendStatus(
            name="Pyannote (AI diarization)",
            available=available,
            error=error,
        )
    except ImportError as e:
        results["pyannote"] = BackendStatus(
            name="Pyannote (AI diarization)",
            available=False,
            error=f"Import error: {e}",
        )
    except Exception as e:
        results["pyannote"] = BackendStatus(
            name="Pyannote (AI diarization)",
            available=False,
            error=str(e),
        )

    return results


def print_backend_status() -> None:
    """Print backend status to console (for CLI diagnostics)."""
    print("\n=== MultiCamEditor Backend Status ===\n")
    status = check_backends()

    for key, s in status.items():
        if s.available:
            print(f"  [OK] {s.name}")
        else:
            print(f"  [--] {s.name}")
            if s.error:
                print(f"       {s.error}")

    print("\nTo enable AI features, install: pip install multicam-editor[ai]")
    print()


def get_available_diarization_modes() -> list[str]:
    """Return list of available diarization mode names.

    Always includes: OFF, ENERGY
    If pyannote available: also includes REAL
    """
    modes = ["OFF", "ENERGY"]
    status = check_backends()
    if status.get("pyannote", BackendStatus("", False)).available:
        modes.append("REAL")
    return modes


def run_health_check() -> HealthCheckResult:
    """Run comprehensive health check of the system.

    Checks:
    - ffmpeg/ffprobe availability and paths
    - All backend availability
    - Python version

    Returns:
        HealthCheckResult with complete status
    """
    from ..utils.ffmpeg import is_ffmpeg_available, get_ffmpeg_path
    from ..utils.ffprobe import is_ffprobe_available

    warnings: List[str] = []

    # Check ffmpeg
    ffmpeg_available = is_ffmpeg_available()
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_available:
        warnings.append("ffmpeg not found - video processing will fail")

    # Check ffprobe
    ffprobe_available = is_ffprobe_available()
    ffprobe_path = None
    if ffprobe_available:
        try:
            from ..utils.ffprobe import _find_ffprobe
            ffprobe_path = _find_ffprobe()
        except Exception:
            pass
    if not ffprobe_available:
        warnings.append("ffprobe not found - video metadata extraction will fail")

    # Check backends
    backends = check_backends()

    # Add warnings for unavailable optional backends
    if not backends.get("audio_sync", BackendStatus("", False)).available:
        warnings.append("Audio sync unavailable - install librosa for external audio support")
    if not backends.get("pyannote", BackendStatus("", False)).available:
        warnings.append("Pyannote unavailable - using CPU-only speaker detection")

    # System is ready if ffmpeg and ffprobe are available
    ready = ffmpeg_available and ffprobe_available

    return HealthCheckResult(
        ready=ready,
        ffmpeg_available=ffmpeg_available,
        ffmpeg_path=ffmpeg_path,
        ffprobe_available=ffprobe_available,
        ffprobe_path=ffprobe_path,
        backends=backends,
        python_version=sys.version,
        warnings=warnings,
    )


def print_health_check() -> bool:
    """Print comprehensive health check to console.

    Returns:
        True if system is ready, False otherwise
    """
    result = run_health_check()

    print("\n" + "=" * 50)
    print("  MultiCamEditor Health Check")
    print("=" * 50 + "\n")

    # Required dependencies
    print("Required:")
    if result.ffmpeg_available:
        print(f"  [OK] FFmpeg: {result.ffmpeg_path or 'in PATH'}")
    else:
        print("  [!!] FFmpeg: NOT FOUND")

    if result.ffprobe_available:
        print(f"  [OK] FFprobe: {result.ffprobe_path or 'in PATH'}")
    else:
        print("  [!!] FFprobe: NOT FOUND")

    print()

    # Backends
    print("Backends:")
    for key, status in result.backends.items():
        if status.available:
            print(f"  [OK] {status.name}")
        else:
            print(f"  [--] {status.name}")
            if status.error:
                # Truncate long error messages
                error = status.error[:60] + "..." if len(status.error) > 60 else status.error
                print(f"       {error}")

    print()

    # Warnings
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  [!] {warning}")
        print()

    # Summary
    print(f"Python: {result.python_version.split()[0]}")
    print(f"Status: {result.summary()}")
    print()

    if not result.ready:
        print("To fix: Install ffmpeg and ensure it's in your PATH")
        print("  Windows: choco install ffmpeg  OR  download from ffmpeg.org")
        print("  macOS:   brew install ffmpeg")
        print("  Linux:   apt install ffmpeg")
        print()

    return result.ready


if __name__ == "__main__":
    # Allow running as: python -m multicam_editor.utils.backends
    print_health_check()
