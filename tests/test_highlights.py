"""
Tests for highlights timeline data structures.
"""

import pytest

from multicam_editor.logic.highlights import (
    HighlightReason,
    HighlightSegment,
    HighlightsTimeline,
    compute_highlights_stub,
)


class TestHighlightSegment:
    """Tests for HighlightSegment dataclass."""
    
    def test_create_basic_segment(self) -> None:
        """Create a basic highlight segment."""
        seg = HighlightSegment(start_s=10.0, end_s=15.0)
        assert seg.start_s == 10.0
        assert seg.end_s == 15.0
        assert seg.score == 0.5  # default
        assert seg.reasons == []
    
    def test_segment_duration(self) -> None:
        """Duration property calculates correctly."""
        seg = HighlightSegment(start_s=5.0, end_s=12.5)
        assert seg.duration_s == 7.5
    
    def test_segment_with_reasons(self) -> None:
        """Segment can have multiple reasons."""
        seg = HighlightSegment(
            start_s=0.0,
            end_s=5.0,
            score=0.9,
            reasons=[HighlightReason.HIGH_ENERGY, HighlightReason.SPEAKER_CHANGE],
        )
        assert len(seg.reasons) == 2
        assert HighlightReason.HIGH_ENERGY in seg.reasons
    
    def test_invalid_start_raises(self) -> None:
        """Negative start time raises ValueError."""
        with pytest.raises(ValueError, match="start_s must be >= 0"):
            HighlightSegment(start_s=-1.0, end_s=5.0)
    
    def test_end_before_start_raises(self) -> None:
        """End before start raises ValueError."""
        with pytest.raises(ValueError, match="end_s .* must be >= start_s"):
            HighlightSegment(start_s=10.0, end_s=5.0)
    
    def test_invalid_score_raises(self) -> None:
        """Score outside [0, 1] raises ValueError."""
        with pytest.raises(ValueError, match="score must be in"):
            HighlightSegment(start_s=0.0, end_s=5.0, score=1.5)


class TestHighlightsTimeline:
    """Tests for HighlightsTimeline dataclass."""
    
    def test_empty_timeline(self) -> None:
        """Empty timeline by default."""
        timeline = HighlightsTimeline()
        assert timeline.is_empty()
        assert len(timeline) == 0
    
    def test_add_segment(self) -> None:
        """Add segments to timeline."""
        timeline = HighlightsTimeline()
        seg = HighlightSegment(start_s=10.0, end_s=15.0, score=0.8)
        timeline.add_segment(seg)
        
        assert len(timeline) == 1
        assert not timeline.is_empty()
    
    def test_segments_sorted_by_start(self) -> None:
        """Segments are kept sorted by start time."""
        timeline = HighlightsTimeline()
        timeline.add_segment(HighlightSegment(start_s=20.0, end_s=25.0))
        timeline.add_segment(HighlightSegment(start_s=5.0, end_s=10.0))
        timeline.add_segment(HighlightSegment(start_s=12.0, end_s=15.0))
        
        assert timeline.segments[0].start_s == 5.0
        assert timeline.segments[1].start_s == 12.0
        assert timeline.segments[2].start_s == 20.0
    
    def test_total_duration(self) -> None:
        """Total highlight duration sums segments."""
        timeline = HighlightsTimeline()
        timeline.add_segment(HighlightSegment(start_s=0.0, end_s=5.0))    # 5s
        timeline.add_segment(HighlightSegment(start_s=10.0, end_s=12.0))  # 2s
        
        assert timeline.total_highlight_duration_s() == 7.0
    
    def test_get_top_highlights(self) -> None:
        """Get top N highlights by score."""
        timeline = HighlightsTimeline()
        timeline.add_segment(HighlightSegment(start_s=0.0, end_s=5.0, score=0.3))
        timeline.add_segment(HighlightSegment(start_s=10.0, end_s=15.0, score=0.9))
        timeline.add_segment(HighlightSegment(start_s=20.0, end_s=25.0, score=0.6))
        
        top = timeline.get_top_highlights(n=2)
        assert len(top) == 2
        assert top[0].score == 0.9
        assert top[1].score == 0.6


class TestComputeHighlightsStub:
    """Tests for compute_highlights_stub function."""
    
    def test_returns_empty_timeline(self) -> None:
        """Stub returns empty HighlightsTimeline."""
        result = compute_highlights_stub()
        
        assert isinstance(result, HighlightsTimeline)
        assert result.is_empty()
    
    def test_preserves_duration(self) -> None:
        """Stub preserves video duration."""
        result = compute_highlights_stub(video_duration_s=120.5)
        
        assert result.source_duration_s == 120.5
    
    def test_accepts_optional_args(self) -> None:
        """Stub accepts optional arguments without error."""
        result = compute_highlights_stub(
            speaker_segments=[],
            audio_path="/fake/path.wav",
            video_duration_s=60.0,
        )
        
        assert result.is_empty()
        assert result.version == "1.0"


class TestHighlightReason:
    """Tests for HighlightReason enum."""
    
    def test_reason_values(self) -> None:
        """All expected reason values exist."""
        assert HighlightReason.HIGH_ENERGY.value == "high_energy"
        assert HighlightReason.SPEAKER_CHANGE.value == "speaker_change"
        assert HighlightReason.KEYWORD.value == "keyword"
        assert HighlightReason.EMOTION.value == "emotion"
        assert HighlightReason.VISUAL_ACTION.value == "visual_action"
        assert HighlightReason.USER_MARKED.value == "user_marked"
