"""Application settings and constants.

This module provides safe-to-import constants for the application.
Heavy imports (like DiarizationMode enum) are loaded lazily to prevent
import-time failures when optional dependencies are missing.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

# Resolution settings
DEFAULT_RESOLUTION: str = "1080p"
SUPPORTED_RESOLUTIONS: tuple[str, ...] = ("1080p", "720p")
REPLACE_AUDIO_BY_DEFAULT: bool = True

# Diarization settings (string constants - safe to import)
# Use get_diarization_mode() to convert to enum
DEFAULT_DIARIZATION_MODE_STR: str = "hybrid"  # Hybrid is the recommended default
DIARIZATION_MODE_STRINGS: tuple[str, ...] = ("off", "stub", "energy", "real", "lips", "hybrid")

# QA Overlay settings
QA_OVERLAY_ENABLED_DEFAULT: bool = False


def get_diarization_mode(mode_str: str):
    """Convert mode string to DiarizationMode enum.

    Lazy-loads the enum to avoid import-time failures.

    Args:
        mode_str: One of "off", "stub", "energy", "real", "lips", "hybrid"

    Returns:
        DiarizationMode enum value, or ENERGY as fallback
    """
    from ..logic.active_speaker import DiarizationMode

    mode_map = {
        "off": DiarizationMode.OFF,
        "stub": DiarizationMode.STUB,
        "energy": DiarizationMode.ENERGY,
        "real": DiarizationMode.REAL,
        "lips": DiarizationMode.LIPS,
        "hybrid": DiarizationMode.HYBRID,
    }
    return mode_map.get(mode_str.lower(), DiarizationMode.ENERGY)


def get_default_diarization_mode():
    """Get the default diarization mode as enum.

    Returns:
        DiarizationMode.ENERGY (V1 default)
    """
    return get_diarization_mode(DEFAULT_DIARIZATION_MODE_STR)


def get_available_diarization_modes() -> list[str]:
    """Get list of available diarization mode strings.

    Checks which backends are actually available.

    Returns:
        List of mode strings that can be used.
    """
    from ..utils.backends import check_backends

    modes = ["off", "energy"]  # Always available

    backends = check_backends()
    if backends.get("pyannote") and backends["pyannote"].available:
        modes.append("real")
    
    # LIPS mode is always available if mediapipe is installed
    try:
        import mediapipe  # noqa: F401
        modes.append("lips")
    except ImportError:
        pass  # MediaPipe not installed

    return modes


# Legacy compatibility - provide enum types only when type checking
if TYPE_CHECKING:
    from ..logic.active_speaker import DiarizationMode
