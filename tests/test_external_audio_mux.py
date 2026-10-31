"""-itsoffset sign for external audio muxing.

audio_sync reports a POSITIVE offset when the external audio is late relative
to the camera audio. ffmpeg's -itsoffset DELAYS its following input when
positive, so lining the audio up requires passing the negated offset.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from multicam_editor.logic.processing_pipeline import ProcessingPipeline
from multicam_editor.utils.signals import ProcessingSignals


def _mux_args(offset_ms: float) -> list[str]:
    pipeline = ProcessingPipeline(["camera1.mp4", "camera2.mp4"], ProcessingSignals())
    with patch("multicam_editor.utils.ffmpeg.is_ffmpeg_available", return_value=True), \
         patch("multicam_editor.utils.ffmpeg.FFmpegProcess") as proc_cls:
        proc_cls.return_value.run.return_value = SimpleNamespace(success=True, error=None)
        result = pipeline._add_external_audio_with_offset(
            "video.mp4", "ext.wav", "out.mp4", offset_ms
        )
    assert result == "out.mp4"
    return proc_cls.call_args[0][0]


def _itsoffset_value(args: list[str]) -> float:
    i = args.index("-itsoffset")
    # The flag must apply to the external audio input, not the video input.
    assert args.index("video.mp4") < i < args.index("ext.wav")
    return float(args[i + 1])


def test_late_external_audio_is_pulled_earlier():
    assert _itsoffset_value(_mux_args(500.0)) == pytest.approx(-0.5)


def test_early_external_audio_is_pushed_later():
    assert _itsoffset_value(_mux_args(-250.0)) == pytest.approx(0.25)


def test_negligible_offset_adds_no_flag():
    assert "-itsoffset" not in _mux_args(0.0)
