import pytest
from unittest.mock import patch, MagicMock
from multicam_editor.utils.backends import (
    check_backends, 
    run_health_check, 
    get_available_diarization_modes,
    BackendStatus
)

def test_check_backends_basic():
    """Test that core and energy_vad are always available."""
    # Mocking audio sync and pyannote to avoid side effects or real detection
    with patch("multicam_editor.utils.backends.is_audio_sync_available", create=True) as mock_sync:
        mock_sync.return_value = (True, None)
        
        # We need to mock the imports inside check_backends if possible, 
        # or just let it run if dependencies are missing (it handles ImportError).
        # Since we can't easily patch local imports without `sys.modules` trickery or `patch.dict`,
        # we will rely on the function's own try/except blocks for optional deps.
        
        results = check_backends()
        
        assert "core" in results
        assert results["core"].available is True
        
        assert "energy_vad" in results
        assert results["energy_vad"].available is True
        
        # Audio Sync & Pyannote depend on environment
        assert "audio_sync" in results
        assert "pyannote" in results

def test_available_diarization_modes():
    """Test modes list based on backend availability."""
    # Case 1: Pyannote unavailable
    with patch("multicam_editor.utils.backends.check_backends") as mock_check:
        mock_check.return_value = {
            "pyannote": BackendStatus("pyannote", False)
        }
        modes = get_available_diarization_modes()
        assert "OFF" in modes
        assert "ENERGY" in modes
        assert "REAL" not in modes

    # Case 2: Pyannote available
    with patch("multicam_editor.utils.backends.check_backends") as mock_check:
        mock_check.return_value = {
            "pyannote": BackendStatus("pyannote", True)
        }
        modes = get_available_diarization_modes()
        assert "REAL" in modes

def test_run_health_check():
    """Test health check aggregation."""
    with patch("multicam_editor.utils.ffmpeg.is_ffmpeg_available", return_value=True), \
         patch("multicam_editor.utils.ffmpeg.get_ffmpeg_path", return_value="/usr/bin/ffmpeg"), \
         patch("multicam_editor.utils.ffprobe.is_ffprobe_available", return_value=True), \
         patch("multicam_editor.utils.ffprobe._find_ffprobe", return_value="/usr/bin/ffprobe"), \
         patch("multicam_editor.utils.backends.check_backends") as mock_backends:
         
        mock_backends.return_value = {
            "core": BackendStatus("core", True),
            "audio_sync": BackendStatus("sync", True),
            "pyannote": BackendStatus("ai", True)
        }
        
        result = run_health_check()
        
        assert result.ready is True
        assert result.ffmpeg_available is True
        assert result.ffprobe_available is True
        assert not result.warnings

def test_run_health_check_missing_deps():
    """Test health check when key deps are missing."""
    with patch("multicam_editor.utils.ffmpeg.is_ffmpeg_available", return_value=False), \
         patch("multicam_editor.utils.ffprobe.is_ffprobe_available", return_value=False), \
         patch("multicam_editor.utils.backends.check_backends") as mock_backends:
         
        mock_backends.return_value = {
            "core": BackendStatus("core", True),
            "audio_sync": BackendStatus("sync", False),
            "pyannote": BackendStatus("ai", False)
        }
        
        result = run_health_check()
        
        assert result.ready is False
        assert result.ffmpeg_available is False
        assert len(result.warnings) > 0
