"""
Tests for ETA estimation logic.
"""

import pytest

from multicam_editor.logic.eta_estimation import (
    RTFRange,
    RTF_FAST_RULES,
    RTF_BALANCED_GPU,
    RTF_BALANCED_CPU,
    RTF_BEST_LIPS_GPU,
    RTF_BEST_LIPS_CPU,
    get_rtf_range,
    compute_eta_range,
    format_eta_range,
    get_strategy_helper_text,
    get_strategy_display_name,
    should_warn_best_no_gpu,
    should_warn_long_project,
    get_eta_display_text,
)
from multicam_editor.logic.switching_strategy import SwitchingStrategy


class TestRTFConstants:
    """Tests for RTF constant values."""
    
    def test_fast_rules_rtf(self) -> None:
        """FAST_RULES has expected RTF range."""
        assert RTF_FAST_RULES.min_rtf == 1.0
        assert RTF_FAST_RULES.max_rtf == 2.0
    
    def test_balanced_cpu_slower_than_gpu(self) -> None:
        """BALANCED CPU is slower than GPU."""
        assert RTF_BALANCED_CPU.min_rtf >= RTF_BALANCED_GPU.min_rtf
    
    def test_best_cpu_much_slower_than_gpu(self) -> None:
        """BEST CPU is significantly slower than GPU."""
        assert RTF_BEST_LIPS_CPU.min_rtf > RTF_BEST_LIPS_GPU.max_rtf


class TestGetRTFRange:
    """Tests for get_rtf_range function."""
    
    def test_fast_rules_ignores_gpu(self) -> None:
        """FAST_RULES returns same RTF regardless of GPU."""
        rtf_gpu = get_rtf_range(SwitchingStrategy.FAST_RULES, gpu_available=True)
        rtf_cpu = get_rtf_range(SwitchingStrategy.FAST_RULES, gpu_available=False)
        assert rtf_gpu == rtf_cpu == RTF_FAST_RULES
    
    def test_balanced_with_gpu(self) -> None:
        """BALANCED uses GPU RTF when available."""
        rtf = get_rtf_range(SwitchingStrategy.BALANCED_LIPS_ENERGY, gpu_available=True)
        assert rtf == RTF_BALANCED_GPU
    
    def test_balanced_without_gpu(self) -> None:
        """BALANCED uses CPU RTF when no GPU."""
        rtf = get_rtf_range(SwitchingStrategy.BALANCED_LIPS_ENERGY, gpu_available=False)
        assert rtf == RTF_BALANCED_CPU
    
    def test_best_with_gpu(self) -> None:
        """BEST uses GPU RTF when available."""
        rtf = get_rtf_range(SwitchingStrategy.BEST_LIPS, gpu_available=True)
        assert rtf == RTF_BEST_LIPS_GPU
    
    def test_best_without_gpu(self) -> None:
        """BEST uses CPU RTF when no GPU."""
        rtf = get_rtf_range(SwitchingStrategy.BEST_LIPS, gpu_available=False)
        assert rtf == RTF_BEST_LIPS_CPU


class TestComputeETARange:
    """Tests for compute_eta_range function."""
    
    def test_returns_none_for_zero_duration(self) -> None:
        """Returns None for zero or negative duration."""
        result = compute_eta_range(0.0, SwitchingStrategy.FAST_RULES, False)
        assert result is None
        
        result = compute_eta_range(-10.0, SwitchingStrategy.FAST_RULES, False)
        assert result is None
    
    def test_fast_rules_60s_video(self) -> None:
        """FAST_RULES on 60s video: 1-2 minutes."""
        min_s, max_s = compute_eta_range(60.0, SwitchingStrategy.FAST_RULES, False)
        assert min_s == 60.0   # 1x
        assert max_s == 120.0  # 2x
    
    def test_best_gpu_60s_video(self) -> None:
        """BEST with GPU on 60s video."""
        min_s, max_s = compute_eta_range(60.0, SwitchingStrategy.BEST_LIPS, True)
        assert min_s == 30.0   # 0.5x
        assert max_s == 120.0  # 2x
    
    def test_best_cpu_60s_video(self) -> None:
        """BEST without GPU on 60s video."""
        min_s, max_s = compute_eta_range(60.0, SwitchingStrategy.BEST_LIPS, False)
        assert min_s == 360.0   # 6x
        assert max_s == 1500.0  # 25x
    
    def test_long_video_calculation(self) -> None:
        """ETA for 1 hour video with BEST CPU."""
        min_s, max_s = compute_eta_range(3600.0, SwitchingStrategy.BEST_LIPS, False)
        assert min_s == 21600.0   # 6 hours
        assert max_s == 90000.0   # 25 hours


class TestFormatETARange:
    """Tests for format_eta_range function."""
    
    def test_seconds_format(self) -> None:
        """Under 1 minute shows seconds."""
        assert format_eta_range(30, 45) == "30s - 45s"
    
    def test_minutes_format(self) -> None:
        """Minutes format for short durations."""
        assert format_eta_range(300, 900) == "5m - 15m"
    
    def test_hours_format(self) -> None:
        """Hours format for long durations."""
        result = format_eta_range(5400, 10800)  # 1.5h - 3h
        assert "1h" in result
        assert "3h" in result
    
    def test_same_min_max(self) -> None:
        """Same min and max shows single value."""
        assert format_eta_range(600, 600) == "10m"
    
    def test_mixed_format(self) -> None:
        """Mixed minutes and hours."""
        result = format_eta_range(2700, 7200)  # 45m - 2h
        assert "45m" in result
        assert "2h" in result


class TestStrategyHelperText:
    """Tests for get_strategy_helper_text function."""
    
    def test_fast_rules_text(self) -> None:
        """FAST_RULES has appropriate helper text."""
        text = get_strategy_helper_text(SwitchingStrategy.FAST_RULES)
        assert "quick" in text.lower() or "fast" in text.lower()
        assert len(text) > 20
    
    def test_balanced_text(self) -> None:
        """BALANCED has appropriate helper text."""
        text = get_strategy_helper_text(SwitchingStrategy.BALANCED_LIPS_ENERGY)
        assert "accuracy" in text.lower() or "better" in text.lower()
    
    def test_best_text(self) -> None:
        """BEST has appropriate helper text mentioning GPU."""
        text = get_strategy_helper_text(SwitchingStrategy.BEST_LIPS)
        assert "gpu" in text.lower()


class TestStrategyDisplayName:
    """Tests for get_strategy_display_name function."""
    
    def test_all_strategies_have_names(self) -> None:
        """All strategies have display names."""
        for strategy in SwitchingStrategy:
            name = get_strategy_display_name(strategy)
            assert len(name) > 0


class TestWarningConditions:
    """Tests for warning condition functions."""
    
    def test_best_no_gpu_warns(self) -> None:
        """BEST without GPU triggers warning."""
        assert should_warn_best_no_gpu(SwitchingStrategy.BEST_LIPS, False) is True
    
    def test_best_with_gpu_no_warning(self) -> None:
        """BEST with GPU does not trigger warning."""
        assert should_warn_best_no_gpu(SwitchingStrategy.BEST_LIPS, True) is False
    
    def test_fast_no_gpu_no_warning(self) -> None:
        """FAST without GPU does not trigger warning."""
        assert should_warn_best_no_gpu(SwitchingStrategy.FAST_RULES, False) is False
    
    def test_long_project_best_cpu_warns(self) -> None:
        """Long project with BEST on CPU warns."""
        assert should_warn_long_project(4000.0, SwitchingStrategy.BEST_LIPS, False) is True
    
    def test_long_project_balanced_cpu_warns(self) -> None:
        """Long project with BALANCED on CPU warns."""
        assert should_warn_long_project(4000.0, SwitchingStrategy.BALANCED_LIPS_ENERGY, False) is True
    
    def test_long_project_fast_no_warning(self) -> None:
        """Long project with FAST does not warn."""
        assert should_warn_long_project(4000.0, SwitchingStrategy.FAST_RULES, False) is False
    
    def test_long_project_with_gpu_no_warning(self) -> None:
        """Long project with GPU does not warn."""
        assert should_warn_long_project(4000.0, SwitchingStrategy.BEST_LIPS, True) is False
    
    def test_short_project_no_warning(self) -> None:
        """Short project does not warn."""
        assert should_warn_long_project(1800.0, SwitchingStrategy.BEST_LIPS, False) is False


class TestGetETADisplayText:
    """Tests for get_eta_display_text function."""
    
    def test_valid_duration_shows_range(self) -> None:
        """Valid duration shows formatted range."""
        text = get_eta_display_text(300.0, SwitchingStrategy.FAST_RULES, False)
        assert "Estimated processing time:" in text
        assert "-" not in text or "m" in text  # Not just "-"
    
    def test_zero_duration_shows_placeholder(self) -> None:
        """Zero duration shows placeholder."""
        text = get_eta_display_text(0.0, SwitchingStrategy.FAST_RULES, False)
        assert text == "Calculating..."
    
    def test_negative_duration_shows_placeholder(self) -> None:
        """Negative duration shows placeholder."""
        text = get_eta_display_text(-100.0, SwitchingStrategy.FAST_RULES, False)
        assert text == "Calculating..."

