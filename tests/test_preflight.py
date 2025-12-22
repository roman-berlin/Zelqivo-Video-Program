# file: tests/test_preflight.py
"""Tests for preflight warning detection."""
import pytest
from unittest.mock import patch, MagicMock

from multicam_editor.logic.preflight import (
    check_preflight_warnings,
    format_warnings_for_display,
    PreflightWarning,
)
from multicam_editor.utils.ffprobe import ProbeResult, StreamInfo


class TestCheckPreflightWarnings:
    """Tests for check_preflight_warnings function."""

    def test_empty_paths(self):
        """Empty list returns no warnings."""
        result = check_preflight_warnings([])
        assert result == []

    @patch("multicam_editor.logic.preflight.probe")
    def test_rotation_warning(self, mock_probe):
        """Rotation metadata triggers warning."""
        mock_probe.return_value = ProbeResult(
            duration_ms=5000,
            rotation=90,
            vfr_risk=False,
            streams=[StreamInfo(codec_type="video", codec_name="h264"),
                     StreamInfo(codec_type="audio", codec_name="aac")],
        )
        result = check_preflight_warnings(["/test/video.mp4"])
        assert len(result) == 1
        assert result[0].warning_type == "rotation"
        assert "90°" in result[0].message

    @patch("multicam_editor.logic.preflight.probe")
    def test_vfr_warning(self, mock_probe):
        """VFR risk triggers warning."""
        mock_probe.return_value = ProbeResult(
            duration_ms=5000,
            rotation=None,
            vfr_risk=True,
            streams=[StreamInfo(codec_type="video", codec_name="h264"),
                     StreamInfo(codec_type="audio", codec_name="aac")],
        )
        result = check_preflight_warnings(["/test/video.mp4"])
        assert len(result) == 1
        assert result[0].warning_type == "vfr"
        assert "VFR" in result[0].message

    @patch("multicam_editor.logic.preflight.probe")
    def test_no_audio_warning(self, mock_probe):
        """No audio stream triggers warning."""
        mock_probe.return_value = ProbeResult(
            duration_ms=5000,
            rotation=None,
            vfr_risk=False,
            streams=[StreamInfo(codec_type="video", codec_name="h264")],
        )
        result = check_preflight_warnings(["/test/video.mp4"])
        assert len(result) == 1
        assert result[0].warning_type == "no_audio"
        assert "No audio" in result[0].message

    @patch("multicam_editor.logic.preflight.probe")
    def test_multiple_warnings_same_file(self, mock_probe):
        """Multiple issues on same file produce multiple warnings."""
        mock_probe.return_value = ProbeResult(
            duration_ms=5000,
            rotation=180,
            vfr_risk=True,
            streams=[StreamInfo(codec_type="video", codec_name="h264")],
        )
        result = check_preflight_warnings(["/test/video.mp4"])
        assert len(result) == 3  # rotation, vfr, no_audio
        types = {w.warning_type for w in result}
        assert types == {"rotation", "vfr", "no_audio"}

    @patch("multicam_editor.logic.preflight.probe")
    def test_no_warnings_clean_file(self, mock_probe):
        """Clean file returns no warnings."""
        mock_probe.return_value = ProbeResult(
            duration_ms=5000,
            rotation=None,
            vfr_risk=False,
            streams=[StreamInfo(codec_type="video", codec_name="h264"),
                     StreamInfo(codec_type="audio", codec_name="aac")],
        )
        result = check_preflight_warnings(["/test/video.mp4"])
        assert result == []

    @patch("multicam_editor.logic.preflight.probe")
    def test_probe_error_skipped(self, mock_probe):
        """Probe errors are skipped gracefully."""
        mock_probe.return_value = ProbeResult(
            duration_ms=0,
            error="File not found",
        )
        result = check_preflight_warnings(["/test/missing.mp4"])
        assert result == []

    @patch("multicam_editor.logic.preflight.probe")
    def test_rotation_zero_no_warning(self, mock_probe):
        """Rotation of 0 does not trigger warning."""
        mock_probe.return_value = ProbeResult(
            duration_ms=5000,
            rotation=0,
            vfr_risk=False,
            streams=[StreamInfo(codec_type="video", codec_name="h264"),
                     StreamInfo(codec_type="audio", codec_name="aac")],
        )
        result = check_preflight_warnings(["/test/video.mp4"])
        assert result == []


class TestFormatWarningsForDisplay:
    """Tests for format_warnings_for_display function."""

    def test_empty_warnings(self):
        """Empty warnings returns empty string."""
        result = format_warnings_for_display([])
        assert result == ""

    def test_single_rotation(self):
        """Single rotation warning formatted correctly."""
        warnings = [
            PreflightWarning(
                path="/test.mp4", filename="test.mp4",
                warning_type="rotation", message="Has rotation"
            )
        ]
        result = format_warnings_for_display(warnings)
        assert "1 rotated" in result
        assert "⚠" in result

    def test_single_vfr(self):
        """Single VFR warning formatted correctly."""
        warnings = [
            PreflightWarning(
                path="/test.mp4", filename="test.mp4",
                warning_type="vfr", message="VFR"
            )
        ]
        result = format_warnings_for_display(warnings)
        assert "1 VFR" in result

    def test_single_no_audio(self):
        """Single no-audio warning formatted correctly."""
        warnings = [
            PreflightWarning(
                path="/test.mp4", filename="test.mp4",
                warning_type="no_audio", message="No audio"
            )
        ]
        result = format_warnings_for_display(warnings)
        assert "1 no-audio" in result

    def test_multiple_types(self):
        """Multiple warning types formatted correctly."""
        warnings = [
            PreflightWarning(
                path="/a.mp4", filename="a.mp4",
                warning_type="rotation", message=""
            ),
            PreflightWarning(
                path="/b.mp4", filename="b.mp4",
                warning_type="rotation", message=""
            ),
            PreflightWarning(
                path="/c.mp4", filename="c.mp4",
                warning_type="vfr", message=""
            ),
        ]
        result = format_warnings_for_display(warnings)
        assert "2 rotated" in result
        assert "1 VFR" in result
        assert "Preflight" in result
