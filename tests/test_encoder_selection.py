# tests/test_encoder_selection.py
"""Unit tests for select_h264_encoder with mocked `ffmpeg -encoders` probe."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from multicam_editor.utils import ffmpeg


def _encoders_output(*names: str) -> bytes:
    """Build realistic `ffmpeg -hide_banner -encoders` output."""
    lines = [
        "Encoders:",
        " V..... = Video",
        " A..... = Audio",
        " S..... = Subtitle",
        " .F.... = Frame-level multithreading",
        " ------",
    ]
    for name in names:
        lines.append(f" V....D {name}              {name} H.264 (codec h264)")
    # Unrelated encoders that must never be picked
    lines.append(" V....D mpeg4                MPEG-4 part 2")
    lines.append(" A....D aac                  AAC (Advanced Audio Coding)")
    return "\n".join(lines).encode("utf-8")


@pytest.fixture(autouse=True)
def reset_caches():
    """Reset ffmpeg detection and encoder caches before/after each test."""
    ffmpeg.reset_ffmpeg_detection()
    ffmpeg.reset_encoder_selection()
    yield
    ffmpeg.reset_ffmpeg_detection()
    ffmpeg.reset_encoder_selection()


def _select(available: tuple[str, ...], **kwargs):
    """Run select_h264_encoder against a mocked probe. Returns (result, mock)."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = _encoders_output(*available)
    with patch("multicam_editor.utils.ffmpeg._find_ffmpeg", return_value="ffmpeg"):
        with patch(
            "multicam_editor.utils.ffmpeg.subprocess.run", return_value=mock_result
        ) as mock_run:
            result = ffmpeg.select_h264_encoder(**kwargs)
    return result, mock_run


class TestSelectH264Encoder:
    """Vendor matrix for select_h264_encoder."""

    def test_nvidia_only(self):
        (encoder, args), _ = _select(("h264_nvenc", "libx264"))
        assert encoder == "h264_nvenc"
        assert args == ["-rc", "vbr", "-cq", "23", "-preset", "p4"]

    def test_intel_only(self):
        (encoder, args), _ = _select(("h264_qsv",))
        assert encoder == "h264_qsv"
        assert args == ["-global_quality", "23"]

    def test_amd_only(self):
        (encoder, args), _ = _select(("h264_amf",))
        assert encoder == "h264_amf"
        assert args == ["-rc", "cqp", "-qp_i", "23", "-qp_p", "23"]

    def test_videotoolbox(self):
        (encoder, args), _ = _select(("h264_videotoolbox", "libx264"))
        assert encoder == "h264_videotoolbox"
        assert args == ["-q:v", "55"]

    def test_openh264_only(self):
        (encoder, args), _ = _select(("libopenh264",))
        assert encoder == "libopenh264"
        assert args == ["-b:v", "6M"]

    def test_everything_available_nvenc_wins(self):
        (encoder, _), _ = _select(
            (
                "libx264",
                "libopenh264",
                "h264_videotoolbox",
                "h264_amf",
                "h264_qsv",
                "h264_nvenc",
            )
        )
        assert encoder == "h264_nvenc"

    def test_only_x264(self):
        (encoder, args), _ = _select(("libx264",))
        assert encoder == "libx264"
        assert args == ["-preset", "fast", "-crf", "18"]

    def test_x264rgb_is_not_x264(self):
        """libx264rgb must not be mistaken for libx264."""
        with pytest.raises(RuntimeError, match="No supported H.264 encoder"):
            _select(("libx264rgb",))

    def test_empty_raises_clear_error(self):
        with pytest.raises(RuntimeError, match="No supported H.264 encoder"):
            _select(())

    def test_ffmpeg_missing_raises_clear_error(self):
        with patch("multicam_editor.utils.ffmpeg._find_ffmpeg", return_value=None):
            with pytest.raises(RuntimeError, match="ffmpeg not found"):
                ffmpeg.select_h264_encoder()

    def test_prefer_hardware_false_skips_hardware(self):
        (encoder, _), _ = _select(
            ("h264_nvenc", "h264_videotoolbox", "libopenh264", "libx264"),
            prefer_hardware=False,
        )
        assert encoder == "libopenh264"

    def test_probe_runs_once(self):
        """Second call must hit the cache, not re-run the probe."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = _encoders_output("h264_nvenc", "libx264")
        with patch("multicam_editor.utils.ffmpeg._find_ffmpeg", return_value="ffmpeg"):
            with patch(
                "multicam_editor.utils.ffmpeg.subprocess.run", return_value=mock_result
            ) as mock_run:
                first = ffmpeg.select_h264_encoder()
                second = ffmpeg.select_h264_encoder()
                third = ffmpeg.select_h264_encoder(prefer_hardware=False)
        assert first == second
        assert third[0] == "libx264"
        assert mock_run.call_count == 1

    def test_returned_args_are_a_copy(self):
        """Mutating the returned args must not corrupt the cache."""
        (_, args), _ = _select(("libx264",))
        args.append("-corrupted")
        cached = ffmpeg._selected_encoders[True][1]
        assert "-corrupted" not in cached


class TestQaSummaryEncoder:
    """The chosen encoder is surfaced in processing_summary.json."""

    def test_summary_names_encoder(self, tmp_path):
        from multicam_editor.logic import qa_artifacts

        with patch(
            "multicam_editor.logic.qa_artifacts.select_h264_encoder",
            return_value=("h264_nvenc", ["-rc", "vbr", "-cq", "23", "-preset", "p4"]),
        ):
            qa_artifacts.export_processing_summary(
                tmp_path,
                num_speakers=1,
                num_segments=1,
                num_cuts=1,
                total_duration_ms=1000,
                thresholds={},
            )
        data = json.loads((tmp_path / "processing_summary.json").read_text(encoding="utf-8"))
        assert data["h264_encoder"] == "h264_nvenc"

    def test_summary_survives_missing_ffmpeg(self, tmp_path):
        from multicam_editor.logic import qa_artifacts

        with patch(
            "multicam_editor.logic.qa_artifacts.select_h264_encoder",
            side_effect=RuntimeError("ffmpeg not found"),
        ):
            qa_artifacts.export_processing_summary(
                tmp_path,
                num_speakers=1,
                num_segments=1,
                num_cuts=1,
                total_duration_ms=1000,
                thresholds={},
            )
        data = json.loads((tmp_path / "processing_summary.json").read_text(encoding="utf-8"))
        assert data["h264_encoder"] == "unavailable"
