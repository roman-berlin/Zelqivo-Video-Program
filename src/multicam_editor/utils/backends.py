"""Backend availability checker for optional dependencies."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class BackendStatus:
    """Status of a backend/feature."""
    name: str
    available: bool
    error: Optional[str] = None


def check_backends() -> Dict[str, BackendStatus]:
    """
    Check which backends are available.

    Returns a dict with status for each backend:
    - core: Always available (PyQt, numpy, ffmpeg-python)
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
        name="Core (PyQt, numpy, ffmpeg)",
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


if __name__ == "__main__":
    # Allow running as: python -m multicam_editor.utils.backends
    print_backend_status()
