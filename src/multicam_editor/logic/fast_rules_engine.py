"""FAST_RULES switching engine: rule-based camera switching on energy timelines.

This engine implements simple, fast rules for camera switching based on
precomputed per-camera energy data. Unlike LIPS or Hybrid modes, this
engine does not perform any visual or complex audio analysis.

Rules (in order of application):
1. Min switch duration: stay on camera for minimum time
2. Cooldown after switch: ignore triggers for cooldown period
3. Speech threshold: energy must exceed noise floor
4. Hysteresis: candidate must beat current by margin
5. Continuity tie-breaker: prefer last active speaker
6. Safety: if no camera qualifies, keep current
7. Smoothing: merge very short segments into neighbors
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FastRulesConfig:
    """Configuration for FAST_RULES engine with safe defaults."""
    
    # Rule 1: Minimum time on a camera before switching (seconds)
    min_switch_duration_s: float = 2.0
    
    # Rule 2: Cooldown period after a switch - ignore triggers (seconds)
    cooldown_s: float = 1.0
    
    # Rule 4: Hysteresis margin - candidate must exceed current by this ratio
    energy_margin: float = 1.3
    
    # Rule 7: Merge segments shorter than this into neighbors (seconds)
    merge_threshold_s: float = 0.6
    
    # Window size for energy computation (should match energy timeline)
    window_ms: int = 200
    
    # Default camera when no speech detected
    default_camera: int = 0
    
    def __post_init__(self) -> None:
        """Validate config values."""
        if self.min_switch_duration_s < 0:
            raise ValueError("min_switch_duration_s must be >= 0")
        if self.cooldown_s < 0:
            raise ValueError("cooldown_s must be >= 0")
        if self.energy_margin < 1.0:
            raise ValueError("energy_margin must be >= 1.0")
        if self.merge_threshold_s < 0:
            raise ValueError("merge_threshold_s must be >= 0")
        if self.window_ms <= 0:
            raise ValueError("window_ms must be > 0")


@dataclass(frozen=True)
class FastRulesCut:
    """A single camera cut from FAST_RULES engine."""
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


class FastRulesEngine:
    """
    Rule-based camera switching engine operating on energy timelines.
    
    Input: Per-camera energy values for each time window.
    Output: List of camera cuts (timeline segments).
    
    This is a pure-logic engine with no I/O or media processing.
    """
    
    def __init__(self, config: Optional[FastRulesConfig] = None) -> None:
        self.config = config or FastRulesConfig()
        logger.info(
            "FastRulesEngine initialized: min_duration=%.1fs, cooldown=%.1fs, "
            "margin=%.2f, merge=%.1fs",
            self.config.min_switch_duration_s,
            self.config.cooldown_s,
            self.config.energy_margin,
            self.config.merge_threshold_s,
        )
    
    def decide(
        self,
        energy_timeline: List[List[float]],
        window_ms: int,
        total_duration_ms: int,
    ) -> List[FastRulesCut]:
        """
        Apply rules to energy timeline and return camera cuts.
        
        Args:
            energy_timeline: energy_timeline[camera_idx][window_idx] = RMS energy
            window_ms: Duration of each window in milliseconds
            total_duration_ms: Total duration of the video in milliseconds
            
        Returns:
            List of FastRulesCut representing camera switches.
            Never returns empty list - always at least one cut on default camera.
        """
        if not energy_timeline or not energy_timeline[0]:
            logger.warning("FAST_RULES: Empty energy timeline, using default camera")
            return self._make_default_cut(total_duration_ms)
        
        num_cameras = len(energy_timeline)
        num_windows = len(energy_timeline[0])
        
        logger.info(
            "FAST_RULES: Processing %d cameras, %d windows (%dms each), total=%dms",
            num_cameras, num_windows, window_ms, total_duration_ms,
        )
        
        # Convert time thresholds to window counts
        min_duration_windows = max(1, int(self.config.min_switch_duration_s * 1000 / window_ms))
        cooldown_windows = max(1, int(self.config.cooldown_s * 1000 / window_ms))
        
        # Step 1: Determine per-window winners with rules
        window_winners = self._apply_rules(
            energy_timeline,
            num_cameras,
            num_windows,
            min_duration_windows,
            cooldown_windows,
        )
        
        # Step 2: Convert window winners to cuts
        raw_cuts = self._windows_to_cuts(window_winners, window_ms, total_duration_ms)
        
        # Step 3: Merge short segments (Rule 7)
        merged_cuts = self._merge_short_segments(raw_cuts, window_ms)
        
        # Safety: Never return empty
        if not merged_cuts:
            logger.warning("FAST_RULES: No cuts after merging, using default camera")
            return self._make_default_cut(total_duration_ms)
        
        logger.info("FAST_RULES: Generated %d cuts", len(merged_cuts))
        return merged_cuts
    
    def _apply_rules(
        self,
        energy: List[List[float]],
        num_cameras: int,
        num_windows: int,
        min_duration_windows: int,
        cooldown_windows: int,
    ) -> List[int]:
        """
        Apply switching rules window-by-window.
        
        Returns list of camera IDs, one per window.
        """
        winners: List[int] = []
        current_camera = self.config.default_camera
        windows_on_current = 0
        windows_since_switch = cooldown_windows  # Allow immediate first switch
        last_active_speaker = current_camera  # For tie-breaker
        
        for w in range(num_windows):
            # Get energy for each camera at this window
            energies = [
                energy[cam][w] if w < len(energy[cam]) else 0.0
                for cam in range(num_cameras)
            ]
            
            current_energy = energies[current_camera]
            windows_on_current += 1
            windows_since_switch += 1
            
            # Find best candidate (Rule 5: tie-breaker prefers last active)
            best_candidate = self._find_best_candidate(
                energies, current_camera, current_energy, last_active_speaker
            )
            
            # Check if we should switch
            should_switch = self._should_switch(
                best_candidate,
                current_camera,
                current_energy,
                energies[best_candidate] if best_candidate >= 0 else 0.0,
                windows_on_current,
                windows_since_switch,
                min_duration_windows,
                cooldown_windows,
            )
            
            if should_switch and best_candidate >= 0:
                logger.debug(
                    "FAST_RULES: Switch to cam%d at window %d (%.1fs)",
                    best_candidate, w, w * self.config.window_ms / 1000
                )
                last_active_speaker = current_camera
                current_camera = best_candidate
                windows_on_current = 0
                windows_since_switch = 0
            
            winners.append(current_camera)
        
        return winners
    
    def _find_best_candidate(
        self,
        energies: List[float],
        current_camera: int,
        current_energy: float,
        last_active_speaker: int,
    ) -> int:
        """
        Find best camera candidate, using tie-breaker (Rule 5).
        
        Returns camera index, or -1 if no valid candidate.
        """
        best_candidate = -1
        best_energy = 0.0
        
        for cam_idx, cam_energy in enumerate(energies):
            if cam_idx == current_camera:
                continue
            
            if cam_energy > best_energy:
                best_energy = cam_energy
                best_candidate = cam_idx
            elif cam_energy == best_energy and cam_idx == last_active_speaker:
                # Rule 5: Tie-breaker - prefer last active speaker (continuity)
                best_candidate = cam_idx
        
        return best_candidate
    
    def _should_switch(
        self,
        candidate: int,
        current_camera: int,
        current_energy: float,
        candidate_energy: float,
        windows_on_current: int,
        windows_since_switch: int,
        min_duration_windows: int,
        cooldown_windows: int,
    ) -> bool:
        """
        Check all switching rules.
        
        Rules 1, 2, 4, 6 are checked here.
        """
        # No valid candidate (Rule 6: safety)
        if candidate < 0:
            return False
        
        # Same camera
        if candidate == current_camera:
            return False
        
        # Rule 1: Min switch duration
        if windows_on_current < min_duration_windows:
            return False
        
        # Rule 2: Cooldown
        if windows_since_switch < cooldown_windows:
            return False
        
        # Rule 4: Hysteresis - candidate must exceed current by margin
        if current_energy > 0:
            ratio = candidate_energy / current_energy
            if ratio < self.config.energy_margin:
                return False
        elif candidate_energy <= 0:
            # Both silent - stay on current (Rule 6: safety)
            return False
        
        # All rules passed
        return True
    
    def _windows_to_cuts(
        self,
        window_winners: List[int],
        window_ms: int,
        total_duration_ms: int,
    ) -> List[FastRulesCut]:
        """Convert window winners to cut segments."""
        if not window_winners:
            return []
        
        cuts: List[FastRulesCut] = []
        current_camera = window_winners[0]
        segment_start_ms = 0
        
        for i, camera in enumerate(window_winners[1:], start=1):
            if camera != current_camera:
                # Close current segment
                end_ms = i * window_ms
                if end_ms > segment_start_ms:
                    cuts.append(FastRulesCut(
                        start_ms=segment_start_ms,
                        end_ms=end_ms,
                        camera_id=current_camera,
                    ))
                segment_start_ms = end_ms
                current_camera = camera
        
        # Close final segment
        end_ms = min(len(window_winners) * window_ms, total_duration_ms)
        if total_duration_ms > 0:
            end_ms = total_duration_ms
        if end_ms > segment_start_ms:
            cuts.append(FastRulesCut(
                start_ms=segment_start_ms,
                end_ms=end_ms,
                camera_id=current_camera,
            ))
        
        return cuts
    
    def _merge_short_segments(
        self,
        cuts: List[FastRulesCut],
        window_ms: int,
    ) -> List[FastRulesCut]:
        """
        Merge segments shorter than merge_threshold_s into neighbors (Rule 7).
        """
        if len(cuts) <= 1:
            return cuts
        
        merge_threshold_ms = int(self.config.merge_threshold_s * 1000)
        
        # Pass 1: Mark segments for merging
        merged: List[FastRulesCut] = []
        i = 0
        
        while i < len(cuts):
            cut = cuts[i]
            duration_ms = cut.end_ms - cut.start_ms
            
            if duration_ms < merge_threshold_ms:
                # Short segment - merge with neighbor
                if merged:
                    # Merge with previous
                    prev = merged[-1]
                    merged[-1] = FastRulesCut(
                        start_ms=prev.start_ms,
                        end_ms=cut.end_ms,
                        camera_id=prev.camera_id,
                    )
                    logger.debug(
                        "FAST_RULES: Merged short segment (cam%d, %dms) into previous",
                        cut.camera_id, duration_ms
                    )
                elif i + 1 < len(cuts):
                    # Merge with next (first segment is short)
                    next_cut = cuts[i + 1]
                    merged.append(FastRulesCut(
                        start_ms=cut.start_ms,
                        end_ms=next_cut.end_ms,
                        camera_id=next_cut.camera_id,
                    ))
                    logger.debug(
                        "FAST_RULES: Merged short first segment (cam%d, %dms) into next",
                        cut.camera_id, duration_ms
                    )
                    i += 1  # Skip next since we merged it
                else:
                    # Only one short segment - keep it
                    merged.append(cut)
            else:
                merged.append(cut)
            
            i += 1
        
        # Pass 2: Merge adjacent same-camera segments
        if len(merged) <= 1:
            return merged
        
        final: List[FastRulesCut] = [merged[0]]
        for cut in merged[1:]:
            if cut.camera_id == final[-1].camera_id:
                # Merge adjacent same-camera
                final[-1] = FastRulesCut(
                    start_ms=final[-1].start_ms,
                    end_ms=cut.end_ms,
                    camera_id=cut.camera_id,
                )
            else:
                final.append(cut)
        
        return final
    
    def _make_default_cut(self, total_duration_ms: int) -> List[FastRulesCut]:
        """Create a single cut on default camera for entire duration."""
        if total_duration_ms <= 0:
            total_duration_ms = 1  # Minimum 1ms
        return [FastRulesCut(
            start_ms=0,
            end_ms=total_duration_ms,
            camera_id=self.config.default_camera,
        )]
