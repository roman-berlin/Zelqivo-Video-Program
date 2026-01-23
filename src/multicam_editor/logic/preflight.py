"""Preflight warnings for media files before processing.

Detects common issues (rotation, no audio, VFR) and returns non-blocking warnings.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List

from ..utils.ffprobe import probe, has_audio_stream

logger = logging.getLogger(__name__)


@dataclass
class PreflightWarning:
    """A single preflight warning for a media file."""
    path: str
    filename: str
    warning_type: str  # "rotation", "no_audio", "vfr"
    message: str


def check_preflight_warnings(paths: List[str]) -> List[PreflightWarning]:
    """Check media files for common issues and return warnings.

    Does not block processing - just provides advisory warnings.

    Args:
        paths: List of media file paths to check

    Returns:
        List of PreflightWarning objects (may be empty)
    """
    warnings: List[PreflightWarning] = []

    for path in paths:
        filename = os.path.basename(path)
        try:
            result = probe(path)
            if result.error:
                logger.debug(f"Preflight: probe error for {filename}: {result.error}")
                continue

            # Check rotation metadata
            if result.rotation and result.rotation != 0:
                rot = abs(result.rotation)
                w = PreflightWarning(
                    path=path,
                    filename=filename,
                    warning_type="rotation",
                    message=f"Has rotation metadata ({rot}°). Output may be auto-rotated.",
                )
                warnings.append(w)
                logger.info(f"Preflight warning: {filename} - rotation {rot}°")

            # Check for VFR risk
            if result.vfr_risk:
                w = PreflightWarning(
                    path=path,
                    filename=filename,
                    warning_type="vfr",
                    message="Likely variable frame rate (VFR). May cause sync issues.",
                )
                warnings.append(w)
                logger.info(f"Preflight warning: {filename} - VFR risk detected")

            # Check for no audio stream
            has_audio = any(s.codec_type == "audio" for s in (result.streams or []))
            if not has_audio:
                w = PreflightWarning(
                    path=path,
                    filename=filename,
                    warning_type="no_audio",
                    message="No audio stream. Will be silent in output unless external audio is used.",
                )
                warnings.append(w)
                logger.info(f"Preflight warning: {filename} - no audio stream")

        except Exception as e:
            logger.debug(f"Preflight: exception checking {filename}: {e}", exc_info=True)

    return warnings


def format_warnings_for_display(warnings: List[PreflightWarning]) -> str:
    """Format warnings for status bar display.

    Args:
        warnings: List of preflight warnings

    Returns:
        Single-line summary string for status bar
    """
    if not warnings:
        return ""

    # Group by type
    rotation_count = sum(1 for w in warnings if w.warning_type == "rotation")
    vfr_count = sum(1 for w in warnings if w.warning_type == "vfr")
    no_audio_count = sum(1 for w in warnings if w.warning_type == "no_audio")

    parts = []
    if rotation_count:
        parts.append(f"{rotation_count} rotated")
    if vfr_count:
        parts.append(f"{vfr_count} VFR")
    if no_audio_count:
        parts.append(f"{no_audio_count} no-audio")

    return f"⚠ Preflight: {', '.join(parts)}" if parts else ""


# =============================================================================
# GPU Preflight Check for Switching Strategy
# =============================================================================

from enum import Enum
from typing import Optional, Tuple, Callable

from .switching_strategy import SwitchingStrategy


class GpuPreflightResult(Enum):
    """Result of GPU preflight check."""
    PROCEED = "proceed"           # No issues, continue
    WARNING_SHOWN = "warning"     # Warning shown, user chose to continue
    SWITCHED = "switched"         # User switched to faster mode
    HEADLESS = "headless"         # Headless mode, logged warning only


@dataclass
class GpuPreflightStatus:
    """Status from GPU preflight check."""
    result: GpuPreflightResult
    gpu_available: bool
    original_strategy: SwitchingStrategy
    final_strategy: SwitchingStrategy
    message: Optional[str] = None


def detect_gpu() -> bool:
    """
    Detect if CUDA GPU is available for PyTorch.
    
    Returns:
        True if GPU available, False otherwise.
    """
    try:
        import torch
        available = torch.cuda.is_available()
        if available:
            device_name = torch.cuda.get_device_name(0)
            logger.info("GPU detected: %s", device_name)
        else:
            logger.info("GPU not detected, using CPU")
        return available
    except ImportError:
        logger.info("PyTorch not installed, assuming no GPU")
        return False
    except Exception as e:
        logger.warning("Error detecting GPU: %s", e)
        return False


def needs_gpu_warning(strategy: SwitchingStrategy, gpu_available: bool) -> bool:
    """
    Check if a GPU warning should be shown.
    
    Args:
        strategy: Selected switching strategy.
        gpu_available: Whether GPU is available.
        
    Returns:
        True if warning needed (BEST_LIPS without GPU).
    """
    if strategy != SwitchingStrategy.BEST_LIPS:
        return False
    
    if gpu_available:
        return False
    
    logger.debug("Warning needed: BEST_LIPS selected without GPU")
    return True


def run_gpu_preflight_check(
    strategy: SwitchingStrategy,
    show_dialog_callback: Optional[Callable[[SwitchingStrategy, str], Tuple[bool, SwitchingStrategy]]] = None,
) -> GpuPreflightStatus:
    """
    Run GPU preflight checks before processing.
    
    Args:
        strategy: Selected switching strategy.
        show_dialog_callback: Optional callback to show warning dialog.
            Should return tuple (proceed: bool, new_strategy: SwitchingStrategy).
            If None, headless mode is assumed.
            
    Returns:
        GpuPreflightStatus with result and final strategy.
    """
    gpu_available = detect_gpu()
    
    # No warning needed for FAST_RULES or BALANCED
    if not needs_gpu_warning(strategy, gpu_available):
        logger.info("GPU preflight passed: strategy=%s, gpu=%s", 
                   strategy.value, gpu_available)
        return GpuPreflightStatus(
            result=GpuPreflightResult.PROCEED,
            gpu_available=gpu_available,
            original_strategy=strategy,
            final_strategy=strategy,
        )
    
    # Warning needed: BEST_LIPS without GPU
    warning_msg = (
        "Visual-only detection (Best) is very slow without GPU.\n"
        "Processing may take several hours on CPU."
    )
    
    # Headless mode: log and continue
    if show_dialog_callback is None:
        logger.warning("HEADLESS: %s", warning_msg)
        logger.warning("Continuing with BEST_LIPS on CPU (no UI available)")
        return GpuPreflightStatus(
            result=GpuPreflightResult.HEADLESS,
            gpu_available=gpu_available,
            original_strategy=strategy,
            final_strategy=strategy,
            message=warning_msg,
        )
    
    # Show dialog and get user choice
    try:
        proceed, new_strategy = show_dialog_callback(strategy, warning_msg)
        
        if proceed and new_strategy == strategy:
            logger.info("User chose to continue with BEST_LIPS on CPU")
            return GpuPreflightStatus(
                result=GpuPreflightResult.WARNING_SHOWN,
                gpu_available=gpu_available,
                original_strategy=strategy,
                final_strategy=strategy,
            )
        elif new_strategy != strategy:
            logger.info("User switched from %s to %s", 
                       strategy.value, new_strategy.value)
            return GpuPreflightStatus(
                result=GpuPreflightResult.SWITCHED,
                gpu_available=gpu_available,
                original_strategy=strategy,
                final_strategy=new_strategy,
            )
        else:
            # User cancelled - still proceed with original
            logger.info("Dialog closed, proceeding with original strategy")
            return GpuPreflightStatus(
                result=GpuPreflightResult.WARNING_SHOWN,
                gpu_available=gpu_available,
                original_strategy=strategy,
                final_strategy=strategy,
            )
    except Exception as e:
        logger.error("Error showing preflight dialog: %s", e)
        # Fail safe: continue with original strategy
        return GpuPreflightStatus(
            result=GpuPreflightResult.HEADLESS,
            gpu_available=gpu_available,
            original_strategy=strategy,
            final_strategy=strategy,
            message=str(e),
        )
