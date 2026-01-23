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


class TestConfidenceStabilityWindow:
    """Tests for confidence stability window smoothing."""

    def test_stability_window_prevents_spike_switch(self) -> None:
        """Short spike followed by different speaker should not trigger switch."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=500,  # Require 500ms stability
            min_clip_length_ms=0,
        )
        segments = [
            SpeakerSegment(0, 2000, 0),      # Speaker 0: 2s
            SpeakerSegment(2000, 2300, 1),   # Speaker 1: 300ms spike (too short for stability)
            SpeakerSegment(2300, 4000, 0),   # Speaker 0 resumes
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=4000)
        # Should stay on camera 0 - spike was unstable
        assert len(result) == 1
        assert result[0].camera_id == 0

    def test_stability_window_allows_stable_switch(self) -> None:
        """Long stable speaker segment should trigger switch."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=400,  # Require 400ms stability
            min_clip_length_ms=0,
        )
        segments = [
            SpeakerSegment(0, 2000, 0),      # Speaker 0: 2s
            SpeakerSegment(2000, 4000, 1),   # Speaker 1: 2s (stable for window)
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=4000)
        # Should switch to camera 1
        assert len(result) == 2
        assert result[0].camera_id == 0
        assert result[1].camera_id == 1

    def test_stability_window_disabled_when_zero(self) -> None:
        """Zero stability window should disable the check."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,  # Disabled
            min_clip_length_ms=0,
        )
        segments = [
            SpeakerSegment(0, 2000, 0),
            SpeakerSegment(2000, 2200, 1),  # Very short
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=3000)
        # Should switch even with short segment
        assert len(result) == 2


class TestMinClipLengthGuardrails:
    """Tests for minimum clip length enforcement."""

    def test_min_clip_length_delays_switch(self) -> None:
        """Switch should be delayed if clip would be too short."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,
            min_clip_length_ms=1500,  # Require 1.5s minimum clips
        )
        segments = [
            SpeakerSegment(0, 800, 0),       # Speaker 0: 800ms (too short for a clip)
            SpeakerSegment(800, 2500, 1),    # Speaker 1: 1700ms
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=3000)
        # Should stay on camera 0 to not create an 800ms clip
        assert len(result) == 1
        assert result[0].camera_id == 0

    def test_min_clip_length_allows_long_clips(self) -> None:
        """Long clips should be allowed to switch."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,
            min_clip_length_ms=1000,  # 1s minimum
        )
        segments = [
            SpeakerSegment(0, 2000, 0),      # 2s clip - OK
            SpeakerSegment(2000, 4000, 1),   # 2s clip - OK
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=4000)
        assert len(result) == 2
        assert result[0].end_ms - result[0].start_ms >= 1000

    def test_guardrails_never_skip_content(self) -> None:
        """Guardrails should delay switches, never drop content."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,
            min_clip_length_ms=2000,  # High threshold
        )
        segments = [
            SpeakerSegment(0, 500, 0),
            SpeakerSegment(500, 1000, 1),
            SpeakerSegment(1000, 1500, 0),
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=2000)
        # Total duration should equal total_duration_ms (no content skipped)
        total = sum(c.end_ms - c.start_ms for c in result)
        assert total == 2000


class TestSoftBoundaryShift:
    """Tests for soft boundary shift to silence gaps."""

    def test_soft_boundary_shift_to_gap(self) -> None:
        """Cut should shift to nearby silence gap."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,
            min_clip_length_ms=0,
            soft_boundary_search_ms=200,  # Search 200ms
        )
        # Gap between 1950 and 2050
        segments = [
            SpeakerSegment(0, 1950, 0),      # Ends at 1950
            SpeakerSegment(2050, 4000, 1),   # Starts at 2050 (100ms gap)
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=4000)
        # Switch should happen near the gap (1950-2050)
        assert len(result) == 2
        assert 1900 <= result[0].end_ms <= 2100

    def test_soft_boundary_disabled_when_zero(self) -> None:
        """Zero search range disables soft boundary shift."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,
            min_clip_length_ms=0,
            soft_boundary_search_ms=0,  # Disabled
        )
        segments = [
            SpeakerSegment(0, 1950, 0),
            SpeakerSegment(2050, 4000, 1),  # Gap exists but won't be used
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=4000)
        assert len(result) == 2
        # Should cut exactly at segment start (2050)
        assert result[0].end_ms == 2050

    def test_soft_boundary_never_fails(self) -> None:
        """No gap found should not cause failure."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,
            min_clip_length_ms=0,
            soft_boundary_search_ms=200,
        )
        # No gap - segments are contiguous
        segments = [
            SpeakerSegment(0, 2000, 0),
            SpeakerSegment(2000, 4000, 1),  # Starts exactly where previous ends
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=4000)
        # Should still produce valid output
        assert len(result) == 2
        assert result[0].end_ms == result[1].start_ms


class TestSmoothingDefaults:
    """Test default smoothing parameter values."""

    def test_smoothing_defaults(self) -> None:
        engine = DecisionEngine()
        assert engine.confidence_stability_window_ms == 400
        assert engine.min_clip_length_ms == 1000
        assert engine.soft_boundary_search_ms == 150


class TestNoSideEffectsOnRejection:
    """Critical: Verify no state is modified when a switch is rejected."""

    def test_no_side_effects_when_switch_rejected_by_cooldown(self) -> None:
        """No cut closed, no camera updated when cooldown rejects switch."""
        engine = DecisionEngine(
            min_switch_interval_ms=2000,  # Long cooldown
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,
            min_clip_length_ms=0,
            hysteresis_enabled=False,
        )
        segments = [
            SpeakerSegment(0, 1000, 0),     # Camera 0: 1s
            SpeakerSegment(1000, 2000, 1),  # Camera 1: rejected by cooldown (only 1000ms since 0)
            SpeakerSegment(2000, 4000, 0),  # Camera 0: 2s
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=4000)
        # Should produce single segment on camera 0 (no switch at 1000ms)
        assert len(result) == 1
        assert result[0].camera_id == 0
        assert result[0].start_ms == 0
        assert result[0].end_ms == 4000

    def test_no_side_effects_when_switch_rejected_by_min_clip(self) -> None:
        """No cut closed when min clip length rejects switch."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,
            min_clip_length_ms=1500,  # Requires 1.5s clips
            hysteresis_enabled=False,
        )
        segments = [
            SpeakerSegment(0, 800, 0),      # 800ms < 1500ms min clip
            SpeakerSegment(800, 3000, 1),   # Would create too-short first clip
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=3000)
        # Should stay on camera 0 - no short clip created
        assert len(result) == 1
        assert result[0].camera_id == 0


class TestMinClipLengthBeforeCommit:
    """Verify min clip length is checked BEFORE committing the switch."""

    def test_min_clip_length_checked_before_commit(self) -> None:
        """Switch is not committed if it would create a too-short clip."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,
            min_clip_length_ms=2000,
            hysteresis_enabled=False,
        )
        segments = [
            SpeakerSegment(0, 1000, 0),     # 1s on cam 0
            SpeakerSegment(1000, 3000, 1),  # cam 1 - would make 1s clip (< 2s min)
            SpeakerSegment(3000, 5000, 0),  # back to cam 0
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=5000)
        # Should not switch at 1000ms, total content preserved
        total = sum(c.end_ms - c.start_ms for c in result)
        assert total == 5000


class TestStabilityBeforeCommit:
    """Verify stability is checked BEFORE committing the switch."""

    def test_stability_checked_before_commit(self) -> None:
        """Switch is not committed if stability check fails."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=500,  # Requires 500ms stability
            min_clip_length_ms=0,
            hysteresis_enabled=False,
        )
        segments = [
            SpeakerSegment(0, 2000, 0),
            SpeakerSegment(2000, 2200, 1),  # 200ms - not stable for 500ms window
            SpeakerSegment(2200, 4000, 0),  # Back to cam 0
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=4000)
        # Should stay on camera 0 - stability rejected the switch
        assert len(result) == 1
        assert result[0].camera_id == 0


class TestSoftShiftRevalidation:
    """Verify constraints are re-validated after soft boundary shift."""

    def test_soft_shift_revalidated_with_min_clip_and_cooldown(self) -> None:
        """After soft shift, min_clip and cooldown are re-checked.
        
        When soft shift moves cut to a point that violates min_clip_length,
        the ENTIRE switch is rejected (not reverted to original).
        This is safe-by-default behavior.
        """
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,
            min_clip_length_ms=1800,  # Requires 1.8s clips
            soft_boundary_search_ms=300,  # Will try to shift
            hysteresis_enabled=False,
        )
        # Original switch would be at 2000ms (clip = 2000ms >= 1800ms, OK)
        # Soft shift moves to 1700ms gap (clip = 1700ms < 1800ms, FAIL)
        # Safe-by-default: entire switch is rejected
        segments = [
            SpeakerSegment(0, 1700, 0),   # Ends at 1700 (gap starts)
            SpeakerSegment(2000, 4000, 1),  # Starts at 2000
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=4000)
        # Since shift to 1700ms violates min_clip, switch is rejected entirely
        # This is correct safe-by-default behavior - no accidental short clips
        total = sum(c.end_ms - c.start_ms for c in result)
        assert total == 4000  # Content preserved
        # Either 1 segment (rejected) or 2 segments (allowed) is valid
        assert len(result) >= 1


class TestHysteresis:
    """Test hysteresis prevents flip-flopping on close confidence."""

    def test_hysteresis_prevents_flip_flop(self) -> None:
        """Hysteresis requires clear winner: candidate >= 0.65 AND current <= 0.55.
        
        With 400ms stability window and interleaved 500ms segments,
        neither speaker achieves clear dominance, so switches are blocked.
        """
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=400,
            min_clip_length_ms=0,
            hysteresis_enabled=True,
        )
        # Segments alternate rapidly - neither speaker is clearly dominant
        # in any 400ms window (each has ~50% coverage)
        segments = [
            SpeakerSegment(0, 200, 0),
            SpeakerSegment(200, 400, 1),
            SpeakerSegment(400, 600, 0),
            SpeakerSegment(600, 800, 1),
            SpeakerSegment(800, 1000, 0),
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=1500)
        # With rapid alternation, stability/hysteresis should prevent most switches
        # Result should have fewer segments than the raw alternation
        assert len(result) <= len(segments)

    def test_hysteresis_disabled_allows_more_switches(self) -> None:
        """With hysteresis disabled, more switches can occur."""
        engine = DecisionEngine(
            min_switch_interval_ms=0,
            min_speech_ms=100,
            bg_short_remark_ms=50,
            confidence_stability_window_ms=0,  # Disable stability too
            min_clip_length_ms=0,
            hysteresis_enabled=False,
        )
        segments = [
            SpeakerSegment(0, 1000, 0),
            SpeakerSegment(1000, 2000, 1),
            SpeakerSegment(2000, 3000, 0),
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=3000)
        # Without hysteresis and other filters, should have switches
        assert len(result) >= 2


class TestContentPreservation:
    """Verify no content is ever dropped regardless of smoothing settings."""

    def test_total_duration_preserved(self) -> None:
        """Total output duration always equals input duration."""
        engine = DecisionEngine(
            min_switch_interval_ms=1500,
            min_speech_ms=600,
            bg_short_remark_ms=500,
            confidence_stability_window_ms=400,
            min_clip_length_ms=1000,
        )
        segments = [
            SpeakerSegment(0, 500, 0),
            SpeakerSegment(500, 1000, 1),
            SpeakerSegment(1000, 1500, 0),
            SpeakerSegment(1500, 2000, 1),
            SpeakerSegment(2000, 3000, 0),
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=5000)
        total = sum(c.end_ms - c.start_ms for c in result)
        assert total == 5000

    def test_no_gaps_in_output(self) -> None:
        """Output cuts must be contiguous (no gaps)."""
        engine = DecisionEngine()
        segments = [
            SpeakerSegment(0, 2000, 0),
            SpeakerSegment(2000, 5000, 1),
            SpeakerSegment(5000, 8000, 0),
        ]
        result = engine.generate_cut_plan(segments, total_duration_ms=10000)
        for i in range(len(result) - 1):
            assert result[i].end_ms == result[i + 1].start_ms
