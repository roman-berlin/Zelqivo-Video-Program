"""Application settings and constants."""

from multicam_editor.logic.active_speaker import DiarizationMode

DEFAULT_RESOLUTION: str = "1080p"
SUPPORTED_RESOLUTIONS: tuple[str, ...] = ("1080p", "720p")
REPLACE_AUDIO_BY_DEFAULT: bool = True

# Diarization settings
DEFAULT_DIARIZATION_MODE: DiarizationMode = DiarizationMode.REAL
DIARIZATION_MODES: tuple[DiarizationMode, ...] = (
    DiarizationMode.REAL,
    DiarizationMode.STUB,
    DiarizationMode.OFF,
)
