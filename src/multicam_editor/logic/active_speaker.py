"""Active speaker diarization with pluggable backends."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


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
