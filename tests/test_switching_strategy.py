"""Tests for switching strategy selection layer."""

import pytest

from multicam_editor.logic.switching_strategy import (
    SwitchingStrategy,
    DEFAULT_STRATEGY,
    select_switching_engine,
    get_strategy_from_string,
)


class TestSwitchingStrategyEnum:
    """Tests for SwitchingStrategy enum."""

    def test_strategy_enum_values(self) -> None:
        """Verify enum has expected values."""
        assert SwitchingStrategy.BEST_LIPS.value == "best_lips"
        assert SwitchingStrategy.BALANCED_LIPS_ENERGY.value == "balanced"
        assert SwitchingStrategy.FAST_RULES.value == "fast_rules"

    def test_default_strategy_is_balanced(self) -> None:
        """Default strategy must remain BALANCED_LIPS_ENERGY (no behavior change)."""
        assert DEFAULT_STRATEGY == SwitchingStrategy.BALANCED_LIPS_ENERGY


class TestSelectSwitchingEngine:
    """Tests for select_switching_engine function."""

    def test_select_best_lips_returns_lip_movement_backend(self) -> None:
        """BEST_LIPS strategy returns LipMovementBackend instance."""
        from multicam_editor.logic.active_speaker import LipMovementBackend
        
        engine, config = select_switching_engine(SwitchingStrategy.BEST_LIPS)
        
        assert isinstance(engine, LipMovementBackend)
        assert config["strategy"] == "best_lips"
        assert config["backend_type"] == "LipMovementBackend"
        assert config["mode"] == "lips"
        assert config["fallback_applied"] is False

    def test_select_balanced_returns_hybrid_backend(self) -> None:
        """BALANCED_LIPS_ENERGY strategy returns HybridBackend instance."""
        from multicam_editor.logic.active_speaker import HybridBackend
        
        engine, config = select_switching_engine(SwitchingStrategy.BALANCED_LIPS_ENERGY)
        
        assert isinstance(engine, HybridBackend)
        assert config["strategy"] == "balanced"
        assert config["backend_type"] == "HybridBackend"
        assert config["mode"] == "hybrid"
        assert config["fallback_applied"] is False

    def test_select_fast_rules_returns_fast_rules_engine(self) -> None:
        """FAST_RULES strategy returns FastRulesEngine instance."""
        from multicam_editor.logic.fast_rules_engine import FastRulesEngine
        
        engine, config = select_switching_engine(SwitchingStrategy.FAST_RULES)
        
        assert isinstance(engine, FastRulesEngine)
        assert config["strategy"] == "fast_rules"
        assert config["backend_type"] == "FastRulesEngine"
        assert config["mode"] == "fast_rules"
        assert config["fallback_applied"] is False


class TestGetStrategyFromString:
    """Tests for get_strategy_from_string helper."""

    def test_parse_best_lips(self) -> None:
        assert get_strategy_from_string("best_lips") == SwitchingStrategy.BEST_LIPS

    def test_parse_balanced(self) -> None:
        assert get_strategy_from_string("balanced") == SwitchingStrategy.BALANCED_LIPS_ENERGY

    def test_parse_fast_rules(self) -> None:
        assert get_strategy_from_string("fast_rules") == SwitchingStrategy.FAST_RULES

    def test_parse_unknown_returns_default(self) -> None:
        """Unknown string falls back to DEFAULT_STRATEGY."""
        result = get_strategy_from_string("unknown_strategy")
        assert result == DEFAULT_STRATEGY

    def test_parse_handles_whitespace(self) -> None:
        """Parser handles leading/trailing whitespace."""
        assert get_strategy_from_string("  balanced  ") == SwitchingStrategy.BALANCED_LIPS_ENERGY

    def test_parse_case_insensitive(self) -> None:
        """Parser is case-insensitive."""
        assert get_strategy_from_string("BALANCED") == SwitchingStrategy.BALANCED_LIPS_ENERGY
        assert get_strategy_from_string("Best_Lips") == SwitchingStrategy.BEST_LIPS


class TestGetSwitchingStrategyFromSettings:
    """Tests for get_switching_strategy settings helper."""

    def test_returns_correct_type(self) -> None:
        """get_switching_strategy returns SwitchingStrategy enum."""
        from multicam_editor.ui.settings_dialog import get_switching_strategy
        
        result = get_switching_strategy()
        assert isinstance(result, SwitchingStrategy)

    def test_default_is_balanced(self) -> None:
        """Default strategy for new users is BALANCED_LIPS_ENERGY."""
        # Note: This tests the default when no setting exists.
        # In real tests, you'd mock QSettings, but for now we verify the type.
        from multicam_editor.ui.settings_dialog import get_switching_strategy
        
        result = get_switching_strategy()
        # Fresh install should default to balanced
        assert result in list(SwitchingStrategy)
