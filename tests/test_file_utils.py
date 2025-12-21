"""Tests for file_utils module - extension detection and path utilities."""

import pytest
from multicam_editor.utils import file_utils


class TestVideoExtensions:
    """Test video file extension detection."""

    @pytest.mark.parametrize("ext", [".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".flv", ".wmv"])
    def test_is_video_valid_extensions(self, ext: str) -> None:
        """All supported video extensions should be detected."""
        assert file_utils.is_video(f"test{ext}")
        assert file_utils.is_video(f"test{ext.upper()}")  # Case insensitive

    @pytest.mark.parametrize("ext", [".txt", ".jpg", ".png", ".pdf", ".doc"])
    def test_is_video_invalid_extensions(self, ext: str) -> None:
        """Non-video extensions should not be detected as video."""
        assert not file_utils.is_video(f"test{ext}")


class TestAudioExtensions:
    """Test audio file extension detection."""

    @pytest.mark.parametrize("ext", [".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a"])
    def test_is_audio_valid_extensions(self, ext: str) -> None:
        """All supported audio extensions should be detected."""
        assert file_utils.is_audio(f"test{ext}")
        assert file_utils.is_audio(f"test{ext.upper()}")  # Case insensitive

    @pytest.mark.parametrize("ext", [".txt", ".mp4", ".jpg"])
    def test_is_audio_invalid_extensions(self, ext: str) -> None:
        """Non-audio extensions should not be detected as audio."""
        assert not file_utils.is_audio(f"test{ext}")


class TestSplitByType:
    """Test split_by_type function."""

    def test_split_by_type_mixed(self) -> None:
        """Mixed list should be split correctly."""
        paths = ["video.mp4", "audio.mp3", "doc.txt", "movie.mkv"]
        videos, non_videos = file_utils.split_by_type(paths)
        assert len(videos) == 2
        assert len(non_videos) == 2
        assert any("video.mp4" in v for v in videos)
        assert any("movie.mkv" in v for v in videos)

    def test_split_by_type_empty(self) -> None:
        """Empty list should return empty lists."""
        videos, non_videos = file_utils.split_by_type([])
        assert videos == []
        assert non_videos == []


class TestSafeBasename:
    """Test safe_basename function."""

    def test_safe_basename_normal_path(self) -> None:
        """Normal path should return basename."""
        assert file_utils.safe_basename("/path/to/file.mp4") == "file.mp4"
        assert file_utils.safe_basename("C:\\Users\\test\\video.avi") == "video.avi"

    def test_safe_basename_just_filename(self) -> None:
        """Just filename should return unchanged."""
        assert file_utils.safe_basename("file.mp4") == "file.mp4"


class TestDialogFilter:
    """Test dialog_filter_videos function."""

    def test_dialog_filter_includes_extensions(self) -> None:
        """Dialog filter should include all supported extensions."""
        filter_str = file_utils.dialog_filter_videos()
        assert "*.mp4" in filter_str
        assert "*.mkv" in filter_str
        assert "*.webm" in filter_str
