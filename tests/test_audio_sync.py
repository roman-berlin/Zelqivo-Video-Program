"""Tests for audio_sync module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from multicam_editor.logic.audio_sync import (
    CameraAlignment,
    SyncResult,
    _apply_offset,
    _cross_correlate_offset,
    align_audio_offset,
    align_cameras,
    sync_external_audio,
)

# Test sample rate
SR = 16000


def _create_test_tone(duration_s: float, freq: float = 440.0, sr: int = SR) -> np.ndarray:
    """Create a simple sine wave tone."""
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _create_chirp(duration_s: float, f0: float = 200, f1: float = 2000, sr: int = SR) -> np.ndarray:
    """Create a chirp signal (frequency sweep) - better for cross-correlation."""
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    # Linear chirp
    phase = 2 * np.pi * (f0 * t + (f1 - f0) * t**2 / (2 * duration_s))
    return (0.5 * np.sin(phase)).astype(np.float32)


class TestCrossCorrelateOffset:
    """Tests for _cross_correlate_offset function."""

    def test_no_offset(self):
        """Identical signals should have zero offset."""
        signal = _create_chirp(2.0)
        offset_ms, corr_score, window_sec = _cross_correlate_offset(signal, signal, SR)
        assert abs(offset_ms) < 10.0  # Within 10ms tolerance
        assert corr_score > 0  # Should have positive correlation
        assert window_sec > 0  # Should report sample window

    def test_positive_offset_200ms(self):
        """External audio delayed by 200ms should return ~200ms offset."""
        ref = _create_chirp(3.0)
        offset_samples = int(0.2 * SR)  # 200ms
        # ext starts later -> pad with zeros at beginning
        ext = np.concatenate([np.zeros(offset_samples, dtype=np.float32), ref[:-offset_samples]])

        offset_ms, corr_score, window_sec = _cross_correlate_offset(ref, ext, SR)
        assert abs(offset_ms - 200.0) < 20.0  # Within 20ms tolerance
        assert corr_score > 0

    def test_negative_offset_200ms(self):
        """External audio early by 200ms should return ~-200ms offset."""
        ref = _create_chirp(3.0)
        offset_samples = int(0.2 * SR)  # 200ms
        # ext starts earlier -> ext is trimmed at start, content matches later part of ref
        # This simulates ext recording starting 200ms before ref
        ext = np.concatenate([ref[offset_samples:], np.zeros(offset_samples, dtype=np.float32)])

        offset_ms, corr_score, window_sec = _cross_correlate_offset(ref, ext, SR)
        # ext content is ahead of ref by 200ms -> negative offset
        assert abs(offset_ms + 200.0) < 20.0  # Should be ~-200ms


class TestApplyOffset:
    """Tests for _apply_offset function."""

    def test_positive_offset_trims(self):
        """Positive offset should trim start of audio."""
        audio = np.ones(SR, dtype=np.float32)  # 1 second
        adjusted, status, _ = _apply_offset(audio, 100.0, SR)  # 100ms

        assert status == "trimmed"
        expected_len = SR - int(0.1 * SR)
        assert len(adjusted) == expected_len

    def test_negative_offset_pads(self):
        """Negative offset should pad start of audio."""
        audio = np.ones(SR, dtype=np.float32)  # 1 second
        adjusted, status, _ = _apply_offset(audio, -100.0, SR)  # -100ms

        assert status == "padded"
        expected_len = SR + int(0.1 * SR)
        assert len(adjusted) == expected_len
        # First samples should be zeros
        assert np.all(adjusted[:int(0.1 * SR)] == 0)

    def test_zero_offset_unchanged(self):
        """Zero offset should return unchanged audio."""
        audio = np.ones(SR, dtype=np.float32)
        adjusted, status, _ = _apply_offset(audio, 0.0, SR)

        assert status == "ok"
        assert len(adjusted) == len(audio)

    def test_offset_exceeds_length_fails(self):
        """Offset exceeding audio length should fail gracefully."""
        audio = np.ones(int(SR * 0.5), dtype=np.float32)  # 0.5s
        adjusted, status, _ = _apply_offset(audio, 1000.0, SR)  # 1s offset > 0.5s audio

        assert status == "failed"


class TestSyncExternalAudio:
    """Integration tests for sync_external_audio."""

    def test_sync_creates_output_file(self, tmp_path: Path):
        """sync_external_audio should create synced WAV file."""
        # Create test files
        ref_audio = _create_chirp(2.0)
        ext_audio = _create_chirp(2.0)

        ref_path = tmp_path / "ref.wav"
        ext_path = tmp_path / "ext.wav"
        sf.write(str(ref_path), ref_audio, SR)
        sf.write(str(ext_path), ext_audio, SR)

        result = sync_external_audio(str(ext_path), str(ref_path), str(tmp_path))

        assert result is not None
        assert result.status != "failed"
        assert Path(result.output_path).exists()

    def test_sync_with_200ms_offset(self, tmp_path: Path):
        """Sync should detect ~200ms offset correctly."""
        ref_audio = _create_chirp(3.0)
        offset_samples = int(0.2 * SR)
        ext_audio = np.concatenate([np.zeros(offset_samples, dtype=np.float32), ref_audio[:-offset_samples]])

        ref_path = tmp_path / "ref.wav"
        ext_path = tmp_path / "ext.wav"
        sf.write(str(ref_path), ref_audio, SR)
        sf.write(str(ext_path), ext_audio, SR)

        result = sync_external_audio(str(ext_path), str(ref_path), str(tmp_path))

        assert result is not None
        assert abs(result.offset_ms - 200.0) < 30.0  # Within 30ms tolerance
        assert result.status in ("ok", "trimmed", "padded")

    def test_sync_missing_file_returns_failed(self, tmp_path: Path):
        """Missing file should return failed result, not crash."""
        result = sync_external_audio(
            str(tmp_path / "nonexistent.wav"),
            str(tmp_path / "also_missing.wav"),
        )

        assert result is not None
        assert result.status == "failed"

    def test_sync_too_short_audio(self, tmp_path: Path):
        """Audio shorter than 0.5s should fail gracefully."""
        short_audio = _create_chirp(0.1)  # 100ms - too short

        ref_path = tmp_path / "ref.wav"
        ext_path = tmp_path / "ext.wav"
        sf.write(str(ref_path), short_audio, SR)
        sf.write(str(ext_path), short_audio, SR)

        result = sync_external_audio(str(ext_path), str(ref_path), str(tmp_path))

        assert result is not None
        assert result.status == "failed"
        assert "too short" in result.message.lower()


class TestAlignAudioOffset:
    """Tests for align_audio_offset convenience function."""

    def test_returns_offset_and_status(self, tmp_path: Path):
        """align_audio_offset should return offset and status."""
        ref_audio = _create_chirp(2.0)
        ext_audio = _create_chirp(2.0)

        ref_path = tmp_path / "ref.wav"
        ext_path = tmp_path / "ext.wav"
        sf.write(str(ref_path), ref_audio, SR)
        sf.write(str(ext_path), ext_audio, SR)

        offset, status = align_audio_offset(str(ext_path), str(ref_path))

        assert status == "ok"
        assert abs(offset) < 20.0  # Should be near zero for identical signals
