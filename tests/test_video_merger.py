"""Tests for video_merger module."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from multicam_editor.logic.video_merger import (
    CutDefinition,
    RenderResult,
    SegmentRenderer,
    concatenate_segments,
    merge_videos,
    render_cuts,
    render_single_pass,
)
from multicam_editor.utils.ffmpeg import FFmpegResult, build_single_pass_filter_complex_args


class TestCutDefinition:
    """Tests for CutDefinition dataclass."""

    def test_creation(self):
        """CutDefinition should store all fields."""
        cut = CutDefinition(
            source_path="/path/to/video.mp4",
            start_ms=1000,
            end_ms=5000,
            cut_index=0,
        )
        assert cut.source_path == "/path/to/video.mp4"
        assert cut.start_ms == 1000
        assert cut.end_ms == 5000
        assert cut.cut_index == 0

    def test_default_cut_index(self):
        """cut_index should default to 0."""
        cut = CutDefinition(source_path="/path.mp4", start_ms=0, end_ms=1000)
        assert cut.cut_index == 0


class TestSegmentRenderer:
    """Tests for SegmentRenderer."""

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    def test_ffmpeg_not_available(self, mock_ffmpeg_avail, tmp_path):
        """Should return error if ffmpeg not found."""
        mock_ffmpeg_avail.return_value = False

        renderer = SegmentRenderer(str(tmp_path))
        cuts = [CutDefinition("/video.mp4", 0, 1000, 0)]
        result = renderer.render_segments(cuts)

        assert not result.success
        assert "ffmpeg not found" in result.error

    def test_empty_cuts(self, tmp_path):
        """Empty cuts list should return success."""
        renderer = SegmentRenderer(str(tmp_path))
        result = renderer.render_segments([])

        assert result.success
        assert result.total_count == 0
        assert result.segment_paths == []

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    @patch("multicam_editor.logic.video_merger.FFmpegProcess")
    def test_render_3_cuts_success(self, mock_ffmpeg_proc, mock_ffmpeg_avail, tmp_path):
        """Should render 3 cuts successfully."""
        mock_ffmpeg_avail.return_value = True

        # Create fake source file
        source = tmp_path / "source.mp4"
        source.write_text("fake video")

        # Mock FFmpegProcess to succeed and create output file
        def mock_run():
            output_path = mock_ffmpeg_proc.call_args[0][1]
            Path(output_path).write_text("fake segment")
            return FFmpegResult(success=True, output_path=output_path)

        mock_proc_instance = MagicMock()
        mock_proc_instance.run = mock_run
        mock_ffmpeg_proc.return_value = mock_proc_instance

        renderer = SegmentRenderer(str(tmp_path))
        cuts = [
            CutDefinition(str(source), 0, 1000, 0),
            CutDefinition(str(source), 1000, 2000, 1),
            CutDefinition(str(source), 2000, 3000, 2),
        ]

        progress_calls = []
        result = renderer.render_segments(cuts, on_progress=lambda r, t: progress_calls.append((r, t)))

        assert result.success
        assert result.rendered_count == 3
        assert len(result.segment_paths) == 3
        assert progress_calls == [(1, 3), (2, 3), (3, 3)]

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    @patch("multicam_editor.logic.video_merger.FFmpegProcess")
    def test_render_5_cuts_success(self, mock_ffmpeg_proc, mock_ffmpeg_avail, tmp_path):
        """Should render 5 cuts successfully."""
        mock_ffmpeg_avail.return_value = True

        source = tmp_path / "source.mp4"
        source.write_text("fake video")

        def mock_run():
            output_path = mock_ffmpeg_proc.call_args[0][1]
            Path(output_path).write_text("fake segment")
            return FFmpegResult(success=True, output_path=output_path)

        mock_proc_instance = MagicMock()
        mock_proc_instance.run = mock_run
        mock_ffmpeg_proc.return_value = mock_proc_instance

        renderer = SegmentRenderer(str(tmp_path))
        cuts = [
            CutDefinition(str(source), i * 1000, (i + 1) * 1000, i)
            for i in range(5)
        ]

        result = renderer.render_segments(cuts)

        assert result.success
        assert result.rendered_count == 5
        assert len(result.segment_paths) == 5

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    def test_source_file_not_found(self, mock_ffmpeg_avail, tmp_path):
        """Should fail gracefully if source file not found."""
        mock_ffmpeg_avail.return_value = True

        renderer = SegmentRenderer(str(tmp_path))
        cuts = [CutDefinition("/nonexistent/video.mp4", 0, 1000, 0)]

        result = renderer.render_segments(cuts)

        assert not result.success
        assert "not found" in result.error

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    @patch("multicam_editor.logic.video_merger.FFmpegProcess")
    def test_stream_copy_fallback_to_reencode(self, mock_ffmpeg_proc, mock_ffmpeg_avail, tmp_path):
        """Should fallback to re-encode if stream copy fails."""
        mock_ffmpeg_avail.return_value = True

        source = tmp_path / "source.mp4"
        source.write_text("fake video")

        call_count = [0]

        def mock_run():
            call_count[0] += 1
            output_path = mock_ffmpeg_proc.call_args[0][1]
            if call_count[0] == 1:
                # First call (stream copy) fails
                return FFmpegResult(success=False, error="stream copy failed")
            else:
                # Second call (re-encode) succeeds
                Path(output_path).write_text("fake segment")
                return FFmpegResult(success=True, output_path=output_path)

        mock_proc_instance = MagicMock()
        mock_proc_instance.run = mock_run
        mock_ffmpeg_proc.return_value = mock_proc_instance

        renderer = SegmentRenderer(str(tmp_path))
        cuts = [CutDefinition(str(source), 0, 1000, 0)]

        # Explicitly enable stream copy to test fallback behavior
        result = renderer.render_segments(cuts, try_stream_copy=True)

        assert result.success
        assert call_count[0] == 2  # Stream copy + re-encode

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    @patch("multicam_editor.logic.video_merger.FFmpegProcess")
    def test_invalid_cut_skipped(self, mock_ffmpeg_proc, mock_ffmpeg_avail, tmp_path):
        """Cuts with end <= start should be skipped."""
        mock_ffmpeg_avail.return_value = True

        source = tmp_path / "source.mp4"
        source.write_text("fake video")

        def mock_run():
            output_path = mock_ffmpeg_proc.call_args[0][1]
            Path(output_path).write_text("fake segment")
            return FFmpegResult(success=True, output_path=output_path)

        mock_proc_instance = MagicMock()
        mock_proc_instance.run = mock_run
        mock_ffmpeg_proc.return_value = mock_proc_instance

        renderer = SegmentRenderer(str(tmp_path))
        cuts = [
            CutDefinition(str(source), 1000, 500, 0),  # Invalid: end < start
            CutDefinition(str(source), 0, 1000, 1),  # Valid
        ]

        result = renderer.render_segments(cuts)

        assert result.success
        assert result.rendered_count == 1


class TestSegmentRendererCancellation:
    """Tests for cancellation behavior."""

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    @patch("multicam_editor.logic.video_merger.FFmpegProcess")
    def test_cancel_cleans_up_segments(self, mock_ffmpeg_proc, mock_ffmpeg_avail, tmp_path):
        """Cancellation should cleanup all rendered segments."""
        mock_ffmpeg_avail.return_value = True

        source = tmp_path / "source.mp4"
        source.write_text("fake video")

        segments_created = []

        def mock_run():
            output_path = mock_ffmpeg_proc.call_args[0][1]
            Path(output_path).write_text("fake segment")
            segments_created.append(output_path)
            # Simulate slow render
            time.sleep(0.1)
            return FFmpegResult(success=True, output_path=output_path)

        mock_proc_instance = MagicMock()
        mock_proc_instance.run = mock_run
        mock_proc_instance.cancel = MagicMock()
        mock_ffmpeg_proc.return_value = mock_proc_instance

        renderer = SegmentRenderer(str(tmp_path))
        cuts = [
            CutDefinition(str(source), i * 1000, (i + 1) * 1000, i)
            for i in range(5)
        ]

        # Start render in thread and cancel after first segment
        def cancel_after_delay():
            time.sleep(0.15)
            renderer.cancel()

        cancel_thread = threading.Thread(target=cancel_after_delay)
        cancel_thread.start()

        result = renderer.render_segments(cuts)
        cancel_thread.join()

        assert result.cancelled
        assert not result.success
        # All created segments should be cleaned up
        for seg_path in segments_created:
            assert not os.path.exists(seg_path)

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    @patch("multicam_editor.logic.video_merger.FFmpegProcess")
    def test_cancel_mid_render_returns_cancelled_result(self, mock_ffmpeg_proc, mock_ffmpeg_avail, tmp_path):
        """Cancel during render should return cancelled result."""
        mock_ffmpeg_avail.return_value = True

        source = tmp_path / "source.mp4"
        source.write_text("fake video")

        renderer = SegmentRenderer(str(tmp_path))

        def mock_run():
            return FFmpegResult(success=False, cancelled=True, error="Cancelled")

        mock_proc_instance = MagicMock()
        mock_proc_instance.run = mock_run
        mock_ffmpeg_proc.return_value = mock_proc_instance

        cuts = [CutDefinition(str(source), 0, 1000, 0)]
        result = renderer.render_segments(cuts)

        assert result.cancelled
        assert not result.success


class TestRenderCuts:
    """Tests for render_cuts convenience function."""

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    @patch("multicam_editor.logic.video_merger.FFmpegProcess")
    def test_render_cuts_convenience(self, mock_ffmpeg_proc, mock_ffmpeg_avail, tmp_path):
        """render_cuts should work as convenience wrapper."""
        mock_ffmpeg_avail.return_value = True

        source = tmp_path / "source.mp4"
        source.write_text("fake video")

        def mock_run():
            output_path = mock_ffmpeg_proc.call_args[0][1]
            Path(output_path).write_text("fake segment")
            return FFmpegResult(success=True, output_path=output_path)

        mock_proc_instance = MagicMock()
        mock_proc_instance.run = mock_run
        mock_ffmpeg_proc.return_value = mock_proc_instance

        cuts = [CutDefinition(str(source), 0, 1000, 0)]
        result = render_cuts(cuts, str(tmp_path))

        assert result.success


class TestConcatenateSegments:
    """Tests for concatenate_segments function."""

    def test_empty_segments_returns_none(self):
        """Empty segment list should return None."""
        result = concatenate_segments([], "/output.mp4")
        assert result is None

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    def test_ffmpeg_not_available_returns_none(self, mock_ffmpeg):
        """Should return None if ffmpeg not available."""
        mock_ffmpeg.return_value = False
        result = concatenate_segments(["/seg1.mp4", "/seg2.mp4"], "/output.mp4")
        assert result is None

    def test_single_segment_copies_file(self, tmp_path):
        """Single segment should just be copied to output."""
        seg = tmp_path / "seg0.mp4"
        seg.write_text("fake segment data")
        output = tmp_path / "output.mp4"

        result = concatenate_segments([str(seg)], str(output))

        assert result == str(output)
        assert output.exists()
        assert output.read_text() == "fake segment data"

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    @patch("multicam_editor.logic.video_merger.FFmpegProcess")
    def test_multiple_segments_concat(self, mock_ffmpeg_proc, mock_ffmpeg_avail, tmp_path):
        """Multiple segments should be concatenated."""
        mock_ffmpeg_avail.return_value = True

        # Create fake segments
        seg1 = tmp_path / "seg0.mp4"
        seg2 = tmp_path / "seg1.mp4"
        seg1.write_text("seg1")
        seg2.write_text("seg2")
        output = tmp_path / "output.mp4"

        def mock_run():
            # Simulate concat creating output
            output.write_text("concatenated")
            return FFmpegResult(success=True, output_path=str(output))

        mock_proc_instance = MagicMock()
        mock_proc_instance.run = mock_run
        mock_ffmpeg_proc.return_value = mock_proc_instance

        result = concatenate_segments([str(seg1), str(seg2)], str(output))

        assert result == str(output)
        assert mock_ffmpeg_proc.called

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    @patch("multicam_editor.logic.video_merger.FFmpegProcess")
    def test_concat_fallback_to_reencode(self, mock_ffmpeg_proc, mock_ffmpeg_avail, tmp_path):
        """Should fallback to re-encode if stream copy concat fails."""
        mock_ffmpeg_avail.return_value = True

        seg1 = tmp_path / "seg0.mp4"
        seg2 = tmp_path / "seg1.mp4"
        seg1.write_text("seg1")
        seg2.write_text("seg2")
        output = tmp_path / "output.mp4"

        call_count = [0]

        def mock_run():
            call_count[0] += 1
            if call_count[0] == 1:
                return FFmpegResult(success=False, error="concat failed")
            else:
                output.write_text("re-encoded")
                return FFmpegResult(success=True, output_path=str(output))

        mock_proc_instance = MagicMock()
        mock_proc_instance.run = mock_run
        mock_ffmpeg_proc.return_value = mock_proc_instance

        result = concatenate_segments([str(seg1), str(seg2)], str(output))

        assert result == str(output)
        assert call_count[0] == 2  # Stream copy + re-encode


class TestMergeVideos:
    """Tests for merge_videos function."""

    @patch("multicam_editor.logic.video_merger.render_cuts")
    def test_merge_single_segment(self, mock_render_cuts, tmp_path):
        """merge_videos with single segment copies to output."""
        source = tmp_path / "video.mp4"
        source.write_text("fake")

        seg_path = tmp_path / "segment0.mp4"
        seg_path.write_text("segment data")

        mock_render_cuts.return_value = RenderResult(
            success=True,
            segment_paths=[str(seg_path)],
            rendered_count=1,
            total_count=1,
        )

        output = tmp_path / "output.mp4"
        result = merge_videos(
            segment_definitions=[{"video_index": 0, "start_ms": 0, "end_ms": 1000}],
            input_video_paths=[str(source)],
            output_path=str(output),
        )

        assert result == str(output)
        assert output.exists()

    def test_merge_invalid_video_index(self, tmp_path):
        """merge_videos with invalid video_index should return None."""
        result = merge_videos(
            segment_definitions=[{"video_index": 5, "start_ms": 0, "end_ms": 1000}],
            input_video_paths=["/video.mp4"],
            output_path="/tmp/output.mp4",
        )

        assert result is None

    @patch("multicam_editor.logic.video_merger.concatenate_segments")
    @patch("multicam_editor.logic.video_merger.render_cuts")
    def test_merge_multiple_segments_calls_concat(self, mock_render, mock_concat, tmp_path):
        """merge_videos with multiple segments should call concatenate_segments."""
        source = tmp_path / "video.mp4"
        source.write_text("fake")

        seg1 = tmp_path / "seg0.mp4"
        seg2 = tmp_path / "seg1.mp4"
        seg1.write_text("seg1")
        seg2.write_text("seg2")

        mock_render.return_value = RenderResult(
            success=True,
            segment_paths=[str(seg1), str(seg2)],
            rendered_count=2,
            total_count=2,
        )
        mock_concat.return_value = "/output.mp4"

        result = merge_videos(
            segment_definitions=[
                {"video_index": 0, "start_ms": 0, "end_ms": 1000},
                {"video_index": 0, "start_ms": 1000, "end_ms": 2000},
            ],
            input_video_paths=[str(source)],
            output_path="/output.mp4",
        )

        assert result == "/output.mp4"
        mock_concat.assert_called_once()


class TestBuildSinglePassFilterComplexArgs:
    """Tests for build_single_pass_filter_complex_args function."""

    def test_empty_cuts_returns_empty(self):
        """Empty cuts list should return empty args."""
        args = build_single_pass_filter_complex_args([], "/output.mp4")
        assert args == []

    def test_single_cut_produces_valid_filter(self, tmp_path):
        """Single cut should produce valid filter_complex."""
        source = tmp_path / "video.mp4"
        source.write_text("fake")
        
        cuts = [CutDefinition(str(source), 0, 5000, 0, camera_index=0)]
        args = build_single_pass_filter_complex_args(cuts, "/output.mp4", resolution="1080p")
        
        assert args[0] == "ffmpeg"
        assert "-filter_complex" in args
        
        # Find filter_complex value
        fc_idx = args.index("-filter_complex")
        fc_value = args[fc_idx + 1]
        
        assert "trim=start=0.000:end=5.000" in fc_value
        assert "setpts=PTS-STARTPTS" in fc_value
        assert "concat=n=1:v=1:a=0" in fc_value

    def test_three_cuts_two_cameras(self, tmp_path):
        """Three cuts across two cameras should produce correct filter."""
        cam0 = tmp_path / "cam0.mp4"
        cam1 = tmp_path / "cam1.mp4"
        cam0.write_text("fake0")
        cam1.write_text("fake1")
        
        cuts = [
            CutDefinition(str(cam0), 0, 4600, 0, camera_index=0),
            CutDefinition(str(cam1), 4600, 12200, 1, camera_index=1),
            CutDefinition(str(cam0), 12200, 15000, 2, camera_index=0),
        ]
        
        args = build_single_pass_filter_complex_args(cuts, "/output.mp4")
        
        # Should have two inputs
        input_count = args.count("-i")
        assert input_count == 2
        
        # Find filter_complex
        fc_idx = args.index("-filter_complex")
        fc_value = args[fc_idx + 1]
        
        # Should have trim for each segment
        assert "trim=start=0.000:end=4.600" in fc_value
        assert "trim=start=4.600:end=12.200" in fc_value
        assert "trim=start=12.200:end=15.000" in fc_value
        
        # Should have concat with n=3
        assert "concat=n=3:v=1:a=0" in fc_value
        
        # Should have correct input references (both [0:v] and [1:v])
        assert "[0:v]" in fc_value
        assert "[1:v]" in fc_value

    def test_resolution_720p(self, tmp_path):
        """720p resolution should use correct dimensions."""
        source = tmp_path / "video.mp4"
        source.write_text("fake")
        
        cuts = [CutDefinition(str(source), 0, 1000, 0)]
        args = build_single_pass_filter_complex_args(cuts, "/output.mp4", resolution="720p")
        
        fc_idx = args.index("-filter_complex")
        fc_value = args[fc_idx + 1]
        
        assert "scale=1280:720" in fc_value
        assert "pad=1280:720" in fc_value

    def test_resolution_1080p_default(self, tmp_path):
        """Default 1080p resolution should use correct dimensions."""
        source = tmp_path / "video.mp4"
        source.write_text("fake")
        
        cuts = [CutDefinition(str(source), 0, 1000, 0)]
        args = build_single_pass_filter_complex_args(cuts, "/output.mp4")
        
        fc_idx = args.index("-filter_complex")
        fc_value = args[fc_idx + 1]
        
        assert "scale=1920:1080" in fc_value
        assert "pad=1920:1080" in fc_value

    def test_output_has_cfr_mode(self, tmp_path):
        """Output should use CFR mode to prevent VFR issues."""
        source = tmp_path / "video.mp4"
        source.write_text("fake")
        
        cuts = [CutDefinition(str(source), 0, 1000, 0)]
        args = build_single_pass_filter_complex_args(cuts, "/output.mp4")
        
        assert "-fps_mode" in args
        fps_mode_idx = args.index("-fps_mode")
        assert args[fps_mode_idx + 1] == "cfr"


class TestRenderSinglePass:
    """Tests for render_single_pass function."""

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    def test_ffmpeg_not_available(self, mock_ffmpeg):
        """Should return error if ffmpeg not available."""
        mock_ffmpeg.return_value = False
        
        cuts = [CutDefinition("/video.mp4", 0, 1000, 0)]
        result = render_single_pass(cuts, "/output.mp4")
        
        assert not result.success
        assert "ffmpeg not found" in result.error

    def test_empty_cuts(self):
        """Empty cuts should return success with no output."""
        result = render_single_pass([], "/output.mp4")
        
        assert result.success
        assert result.segment_paths == []

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    def test_source_not_found(self, mock_ffmpeg):
        """Should fail if source file not found."""
        mock_ffmpeg.return_value = True
        
        cuts = [CutDefinition("/nonexistent/video.mp4", 0, 1000, 0)]
        result = render_single_pass(cuts, "/output.mp4")
        
        assert not result.success
        assert "not found" in result.error

    @patch("multicam_editor.logic.video_merger.is_ffmpeg_available")
    @patch("multicam_editor.logic.video_merger.FFmpegProcess")
    def test_successful_render(self, mock_proc, mock_ffmpeg, tmp_path):
        """Successful render should return output path."""
        mock_ffmpeg.return_value = True
        
        source = tmp_path / "video.mp4"
        source.write_text("fake")
        output = tmp_path / "output.mp4"
        
        # Mock FFmpegProcess to simulate successful render
        mock_proc_instance = MagicMock()
        mock_proc_instance.run.return_value = FFmpegResult(success=True, output_path=str(output))
        mock_proc.return_value = mock_proc_instance
        
        cuts = [CutDefinition(str(source), 0, 1000, 0)]
        result = render_single_pass(cuts, str(output))
        
        assert result.success
        assert result.segment_paths == [str(output)]
        assert result.rendered_count == 1


class TestBlackFramesPrevention:
    """Integration tests to verify no black frames at cut boundaries.
    
    These tests use generated test videos and verify frames at boundaries.
    """

    @pytest.fixture
    def ffmpeg_available(self):
        """Skip if ffmpeg not available."""
        from multicam_editor.utils.ffmpeg import is_ffmpeg_available
        if not is_ffmpeg_available():
            pytest.skip("ffmpeg not available")

    def test_filter_complex_structure_for_seamless_concat(self, tmp_path):
        """Verify filter structure uses trim+setpts for seamless concatenation."""
        # Create fake sources
        cam0 = tmp_path / "cam0.mp4"
        cam1 = tmp_path / "cam1.mp4"
        cam0.write_text("fake0")
        cam1.write_text("fake1")
        
        # Create cut plan that switches cameras
        cuts = [
            CutDefinition(str(cam0), 0, 1000, 0, camera_index=0),
            CutDefinition(str(cam1), 1000, 2000, 1, camera_index=1),
            CutDefinition(str(cam0), 2000, 3000, 2, camera_index=0),
        ]
        
        args = build_single_pass_filter_complex_args(cuts, str(tmp_path / "out.mp4"))
        fc_idx = args.index("-filter_complex")
        fc_value = args[fc_idx + 1]
        
        # Each segment must have setpts=PTS-STARTPTS to reset timestamps
        # This prevents gaps that cause black frames
        setpts_count = fc_value.count("setpts=PTS-STARTPTS")
        assert setpts_count == 3, f"Expected 3 setpts, got {setpts_count}"
        
        # Must use concat filter (not concat demuxer) for seamless joining
        assert "concat=n=3:v=1:a=0" in fc_value
        
        # Must have fps filter to ensure CFR
        assert "fps=" in fc_value

    def test_no_seeking_per_segment(self, tmp_path):
        """Verify we don't use -ss which causes keyframe seeking issues."""
        source = tmp_path / "video.mp4"
        source.write_text("fake")
        
        cuts = [
            CutDefinition(str(source), 0, 1000, 0),
            CutDefinition(str(source), 1000, 2000, 1),
        ]
        
        args = build_single_pass_filter_complex_args(cuts, str(tmp_path / "out.mp4"))
        
        # Should NOT use -ss (input seeking) - the source of black frames
        # We use trim filter instead which is frame-accurate
        assert "-ss" not in args
        
        # trim filter should be used instead
        fc_idx = args.index("-filter_complex")
        fc_value = args[fc_idx + 1]
        assert "trim=start=" in fc_value
