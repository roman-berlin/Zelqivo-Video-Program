"""Active speaker diarization with pluggable backends."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class DiarizationMode(Enum):
    """Diarization backend mode selection."""
    OFF = "off"          # No diarization, single camera
    STUB = "stub"        # Dev-only stub (EnergyVADBackend)
    REAL = "real"        # Real pyannote.audio backend


@dataclass(frozen=True)
class SpeakerSegment:
    """A single speaker segment."""
    start_ms: int
    end_ms: int
    speaker_id: int

    def __post_init__(self) -> None:
        if self.start_ms < 0:
            raise ValueError("start_ms must be >= 0")
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be > start_ms")
        if self.speaker_id < 0:
            raise ValueError("speaker_id must be >= 0")


@runtime_checkable
class DiarizationBackend(Protocol):
    """Protocol for diarization backends."""

    def diarize(self, audio_path: str, num_channels: int = 2) -> List[SpeakerSegment]:
        """Return non-overlapping speaker segments sorted by start_ms."""
        ...


class NullBackend:
    """No-op backend for OFF mode - returns empty segments."""

    def diarize(self, audio_path: str, num_channels: int = 2) -> List[SpeakerSegment]:
        logger.debug("NullBackend: diarization disabled, returning empty")
        return []


class EnergyVADBackend:
    """
    Stub backend: energy-based VAD with channel gating.

    Simulates detection by creating mock segments based on channel count.
    In production, this would analyze actual audio energy levels.
    """

    def __init__(self, min_segment_ms: int = 500, silence_threshold: float = 0.01) -> None:
        self.min_segment_ms = min_segment_ms
        self.silence_threshold = silence_threshold

    def diarize(self, audio_path: str, num_channels: int = 2) -> List[SpeakerSegment]:
        """
        Stub implementation returning mock segments.

        Creates alternating speaker segments (one per channel) for demonstration.
        Real implementation would analyze audio energy per channel.
        """
        logger.debug("EnergyVADBackend.diarize called: %s, channels=%d", audio_path, num_channels)

        if num_channels < 1:
            return []

        # Stub: create 3 alternating segments per channel (6 total for stereo)
        segments: List[SpeakerSegment] = []
        segment_duration_ms = 2000
        current_ms = 0

        for i in range(min(num_channels * 3, 10)):  # cap at 10 segments
            speaker_id = i % num_channels
            segments.append(SpeakerSegment(
                start_ms=current_ms,
                end_ms=current_ms + segment_duration_ms,
                speaker_id=speaker_id,
            ))
            current_ms += segment_duration_ms

        return segments


class PyannoteBackend:
    """
    Real diarization backend using pyannote.audio.

    Models are downloaded on first use to ~/.cache/torch/pyannote/.
    Requires HuggingFace token for some models (see pyannote docs).
    """

    _pipeline: Optional["Pipeline"] = None  # type: ignore[name-defined]
    _load_error: Optional[str] = None

    def __init__(self, use_auth_token: Optional[str] = None) -> None:
        self.use_auth_token = use_auth_token
        self._ensure_loaded()

    @classmethod
    def _ensure_loaded(cls) -> None:
        """Lazy-load the pyannote pipeline (singleton)."""
        if cls._pipeline is not None or cls._load_error is not None:
            return

        try:
            logger.info("Loading pyannote.audio diarization pipeline...")
            start = time.time()

            from pyannote.audio import Pipeline

            # Use pretrained pipeline - models auto-download on first run
            # pyannote 3.x uses HuggingFace Hub token from environment or login
            # Try different model versions with different auth approaches
            model_ids = [
                "pyannote/speaker-diarization-3.1",
                "pyannote/speaker-diarization@2.1",
            ]

            for model_id in model_ids:
                try:
                    # Try without explicit token first (uses HF_TOKEN env or cached login)
                    cls._pipeline = Pipeline.from_pretrained(model_id)
                    logger.info("Loaded model: %s", model_id)
                    break
                except Exception as e:
                    logger.debug("Model %s failed: %s", model_id, e)
                    continue

            if cls._pipeline is None:
                raise RuntimeError(
                    "Could not load any pyannote model. "
                    "Please run 'huggingface-cli login' or set HF_TOKEN environment variable."
                )

            elapsed = time.time() - start
            logger.info("Pyannote pipeline loaded in %.2fs", elapsed)

        except ImportError as e:
            cls._load_error = f"pyannote.audio not installed: {e}"
            logger.error(cls._load_error)
        except Exception as e:
            cls._load_error = f"Failed to load pyannote model: {e}"
            logger.error(cls._load_error, exc_info=True)

    @classmethod
    def is_available(cls) -> bool:
        """Check if pyannote backend is usable."""
        cls._ensure_loaded()
        return cls._pipeline is not None

    @classmethod
    def get_error(cls) -> Optional[str]:
        """Get error message if backend failed to load."""
        cls._ensure_loaded()
        return cls._load_error

    def diarize(self, audio_path: str, num_channels: int = 2) -> List[SpeakerSegment]:
        """
        Run pyannote diarization on audio file.

        Returns non-overlapping segments sorted by start_ms.
        """
        if not Path(audio_path).exists():
            logger.error("Audio file not found: %s", audio_path)
            return []

        if self._pipeline is None:
            logger.error("Pyannote pipeline not loaded: %s", self._load_error)
            return []

        logger.info("Starting diarization: %s", audio_path)
        start = time.time()

        try:
            diarization = self._pipeline(audio_path)

            # Convert pyannote output to SpeakerSegments
            segments: List[SpeakerSegment] = []
            speaker_map: dict[str, int] = {}
            total_speech_ms = 0

            for turn, _, speaker in diarization.itertracks(yield_label=True):
                # Map speaker labels to integer IDs
                if speaker not in speaker_map:
                    speaker_map[speaker] = len(speaker_map)
                speaker_id = speaker_map[speaker]

                start_ms = int(turn.start * 1000)
                end_ms = int(turn.end * 1000)

                # Skip invalid/tiny segments
                if end_ms <= start_ms:
                    continue

                segments.append(SpeakerSegment(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    speaker_id=speaker_id,
                ))
                total_speech_ms += (end_ms - start_ms)

            # Sort by start time (should already be sorted, but ensure)
            segments.sort(key=lambda s: s.start_ms)

            # Merge overlapping segments (pyannote can produce overlaps)
            segments = self._merge_overlaps(segments)

            elapsed = time.time() - start
            logger.info(
                "Diarization complete: %.2fs, %d speakers, %d segments, %.1fs total speech",
                elapsed,
                len(speaker_map),
                len(segments),
                total_speech_ms / 1000,
            )

            return segments

        except Exception as e:
            logger.error("Diarization failed: %s", e, exc_info=True)
            return []

    @staticmethod
    def _merge_overlaps(segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """Merge overlapping segments, keeping the longer/earlier one."""
        if not segments:
            return []

        merged: List[SpeakerSegment] = [segments[0]]
        for seg in segments[1:]:
            prev = merged[-1]
            if seg.start_ms < prev.end_ms:
                # Overlap: extend previous if same speaker, else truncate current
                if seg.speaker_id == prev.speaker_id:
                    merged[-1] = SpeakerSegment(
                        prev.start_ms, max(prev.end_ms, seg.end_ms), prev.speaker_id
                    )
                else:
                    # Start current segment after previous ends
                    if seg.end_ms > prev.end_ms:
                        merged.append(SpeakerSegment(
                            prev.end_ms, seg.end_ms, seg.speaker_id
                        ))
            else:
                merged.append(seg)
        return merged


def create_backend(
    mode: DiarizationMode,
    fallback_on_error: bool = True,
) -> tuple[DiarizationBackend, Optional[str]]:
    """
    Factory to create diarization backend based on mode.

    Args:
        mode: Which backend to use
        fallback_on_error: If True and REAL backend fails, fall back to STUB

    Returns:
        (backend, error_message) - error_message is None if OK
    """
    if mode == DiarizationMode.OFF:
        return NullBackend(), None

    if mode == DiarizationMode.STUB:
        return EnergyVADBackend(), None

    if mode == DiarizationMode.REAL:
        if PyannoteBackend.is_available():
            return PyannoteBackend(), None
        else:
            error = PyannoteBackend.get_error() or "Unknown error loading pyannote"
            if fallback_on_error:
                logger.warning("Falling back to stub backend: %s", error)
                return EnergyVADBackend(), error
            else:
                return NullBackend(), error

    # Unknown mode, default to stub
    return EnergyVADBackend(), f"Unknown mode: {mode}"


class ActiveSpeakerDetector:
    """Main detector with pluggable backend."""

    def __init__(self, backend: DiarizationBackend | None = None) -> None:
        self._backend = backend or EnergyVADBackend()

    @property
    def backend(self) -> DiarizationBackend:
        return self._backend

    @backend.setter
    def backend(self, value: DiarizationBackend) -> None:
        self._backend = value

    def detect(self, audio_path: str, num_channels: int = 2) -> List[SpeakerSegment]:
        """
        Run diarization and validate output.

        Returns sorted, non-overlapping segments.
        """
        segments = self._backend.diarize(audio_path, num_channels)
        self._validate_segments(segments)
        return segments

    @staticmethod
    def _validate_segments(segments: List[SpeakerSegment]) -> None:
        """Ensure segments are sorted and non-overlapping."""
        for i, seg in enumerate(segments):
            if i > 0:
                prev = segments[i - 1]
                if seg.start_ms < prev.start_ms:
                    raise ValueError(f"Segments not sorted at index {i}")
                if seg.start_ms < prev.end_ms:
                    raise ValueError(f"Overlapping segments at index {i}")


# Legacy API compatibility
def detect_active_speakers(audio_path: str, num_channels: int = 2) -> List[dict]:
    """
    Legacy function for backward compatibility.

    Returns list of dicts: [{"start_ms": int, "end_ms": int, "speaker_id": int}, ...]
    """
    detector = ActiveSpeakerDetector()
    segments = detector.detect(audio_path, num_channels)
    return [
        {"start_ms": s.start_ms, "end_ms": s.end_ms, "speaker_id": s.speaker_id}
        for s in segments
    ]
