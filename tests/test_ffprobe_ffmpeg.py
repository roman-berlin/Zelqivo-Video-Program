# tests/test_ffprobe_ffmpeg.py
"""Unit tests for ffprobe and ffmpeg wrappers with mocked subprocess."""
from __future__ import annotations

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from multicam_editor.utils import ffprobe, ffmpeg


# Sample ffprobe JSON output
SAMPLE_PROBE_JSON = {
    "format": {
        "duration": "10.500",
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    },
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "avg_frame_rate": "30/1",
            "r_frame_rate": "30/1",
        },
        {
            "codec_type": "audio",
            "codec_name": "aac",
            "sample_rate": "48000",
            "channels": 2,
        },
    ],
}


@pytest.fixture(autouse=True)
def reset_caches():
    """Reset ffprobe/ffmpeg caches before each test."""
    ffprobe.clear_cache()
    ffprobe.reset_ffprobe_detection()
    ffmpeg.reset_ffmpeg_detection()
    ffmpeg.reset_encoder_selection()
    yield
    ffprobe.clear_cache()
    ffprobe.reset_ffprobe_detection()
    ffmpeg.reset_ffmpeg_detection()
    ffmpeg.reset_encoder_selection()


class TestFFprobe:
    """Tests for ffprobe wrapper."""

    def test_probe_success(self, tmp_path):
        """Probe returns correct metadata from mocked ffprobe output."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake video data")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(SAMPLE_PROBE_JSON).encode("utf-8")
        mock_result.stderr = b""

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            result = ffprobe.probe(str(test_file))

        assert result.error is None
        assert result.duration_ms == 10500
        assert result.width == 1920
        assert result.height == 1080
        assert result.fps == 30.0
        assert result.video_codec == "h264"
        assert result.audio_codec == "aac"
        assert result.resolution_str() == "1920x1080"
        assert result.fps_str() == "30.00"

    def test_probe_cached(self, tmp_path):
        """Second probe call uses cache, not subprocess."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake video data")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(SAMPLE_PROBE_JSON).encode("utf-8")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            result1 = ffprobe.probe(str(test_file))
            result2 = ffprobe.probe(str(test_file))

        # subprocess.run called once for ffprobe check, once for probe
        # Second probe should use cache
        assert result1.duration_ms == result2.duration_ms
        # Should be 2 calls: 1 for _find_ffprobe, 1 for actual probe
        assert mock_run.call_count == 2

    def test_probe_file_not_found(self):
        """Probe returns error for non-existent file."""
        result = ffprobe.probe("/nonexistent/path/video.mp4")
        assert result.error == "File not found"
        assert result.duration_ms == 0

    def test_probe_empty_path(self):
        """Probe returns error for empty path."""
        result = ffprobe.probe("")
        assert result.error == "Empty path"

    def test_probe_ffprobe_not_found(self, tmp_path):
        """Probe returns error when ffprobe not available."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake video data")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("ffprobe not found")
            result = ffprobe.probe(str(test_file))

        assert result.error == "ffprobe not found"

    def test_probe_invalid_json(self, tmp_path):
        """Probe handles invalid JSON from ffprobe."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake video data")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"not valid json"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            result = ffprobe.probe(str(test_file))

        assert result.error is not None
        assert "Invalid JSON" in result.error

    def test_probe_no_duration(self, tmp_path):
        """Probe handles files without duration."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake video data")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"format": {}, "streams": []}).encode()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            result = ffprobe.probe(str(test_file))

        assert result.error == "No duration in file"

    def test_probe_ffprobe_error(self, tmp_path):
        """Probe handles ffprobe returning error."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake video data")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = b""
        mock_result.stderr = b"Invalid data found"

        with patch.object(ffprobe, "_find_ffprobe", return_value="ffprobe"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = mock_result
                result = ffprobe.probe(str(test_file))

        assert result.error is not None
        assert "ffprobe failed" in result.error

    def test_get_duration_ms_wrapper(self, tmp_path):
        """get_duration_ms returns duration or None on error."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake video data")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(SAMPLE_PROBE_JSON).encode()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            duration = ffprobe.get_duration_ms(str(test_file))

        assert duration == 10500

        # Test None return on error
        assert ffprobe.get_duration_ms("/nonexistent") is None

    def test_fps_parsing_fraction(self, tmp_path):
        """FPS parsing handles fractional rates like 30000/1001."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake video data")

        probe_json = {
            "format": {"duration": "5.0"},
            "streams": [{"codec_type": "video", "codec_name": "h264",
                        "avg_frame_rate": "30000/1001", "width": 1280, "height": 720}]
        }
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(probe_json).encode()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            result = ffprobe.probe(str(test_file))

        assert result.fps is not None
        assert abs(result.fps - 29.97) < 0.01


class TestFFmpeg:
    """Tests for ffmpeg wrapper."""

    def test_is_ffmpeg_available(self):
        """is_ffmpeg_available returns bool."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            assert ffmpeg.is_ffmpeg_available() is True

    def test_ffmpeg_not_available(self):
        """is_ffmpeg_available returns False when not found."""
        with patch("multicam_editor.utils.ffmpeg.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            # Also mock os.path.isfile to prevent finding ffmpeg in common paths
            with patch("multicam_editor.utils.ffmpeg.os.path.isfile", return_value=False):
                with patch("multicam_editor.utils.ffmpeg.os.path.isdir", return_value=False):
                    assert ffmpeg.is_ffmpeg_available() is False

    def test_build_trim_args(self):
        """build_trim_args creates correct command."""
        args = ffmpeg.build_trim_args(
            "/input.mp4", "/output.mp4",
            start_ms=5000, end_ms=10000, copy_codec=True
        )
        assert "ffmpeg" in args
        assert "-ss" in args
        assert "5.000" in args
        assert "-t" in args
        assert "5.000" in args
        assert "-c" in args
        assert "copy" in args

    def test_build_trim_args_reencode(self):
        """build_trim_args with re-encode uses the selected H.264 encoder."""
        with patch(
            "multicam_editor.utils.ffmpeg.select_h264_encoder",
            return_value=("libx264", ["-preset", "fast", "-crf", "18"]),
        ):
            args = ffmpeg.build_trim_args(
                "/input.mp4", "/output.mp4",
                start_ms=0, end_ms=1000, copy_codec=False
            )
        assert "libx264" in args
        assert "-crf" in args

    def test_has_effects_none(self):
        """has_effects returns False when no effects applied."""
        assert ffmpeg.has_effects() is False
        assert ffmpeg.has_effects(fade_in_ms=0, fade_out_ms=0, grayscale=False, speed=1.0) is False

    def test_has_effects_fade_in(self):
        """has_effects returns True for fade in."""
        assert ffmpeg.has_effects(fade_in_ms=500) is True

    def test_has_effects_fade_out(self):
        """has_effects returns True for fade out."""
        assert ffmpeg.has_effects(fade_out_ms=500) is True

    def test_has_effects_grayscale(self):
        """has_effects returns True for grayscale."""
        assert ffmpeg.has_effects(grayscale=True) is True

    def test_has_effects_speed(self):
        """has_effects returns True for speed != 1.0."""
        assert ffmpeg.has_effects(speed=2.0) is True
        assert ffmpeg.has_effects(speed=0.5) is True

    def test_build_segment_with_effects_fade_in(self):
        """build_segment_with_effects_args includes fade filter."""
        args = ffmpeg.build_segment_with_effects_args(
            "/input.mp4", "/output.mp4",
            start_ms=0, end_ms=5000,
            fade_in_ms=500
        )
        assert "-vf" in args
        vf_idx = args.index("-vf")
        vf_value = args[vf_idx + 1]
        assert "fade=t=in" in vf_value
        assert "-af" in args
        af_idx = args.index("-af")
        af_value = args[af_idx + 1]
        assert "afade=t=in" in af_value

    def test_build_segment_with_effects_fade_out(self):
        """build_segment_with_effects_args includes fade out filter."""
        args = ffmpeg.build_segment_with_effects_args(
            "/input.mp4", "/output.mp4",
            start_ms=0, end_ms=5000,
            fade_out_ms=500
        )
        vf_idx = args.index("-vf")
        vf_value = args[vf_idx + 1]
        assert "fade=t=out" in vf_value

    def test_build_segment_with_effects_grayscale(self):
        """build_segment_with_effects_args includes grayscale filter."""
        args = ffmpeg.build_segment_with_effects_args(
            "/input.mp4", "/output.mp4",
            start_ms=0, end_ms=5000,
            grayscale=True
        )
        vf_idx = args.index("-vf")
        vf_value = args[vf_idx + 1]
        assert "format=gray" in vf_value

    def test_build_segment_with_effects_speed(self):
        """build_segment_with_effects_args includes speed filters."""
        args = ffmpeg.build_segment_with_effects_args(
            "/input.mp4", "/output.mp4",
            start_ms=0, end_ms=5000,
            speed=2.0
        )
        vf_idx = args.index("-vf")
        vf_value = args[vf_idx + 1]
        assert "setpts=PTS/2.0" in vf_value
        af_idx = args.index("-af")
        af_value = args[af_idx + 1]
        assert "atempo=2.0" in af_value

    def test_build_segment_with_effects_speed_slow(self):
        """build_segment_with_effects_args handles slow speed."""
        args = ffmpeg.build_segment_with_effects_args(
            "/input.mp4", "/output.mp4",
            start_ms=0, end_ms=5000,
            speed=0.5
        )
        vf_idx = args.index("-vf")
        vf_value = args[vf_idx + 1]
        assert "setpts=PTS/0.5" in vf_value
        af_idx = args.index("-af")
        af_value = args[af_idx + 1]
        assert "atempo=0.5" in af_value

    def test_build_segment_with_effects_combined(self):
        """build_segment_with_effects_args combines multiple effects."""
        args = ffmpeg.build_segment_with_effects_args(
            "/input.mp4", "/output.mp4",
            start_ms=0, end_ms=5000,
            fade_in_ms=500,
            fade_out_ms=500,
            grayscale=True,
            speed=1.5
        )
        vf_idx = args.index("-vf")
        vf_value = args[vf_idx + 1]
        assert "setpts=PTS/1.5" in vf_value
        assert "format=gray" in vf_value
        assert "fade=t=in" in vf_value
        assert "fade=t=out" in vf_value

    def test_build_segment_with_effects_clamps_speed(self):
        """build_segment_with_effects_args clamps extreme speeds."""
        args = ffmpeg.build_segment_with_effects_args(
            "/input.mp4", "/output.mp4",
            start_ms=0, end_ms=5000,
            speed=10.0  # Should clamp to 4.0
        )
        vf_idx = args.index("-vf")
        vf_value = args[vf_idx + 1]
        assert "setpts=PTS/4.0" in vf_value  # Clamped to max 4.0

    def test_build_concat_args(self):
        """build_concat_args creates correct command."""
        args = ffmpeg.build_concat_args(
            ["/a.mp4", "/b.mp4"], "/out.mp4", "/list.txt"
        )
        assert "-f" in args
        assert "concat" in args
        assert "/list.txt" in args

    def test_create_concat_list(self, tmp_path):
        """create_concat_list writes proper format."""
        list_file = tmp_path / "list.txt"
        ffmpeg.create_concat_list(
            ["/path/to/video1.mp4", "/path/to/video2.mp4"],
            str(list_file)
        )
        content = list_file.read_text()
        assert "file '/path/to/video1.mp4'" in content
        assert "file '/path/to/video2.mp4'" in content

    def test_get_temp_output_path(self):
        """get_temp_output_path returns valid path."""
        path = ffmpeg.get_temp_output_path(".mp4")
        assert path.endswith(".mp4")
        assert "multicam_" in path

    def test_run_ffmpeg_success(self, tmp_path):
        """run_ffmpeg returns success result."""
        output = tmp_path / "output.mp4"

        with patch.object(ffmpeg, "_find_ffmpeg", return_value="ffmpeg"):
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.communicate.return_value = (b"", b"")
                mock_proc.returncode = 0
                mock_popen.return_value = mock_proc

                result = ffmpeg.run_ffmpeg(
                    ["ffmpeg", "-i", "input.mp4", str(output)],
                    str(output)
                )

        assert result.success is True
        assert result.error is None

    def test_run_ffmpeg_failure(self):
        """run_ffmpeg returns error on failure."""
        with patch.object(ffmpeg, "_find_ffmpeg", return_value="ffmpeg"):
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.communicate.return_value = (b"", b"Error message")
                mock_proc.returncode = 1
                mock_popen.return_value = mock_proc

                result = ffmpeg.run_ffmpeg(["ffmpeg", "-i", "bad.mp4", "out.mp4"])

        assert result.success is False
        assert result.error is not None

    def test_ffmpeg_process_cancel(self, tmp_path):
        """FFmpegProcess.cancel terminates process."""
        output = tmp_path / "output.mp4"

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_popen.return_value = mock_proc

            proc = ffmpeg.FFmpegProcess(["ffmpeg", "-i", "in.mp4"], str(output))
            proc.cancel()

        assert proc._cancelled is True


class TestProbeResult:
    """Tests for ProbeResult dataclass methods."""

    def test_resolution_str_empty(self):
        """resolution_str returns empty when no dimensions."""
        result = ffprobe.ProbeResult(duration_ms=1000)
        assert result.resolution_str() == ""

    def test_fps_str_empty(self):
        """fps_str returns empty when no fps."""
        result = ffprobe.ProbeResult(duration_ms=1000)
        assert result.fps_str() == ""

    def test_resolution_str_valid(self):
        """resolution_str returns WxH format."""
        result = ffprobe.ProbeResult(duration_ms=1000, width=1920, height=1080)
        assert result.resolution_str() == "1920x1080"

    def test_fps_str_valid(self):
        """fps_str returns formatted fps."""
        result = ffprobe.ProbeResult(duration_ms=1000, fps=29.97)
        assert result.fps_str() == "29.97"


class TestCustomFfmpegOverride:
    """The "Use my own FFmpeg" setting (ffmpeg/custom_path) wins discovery."""

    def test_derive_sibling_tool_replaces_only_filename(self):
        from pathlib import Path

        # str(Path(...)) normalizes separators per platform (Windows uses "\\")
        assert ffmpeg.derive_sibling_tool("/opt/ffmpeg/bin/ffmpeg", "ffprobe") == str(
            Path("/opt/ffmpeg/bin/ffprobe")
        )
        # bare PATH-style command
        assert ffmpeg.derive_sibling_tool("ffmpeg", "ffplay") == "ffplay"
        # suffix is preserved
        assert ffmpeg.derive_sibling_tool("tools/ffmpeg.exe", "ffprobe").endswith(
            "ffprobe.exe"
        )

    def test_custom_ffmpeg_wins_discovery(self, tmp_path, monkeypatch):
        fake = tmp_path / "ffmpeg" / "bin" / "ffmpeg"
        fake.parent.mkdir(parents=True)
        fake.write_text("")
        monkeypatch.setattr(ffmpeg, "_custom_ffmpeg_path", lambda: str(fake))
        assert ffmpeg._find_ffmpeg() == str(fake)

    def test_custom_ffprobe_found_as_sibling(self, tmp_path, monkeypatch):
        # "ffmpeg" appears twice in the path — sibling derivation must not
        # rewrite the directory component (regression guard for str.replace)
        bin_dir = tmp_path / "ffmpeg" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "ffmpeg").write_text("")
        (bin_dir / "ffprobe").write_text("")
        monkeypatch.setattr(ffmpeg, "_custom_ffmpeg_path", lambda: str(bin_dir / "ffmpeg"))
        found = ffprobe._find_ffprobe()
        assert found == str(bin_dir / "ffprobe")

    def test_missing_custom_path_falls_through(self, monkeypatch):
        monkeypatch.setattr(ffmpeg, "_custom_ffmpeg_path", lambda: None)
        # Must not raise; discovery continues down the normal chain
        ffmpeg._find_ffmpeg()
