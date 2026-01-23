"""Switching strategy selection layer.

This module provides a high-level abstraction for switching strategies,
sitting above the lower-level DiarizationMode backends.

Strategies:
- BEST_LIPS: Visual-first approach, highest quality speaker detection
- BALANCED_LIPS_ENERGY: Hybrid approach combining audio VAD + visual (current default)
- FAST_RULES: Rule-based switching (not yet implemented)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .active_speaker import DiarizationBackend

logger = logging.getLogger(__name__)


class SwitchingStrategy(Enum):
    """High-level switching strategy selection.
    
    These strategies represent different approaches to camera switching,
    independent of the underlying detection backend.
    """
    BEST_LIPS = "best_lips"           # Visual-first, highest quality
    BALANCED_LIPS_ENERGY = "balanced" # Hybrid (LIPS + Energy) - current default
    FAST_RULES = "fast_rules"         # Rule-based switching (not implemented)


# Default strategy - matches current behavior (Hybrid mode)
DEFAULT_STRATEGY = SwitchingStrategy.BALANCED_LIPS_ENERGY


def select_switching_engine(
    strategy: SwitchingStrategy,
) -> Tuple[Optional[Any], Dict[str, Any]]:
    """Select the appropriate switching engine based on strategy.
    
    Args:
        strategy: The switching strategy to use.
        
    Returns:
        Tuple of (engine_instance_or_None, config_dict).
        For FAST_RULES, raises NotImplementedError.
        
    Raises:
        NotImplementedError: If FAST_RULES strategy is selected.
    """
    logger.info("Selecting switching engine for strategy: %s", strategy.value)
    
    config: Dict[str, Any] = {
        "strategy": strategy.value,
        "fallback_applied": False,
    }
    
    if strategy == SwitchingStrategy.BEST_LIPS:
        logger.info("Strategy BEST_LIPS: Using visual-first lip movement detection")
        # Import here to avoid circular imports
        from .active_speaker import LipMovementBackend
        engine = LipMovementBackend(
            sample_interval_ms=200,
            min_segment_ms=500,
        )
        config["backend_type"] = "LipMovementBackend"
        config["mode"] = "lips"
        return engine, config
        
    elif strategy == SwitchingStrategy.BALANCED_LIPS_ENERGY:
        logger.info("Strategy BALANCED_LIPS_ENERGY: Using hybrid audio+visual detection")
        # Import here to avoid circular imports
        from .active_speaker import HybridBackend
        engine = HybridBackend(
            sample_interval_ms=200,
            min_segment_ms=500,
        )
        config["backend_type"] = "HybridBackend"
        config["mode"] = "hybrid"
        return engine, config
        
    elif strategy == SwitchingStrategy.FAST_RULES:
        logger.info("Strategy FAST_RULES: Using rule-based energy switching")
        # Import here to avoid circular imports
        from .fast_rules_engine import FastRulesEngine, FastRulesConfig
        engine = FastRulesEngine(FastRulesConfig())
        config["backend_type"] = "FastRulesEngine"
        config["mode"] = "fast_rules"
        return engine, config
    
    else:
        # Fallback to default strategy
        logger.warning(
            "Unknown strategy %s, falling back to default: %s",
            strategy, DEFAULT_STRATEGY.value
        )
        config["fallback_applied"] = True
        config["original_strategy"] = strategy.value
        return select_switching_engine(DEFAULT_STRATEGY)


def get_strategy_from_string(strategy_str: str) -> SwitchingStrategy:
    """Convert string to SwitchingStrategy enum.
    
    Args:
        strategy_str: String representation of strategy.
        
    Returns:
        Corresponding SwitchingStrategy enum value.
        Falls back to DEFAULT_STRATEGY if not recognized.
    """
    strategy_str_lower = strategy_str.lower().strip()
    
    for strategy in SwitchingStrategy:
        if strategy.value == strategy_str_lower:
            logger.debug("Parsed strategy string '%s' -> %s", strategy_str, strategy)
            return strategy
    
    logger.warning(
        "Unknown strategy string '%s', using default: %s",
        strategy_str, DEFAULT_STRATEGY.value
    )
    return DEFAULT_STRATEGY
