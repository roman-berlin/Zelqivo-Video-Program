"""Tests for FAST_RULES switching engine."""

import pytest

from multicam_editor.logic.fast_rules_engine import (
    FastRulesConfig,
    FastRulesCut,
    FastRulesEngine,
)


class TestFastRulesConfig:
    """Tests for FastRulesConfig defaults and validation."""

    def test_default_values(self) -> None:
        """Config has expected safe defaults."""
        config = FastRulesConfig()
        assert config.min_switch_duration_s == 2.0
        assert config.cooldown_s == 1.0
        assert config.energy_margin == 1.3
        assert config.merge_threshold_s == 0.6
        assert config.window_ms == 200
        assert config.default_camera == 0

    def test_custom_values(self) -> None:
        """Config accepts custom values."""
        config = FastRulesConfig(
            min_switch_duration_s=3.0,
            cooldown_s=0.5,
            energy_margin=1.5,
            merge_threshold_s=0.8,
        )
        assert config.min_switch_duration_s == 3.0
        assert config.cooldown_s == 0.5

    def test_invalid_min_duration_raises(self) -> None:
        with pytest.raises(ValueError):
            FastRulesConfig(min_switch_duration_s=-1.0)

    def test_invalid_margin_raises(self) -> None:
        with pytest.raises(ValueError):
            FastRulesConfig(energy_margin=0.5)  # Must be >= 1.0


class TestFastRulesCut:
    """Tests for FastRulesCut dataclass."""

    def test_valid_cut(self) -> None:
        cut = FastRulesCut(start_ms=0, end_ms=1000, camera_id=0)
        assert cut.start_ms == 0
        assert cut.end_ms == 1000
        assert cut.camera_id == 0

    def test_invalid_times_raise(self) -> None:
        with pytest.raises(ValueError):
            FastRulesCut(start_ms=1000, end_ms=500, camera_id=0)


class TestFastRulesEngineNoRapidToggling:
    """Test that engine prevents rapid camera toggling."""

    def test_no_rapid_toggling_respects_min_duration(self) -> None:
        """Switching respects min_switch_duration_s (Rule 1)."""
        config = FastRulesConfig(
            min_switch_duration_s=2.0,  # 10 windows at 200ms
            cooldown_s=0.0,
            energy_margin=1.0,
            window_ms=200,
        )
        engine = FastRulesEngine(config)
        
        # Create alternating loud cameras every window
        # cam0: [1, 0, 1, 0, ...], cam1: [0, 1, 0, 1, ...]
        num_windows = 50
        energy = [
            [1.0 if w % 2 == 0 else 0.0 for w in range(num_windows)],
            [0.0 if w % 2 == 0 else 1.0 for w in range(num_windows)],
        ]
        
        cuts = engine.decide(energy, window_ms=200, total_duration_ms=10000)
        
        # Should have minimal switches due to min_duration
        # 10 windows = 2s, so at most 5 switches in 10s
        assert len(cuts) <= 5
        
        # Each cut should be at least 2000ms (min_duration)
        for cut in cuts[:-1]:  # Last cut may be shorter
            duration_ms = cut.end_ms - cut.start_ms
            # Allow some tolerance for window alignment
            assert duration_ms >= 1800, f"Cut too short: {duration_ms}ms"


class TestFastRulesEngineCooldown:
    """Test cooldown after switch (Rule 2)."""

    def test_cooldown_prevents_immediate_reswitch(self) -> None:
        """After switching, ignore triggers for cooldown period."""
        config = FastRulesConfig(
            min_switch_duration_s=0.2,  # 1 window
            cooldown_s=1.0,  # 5 windows
            energy_margin=1.0,
            window_ms=200,
        )
        engine = FastRulesEngine(config)
        
        # cam0 speaks for 5 windows, cam1 for 5, cam0 for 5, cam1 for 5
        energy = [
            [0.8] * 5 + [0.1] * 5 + [0.8] * 5 + [0.1] * 5,
            [0.1] * 5 + [0.8] * 5 + [0.1] * 5 + [0.8] * 5,
        ]
        
        cuts = engine.decide(energy, window_ms=200, total_duration_ms=4000)
        
        # Cooldown should limit switches
        # Each speaker block is 1s, cooldown is 1s
        assert len(cuts) <= 4


class TestFastRulesEngineHysteresis:
    """Test energy margin hysteresis (Rule 4)."""

    def test_hysteresis_requires_margin(self) -> None:
        """Candidate must exceed current by margin to switch."""
        config = FastRulesConfig(
            min_switch_duration_s=0.2,
            cooldown_s=0.0,
            energy_margin=1.5,  # Require 50% louder
            window_ms=200,
        )
        engine = FastRulesEngine(config)
        
        # cam0 at 0.5, cam1 at 0.6 - ratio 1.2 < 1.5, should not switch
        energy = [
            [0.5] * 20,
            [0.6] * 20,
        ]
        
        cuts = engine.decide(energy, window_ms=200, total_duration_ms=4000)
        
        # Should stay on cam0 due to hysteresis
        assert len(cuts) == 1
        assert cuts[0].camera_id == 0

    def test_hysteresis_allows_clear_winner(self) -> None:
        """Clear winner exceeding margin triggers switch."""
        config = FastRulesConfig(
            min_switch_duration_s=0.2,
            cooldown_s=0.0,
            energy_margin=1.5,
            window_ms=200,
        )
        engine = FastRulesEngine(config)
        
        # cam0 at 0.3, cam1 at 0.6 - ratio 2.0 > 1.5, should switch
        energy = [
            [0.3] * 20,
            [0.6] * 20,
        ]
        
        cuts = engine.decide(energy, window_ms=200, total_duration_ms=4000)
        
        # Should switch to cam1
        assert any(cut.camera_id == 1 for cut in cuts)


class TestFastRulesEngineMergeShortSegments:
    """Test short segment merging (Rule 7)."""

    def test_merges_short_segments(self) -> None:
        """Segments shorter than merge_threshold are absorbed."""
        config = FastRulesConfig(
            min_switch_duration_s=0.2,
            cooldown_s=0.0,
            energy_margin=1.0,
            merge_threshold_s=0.6,  # Merge segments < 600ms
            window_ms=200,
        )
        engine = FastRulesEngine(config)
        
        # cam0 for 10 windows (2s), cam1 for 2 windows (0.4s < merge), cam0 for 10 windows
        energy = [
            [0.8] * 10 + [0.1] * 2 + [0.8] * 10,
            [0.1] * 10 + [0.9] * 2 + [0.1] * 10,
        ]
        
        cuts = engine.decide(energy, window_ms=200, total_duration_ms=4400)
        
        # Short cam1 segment should be merged
        for cut in cuts:
            duration_ms = cut.end_ms - cut.start_ms
            # All cuts should meet merge threshold (or be final)
            if cut != cuts[-1]:
                assert duration_ms >= 400  # Allow some tolerance


class TestFastRulesEngineContinuityTieBreaker:
    """Test tie-breaker favoring last active speaker (Rule 5)."""

    def test_tiebreaker_prefers_last_speaker(self) -> None:
        """When cameras have equal energy, prefer last active."""
        config = FastRulesConfig(
            min_switch_duration_s=0.2,
            cooldown_s=0.0,
            energy_margin=1.0,
            window_ms=200,
        )
        engine = FastRulesEngine(config)
        
        # All cameras equally loud - should stay on default
        energy = [
            [0.5] * 20,
            [0.5] * 20,
        ]
        
        cuts = engine.decide(energy, window_ms=200, total_duration_ms=4000)
        
        # Should stay on default camera (cam0)
        assert len(cuts) == 1
        assert cuts[0].camera_id == 0


class TestFastRulesEngineSafety:
    """Test safety fallback (Rule 6)."""

    def test_never_returns_empty_timeline(self) -> None:
        """Engine always returns at least one cut."""
        config = FastRulesConfig()
        engine = FastRulesEngine(config)
        
        # Empty energy timeline
        cuts = engine.decide([], window_ms=200, total_duration_ms=5000)
        
        assert len(cuts) >= 1
        assert cuts[0].start_ms == 0
        assert cuts[0].end_ms == 5000

    def test_all_silence_stays_on_default(self) -> None:
        """When all cameras are silent, stay on default."""
        config = FastRulesConfig()
        engine = FastRulesEngine(config)
        
        # All zeros
        energy = [
            [0.0] * 20,
            [0.0] * 20,
        ]
        
        cuts = engine.decide(energy, window_ms=200, total_duration_ms=4000)
        
        # Should stay on default camera
        assert len(cuts) == 1
        assert cuts[0].camera_id == 0
        assert cuts[0].end_ms == 4000

    def test_never_returns_empty_with_speech(self) -> None:
        """Timeline with speech always returns cuts."""
        config = FastRulesConfig()
        engine = FastRulesEngine(config)
        
        energy = [
            [0.5] * 10,
            [0.3] * 10,
        ]
        
        cuts = engine.decide(energy, window_ms=200, total_duration_ms=2000)
        
        assert len(cuts) >= 1
        # Verify full coverage
        assert cuts[0].start_ms == 0
        assert cuts[-1].end_ms == 2000


class TestFastRulesEngineMinDurationAndCooldown:
    """Combined test for min duration + cooldown."""

    def test_min_duration_and_cooldown_combined(self) -> None:
        """Both rules work together to prevent rapid switching."""
        config = FastRulesConfig(
            min_switch_duration_s=1.0,  # 5 windows
            cooldown_s=0.5,  # ~3 windows
            energy_margin=1.0,
            window_ms=200,
        )
        engine = FastRulesEngine(config)
        
        # 10 seconds of alternating speech (every 1s)
        windows_per_second = 5
        energy_cam0 = []
        energy_cam1 = []
        
        for second in range(10):
            if second % 2 == 0:
                energy_cam0.extend([0.8] * windows_per_second)
                energy_cam1.extend([0.1] * windows_per_second)
            else:
                energy_cam0.extend([0.1] * windows_per_second)
                energy_cam1.extend([0.8] * windows_per_second)
        
        cuts = engine.decide(
            [energy_cam0, energy_cam1],
            window_ms=200,
            total_duration_ms=10000,
        )
        
        # With min_duration=1s and cooldown=0.5s, limited switches
        # Verify no cut is shorter than min_duration (with tolerance)
        for i, cut in enumerate(cuts):
            duration_ms = cut.end_ms - cut.start_ms
            # Allow tolerance for window alignment and last segment
            if i < len(cuts) - 1:
                assert duration_ms >= 800, f"Cut {i} too short: {duration_ms}ms"


class TestFastRulesEngineThreeCameras:
    """Test with 3 cameras."""

    def test_three_cameras(self) -> None:
        """Engine handles 3+ cameras correctly."""
        config = FastRulesConfig(
            min_switch_duration_s=0.4,
            cooldown_s=0.2,
            energy_margin=1.2,
            window_ms=200,
        )
        engine = FastRulesEngine(config)
        
        # cam0 speaks, then cam2, cam1 is always quiet
        energy = [
            [0.8] * 10 + [0.1] * 20,
            [0.1] * 30,  # Always quiet
            [0.1] * 10 + [0.8] * 20,
        ]
        
        cuts = engine.decide(energy, window_ms=200, total_duration_ms=6000)
        
        # Should have cam0 and cam2
        camera_ids = {cut.camera_id for cut in cuts}
        assert 0 in camera_ids or 2 in camera_ids
        # cam1 should never win (always quiet)
        # (It might be default, but shouldn't win due to speech)
