"""Tests for video_utils module."""

from unittest.mock import patch, MagicMock

import pytest

from multicam_editor.logic.video_utils import (
    extract_audio,
    get_video_duration,
    split_video,
    _is_ffmpeg_available,
    _get_ffmpeg_path,
)


class TestExtractAudio:
    """Tests for extract_audio stub."""

    def test_returns_none(self):
        """Stub should return None without error."""
        result = extract_audio("nonexistent.mp4", "out.wav")
        assert result is None


class TestGetVideoDuration:
    """Tests for get_video_duration."""

    @patch("multicam_editor.logic.video_utils.cv2")
    def test_returns_duration_for_valid_video(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            mock_cv2.CAP_PROP_FPS: 30.0,
            mock_cv2.CAP_PROP_FRAME_COUNT: 300.0,
        }.get(prop, 0)

        result = get_video_duration("test.mp4")
        assert result == pytest.approx(10.0)
        mock_cap.release.assert_called_once()

    @patch("multicam_editor.logic.video_utils.cv2")
    def test_returns_none_for_unopenable_file(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = False

        result = get_video_duration("missing.mp4")
        assert result is None

    @patch("multicam_editor.logic.video_utils.cv2")
    def test_returns_none_for_zero_fps(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            mock_cv2.CAP_PROP_FPS: 0.0,
            mock_cv2.CAP_PROP_FRAME_COUNT: 300.0,
        }.get(prop, 0)

        result = get_video_duration("test.mp4")
        assert result is None

    @patch("multicam_editor.logic.video_utils.cv2")
    def test_returns_none_on_exception(self, mock_cv2):
        mock_cv2.VideoCapture.side_effect = Exception("cv2 error")
        result = get_video_duration("test.mp4")
        assert result is None


class TestSplitVideo:
    """Tests for split_video routing logic."""

    @patch("multicam_editor.logic.video_utils.os.path.isfile", return_value=False)
    def test_nonexistent_file_returns_empty_list(self, _):
        result = split_video("nonexistent.mp4", 5000)
        assert result == []

    @patch("multicam_editor.logic.video_utils._split_video_ffmpeg", return_value=["part1.mp4", "part2.mp4"])
    @patch("multicam_editor.logic.video_utils._is_ffmpeg_available", return_value=True)
    @patch("multicam_editor.logic.video_utils.os.path.isfile", return_value=True)
    def test_uses_ffmpeg_when_available(self, _, __, mock_ffmpeg_split):
        result = split_video("video.mp4", 5000)
        mock_ffmpeg_split.assert_called_once_with("video.mp4", 5000)
        assert result == ["part1.mp4", "part2.mp4"]

    @patch("multicam_editor.logic.video_utils._split_video_cv2", return_value=["p1.mp4", "p2.mp4"])
    @patch("multicam_editor.logic.video_utils._is_ffmpeg_available", return_value=False)
    @patch("multicam_editor.logic.video_utils.os.path.isfile", return_value=True)
    def test_falls_back_to_cv2_when_no_ffmpeg(self, _, __, mock_cv2_split):
        result = split_video("video.mp4", 5000)
        mock_cv2_split.assert_called_once_with("video.mp4", 5000)
        assert result == ["p1.mp4", "p2.mp4"]

    @patch("multicam_editor.logic.video_utils._split_video_ffmpeg", return_value=["p1.mp4", "p2.mp4"])
    @patch("multicam_editor.logic.video_utils._is_ffmpeg_available", return_value=True)
    @patch("multicam_editor.logic.video_utils.os.path.isfile", return_value=True)
    def test_negative_split_ms_clamped_to_zero(self, _, __, mock_ffmpeg_split):
        split_video("video.mp4", -100)
        mock_ffmpeg_split.assert_called_once_with("video.mp4", 0)


class TestIsFFmpegAvailable:
    """Tests for _is_ffmpeg_available."""

    @patch("multicam_editor.logic.video_utils.subprocess.run")
    def test_returns_bool(self, mock_run):
        """Should return a boolean regardless of ffmpeg availability."""
        mock_run.return_value = MagicMock(returncode=0)
        # We just verify it returns a bool and doesn't crash
        result = _is_ffmpeg_available()
        assert isinstance(result, bool)


class TestGetFFmpegPath:
    """Tests for _get_ffmpeg_path."""

    def test_returns_string(self):
        result = _get_ffmpeg_path()
        assert isinstance(result, str)
        assert len(result) > 0
