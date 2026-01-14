"""Decision engine: convert diarization segments into cut plan.

Implements smoothing strategies for natural camera transitions:
- Confidence stability window: require candidate coverage for window before switching
- Minimum clip length: ensure clips meet minimum duration
- Soft boundary shift: shift cuts to silence gaps when possible
- Optional hysteresis: require threshold gap to prevent flip-flopping

CRITICAL: All checks pass BEFORE any state is modified (no side effects on rejection).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

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

    Smoothing rules (applied in order, no side effects until ALL pass):
    1. Different speaker check: candidate != current camera
    2. Min speech duration: segment >= min_speech_ms
    3. Cooldown check: time since last switch >= min_switch_interval_ms
    4. Stability window: candidate maintains coverage for confidence_stability_window_ms
    5. Hysteresis check (optional): prevents flip-flopping on close confidence
    6. Min clip length: proposed clip >= min_clip_length_ms

    After soft boundary shift, re-validate min clip length and cooldown.
    Only commit switch if ALL checks pass.
    """

    # Internal hysteresis thresholds (no UI)
    STAY_THRESHOLD = 0.55
    SWITCH_THRESHOLD = 0.65

    def __init__(
        self,
        min_switch_interval_ms: int = 1500,
        min_speech_ms: int = 600,
        bg_short_remark_ms: int = 500,
        default_camera: int = 0,
        # Smoothing parameters
        confidence_stability_window_ms: int = 400,
        min_clip_length_ms: int = 1000,
        soft_boundary_search_ms: int = 150,
        # Hysteresis (optional, enabled by default)
        hysteresis_enabled: bool = True,
    ) -> None:
        self.min_switch_interval_ms = min_switch_interval_ms
        self.min_speech_ms = min_speech_ms
        self.bg_short_remark_ms = bg_short_remark_ms
        self.default_camera = default_camera
        # Smoothing
        self.confidence_stability_window_ms = confidence_stability_window_ms
        self.min_clip_length_ms = min_clip_length_ms
        self.soft_boundary_search_ms = soft_boundary_search_ms
        self.hysteresis_enabled = hysteresis_enabled

    def _find_silence_boundary(
        self,
        target_ms: int,
        filtered_segments: List[SpeakerSegment],
        search_range_ms: int,
    ) -> int:
        """
        Find the nearest silence gap within search_range_ms of target_ms.

        Uses filtered segments (same as decision making) to find gaps.
        A gap is detected between consecutive segments where gap > 0.
        Returns target_ms if no suitable gap is found (never fails).

        Args:
            target_ms: The proposed cut point
            filtered_segments: Segments already filtered by bg_short_remark_ms
            search_range_ms: Maximum distance to search (±)

        Returns:
            Best gap point within range, or target_ms if none found.
        """
        if search_range_ms <= 0 or not filtered_segments:
            return target_ms

        best_gap_point: Optional[int] = None
        best_distance = search_range_ms + 1

        # Search for gaps between consecutive segments
        for i in range(len(filtered_segments) - 1):
            gap_start = filtered_segments[i].end_ms
            gap_end = filtered_segments[i + 1].start_ms

            if gap_end <= gap_start:
                continue  # No actual gap (contiguous or overlapping)

            # Prefer the start of the gap (end of previous speech)
            # as this is the most reliable silence indicator
            gap_point = gap_start

            distance = abs(gap_point - target_ms)
            if distance <= search_range_ms and distance < best_distance:
                best_distance = distance
                best_gap_point = gap_point

        return best_gap_point if best_gap_point is not None else target_ms

    def _compute_coverage_in_window(
        self,
        speaker_id: int,
        window_start_ms: int,
        window_end_ms: int,
        segments: List[SpeakerSegment],
    ) -> Tuple[int, int]:
        """
        Compute coverage for a speaker within a time window.

        Returns:
            (speaker_coverage_ms, total_speech_ms) - coverage of candidate
            and total speech from all speakers in the window.
        """
        speaker_coverage = 0
        total_coverage = 0

        for seg in segments:
            if seg.end_ms <= window_start_ms or seg.start_ms >= window_end_ms:
                continue
            # Overlap with window
            overlap_start = max(seg.start_ms, window_start_ms)
            overlap_end = min(seg.end_ms, window_end_ms)
            overlap_ms = overlap_end - overlap_start

            total_coverage += overlap_ms
            if seg.speaker_id == speaker_id:
                speaker_coverage += overlap_ms

        return speaker_coverage, total_coverage

    def _check_stability_window(
        self,
        candidate_speaker: int,
        switch_time_ms: int,
        segments: List[SpeakerSegment],
    ) -> Tuple[bool, float]:
        """
        Verify candidate speaker has sufficient coverage in stability window.

        Measures candidate coverage (not dominance over others) within the
        window [switch_time_ms, switch_time_ms + confidence_stability_window_ms].

        Returns:
            (is_stable, coverage_ratio) - stability result and ratio for hysteresis
        """
        if self.confidence_stability_window_ms <= 0:
            return True, 1.0  # Disabled

        window_end = switch_time_ms + self.confidence_stability_window_ms

        candidate_ms, total_ms = self._compute_coverage_in_window(
            candidate_speaker, switch_time_ms, window_end, segments
        )

        # Require at least 60% candidate coverage of the window
        # (lower than before to be less aggressive, hysteresis handles edge cases)
        window_duration = self.confidence_stability_window_ms
        coverage_ratio = candidate_ms / window_duration if window_duration > 0 else 0

        # Candidate coverage threshold: 60% of window
        is_stable = coverage_ratio >= 0.60

        return is_stable, coverage_ratio

    def _check_hysteresis(
        self,
        candidate_coverage: float,
        current_speaker: int,
        switch_time_ms: int,
        segments: List[SpeakerSegment],
    ) -> bool:
        """
        Apply hysteresis to prevent flip-flopping on close confidence.

        Rule: switch only if candidate >= SWITCH_THRESHOLD AND
              current speaker coverage <= STAY_THRESHOLD

        If hysteresis is disabled, always returns True.
        """
        if not self.hysteresis_enabled:
            return True

        if self.confidence_stability_window_ms <= 0:
            return True  # Can't check without window

        # Check if candidate exceeds switch threshold
        if candidate_coverage < self.SWITCH_THRESHOLD:
            logger.debug(
                "Hysteresis: candidate coverage %.2f < switch threshold %.2f",
                candidate_coverage, self.SWITCH_THRESHOLD
            )
            return False

        # Check current speaker's coverage in the same window
        window_end = switch_time_ms + self.confidence_stability_window_ms
        current_ms, _ = self._compute_coverage_in_window(
            current_speaker, switch_time_ms, window_end, segments
        )
        current_ratio = current_ms / self.confidence_stability_window_ms

        # Only switch if current speaker is below stay threshold
        if current_ratio > self.STAY_THRESHOLD:
            logger.debug(
                "Hysteresis: current speaker coverage %.2f > stay threshold %.2f",
                current_ratio, self.STAY_THRESHOLD
            )
            return False

        return True

    def _evaluate_switch_candidate(
        self,
        seg: SpeakerSegment,
        current_camera: int,
        cut_start_ms: int,
        last_switch_ms: int,
        filtered_segments: List[SpeakerSegment],
    ) -> Tuple[bool, str, float]:
        """
        Evaluate a potential switch without any side effects.

        Returns:
            (should_switch, rejection_reason, candidate_coverage)
            - should_switch: True if ALL checks pass
            - rejection_reason: Empty string if passed, else reason for rejection
            - candidate_coverage: Coverage ratio from stability check (for hysteresis)
        """
        candidate_time = seg.start_ms
        seg_duration = seg.end_ms - seg.start_ms

        # Check 1: Different speaker
        if seg.speaker_id == current_camera:
            return False, "same_speaker", 0.0

        # Check 2: Min speech duration
        if seg_duration < self.min_speech_ms:
            return False, "min_speech", 0.0

        # Check 3: Cooldown (min switch interval)
        time_since_switch = candidate_time - last_switch_ms
        if time_since_switch < self.min_switch_interval_ms:
            return False, "cooldown", 0.0

        # Check 4: Stability window (candidate coverage)
        is_stable, coverage_ratio = self._check_stability_window(
            seg.speaker_id, candidate_time, filtered_segments
        )
        if not is_stable:
            return False, "stability", coverage_ratio

        # Check 5: Hysteresis (optional)
        if not self._check_hysteresis(
            coverage_ratio, current_camera, candidate_time, filtered_segments
        ):
            return False, "hysteresis", coverage_ratio

        # Check 6: Min clip length
        proposed_clip_length = candidate_time - cut_start_ms
        if proposed_clip_length < self.min_clip_length_ms:
            return False, "min_clip_length", coverage_ratio

        # All checks passed
        return True, "", coverage_ratio

    def generate_cut_plan(
        self,
        segments: List[SpeakerSegment],
        total_duration_ms: int | None = None,
    ) -> List[CutSegment]:
        """
        Generate a cut plan from speaker segments with smoothing.

        CRITICAL: No state is modified until ALL checks pass for a switch.
        If any check fails, no cut is closed, no camera updated, no timestamps changed.

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

        # Filter out short remarks - used for ALL decision making
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
            # PHASE 1: Evaluate switch candidate (no side effects)
            should_switch, rejection_reason, _ = self._evaluate_switch_candidate(
                seg, current_camera, cut_start_ms, last_switch_ms, filtered
            )

            if not should_switch:
                if rejection_reason and rejection_reason not in ("same_speaker",):
                    logger.debug(
                        "Switch to camera %d at %dms rejected: %s",
                        seg.speaker_id, seg.start_ms, rejection_reason
                    )
                # CRITICAL: No state modified - just continue
                continue

            # PHASE 2: Determine cut point with optional soft boundary shift
            cut_point = seg.start_ms

            if self.soft_boundary_search_ms > 0:
                shifted = self._find_silence_boundary(
                    cut_point, filtered, self.soft_boundary_search_ms
                )
                if shifted != cut_point:
                    logger.debug(
                        "Soft boundary shift: %dms -> %dms", cut_point, shifted
                    )
                    cut_point = shifted

            # PHASE 3: Re-validate after shift (may have changed constraints)
            # Check min clip length with new cut point
            if cut_point - cut_start_ms < self.min_clip_length_ms:
                logger.debug(
                    "Post-shift rejection: clip length %dms < min %dms",
                    cut_point - cut_start_ms, self.min_clip_length_ms
                )
                continue

            # Check cooldown with new cut point
            if cut_point - last_switch_ms < self.min_switch_interval_ms:
                logger.debug(
                    "Post-shift rejection: cooldown %dms < min %dms",
                    cut_point - last_switch_ms, self.min_switch_interval_ms
                )
                continue

            # Ensure cut point is valid (after cut_start, before end)
            if cut_point <= cut_start_ms:
                logger.debug(
                    "Post-shift rejection: cut_point %dms <= cut_start %dms",
                    cut_point, cut_start_ms
                )
                continue

            # PHASE 4: COMMIT - All checks passed, now modify state
            cuts.append(CutSegment(cut_start_ms, cut_point, current_camera))
            current_camera = seg.speaker_id
            cut_start_ms = cut_point
            last_switch_ms = cut_point

            logger.debug(
                "Committed switch to camera %d at %dms",
                current_camera, cut_point
            )

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
