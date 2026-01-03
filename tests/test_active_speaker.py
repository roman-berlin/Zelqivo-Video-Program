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
        assert DiarizationMode.LIPS.value == "lips"
        assert DiarizationMode.HYBRID.value == "hybrid"

    def test_from_string(self) -> None:
        assert DiarizationMode("off") == DiarizationMode.OFF
        assert DiarizationMode("stub") == DiarizationMode.STUB
        assert DiarizationMode("energy") == DiarizationMode.ENERGY
        assert DiarizationMode("real") == DiarizationMode.REAL
        assert DiarizationMode("lips") == DiarizationMode.LIPS
        assert DiarizationMode("hybrid") == DiarizationMode.HYBRID


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

    def test_robustness_parameters_initialization(self) -> None:
        """Test all robustness parameters can be customized."""
        backend = RealEnergyVADBackend(
            noise_percentile=15,
            gate_factor=3.0,
            hysteresis_ratio=2.0,
            consecutive_wins=5,
            hold_time_ms=3000,
        )
        assert backend.noise_percentile == 15
        assert backend.gate_factor == 3.0
        assert backend.hysteresis_ratio == 2.0
        assert backend.consecutive_wins == 5
        assert backend.hold_time_ms == 3000

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

    # --- Noise floor estimation tests ---

    def test_estimate_noise_floors_empty(self) -> None:
        """Test noise floor estimation with empty energy matrix."""
        backend = RealEnergyVADBackend()
        noise_floors = backend._estimate_noise_floors([[]])
        assert len(noise_floors) == 1
        assert noise_floors[0] == backend.silence_threshold

    def test_estimate_noise_floors_constant_energy(self) -> None:
        """Test noise floor with constant energy (all same value)."""
        backend = RealEnergyVADBackend(noise_percentile=20, silence_threshold=0.01)
        energy = [[0.1] * 100]  # 100 windows at 0.1 RMS
        noise_floors = backend._estimate_noise_floors(energy)
        assert abs(noise_floors[0] - 0.1) < 0.001

    def test_estimate_noise_floors_mixed_energy(self) -> None:
        """Test noise floor picks lower percentile ignoring speech peaks."""
        backend = RealEnergyVADBackend(noise_percentile=20, silence_threshold=0.01)
        # 80 windows at 0.05 (ambient), 20 windows at 0.5 (speech)
        energy = [[0.05] * 80 + [0.5] * 20]
        noise_floors = backend._estimate_noise_floors(energy)
        # p20 should be in the low region (0.05)
        assert noise_floors[0] < 0.1

    def test_estimate_noise_floors_minimum_threshold(self) -> None:
        """Test noise floor never goes below silence_threshold."""
        backend = RealEnergyVADBackend(silence_threshold=0.02)
        energy = [[0.001] * 100]  # Very quiet
        noise_floors = backend._estimate_noise_floors(energy)
        assert noise_floors[0] >= 0.02

    # --- Speech gating tests ---

    def test_apply_speech_gating_filters_low_energy(self) -> None:
        """Test that gating zeros out energy below threshold."""
        backend = RealEnergyVADBackend(gate_factor=2.0)
        energy = [[0.01, 0.02, 0.05, 0.1, 0.2]]
        noise_floors = [0.03]  # threshold = 0.03 * 2.0 = 0.06
        gated = backend._apply_speech_gating(energy, noise_floors)
        # Values below 0.06 should be zeroed
        assert gated[0][0] == 0.0  # 0.01 < 0.06
        assert gated[0][1] == 0.0  # 0.02 < 0.06
        assert gated[0][2] == 0.0  # 0.05 < 0.06
        assert gated[0][3] == 0.1  # 0.1 >= 0.06
        assert gated[0][4] == 0.2  # 0.2 >= 0.06

    # --- Robust winner determination tests ---

    def test_determine_winners_all_silence(self) -> None:
        """Test that silence keeps current camera (no guessing)."""
        backend = RealEnergyVADBackend(consecutive_wins=3, hold_time_ms=200)
        # All zeros - no speech detected
        gated = [[0.0] * 20, [0.0] * 20]
        winners = backend._determine_winners_robust(gated, 2, 20)
        # Should stay on cam0 throughout (default)
        assert all(w == 0 for w in winners)

    def test_determine_winners_hysteresis_prevents_switch(self) -> None:
        """Test hysteresis prevents switching on similar energy levels."""
        backend = RealEnergyVADBackend(
            hysteresis_ratio=1.6,
            consecutive_wins=1,
            hold_time_ms=0,
        )
        # cam0 at 0.5, cam1 at 0.6 - ratio 1.2 < 1.6, should not switch
        gated = [[0.5] * 10, [0.6] * 10]
        winners = backend._determine_winners_robust(gated, 2, 10)
        # Should stay on cam0 (hysteresis blocks switch)
        assert all(w == 0 for w in winners)

    def test_determine_winners_hysteresis_allows_switch(self) -> None:
        """Test hysteresis allows switching when clearly louder."""
        backend = RealEnergyVADBackend(
            hysteresis_ratio=1.6,
            consecutive_wins=3,
            hold_time_ms=0,
        )
        # cam0 at 0.3, cam1 at 0.6 - ratio 2.0 > 1.6, should switch
        gated = [[0.3] * 20, [0.6] * 20]
        winners = backend._determine_winners_robust(gated, 2, 20)
        # After consecutive_wins (3), should switch to cam1
        # Window 0,1: building count (count=1,2), window 2: count=3, switch happens
        assert winners[0] == 0
        assert winners[1] == 0
        assert winners[2] == 1  # Switch happens when consecutive_wins reached
        assert all(w == 1 for w in winners[2:])

    def test_determine_winners_consecutive_requirement(self) -> None:
        """Test that short spikes don't trigger switch (consecutive wins)."""
        backend = RealEnergyVADBackend(
            hysteresis_ratio=1.5,
            consecutive_wins=3,
            hold_time_ms=0,
        )
        # cam0 mostly speaking, cam1 has single spike
        gated_cam0 = [0.3] * 20
        gated_cam1 = [0.0] * 8 + [0.8, 0.8] + [0.0] * 10  # 2-window spike
        gated = [gated_cam0, gated_cam1]
        winners = backend._determine_winners_robust(gated, 2, 20)
        # Spike only 2 windows, needs 3 consecutive - should stay on cam0
        assert all(w == 0 for w in winners)

    def test_determine_winners_hold_time(self) -> None:
        """Test hold time prevents rapid re-switching."""
        backend = RealEnergyVADBackend(
            hysteresis_ratio=1.5,
            consecutive_wins=2,
            hold_time_ms=1000,  # 5 windows at 200ms
            window_ms=200,
        )
        # Pattern: cam1 loud for 5 windows, then cam0 loud
        gated_cam0 = [0.1] * 5 + [0.8] * 15
        gated_cam1 = [0.8] * 5 + [0.1] * 15
        gated = [gated_cam0, gated_cam1]
        winners = backend._determine_winners_robust(gated, 2, 20)
        # Initial switch to cam1 at window 1 (consecutive_wins=2, so index 1)
        switch_to_cam1_idx = next(i for i, w in enumerate(winners) if w == 1)
        assert switch_to_cam1_idx == 1  # First switch at index 1
        # Hold prevents immediate switch back (hold = 5 windows)
        assert winners[5] == 1  # Still held on cam1

    def test_determine_winners_current_silent_any_speech_wins(self) -> None:
        """Test that any speech wins when current camera is silent."""
        backend = RealEnergyVADBackend(
            hysteresis_ratio=2.0,
            consecutive_wins=3,
            hold_time_ms=0,
        )
        # cam0 silent, cam1 speaking (even quietly)
        gated = [[0.0] * 20, [0.2] * 20]
        winners = backend._determine_winners_robust(gated, 2, 20)
        # After consecutive_wins, should switch to cam1
        assert winners[3] == 1
        assert all(w == 1 for w in winners[3:])

    def test_determine_winners_no_windows(self) -> None:
        """Test empty input returns empty output."""
        backend = RealEnergyVADBackend()
        winners = backend._determine_winners_robust([[]], 1, 0)
        assert winners == []


class TestRealEnergyVADBackendEdgeCases:
    """
    Edge case tests for robust camera switching.

    Tests scenarios that previously caused issues:
    - Pure silence
    - Constant background noise
    - Short noise spikes (scratching, coughing)
    - Overlapping speech
    - Cameras with different gain levels
    """

    def test_pure_silence_stays_on_default_camera(self) -> None:
        """Pure silence should stay on cam0 (never guess)."""
        backend = RealEnergyVADBackend()
        # Simulate 10 seconds of silence (50 windows at 200ms)
        gated = [[0.0] * 50, [0.0] * 50]
        winners = backend._determine_winners_robust(gated, 2, 50)
        assert all(w == 0 for w in winners)

    def test_constant_low_noise_stays_on_default(self) -> None:
        """Constant low-level noise (gated out) should stay on default."""
        backend = RealEnergyVADBackend(gate_factor=2.0)
        # Both cameras have same low noise - gating should zero both
        energy = [[0.02] * 50, [0.02] * 50]
        noise_floors = [0.02, 0.02]  # threshold = 0.04
        gated = backend._apply_speech_gating(energy, noise_floors)
        # All gated to zero
        assert all(e == 0.0 for e in gated[0])
        assert all(e == 0.0 for e in gated[1])
        winners = backend._determine_winners_robust(gated, 2, 50)
        assert all(w == 0 for w in winners)

    def test_short_spike_ignored(self) -> None:
        """Single-window spike (scratch, bump) should not cause switch."""
        backend = RealEnergyVADBackend(
            consecutive_wins=3,
            hysteresis_ratio=1.5,
            hold_time_ms=0,
        )
        # cam0 speaking steadily, cam1 has brief spike
        gated_cam0 = [0.3] * 50
        gated_cam1 = [0.0] * 20 + [0.9] + [0.0] * 29  # Single loud spike
        gated = [gated_cam0, gated_cam1]
        winners = backend._determine_winners_robust(gated, 2, 50)
        # Should never switch to cam1
        assert all(w == 0 for w in winners)

    def test_two_window_spike_ignored(self) -> None:
        """Two consecutive windows of noise should not switch (needs 3)."""
        backend = RealEnergyVADBackend(
            consecutive_wins=3,
            hysteresis_ratio=1.5,
            hold_time_ms=0,
        )
        gated_cam0 = [0.3] * 50
        gated_cam1 = [0.0] * 20 + [0.9, 0.9] + [0.0] * 28  # 2-window spike
        gated = [gated_cam0, gated_cam1]
        winners = backend._determine_winners_robust(gated, 2, 50)
        assert all(w == 0 for w in winners)

    def test_sustained_speech_triggers_switch(self) -> None:
        """Sustained speech (3+ windows) should trigger switch."""
        backend = RealEnergyVADBackend(
            consecutive_wins=3,
            hysteresis_ratio=1.5,
            hold_time_ms=0,
        )
        gated_cam0 = [0.3] * 50
        gated_cam1 = [0.0] * 20 + [0.8] * 10 + [0.0] * 20  # 10 windows of speech
        gated = [gated_cam0, gated_cam1]
        winners = backend._determine_winners_robust(gated, 2, 50)
        # Should switch to cam1 at window 22 (20 + consecutive_wins-1 = 22)
        # Window 20: count=1, 21: count=2, 22: count=3 -> switch
        assert winners[21] == 0
        assert winners[22] == 1

    def test_overlapping_speech_stays_on_current(self) -> None:
        """When both cameras have similar energy, stay on current."""
        backend = RealEnergyVADBackend(
            hysteresis_ratio=1.6,
            consecutive_wins=3,
            hold_time_ms=0,
        )
        # Both cameras speaking at similar levels
        gated = [[0.4] * 50, [0.5] * 50]  # ratio 1.25 < 1.6
        winners = backend._determine_winners_robust(gated, 2, 50)
        # Should stay on cam0 due to hysteresis
        assert all(w == 0 for w in winners)

    def test_different_gain_adaptive_noise_floor(self) -> None:
        """Test that adaptive noise floor handles different camera gains."""
        backend = RealEnergyVADBackend(
            noise_percentile=20,
            gate_factor=2.0,
        )
        # cam0: low gain (quiet ambient, quiet speech)
        # cam1: high gain (loud ambient, loud speech)
        # Both have 20% speech, 80% ambient noise
        cam0_energy = [0.02] * 80 + [0.15] * 20  # low gain
        cam1_energy = [0.1] * 80 + [0.6] * 20    # high gain (5x)
        energy = [cam0_energy, cam1_energy]

        noise_floors = backend._estimate_noise_floors(energy)
        # Noise floors should reflect each camera's ambient level
        assert noise_floors[0] < 0.05  # Low gain cam
        assert noise_floors[1] < 0.2   # High gain cam

        # After gating, both should have similar speech/noise separation
        gated = backend._apply_speech_gating(energy, noise_floors)
        # Speech windows should pass, noise should be filtered
        cam0_speech_count = sum(1 for e in gated[0] if e > 0)
        cam1_speech_count = sum(1 for e in gated[1] if e > 0)
        # Both should have roughly same number of speech windows (20)
        assert 15 <= cam0_speech_count <= 25
        assert 15 <= cam1_speech_count <= 25

    def test_gradual_transition_needs_sustained_lead(self) -> None:
        """Gradual energy changes should not cause rapid switching."""
        backend = RealEnergyVADBackend(
            hysteresis_ratio=1.6,
            consecutive_wins=3,
            hold_time_ms=2000,
            window_ms=200,
        )
        # cam0 fading out, cam1 fading in
        gated_cam0 = [0.5 - i * 0.01 for i in range(50)]  # 0.5 -> 0.0
        gated_cam1 = [0.0 + i * 0.01 for i in range(50)]  # 0.0 -> 0.5
        gated = [gated_cam0, gated_cam1]
        winners = backend._determine_winners_robust(gated, 2, 50)

        # Count switches - should be minimal due to hold time
        switches = sum(1 for i in range(1, len(winners)) if winners[i] != winners[i-1])
        assert switches <= 2  # At most 1-2 switches for this gradual transition

    def test_three_cameras_robust_switching(self) -> None:
        """Test robust switching with 3 cameras."""
        backend = RealEnergyVADBackend(
            hysteresis_ratio=1.6,
            consecutive_wins=3,
            hold_time_ms=1000,
            window_ms=200,
        )
        # cam0 speaks first, then cam2 (cam1 silent throughout)
        gated_cam0 = [0.5] * 20 + [0.1] * 30
        gated_cam1 = [0.0] * 50
        gated_cam2 = [0.1] * 20 + [0.6] * 30
        gated = [gated_cam0, gated_cam1, gated_cam2]
        winners = backend._determine_winners_robust(gated, 3, 50)

        # Should start on cam0, eventually switch to cam2
        assert winners[0] == 0
        # cam1 should never win (always silent)
        assert 1 not in winners
        # Should switch to cam2 eventually
        assert 2 in winners


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


class TestLipMovementBackend:
    """Tests for LipMovementBackend (LIPS mode - visual detection)."""

    def test_initialization(self) -> None:
        """Test backend initializes with default parameters."""
        from multicam_editor.logic.active_speaker import LipMovementBackend
        
        backend = LipMovementBackend()
        assert backend.sample_interval_ms == 100
        assert backend.min_segment_ms == 500
        assert backend.movement_threshold == 0.02

    def test_custom_parameters(self) -> None:
        """Test backend accepts custom parameters."""
        from multicam_editor.logic.active_speaker import LipMovementBackend
        
        backend = LipMovementBackend(
            sample_interval_ms=200,
            min_segment_ms=1000,
            movement_threshold=0.05,
        )
        assert backend.sample_interval_ms == 200
        assert backend.min_segment_ms == 1000
        assert backend.movement_threshold == 0.05

    def test_apply_min_duration_empty(self) -> None:
        """Test min duration with empty segments."""
        from multicam_editor.logic.active_speaker import LipMovementBackend
        
        backend = LipMovementBackend(min_segment_ms=500)
        result = backend._apply_min_duration([])
        assert result == []

    def test_apply_min_duration_single_segment(self) -> None:
        """Test min duration with single segment returns unchanged."""
        from multicam_editor.logic.active_speaker import LipMovementBackend
        
        backend = LipMovementBackend(min_segment_ms=500)
        segments = [SpeakerSegment(0, 100, 0)]  # Short segment
        result = backend._apply_min_duration(segments)
        assert len(result) == 1
        assert result[0] == segments[0]

    def test_apply_min_duration_merges_short_segments(self) -> None:
        """Test that short segments are merged with previous."""
        from multicam_editor.logic.active_speaker import LipMovementBackend
        
        backend = LipMovementBackend(min_segment_ms=500)
        segments = [
            SpeakerSegment(0, 1000, 0),    # Long segment (cam0)
            SpeakerSegment(1000, 1200, 1), # Short segment - should merge
        ]
        result = backend._apply_min_duration(segments)
        assert len(result) == 1
        assert result[0].start_ms == 0
        assert result[0].end_ms == 1200  # Extended to include short segment
        assert result[0].speaker_id == 0  # Kept previous camera

    def test_apply_min_duration_keeps_long_segments(self) -> None:
        """Test that long segments are kept separate."""
        from multicam_editor.logic.active_speaker import LipMovementBackend
        
        backend = LipMovementBackend(min_segment_ms=500)
        segments = [
            SpeakerSegment(0, 1000, 0),    # Long segment
            SpeakerSegment(1000, 2000, 1), # Long segment - should keep
        ]
        result = backend._apply_min_duration(segments)
        assert len(result) == 2
        assert result[0].speaker_id == 0
        assert result[1].speaker_id == 1

    def test_detector_initialization(self) -> None:
        """Test that detector initializes OpenCV cascades."""
        from multicam_editor.logic.active_speaker import LipMovementBackend
        
        backend = LipMovementBackend()
        backend._ensure_detector()
        assert backend._initialized is True

    def test_detect_speakers_empty_videos(self) -> None:
        """Test with empty video list returns empty."""
        from multicam_editor.logic.active_speaker import LipMovementBackend
        
        backend = LipMovementBackend()
        result = backend.detect_speakers([], 5000)
        assert result == []

