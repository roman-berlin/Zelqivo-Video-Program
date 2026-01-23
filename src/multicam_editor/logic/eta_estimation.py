"""
ETA Estimation for processing pipeline.

Provides estimated processing time based on switching strategy,
media duration, and GPU availability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from .switching_strategy import SwitchingStrategy

logger = logging.getLogger(__name__)


# =============================================================================
# RTF (Real-Time Factor) Constants
# RTF = processing_time / media_duration
# =============================================================================

@dataclass(frozen=True)
class RTFRange:
    """Real-time factor range for a strategy."""
    min_rtf: float  # Best case (faster)
    max_rtf: float  # Worst case (slower)


# RTF ranges by strategy and GPU availability
RTF_FAST_RULES = RTFRange(1.0, 2.0)  # Always CPU, fast

RTF_BALANCED_GPU = RTFRange(1.5, 4.0)
RTF_BALANCED_CPU = RTFRange(2.0, 6.0)

RTF_BEST_LIPS_GPU = RTFRange(0.5, 2.0)   # GPU accelerated
RTF_BEST_LIPS_CPU = RTFRange(6.0, 25.0)  # Very slow on CPU


# =============================================================================
# Strategy Helper Text
# =============================================================================

STRATEGY_HELPER_TEXT = {
    SwitchingStrategy.FAST_RULES: (
        "Best default for most projects. Stable and quick on any PC. "
        "Less accurate with heavy overlaps."
    ),
    SwitchingStrategy.BALANCED_LIPS_ENERGY: (
        "Improves speaker switching accuracy. "
        "May be slower on long videos."
    ),
    SwitchingStrategy.BEST_LIPS: (
        "Best quality speaker detection. GPU recommended. "
        "On CPU may take many hours for long videos."
    ),
}


# =============================================================================
# ETA Computation Functions
# =============================================================================

def get_rtf_range(strategy: SwitchingStrategy, gpu_available: bool) -> RTFRange:
    """Get RTF range for a strategy and GPU availability.
    
    Args:
        strategy: Selected switching strategy.
        gpu_available: Whether GPU is available.
        
    Returns:
        RTFRange with min and max real-time factors.
    """
    if strategy == SwitchingStrategy.FAST_RULES:
        return RTF_FAST_RULES
    elif strategy == SwitchingStrategy.BALANCED_LIPS_ENERGY:
        return RTF_BALANCED_GPU if gpu_available else RTF_BALANCED_CPU
    elif strategy == SwitchingStrategy.BEST_LIPS:
        return RTF_BEST_LIPS_GPU if gpu_available else RTF_BEST_LIPS_CPU
    else:
        # Fallback to balanced CPU
        logger.warning("Unknown strategy %s, using balanced CPU RTF", strategy)
        return RTF_BALANCED_CPU


def compute_eta_range(
    total_audio_seconds: float,
    strategy: SwitchingStrategy,
    gpu_available: bool,
) -> Optional[Tuple[float, float]]:
    """Compute estimated processing time range.
    
    Args:
        total_audio_seconds: Total audio duration in seconds.
        strategy: Selected switching strategy.
        gpu_available: Whether GPU is available.
        
    Returns:
        Tuple of (min_seconds, max_seconds) or None if cannot compute.
    """
    if total_audio_seconds <= 0:
        logger.debug("Cannot compute ETA: total_audio_seconds=%s", total_audio_seconds)
        return None
    
    rtf = get_rtf_range(strategy, gpu_available)
    min_seconds = total_audio_seconds * rtf.min_rtf
    max_seconds = total_audio_seconds * rtf.max_rtf
    
    logger.info(
        "ETA computed: audio=%.1fs, strategy=%s, gpu=%s, range=%.0f-%.0fs",
        total_audio_seconds, strategy.value, gpu_available, min_seconds, max_seconds
    )
    
    return (min_seconds, max_seconds)


def format_eta_range(min_seconds: float, max_seconds: float) -> str:
    """Format ETA range as human-readable string.
    
    Args:
        min_seconds: Minimum estimated seconds.
        max_seconds: Maximum estimated seconds.
        
    Returns:
        Human-readable string like "12m - 25m" or "1h 30m - 3h 00m".
    """
    def format_duration(seconds: float) -> str:
        """Format single duration value."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}m"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            if minutes > 0:
                return f"{hours}h {minutes:02d}m"
            else:
                return f"{hours}h"
    
    min_str = format_duration(min_seconds)
    max_str = format_duration(max_seconds)
    
    if min_str == max_str:
        return min_str
    
    return f"{min_str} - {max_str}"


def get_strategy_helper_text(strategy: SwitchingStrategy) -> str:
    """Get helper text for a switching strategy.
    
    Args:
        strategy: The switching strategy.
        
    Returns:
        Helper text describing the strategy.
    """
    return STRATEGY_HELPER_TEXT.get(strategy, "")


def get_strategy_display_name(strategy: SwitchingStrategy) -> str:
    """Get display name for a strategy.
    
    Args:
        strategy: The switching strategy.
        
    Returns:
        Human-readable display name.
    """
    names = {
        SwitchingStrategy.FAST_RULES: "⚡ Fast (CPU) - Recommended",
        SwitchingStrategy.BALANCED_LIPS_ENERGY: "⚖️ Balanced - Better accuracy",
        SwitchingStrategy.BEST_LIPS: "🎯 Best - Highest quality",
    }
    return names.get(strategy, strategy.value)


# =============================================================================
# Warning Conditions
# =============================================================================

def should_warn_best_no_gpu(
    strategy: SwitchingStrategy,
    gpu_available: bool,
) -> bool:
    """Check if warning needed for BEST_LIPS without GPU.
    
    Args:
        strategy: Selected strategy.
        gpu_available: Whether GPU is available.
        
    Returns:
        True if warning should be shown.
    """
    return strategy == SwitchingStrategy.BEST_LIPS and not gpu_available


def should_warn_long_project(
    total_audio_seconds: float,
    strategy: SwitchingStrategy,
    gpu_available: bool,
    threshold_seconds: float = 3600.0,  # 60 minutes
) -> bool:
    """Check if warning needed for long project on CPU.
    
    Args:
        total_audio_seconds: Total audio duration.
        strategy: Selected strategy.
        gpu_available: Whether GPU is available.
        threshold_seconds: Duration threshold (default 60 min).
        
    Returns:
        True if warning should be shown.
    """
    if total_audio_seconds < threshold_seconds:
        return False
    
    if gpu_available:
        return False
    
    # Warn for BALANCED or BEST on CPU with long projects
    return strategy in (
        SwitchingStrategy.BALANCED_LIPS_ENERGY,
        SwitchingStrategy.BEST_LIPS,
    )


def get_eta_display_text(
    total_audio_seconds: float,
    strategy: SwitchingStrategy,
    gpu_available: bool,
) -> str:
    """Get formatted ETA text for display.
    
    Args:
        total_audio_seconds: Total audio duration.
        strategy: Selected strategy.
        gpu_available: Whether GPU is available.
        
    Returns:
        Display text like "Estimated processing time: 12m - 25m".
    """
    eta_range = compute_eta_range(total_audio_seconds, strategy, gpu_available)
    
    if eta_range is None:
        return "Calculating..."
    
    min_s, max_s = eta_range
    formatted = format_eta_range(min_s, max_s)
    
    return f"Estimated processing time: {formatted}"
