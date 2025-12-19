"""Decision engine: convert diarization segments into cut plan."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from .active_speaker import SpeakerSegment

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CutSegment:
    """A single cut in the edit timeline."""
    start_ms: int
    end_ms: int
    camera_id: int

    def __post_init__(self) -> None:
        if self.start_ms < 0:
            raise ValueError("start_ms must be >= 0")
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be > start_ms")
        if self.camera_id < 0:
            raise ValueError("camera_id must be >= 0")


class DecisionEngine:
    """
    Convert speaker diarization segments into a camera cut plan.

    Rules:
    - Ignore short remarks below bg_short_remark_ms
    - Require min_speech_ms of speech to trigger a cut
    - Enforce min_switch_interval_ms between camera switches
    - On uncertainty, prefer current camera
    """

    def __init__(
        self,
        min_switch_interval_ms: int = 1500,
        min_speech_ms: int = 600,
        bg_short_remark_ms: int = 500,
        default_camera: int = 0,
    ) -> None:
        self.min_switch_interval_ms = min_switch_interval_ms
        self.min_speech_ms = min_speech_ms
        self.bg_short_remark_ms = bg_short_remark_ms
        self.default_camera = default_camera

    def generate_cut_plan(
        self,
        segments: List[SpeakerSegment],
        total_duration_ms: int | None = None,
    ) -> List[CutSegment]:
        """
        Generate a cut plan from speaker segments.

        Args:
            segments: Non-overlapping, sorted speaker segments.
            total_duration_ms: Optional total duration; if provided, extends
                               the final cut to cover the full duration.

        Returns:
            List of CutSegment representing camera switches.
        """
        if not segments:
            if total_duration_ms and total_duration_ms > 0:
                return [CutSegment(0, total_duration_ms, self.default_camera)]
            return []

        # Filter out short remarks
        filtered = [s for s in segments if (s.end_ms - s.start_ms) >= self.bg_short_remark_ms]

        if not filtered:
            end = total_duration_ms if total_duration_ms else segments[-1].end_ms
            if end > 0:
                return [CutSegment(0, end, self.default_camera)]
            return []

        cuts: List[CutSegment] = []
        current_camera = self.default_camera
        last_switch_ms = 0
        cut_start_ms = 0

        for seg in filtered:
            seg_duration = seg.end_ms - seg.start_ms
            time_since_switch = seg.start_ms - last_switch_ms

            # Check if this segment warrants a camera switch
            should_switch = (
                seg.speaker_id != current_camera
                and seg_duration >= self.min_speech_ms
                and time_since_switch >= self.min_switch_interval_ms
            )

            if should_switch:
                # Close current cut if we have content
                if seg.start_ms > cut_start_ms:
                    cuts.append(CutSegment(cut_start_ms, seg.start_ms, current_camera))

                # Switch camera
                current_camera = seg.speaker_id
                cut_start_ms = seg.start_ms
                last_switch_ms = seg.start_ms

        # Close final segment
        end_ms = total_duration_ms if total_duration_ms else filtered[-1].end_ms
        if end_ms > cut_start_ms:
            cuts.append(CutSegment(cut_start_ms, end_ms, current_camera))

        return cuts

    def merge_adjacent(self, cuts: List[CutSegment]) -> List[CutSegment]:
        """Merge adjacent cuts with the same camera."""
        if not cuts:
            return []

        merged: List[CutSegment] = []
        current = cuts[0]

        for cut in cuts[1:]:
            if cut.camera_id == current.camera_id and cut.start_ms == current.end_ms:
                current = CutSegment(current.start_ms, cut.end_ms, current.camera_id)
            else:
                merged.append(current)
                current = cut

        merged.append(current)
        return merged
