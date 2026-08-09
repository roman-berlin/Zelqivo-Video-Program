# file: tests/test_preflight_manager.py
"""Comprehensive tests for PreflightManager validation system."""
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from multicam_editor.logic.preflight import (
    PreflightManager,
    PreflightError,
    PreflightErrorType,
    PreflightResult,
)
from multicam_editor.utils.ffprobe import ProbeResult, StreamInfo


class TestPreflightManager:
    """Tests for PreflightManager comprehensive validation."""

    @patch("multicam_editor.logic.preflight.probe")
    @patch("multicam_editor.logic.preflight.shutil.disk_usage")
    @patch("multicam_editor.logic.preflight.os.path.getsize")
    @patch("multicam_editor.logic.preflight.os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=MagicMock)
    @patch("multicam_editor.logic.preflight.os.remove")
    def test_all_checks_pass(self, mock_remove, mock_file, mock_isfile, mock_getsize, mock_disk_usage, mock_probe):
        """Clean files with sufficient resources should pass all checks."""
        # Mock probe to return valid video+audio
        mock_probe.return_value = ProbeResult(
            duration_ms=10000,
            streams=[
                StreamInfo(codec_type="video", codec_name="h264"),
                StreamInfo(codec_type="audio", codec_name="aac"),
            ],
            vfr_risk=False,
        )
        
        # Mock disk space (100 GB free)
        mock_disk_usage.return_value = MagicMock(free=100 * 1024**3)
        
        # Mock file size (1 GB input)
        mock_getsize.return_value = 1 * 1024**3
        
        manager = PreflightManager()
        result = manager.run_full_check(["/test/video1.mp4", "/test/video2.mp4"])
        
        assert result.ok is True
        assert len(result.critical_errors) == 0
        assert len(result.warnings) == 0

    @patch("multicam_editor.logic.preflight.probe")
    @patch("multicam_editor.logic.preflight.os.path.isfile", return_value=True)
    def test_corrupt_header_detection(self, mock_isfile, mock_probe):
        """Corrupt file header (probe failure) should block processing."""
        # Simulate ffprobe failure (corrupt header)
        mock_probe.return_value = ProbeResult(
            duration_ms=0,
            error="Invalid data found when processing input"
        )
        
        manager = PreflightManager()
        result = manager.run_full_check(["/test/fake_video.mp4"])
        
        assert result.ok is False
        assert len(result.critical_errors) == 1
        assert result.critical_errors[0].error_type == "corrupt_header"
        assert "Corrupt or unreadable" in result.critical_errors[0].message

    @patch("multicam_editor.logic.preflight.probe")
    @patch("multicam_editor.logic.preflight.os.path.isfile", return_value=True)
    def test_no_audio_stream_blocks(self, mock_isfile, mock_probe):
        """Video without audio stream should be blocked (required for sync)."""
        # Mock probe to return video only (no audio)
        mock_probe.return_value = ProbeResult(
            duration_ms=10000,
            streams=[
                StreamInfo(codec_type="video", codec_name="h264"),
            ],
            vfr_risk=False,
        )
        
        manager = PreflightManager()
        result = manager.run_full_check(["/test/silent_video.mp4"])
        
        assert result.ok is False
        assert len(result.critical_errors) == 1
        assert result.critical_errors[0].error_type == "no_audio"
        assert "required for sync" in result.critical_errors[0].message

    @patch("multicam_editor.logic.preflight.probe")
    @patch("multicam_editor.logic.preflight.os.path.isfile", return_value=True)
    def test_no_video_stream_blocks(self, mock_isfile, mock_probe):
        """Audio-only file should be blocked (no video stream)."""
        # Mock probe to return audio only (no video)
        mock_probe.return_value = ProbeResult(
            duration_ms=10000,
            streams=[
                StreamInfo(codec_type="audio", codec_name="aac"),
            ],
            vfr_risk=False,
        )
        
        manager = PreflightManager()
        result = manager.run_full_check(["/test/audio_only.m4a"])
        
        assert result.ok is False
        assert len(result.critical_errors) == 1
        assert result.critical_errors[0].error_type == "no_video"
        assert "No video stream" in result.critical_errors[0].message

    @patch("multicam_editor.logic.preflight.probe")
    @patch("multicam_editor.logic.preflight.shutil.disk_usage")
    @patch("multicam_editor.logic.preflight.os.path.getsize")
    @patch("multicam_editor.logic.preflight.os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=MagicMock)
    @patch("multicam_editor.logic.preflight.os.remove")
    def test_insufficient_disk_space_blocks(self, mock_remove, mock_file, mock_isfile, mock_getsize, mock_disk_usage, mock_probe):
        """Insufficient disk space (< 2.5x input) should block processing."""
        # Mock valid probe
        mock_probe.return_value = ProbeResult(
            duration_ms=10000,
            streams=[
                StreamInfo(codec_type="video", codec_name="h264"),
                StreamInfo(codec_type="audio", codec_name="aac"),
            ],
            vfr_risk=False,
        )
        
        # Mock file size: 10 GB input
        mock_getsize.return_value = 10 * 1024**3
        
        # Mock disk space: Only 15 GB free (< 2.5x = 25 GB required)
        mock_disk_usage.return_value = MagicMock(free=15 * 1024**3)
        
        manager = PreflightManager()
        result = manager.run_full_check(["/test/large_video.mp4"], "/output")
        
        assert result.ok is False
        assert len(result.critical_errors) == 1
        assert result.critical_errors[0].error_type == "disk_space_critical"
        assert "Insufficient disk space" in result.critical_errors[0].message
        assert "25.0 GB required" in result.critical_errors[0].message

    @patch("multicam_editor.logic.preflight.os.makedirs")
    @patch("multicam_editor.logic.preflight.probe")
    @patch("multicam_editor.logic.preflight.shutil.disk_usage")
    @patch("multicam_editor.logic.preflight.os.path.getsize")
    @patch("multicam_editor.logic.preflight.os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=MagicMock)
    @patch("multicam_editor.logic.preflight.os.remove")
    def test_low_disk_space_warning(self, mock_remove, mock_file, mock_isfile, mock_getsize, mock_disk_usage, mock_probe, mock_makedirs):
        """Low disk space (< 3x but >= 2.5x) should generate warning."""
        # Mock valid probe
        mock_probe.return_value = ProbeResult(
            duration_ms=10000,
            streams=[
                StreamInfo(codec_type="video", codec_name="h264"),
                StreamInfo(codec_type="audio", codec_name="aac"),
            ],
            vfr_risk=False,
        )
        
        # Mock file size: 10 GB input
        mock_getsize.return_value = 10 * 1024**3
        
        # Mock disk space: 27 GB free (>= 2.5x but < 3x)
        mock_disk_usage.return_value = MagicMock(free=27 * 1024**3)
        
        manager = PreflightManager()
        result = manager.run_full_check(["/test/video.mp4"], "/output")
        
        # Should pass critical checks but have warning
        assert result.ok is True
        assert len(result.critical_errors) == 0
        assert len(result.warnings) == 1
        assert result.warnings[0].error_type == "disk_space_low"
        assert "Low disk space" in result.warnings[0].message

    @patch("multicam_editor.logic.preflight.probe")
    @patch("multicam_editor.logic.preflight.os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=MagicMock)
    @patch("multicam_editor.logic.preflight.os.remove")
    def test_vfr_generates_warning(self, mock_remove, mock_file, mock_isfile, mock_probe):
        """VFR (variable frame rate) should generate warning, not block."""
        # Mock probe with VFR risk
        mock_probe.return_value = ProbeResult(
            duration_ms=10000,
            streams=[
                StreamInfo(codec_type="video", codec_name="h264"),
                StreamInfo(codec_type="audio", codec_name="aac"),
            ],
            vfr_risk=True,  # VFR detected
        )
        
        manager = PreflightManager()
        result = manager.run_full_check(["/test/smartphone_video.mp4"])
        
        # Should not block, but generate warning
        assert result.ok is True
        assert len(result.critical_errors) == 0
        assert len(result.warnings) == 1
        assert result.warnings[0].error_type == "vfr_risk"
        assert result.warnings[0].severity == PreflightErrorType.WARNING
        assert "Variable frame rate" in result.warnings[0].message

    def test_file_not_found_blocks(self):
        """Non-existent file should block processing."""
        manager = PreflightManager()
        result = manager.run_full_check(["/nonexistent/file.mp4"])
        
        assert result.ok is False
        assert len(result.critical_errors) == 1
        assert result.critical_errors[0].error_type == "file_not_found"
        assert "File not found" in result.critical_errors[0].message

    @patch("multicam_editor.logic.preflight.probe")
    @patch("multicam_editor.logic.preflight.os.path.isfile", return_value=True)
    @patch("builtins.open", side_effect=PermissionError())
    def test_write_permission_denied_blocks(self, mock_open_perm, mock_isfile, mock_probe):
        """No write permission should block processing."""
        # Mock valid probe
        mock_probe.return_value = ProbeResult(
            duration_ms=10000,
            streams=[
                StreamInfo(codec_type="video", codec_name="h264"),
                StreamInfo(codec_type="audio", codec_name="aac"),
            ],
            vfr_risk=False,
        )
        
        manager = PreflightManager()
        result = manager.run_full_check(["/test/video.mp4"], "/readonly/output")
        
        assert result.ok is False
        # Should have write permission error
        has_write_error = any(
            e.error_type == "write_permission" 
            for e in result.critical_errors
        )
        assert has_write_error

    @patch("multicam_editor.logic.preflight.probe")
    @patch("multicam_editor.logic.preflight.shutil.disk_usage")
    @patch("multicam_editor.logic.preflight.os.path.getsize")
    @patch("multicam_editor.logic.preflight.os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=MagicMock)
    @patch("multicam_editor.logic.preflight.os.remove")
    def test_multiple_errors_reported(self, mock_remove, mock_file, mock_isfile, mock_getsize, mock_disk_usage, mock_probe):
        """Multiple files with different errors should all be reported."""
        # File 1: corrupt header
        # File 2: no audio
        def probe_side_effect(path):
            if "corrupt" in path:
                return ProbeResult(duration_ms=0, error="Invalid data")
            elif "silent" in path:
                return ProbeResult(
                    duration_ms=10000,
                    streams=[StreamInfo(codec_type="video", codec_name="h264")],
                    vfr_risk=False,
                )
            else:
                return ProbeResult(
                    duration_ms=10000,
                    streams=[
                        StreamInfo(codec_type="video", codec_name="h264"),
                        StreamInfo(codec_type="audio", codec_name="aac"),
                    ],
                    vfr_risk=False,
                )
        
        mock_probe.side_effect = probe_side_effect
        mock_getsize.return_value = 1 * 1024**3
        mock_disk_usage.return_value = MagicMock(free=100 * 1024**3)
        
        manager = PreflightManager()
        result = manager.run_full_check([
            "/test/corrupt.mp4",
            "/test/silent.mp4",
        ])
        
        assert result.ok is False
        assert len(result.critical_errors) == 2
        
        error_types = {e.error_type for e in result.critical_errors}
        assert "corrupt_header" in error_types
        assert "no_audio" in error_types


class TestPreflightResultDataclass:
    """Tests for PreflightResult dataclass behavior."""

    def test_ok_auto_set_on_critical_errors(self):
        """PreflightResult.ok should auto-set to False if critical errors present."""
        result = PreflightResult(
            ok=True,  # Will be overridden
            critical_errors=[
                PreflightError(
                    path="/test.mp4",
                    filename="test.mp4",
                    error_type="no_audio",
                    severity=PreflightErrorType.CRITICAL,
                    message="Test error"
                )
            ]
        )
        
        # __post_init__ should set ok=False
        assert result.ok is False

    def test_ok_remains_true_with_warnings_only(self):
        """PreflightResult.ok should stay True if only warnings (no critical errors)."""
        result = PreflightResult(
            ok=True,
            warnings=[
                PreflightError(
                    path="/test.mp4",
                    filename="test.mp4",
                    error_type="vfr_risk",
                    severity=PreflightErrorType.WARNING,
                    message="VFR warning"
                )
            ]
        )
        
        assert result.ok is True
