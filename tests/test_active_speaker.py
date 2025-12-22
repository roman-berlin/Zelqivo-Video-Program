"""Tests for active speaker diarization."""

import os
from pathlib import Path

import pytest

from multicam_editor.logic.active_speaker import (
    ActiveSpeakerDetector,
    DiarizationBackend,
    DiarizationMode,
    EnergyVADBackend,
    NullBackend,
    PyannoteBackend,
    RealEnergyVADBackend,
    SpeakerSegment,
    create_backend,
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


class TestNullBackend:
    """Tests for NullBackend (OFF mode)."""

    def test_returns_empty_segments(self) -> None:
        backend = NullBackend()
        segments = backend.diarize("any_file.wav", num_channels=2)
        assert segments == []

    def test_is_diarization_backend(self) -> None:
        backend = NullBackend()
        assert isinstance(backend, DiarizationBackend)


class TestDiarizationMode:
    """Tests for DiarizationMode enum."""

    def test_mode_values(self) -> None:
        assert DiarizationMode.OFF.value == "off"
        assert DiarizationMode.STUB.value == "stub"
        assert DiarizationMode.ENERGY.value == "energy"
        assert DiarizationMode.REAL.value == "real"

    def test_from_string(self) -> None:
        assert DiarizationMode("off") == DiarizationMode.OFF
        assert DiarizationMode("stub") == DiarizationMode.STUB
        assert DiarizationMode("energy") == DiarizationMode.ENERGY
        assert DiarizationMode("real") == DiarizationMode.REAL


class TestRealEnergyVADBackend:
    """Tests for RealEnergyVADBackend (ENERGY mode - CPU-only)."""

    def test_is_diarization_backend(self) -> None:
        backend = RealEnergyVADBackend()
        assert isinstance(backend, DiarizationBackend)

    def test_fallback_to_stub_without_audio_paths(self) -> None:
        """Without camera audio paths set, falls back to stub behavior."""
        backend = RealEnergyVADBackend()
        # No camera paths set - should fallback to stub
        segments = backend.diarize("dummy.wav", num_channels=2)
        assert len(segments) > 0  # Stub returns mock segments

    def test_set_camera_audio_paths(self) -> None:
        """Test that camera audio paths can be set."""
        backend = RealEnergyVADBackend()
        backend.set_camera_audio_paths(["/path/cam0.wav", "/path/cam1.wav"])
        assert len(backend._camera_audio_paths) == 2

    def test_custom_window_size(self) -> None:
        """Test custom window size initialization."""
        backend = RealEnergyVADBackend(window_ms=100)
        assert backend.window_ms == 100

    def test_custom_silence_threshold(self) -> None:
        """Test custom silence threshold initialization."""
        backend = RealEnergyVADBackend(silence_threshold=0.05)
        assert backend.silence_threshold == 0.05

    def test_compute_rms_empty_samples(self) -> None:
        """Test RMS computation with empty samples."""
        rms = RealEnergyVADBackend._compute_rms([])
        assert rms == 0.0

    def test_compute_rms_valid_samples(self) -> None:
        """Test RMS computation with valid samples."""
        # Constant signal should have RMS equal to amplitude
        samples = [0.5, 0.5, 0.5, 0.5]
        rms = RealEnergyVADBackend._compute_rms(samples)
        assert abs(rms - 0.5) < 0.001

    def test_compute_rms_sine_wave(self) -> None:
        """Test RMS computation with sine-like samples."""
        import math
        samples = [math.sin(i * 0.1) for i in range(100)]
        rms = RealEnergyVADBackend._compute_rms(samples)
        # RMS of sine wave is ~0.707 * amplitude
        assert 0.6 < rms < 0.75

    def test_merge_windows_empty(self) -> None:
        """Test merging with empty window winners."""
        backend = RealEnergyVADBackend()
        segments = backend._merge_windows_to_segments([], 200, 10000)
        assert segments == []

    def test_merge_windows_single_speaker(self) -> None:
        """Test merging with single speaker throughout."""
        backend = RealEnergyVADBackend()
        window_winners = [0, 0, 0, 0, 0]
        segments = backend._merge_windows_to_segments(window_winners, 200, 1000)
        assert len(segments) == 1
        assert segments[0].speaker_id == 0
        assert segments[0].start_ms == 0
        assert segments[0].end_ms == 1000

    def test_merge_windows_two_speakers(self) -> None:
        """Test merging with two alternating speakers."""
        backend = RealEnergyVADBackend(min_segment_ms=200)
        # cam0 for 3 windows, then cam1 for 2 windows
        window_winners = [0, 0, 0, 1, 1]
        segments = backend._merge_windows_to_segments(window_winners, 200, 1000)
        assert len(segments) == 2
        assert segments[0].speaker_id == 0
        assert segments[0].start_ms == 0
        assert segments[0].end_ms == 600
        assert segments[1].speaker_id == 1
        assert segments[1].start_ms == 600


class TestCreateBackend:
    """Tests for create_backend factory function."""

    def test_off_mode_returns_null_backend(self) -> None:
        backend, error = create_backend(DiarizationMode.OFF)
        assert isinstance(backend, NullBackend)
        assert error is None

    def test_stub_mode_returns_energy_vad(self) -> None:
        backend, error = create_backend(DiarizationMode.STUB)
        assert isinstance(backend, EnergyVADBackend)
        assert error is None

    def test_energy_mode_returns_real_energy_backend(self) -> None:
        """ENERGY mode returns RealEnergyVADBackend."""
        backend, error = create_backend(DiarizationMode.ENERGY)
        assert isinstance(backend, RealEnergyVADBackend)
        assert error is None

    def test_real_mode_fallback_on_error(self) -> None:
        # When pyannote not available, should fallback to ENERGY with error msg
        backend, error = create_backend(DiarizationMode.REAL, fallback_on_error=True)
        # Either pyannote works, or we get RealEnergyVADBackend with error
        assert isinstance(backend, (PyannoteBackend, RealEnergyVADBackend))
        if isinstance(backend, RealEnergyVADBackend):
            assert error is not None  # Should have error message

    def test_real_mode_no_fallback(self) -> None:
        # When no fallback, should return NullBackend with error
        backend, error = create_backend(DiarizationMode.REAL, fallback_on_error=False)
        if not PyannoteBackend.is_available():
            assert isinstance(backend, NullBackend)
            assert error is not None


class TestPyannoteBackend:
    """Tests for PyannoteBackend availability checking."""

    def test_is_available_returns_bool(self) -> None:
        result = PyannoteBackend.is_available()
        assert isinstance(result, bool)

    def test_get_error_returns_str_or_none(self) -> None:
        error = PyannoteBackend.get_error()
        assert error is None or isinstance(error, str)

    def test_backend_is_protocol(self) -> None:
        # If available, it should satisfy protocol
        if PyannoteBackend.is_available():
            backend = PyannoteBackend()
            assert isinstance(backend, DiarizationBackend)


# =============================================================================
# Integration Tests (require env setup)
# =============================================================================

@pytest.mark.integration
class TestPyannoteIntegration:
    """
    Integration tests for REAL pyannote diarization.

    Run with: DIARIZATION_SMOKE_AUDIO=path/to/audio.wav pytest -m integration

    Skips if:
    - DIARIZATION_SMOKE_AUDIO env var not set or file doesn't exist
    - HuggingFace auth missing or gated model not accepted
    """

    @pytest.fixture
    def audio_path(self) -> str:
        """Get audio path from env, skip if missing."""
        audio_env = os.environ.get("DIARIZATION_SMOKE_AUDIO")
        if not audio_env:
            pytest.skip(
                "DIARIZATION_SMOKE_AUDIO not set. "
                "Set it to a local audio file path to run this test."
            )
        audio_file = Path(audio_env)
        if not audio_file.exists():
            pytest.skip(f"Audio file not found: {audio_file}")
        return str(audio_file)

    @pytest.fixture
    def pyannote_backend(self) -> PyannoteBackend:
        """Get pyannote backend, skip if not available."""
        if not PyannoteBackend.is_available():
            error = PyannoteBackend.get_error() or "Unknown error"
            # Provide actionable skip message
            if "401" in error or "unauthorized" in error.lower():
                pytest.skip(
                    "HuggingFace auth required. Run: hf auth login"
                )
            elif "gated" in error.lower() or "access" in error.lower():
                pytest.skip(
                    "Gated model not accepted. Visit: "
                    "https://hf.co/pyannote/speaker-diarization-3.1"
                )
            elif "token" in error.lower():
                pytest.skip(
                    "HuggingFace token missing. Run: hf auth login"
                )
            else:
                pytest.skip(f"Pyannote not available: {error[:80]}")
        return PyannoteBackend()

    def test_real_diarization_returns_segments(
        self, audio_path: str, pyannote_backend: PyannoteBackend
    ) -> None:
        """Test that real diarization returns valid segments."""
        segments = pyannote_backend.diarize(audio_path, num_channels=2)

        # Should return at least 1 segment for any audio with speech
        assert len(segments) >= 1, "Expected at least 1 segment"

        for seg in segments:
            # Validate segment structure
            assert isinstance(seg, SpeakerSegment)
            assert seg.start_ms >= 0, "start_ms must be >= 0"
            assert seg.end_ms > seg.start_ms, "end_ms must be > start_ms"
            assert seg.speaker_id >= 0, "speaker_id must be >= 0"

    def test_segments_are_valid_timeline(
        self, audio_path: str, pyannote_backend: PyannoteBackend
    ) -> None:
        """Test that segments form a valid non-overlapping timeline."""
        segments = pyannote_backend.diarize(audio_path, num_channels=2)

        if len(segments) < 2:
            pytest.skip("Need at least 2 segments to test timeline validity")

        # Check sorted order
        for i in range(1, len(segments)):
            assert segments[i].start_ms >= segments[i - 1].start_ms, (
                f"Segments not sorted at index {i}"
            )

        # Check non-overlapping
        for i in range(1, len(segments)):
            assert segments[i].start_ms >= segments[i - 1].end_ms, (
                f"Overlapping segments at index {i}"
            )
