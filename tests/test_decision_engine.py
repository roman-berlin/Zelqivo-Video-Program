"""Unit tests for DecisionEngine."""

import pytest

from multicam_editor.logic.active_speaker import SpeakerSegment
from multicam_editor.logic.decision_engine import CutSegment, DecisionEngine


class TestCutSegment:
    """Tests for CutSegment dataclass validation."""

    def test_valid_segment(self) -> None:
        seg = CutSegment(0, 1000, 0)
        assert seg.start_ms == 0
        assert seg.end_ms == 1000
        assert seg.camera_id == 0

    def test_negative_start_raises(self) -> None:
        with pytest.raises(ValueError, match="start_ms must be >= 0"):
            CutSegment(-1, 1000, 0)

    def test_end_before_start_raises(self) -> None:
        with pytest.raises(ValueError, match="end_ms must be > start_ms"):
            CutSegment(1000, 500, 0)

    def test_negative_camera_id_raises(self) -> None:
        with pytest.raises(ValueError, match="camera_id must be >= 0"):
            CutSegment(0, 1000, -1)


class TestDecisionEngineDefaults:
    """Test default parameter values."""

    def test_defaults(self) -> None:
        engine = DecisionEngine()
        assert engine.min_switch_interval_ms == 1500
        assert engine.min_speech_ms == 600
        assert engine.bg_short_remark_ms == 500
        assert engine.default_camera == 0


class TestDecisionEngineEmptyInput:
    """Edge cases for empty or minimal input."""

    def test_empty_segments_no_duration(self) -> None:
        engine = DecisionEngine()
        result = engine.generate_cut_plan([])
        assert result == []

    def test_empty_segments_with_duration(self) -> None:
        engine = DecisionEngine()
        result = engine.generate_cut_plan([], total_duration_ms=5000)
        assert len(result) == 1
        assert result[0] == CutSegment(0, 5000, 0)

    def test_all_segments_filtered_as_short_remarks(self) -> None:
        engine = DecisionEngine(bg_short_remark_ms=500)
        segments = [
            SpeakerSegment(0, 400, 1),  # 400ms < 500ms threshold
            SpeakerSegment(500, 800, 0),  # 300ms < 500ms threshold
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=1000)
        # All filtered, should return default camera for full duration
        assert len(result) == 1
        assert result[0].camera_id == 0


class TestDecisionEngineShortRemarkFiltering:
    """Test bg_short_remark_ms filtering."""

    def test_short_remark_ignored(self) -> None:
        engine = DecisionEngine(bg_short_remark_ms=500, min_speech_ms=600, min_switch_interval_ms=0)
        segments = [
            SpeakerSegment(0, 2000, 0),  # 2000ms speech
            SpeakerSegment(2000, 2300, 1),  # 300ms short remark - ignored
            SpeakerSegment(2500, 4500, 0),  # 2000ms speech
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=5000)
        # Should stay on camera 0 throughout (short remark filtered)
        assert len(result) == 1
        assert result[0].camera_id == 0

    def test_long_enough_remark_not_filtered(self) -> None:
        engine = DecisionEngine(bg_short_remark_ms=500, min_speech_ms=600, min_switch_interval_ms=0)
        segments = [
            SpeakerSegment(0, 2000, 0),  # 2000ms camera 0
            SpeakerSegment(2000, 3000, 1),  # 1000ms camera 1 - long enough
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=3000)
        assert len(result) == 2
        assert result[0].camera_id == 0
        assert result[1].camera_id == 1


class TestDecisionEngineMinSpeech:
    """Test min_speech_ms requirement."""

    def test_segment_below_min_speech_no_switch(self) -> None:
        engine = DecisionEngine(min_speech_ms=600, bg_short_remark_ms=100, min_switch_interval_ms=0)
        segments = [
            SpeakerSegment(0, 2000, 0),
            SpeakerSegment(2000, 2500, 1),  # 500ms < 600ms min_speech
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=3000)
        # No switch because segment 1 is too short
        assert len(result) == 1
        assert result[0].camera_id == 0

    def test_segment_at_min_speech_triggers_switch(self) -> None:
        engine = DecisionEngine(min_speech_ms=600, bg_short_remark_ms=100, min_switch_interval_ms=0)
        segments = [
            SpeakerSegment(0, 2000, 0),
            SpeakerSegment(2000, 2600, 1),  # 600ms exactly
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=3000)
        assert len(result) == 2
        assert result[1].camera_id == 1


class TestDecisionEngineMinSwitchInterval:
    """Test min_switch_interval_ms enforcement."""

    def test_rapid_switches_blocked(self) -> None:
        engine = DecisionEngine(min_switch_interval_ms=1500, min_speech_ms=100, bg_short_remark_ms=100)
        segments = [
            SpeakerSegment(0, 1000, 0),
            SpeakerSegment(1000, 2000, 1),  # Only 1000ms since start, blocked
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=2000)
        assert len(result) == 1
        assert result[0].camera_id == 0

    def test_switch_after_interval(self) -> None:
        engine = DecisionEngine(min_switch_interval_ms=1500, min_speech_ms=100, bg_short_remark_ms=100)
        segments = [
            SpeakerSegment(0, 1000, 0),
            SpeakerSegment(1500, 2500, 1),  # Exactly 1500ms since start
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=3000)
        assert len(result) == 2
        assert result[0].camera_id == 0
        assert result[1].camera_id == 1


class TestDecisionEnginePreferCurrentCamera:
    """Test preference for current camera on uncertainty."""

    def test_same_speaker_no_switch(self) -> None:
        engine = DecisionEngine(min_switch_interval_ms=0, min_speech_ms=100, bg_short_remark_ms=100)
        segments = [
            SpeakerSegment(0, 2000, 0),
            SpeakerSegment(2000, 4000, 0),  # Same speaker
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=4000)
        assert len(result) == 1
        assert result[0].camera_id == 0


class TestDecisionEngineDeterminism:
    """Verify deterministic output for same input."""

    def test_same_input_same_output(self) -> None:
        engine = DecisionEngine()
        segments = [
            SpeakerSegment(0, 2000, 0),
            SpeakerSegment(2000, 5000, 1),
            SpeakerSegment(5000, 8000, 0),
        ]
        result1 = engine.generate_cut_plan(segments, total_duration_ms=10000)
        result2 = engine.generate_cut_plan(segments, total_duration_ms=10000)
        assert result1 == result2

    def test_deterministic_complex_sequence(self) -> None:
        engine = DecisionEngine(min_switch_interval_ms=1000, min_speech_ms=500, bg_short_remark_ms=300)
        segments = [
            SpeakerSegment(0, 1500, 0),
            SpeakerSegment(1500, 1700, 1),  # Short, filtered
            SpeakerSegment(1700, 3500, 0),
            SpeakerSegment(3500, 5000, 1),  # Long enough
            SpeakerSegment(5000, 5200, 0),  # Short
            SpeakerSegment(5200, 7000, 1),
        ]
        result1 = engine.generate_cut_plan(segments, total_duration_ms=8000)
        result2 = engine.generate_cut_plan(segments, total_duration_ms=8000)
        assert result1 == result2


class TestDecisionEngineMergeAdjacent:
    """Test merge_adjacent helper."""

    def test_merge_same_camera(self) -> None:
        engine = DecisionEngine()
        cuts = [
            CutSegment(0, 1000, 0),
            CutSegment(1000, 2000, 0),
            CutSegment(2000, 3000, 0),
        ]
        merged = engine.merge_adjacent(cuts)
        assert len(merged) == 1
        assert merged[0] == CutSegment(0, 3000, 0)

    def test_no_merge_different_cameras(self) -> None:
        engine = DecisionEngine()
        cuts = [
            CutSegment(0, 1000, 0),
            CutSegment(1000, 2000, 1),
        ]
        merged = engine.merge_adjacent(cuts)
        assert len(merged) == 2

    def test_merge_empty_list(self) -> None:
        engine = DecisionEngine()
        merged = engine.merge_adjacent([])
        assert merged == []


class TestDecisionEngineIntegration:
    """Integration tests with realistic scenarios."""

    def test_typical_conversation(self) -> None:
        """Two speakers alternating with pauses."""
        engine = DecisionEngine()
        segments = [
            SpeakerSegment(0, 3000, 0),     # Speaker 0: 3s
            SpeakerSegment(3500, 6500, 1),  # Speaker 1: 3s (after pause)
            SpeakerSegment(7000, 10000, 0), # Speaker 0: 3s
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=12000)

        # Verify we have switches at appropriate points
        assert len(result) >= 2
        assert result[0].camera_id == 0
        # Should switch to camera 1 at 3500
        found_cam1 = any(c.camera_id == 1 for c in result)
        assert found_cam1

    def test_default_camera_custom(self) -> None:
        """Test with non-zero default camera."""
        engine = DecisionEngine(default_camera=1)
        segments = [
            SpeakerSegment(5000, 8000, 0),  # Late start
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=10000)
        # Should start with default camera 1
        assert result[0].camera_id == 1
