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
