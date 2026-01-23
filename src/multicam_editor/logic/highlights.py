"""
Highlights Timeline data structures for Teaser Cutting feature.

This module provides infrastructure for identifying and storing
highlight moments in video content for automated teaser generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class HighlightReason(Enum):
    """Reason tags for why a segment is marked as a highlight."""
    HIGH_ENERGY = "high_energy"           # High audio energy / excitement
    SPEAKER_CHANGE = "speaker_change"     # Camera switch moment
    KEYWORD = "keyword"                   # Detected keyword/phrase
    EMOTION = "emotion"                   # Emotional peak detected
    VISUAL_ACTION = "visual_action"       # Visual motion/action
    USER_MARKED = "user_marked"           # Manually marked by user


@dataclass
class HighlightSegment:
    """A single highlighted segment in the timeline.
    
    Attributes:
        start_s: Start timestamp in seconds.
        end_s: End timestamp in seconds.
        score: Confidence/importance score (0.0 to 1.0).
        reasons: List of reasons why this is a highlight.
        metadata: Optional additional metadata.
    """
    start_s: float
    end_s: float
    score: float = 0.5
    reasons: List[HighlightReason] = field(default_factory=list)
    metadata: Optional[dict] = None
    
    @property
    def duration_s(self) -> float:
        """Duration of the highlight in seconds."""
        return self.end_s - self.start_s
    
    def __post_init__(self) -> None:
        """Validate segment data."""
        if self.start_s < 0:
            raise ValueError(f"start_s must be >= 0, got {self.start_s}")
        if self.end_s < self.start_s:
            raise ValueError(f"end_s ({self.end_s}) must be >= start_s ({self.start_s})")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be in [0.0, 1.0], got {self.score}")


@dataclass
class HighlightsTimeline:
    """A collection of highlight segments for teaser generation.
    
    This is the main data structure for storing identified highlight
    moments that can be used to generate video teasers.
    
    Attributes:
        segments: List of highlight segments, sorted by start time.
        source_duration_s: Total duration of source video in seconds.
        version: Schema version for future compatibility.
    """
    segments: List[HighlightSegment] = field(default_factory=list)
    source_duration_s: float = 0.0
    version: str = "1.0"
    
    def __len__(self) -> int:
        """Number of highlight segments."""
        return len(self.segments)
    
    def is_empty(self) -> bool:
        """Check if timeline has no highlights."""
        return len(self.segments) == 0
    
    def total_highlight_duration_s(self) -> float:
        """Sum of all highlight segment durations."""
        return sum(seg.duration_s for seg in self.segments)
    
    def get_top_highlights(self, n: int = 5) -> List[HighlightSegment]:
        """Get top N highlights by score.
        
        Args:
            n: Number of highlights to return.
            
        Returns:
            List of top N segments sorted by score (descending).
        """
        return sorted(self.segments, key=lambda s: s.score, reverse=True)[:n]
    
    def add_segment(self, segment: HighlightSegment) -> None:
        """Add a highlight segment and maintain sorted order.
        
        Args:
            segment: The highlight segment to add.
        """
        self.segments.append(segment)
        self.segments.sort(key=lambda s: s.start_s)


def compute_highlights_stub(
    speaker_segments: list = None,
    audio_path: str = None,
    video_duration_s: float = 0.0,
) -> HighlightsTimeline:
    """Stub function for highlight computation.
    
    This is a placeholder that returns an empty highlights timeline.
    Actual implementation will be added in future versions.
    
    Args:
        speaker_segments: Optional list of speaker segments (not used yet).
        audio_path: Optional path to audio file (not used yet).
        video_duration_s: Total video duration in seconds.
        
    Returns:
        Empty HighlightsTimeline ready for future population.
    """
    logger.debug("compute_highlights_stub called (returning empty timeline)")
    return HighlightsTimeline(
        segments=[],
        source_duration_s=video_duration_s,
        version="1.0",
    )
