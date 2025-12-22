"""Tests for debug_export module."""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_export_debug_package_creates_zip_with_env_info():
    """Test that export creates zip with environment_info.json even without run folder."""
    from multicam_editor.logic.debug_export import export_debug_package

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "debug.zip")

        # Mock no run folder
        with patch("multicam_editor.logic.debug_export.get_last_run_folder", return_value=None):
            success, message, warnings = export_debug_package(out_path)

        assert success is True
        assert os.path.exists(out_path)
        assert "No QA run folder" in str(warnings)

        # Verify zip contents
        with zipfile.ZipFile(out_path, "r") as zf:
            names = zf.namelist()
            assert "environment_info.json" in names

            # Verify environment_info content
            with zf.open("environment_info.json") as f:
                env = json.load(f)
                assert "app_version" in env
                assert "python_version" in env
                assert "platform" in env
                assert "ffmpeg_path" in env
                assert "ffprobe_path" in env


def test_export_debug_package_includes_qa_files():
    """Test that export includes QA artifacts when run folder exists."""
    from multicam_editor.logic.debug_export import export_debug_package

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "debug.zip")

        # Create fake run folder with QA files
        run_folder = Path(tmpdir) / "run_folder"
        run_folder.mkdir()

        diarization = {"speakers": [], "segments": []}
        cut_plan = {"cuts": []}
        summary = {"counts": {}, "thresholds": {}}

        (run_folder / "diarization.json").write_text(json.dumps(diarization))
        (run_folder / "cut_plan.json").write_text(json.dumps(cut_plan))
        (run_folder / "processing_summary.json").write_text(json.dumps(summary))

        with patch("multicam_editor.logic.debug_export.get_last_run_folder", return_value=run_folder):
            success, message, warnings = export_debug_package(out_path)

        assert success is True
        assert "No log file" in str(warnings)  # logs not available in test

        with zipfile.ZipFile(out_path, "r") as zf:
            names = zf.namelist()
            assert "environment_info.json" in names
            assert "diarization.json" in names
            assert "cut_plan.json" in names
            assert "processing_summary.json" in names


def test_export_debug_package_handles_missing_qa_files():
    """Test that export warns but continues when QA files are missing."""
    from multicam_editor.logic.debug_export import export_debug_package

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "debug.zip")

        # Create run folder without QA files
        run_folder = Path(tmpdir) / "run_folder"
        run_folder.mkdir()

        with patch("multicam_editor.logic.debug_export.get_last_run_folder", return_value=run_folder):
            success, message, warnings = export_debug_package(out_path)

        assert success is True
        # Should have warnings about missing files
        assert any("diarization.json" in w for w in warnings)
        assert any("cut_plan.json" in w for w in warnings)
        assert any("processing_summary.json" in w for w in warnings)

        # Zip should still contain environment_info
        with zipfile.ZipFile(out_path, "r") as zf:
            names = zf.namelist()
            assert "environment_info.json" in names


def test_collect_environment_info():
    """Test environment info collection."""
    from multicam_editor.logic.debug_export import _collect_environment_info

    env = _collect_environment_info()

    assert "app_version" in env
    assert env["app_version"] == "0.1.0"
    assert "python_version" in env
    assert "platform" in env
    assert "machine" in env
    # ffmpeg_path and ffprobe_path may be None if not installed
    assert "ffmpeg_path" in env
    assert "ffprobe_path" in env


def test_export_debug_package_bad_path():
    """Test export fails gracefully with invalid output path."""
    from multicam_editor.logic.debug_export import export_debug_package

    # Try to write to impossible path
    bad_path = "/nonexistent/directory/that/does/not/exist/debug.zip"

    with patch("multicam_editor.logic.debug_export.get_last_run_folder", return_value=None):
        success, message, warnings = export_debug_package(bad_path)

    assert success is False
    assert "failed" in message.lower() or "error" in message.lower()
