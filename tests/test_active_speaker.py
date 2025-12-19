"""Tests for active speaker diarization."""

import pytest

from multicam_editor.logic.active_speaker import (
    ActiveSpeakerDetector,
    DiarizationBackend,
    EnergyVADBackend,
    SpeakerSegment,
    detect_active_speakers,
)


class TestSpeakerSegment:
    """Tests for SpeakerSegment dataclass."""

    def test_valid_segment(self) -> None:
        seg = SpeakerSegment(start_ms=0, end_ms=1000, speaker_id=0)
        assert seg.start_ms == 0
        assert seg.end_ms == 1000
        assert seg.speaker_id == 0

    def test_negative_start_raises(self) -> None:
        with pytest.raises(ValueError, match="start_ms must be >= 0"):
            SpeakerSegment(start_ms=-1, end_ms=1000, speaker_id=0)

    def test_end_not_greater_than_start_raises(self) -> None:
        with pytest.raises(ValueError, match="end_ms must be > start_ms"):
            SpeakerSegment(start_ms=1000, end_ms=1000, speaker_id=0)
        with pytest.raises(ValueError, match="end_ms must be > start_ms"):
            SpeakerSegment(start_ms=1000, end_ms=500, speaker_id=0)

    def test_negative_speaker_id_raises(self) -> None:
        with pytest.raises(ValueError, match="speaker_id must be >= 0"):
            SpeakerSegment(start_ms=0, end_ms=1000, speaker_id=-1)


class TestEnergyVADBackend:
    """Tests for stub EnergyVADBackend."""

    def test_returns_segments(self) -> None:
        backend = EnergyVADBackend()
        segments = backend.diarize("dummy.wav", num_channels=2)
        assert len(segments) > 0

    def test_segments_are_sorted(self) -> None:
        backend = EnergyVADBackend()
        segments = backend.diarize("dummy.wav", num_channels=2)
        for i in range(1, len(segments)):
            assert segments[i].start_ms >= segments[i - 1].start_ms

    def test_segments_non_overlapping(self) -> None:
        backend = EnergyVADBackend()
        segments = backend.diarize("dummy.wav", num_channels=2)
        for i in range(1, len(segments)):
            assert segments[i].start_ms >= segments[i - 1].end_ms

    def test_zero_channels_returns_empty(self) -> None:
        backend = EnergyVADBackend()
        segments = backend.diarize("dummy.wav", num_channels=0)
        assert segments == []

    def test_single_channel(self) -> None:
        backend = EnergyVADBackend()
        segments = backend.diarize("dummy.wav", num_channels=1)
        assert len(segments) == 3
        for seg in segments:
            assert seg.speaker_id == 0

    def test_stereo_channels(self) -> None:
        backend = EnergyVADBackend()
        segments = backend.diarize("dummy.wav", num_channels=2)
        assert len(segments) == 6
        speaker_ids = {seg.speaker_id for seg in segments}
        assert speaker_ids == {0, 1}


class TestActiveSpeakerDetector:
    """Tests for ActiveSpeakerDetector."""

    def test_default_backend(self) -> None:
        detector = ActiveSpeakerDetector()
        assert isinstance(detector.backend, EnergyVADBackend)

    def test_custom_backend(self) -> None:
        class CustomBackend:
            def diarize(self, audio_path: str, num_channels: int = 2):
                return [SpeakerSegment(0, 1000, 0)]

        detector = ActiveSpeakerDetector(backend=CustomBackend())
        segments = detector.detect("test.wav")
        assert len(segments) == 1

    def test_backend_setter(self) -> None:
        detector = ActiveSpeakerDetector()
        new_backend = EnergyVADBackend(min_segment_ms=1000)
        detector.backend = new_backend
        assert detector.backend is new_backend

    def test_validates_sorted(self) -> None:
        class BadBackend:
            def diarize(self, audio_path: str, num_channels: int = 2):
                return [
                    SpeakerSegment(2000, 3000, 0),
                    SpeakerSegment(0, 1000, 0),  # out of order
                ]

        detector = ActiveSpeakerDetector(backend=BadBackend())
        with pytest.raises(ValueError, match="not sorted"):
            detector.detect("test.wav")

    def test_validates_non_overlapping(self) -> None:
        class BadBackend:
            def diarize(self, audio_path: str, num_channels: int = 2):
                return [
                    SpeakerSegment(0, 2000, 0),
                    SpeakerSegment(1000, 3000, 1),  # overlaps
                ]

        detector = ActiveSpeakerDetector(backend=BadBackend())
        with pytest.raises(ValueError, match="Overlapping"):
            detector.detect("test.wav")

    def test_detect_returns_valid_segments(self) -> None:
        detector = ActiveSpeakerDetector()
        segments = detector.detect("test.wav", num_channels=2)
        assert len(segments) > 0
        # Verify sorted
        for i in range(1, len(segments)):
            assert segments[i].start_ms >= segments[i - 1].start_ms
        # Verify non-overlapping
        for i in range(1, len(segments)):
            assert segments[i].start_ms >= segments[i - 1].end_ms


class TestLegacyAPI:
    """Tests for legacy detect_active_speakers function."""

    def test_returns_list_of_dicts(self) -> None:
        result = detect_active_speakers("test.wav", num_channels=2)
        assert isinstance(result, list)
        assert len(result) > 0
        for item in result:
            assert isinstance(item, dict)
            assert "start_ms" in item
            assert "end_ms" in item
            assert "speaker_id" in item

    def test_dict_values_are_integers(self) -> None:
        result = detect_active_speakers("test.wav", num_channels=2)
        for item in result:
            assert isinstance(item["start_ms"], int)
            assert isinstance(item["end_ms"], int)
            assert isinstance(item["speaker_id"], int)


class TestDiarizationBackendProtocol:
    """Tests for DiarizationBackend protocol."""

    def test_energy_vad_is_backend(self) -> None:
        backend = EnergyVADBackend()
        assert isinstance(backend, DiarizationBackend)

    def test_custom_class_satisfies_protocol(self) -> None:
        class MyBackend:
            def diarize(self, audio_path: str, num_channels: int = 2):
                return []

        assert isinstance(MyBackend(), DiarizationBackend)
