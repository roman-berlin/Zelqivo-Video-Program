"""Preflight validation for media files before processing.

Performs comprehensive "fitness checks" on input media and system resources:
- Stream integrity (mandatory video + audio streams)
- Corrupt header detection via FFprobe
- VFR (Variable Frame Rate) detection
- Disk space requirements validation
- Write permission verification

Critical errors block processing; warnings allow user override.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from ..utils.ffprobe import probe, has_audio_stream, ProbeResult

logger = logging.getLogger(__name__)


# =============================================================================
# New Preflight Manager - Comprehensive Validation
# =============================================================================

class PreflightErrorType(Enum):
    """Severity level for preflight errors."""
    CRITICAL = "critical"  # Blocks processing
    WARNING = "warning"    # User can override


@dataclass
class PreflightError:
    """A single preflight error or warning."""
    path: str
    filename: str
    error_type: str  # "corrupt_header", "no_audio", "no_video", "disk_space", etc.
    severity: PreflightErrorType
    message: str


@dataclass
class PreflightResult:
    """Result of comprehensive preflight checks."""
    ok: bool
    critical_errors: List[PreflightError] = field(default_factory=list)
    warnings: List[PreflightError] = field(default_factory=list)
    
    def __post_init__(self):
        """Auto-set ok status based on critical errors."""
        if self.critical_errors:
            self.ok = False


class PreflightManager:
    """Orchestrates all preflight validation checks before processing."""
    
    def __init__(self):
        self._probe_results: dict[str, ProbeResult] = {}
    
    def run_full_check(
        self, 
        input_files: List[str], 
        output_dir: Optional[str] = None
    ) -> PreflightResult:
        """Execute all preflight checks on input files and system resources.
        
        Args:
            input_files: List of video file paths to validate
            output_dir: Target output directory (uses temp if None)
        
        Returns:
            PreflightResult with categorized errors and warnings
        """
        critical_errors: List[PreflightError] = []
        warnings: List[PreflightError] = []
        
        logger.info("Running preflight checks on %d files", len(input_files))
        
        # 1. Probe all files and check stream integrity
        for path in input_files:
            filename = os.path.basename(path)
            
            # Check file exists
            if not os.path.isfile(path):
                critical_errors.append(PreflightError(
                    path=path,
                    filename=filename,
                    error_type="file_not_found",
                    severity=PreflightErrorType.CRITICAL,
                    message=f"File not found: {filename}"
                ))
                continue
            
            # Probe file
            result = probe(path)
            self._probe_results[path] = result
            
            # Check for corrupt header (probe failure)
            if result.error:
                critical_errors.append(PreflightError(
                    path=path,
                    filename=filename,
                    error_type="corrupt_header",
                    severity=PreflightErrorType.CRITICAL,
                    message=f"Corrupt or unreadable file: {filename} ({result.error})"
                ))
                continue
            
            # Check for mandatory video stream
            has_video = any(s.codec_type == "video" for s in (result.streams or []))
            if not has_video:
                critical_errors.append(PreflightError(
                    path=path,
                    filename=filename,
                    error_type="no_video",
                    severity=PreflightErrorType.CRITICAL,
                    message=f"No video stream found in {filename}"
                ))
            
            # Check for mandatory audio stream (required for sync)
            has_audio = any(s.codec_type == "audio" for s in (result.streams or []))
            if not has_audio:
                critical_errors.append(PreflightError(
                    path=path,
                    filename=filename,
                    error_type="no_audio",
                    severity=PreflightErrorType.CRITICAL,
                    message=f"No audio stream in {filename} (required for sync)"
                ))
            
            # Check for VFR risk (warning only)
            if result.vfr_risk:
                warnings.append(PreflightError(
                    path=path,
                    filename=filename,
                    error_type="vfr_risk",
                    severity=PreflightErrorType.WARNING,
                    message=f"Variable frame rate detected in {filename} (may cause sync drift)"
                ))
        
        # 2. Calculate disk space requirements
        if self._probe_results and not critical_errors:
            disk_errors = self._check_disk_space_requirements(
                input_files, 
                output_dir or tempfile.gettempdir()
            )
            for err in disk_errors:
                if err.severity == PreflightErrorType.CRITICAL:
                    critical_errors.append(err)
                else:
                    warnings.append(err)
        
        # 3. Check write permissions
        if not critical_errors:
            perm_errors = self._check_write_permissions(output_dir)
            critical_errors.extend(perm_errors)
        
        # Build result
        result = PreflightResult(
            ok=len(critical_errors) == 0,
            critical_errors=critical_errors,
            warnings=warnings
        )
        
        if result.ok:
            logger.info("Preflight checks passed ✓")
        else:
            logger.error("Preflight checks failed with %d critical errors", len(critical_errors))
        
        return result
    
    def _check_disk_space_requirements(
        self, 
        input_files: List[str], 
        output_dir: str
    ) -> List[PreflightError]:
        """Calculate required disk space and verify availability.
        
        Estimates 2.5x the total input file size for:
        - Temporary WAV extraction
        - Rendered segments
        - Final output file
        
        Args:
            input_files: List of input video paths
            output_dir: Directory where output will be written
        
        Returns:
            List of errors (critical if < 2.5x, warning if < 3.0x)
        """
        errors: List[PreflightError] = []
        
        try:
            # Calculate total input size
            total_input_bytes = 0
            for path in input_files:
                if os.path.isfile(path):
                    total_input_bytes += os.path.getsize(path)
            
            if total_input_bytes == 0:
                return errors  # No valid files
            
            # Require 2.5x input size (critical), warn if < 3.0x
            required_bytes_critical = int(total_input_bytes * 2.5)
            required_bytes_warning = int(total_input_bytes * 3.0)
            
            # Check available space
            usage = shutil.disk_usage(output_dir)
            free_bytes = usage.free
            
            # Format sizes for messages
            total_gb = total_input_bytes / (1024**3)
            free_gb = free_bytes / (1024**3)
            required_gb = required_bytes_critical / (1024**3)
            
            logger.debug(
                "Disk space: %.2f GB input, %.2f GB free, %.2f GB required",
                total_gb, free_gb, required_gb
            )
            
            if free_bytes < required_bytes_critical:
                errors.append(PreflightError(
                    path=output_dir,
                    filename="",
                    error_type="disk_space_critical",
                    severity=PreflightErrorType.CRITICAL,
                    message=(
                        f"Insufficient disk space: {free_gb:.1f} GB available, "
                        f"{required_gb:.1f} GB required (2.5× input size). "
                        f"Free up disk space and try again."
                    )
                ))
            elif free_bytes < required_bytes_warning:
                warn_gb = required_bytes_warning / (1024**3)
                errors.append(PreflightError(
                    path=output_dir,
                    filename="",
                    error_type="disk_space_low",
                    severity=PreflightErrorType.WARNING,
                    message=(
                        f"Low disk space: {free_gb:.1f} GB available, "
                        f"{warn_gb:.1f} GB recommended (3× input size). "
                        f"Processing may fail if disk fills up."
                    )
                ))
        
        except Exception as e:
            logger.warning("Could not check disk space: %s", e)
            # Don't fail on disk check errors - continue processing
        
        return errors
    
    def _check_write_permissions(self, output_dir: Optional[str]) -> List[PreflightError]:
        """Verify write access to output and temp directories.
        
        Args:
            output_dir: Target output directory (None = temp dir)
        
        Returns:
            List of critical errors if write access denied
        """
        errors: List[PreflightError] = []
        
        dirs_to_check = [tempfile.gettempdir()]
        if output_dir:
            dirs_to_check.append(output_dir)
        
        for dir_path in dirs_to_check:
            try:
                # Ensure directory exists
                os.makedirs(dir_path, exist_ok=True)
                
                # Try to create a test file
                test_file = os.path.join(dir_path, f".preflight_test_{os.getpid()}.tmp")
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
                
                logger.debug("Write permission OK: %s", dir_path)
            
            except PermissionError:
                errors.append(PreflightError(
                    path=dir_path,
                    filename="",
                    error_type="write_permission",
                    severity=PreflightErrorType.CRITICAL,
                    message=f"No write permission for directory: {dir_path}"
                ))
            except Exception as e:
                logger.warning("Could not verify write access to %s: %s", dir_path, e)
        
        return errors


# =============================================================================
# Legacy Preflight Warnings (Backward Compatibility)
# =============================================================================



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
    Detect if a CUDA or Apple MPS GPU is available for PyTorch.
    
    Returns:
        True if GPU available, False otherwise.
    """
    try:
        import torch

        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            logger.info("CUDA GPU detected: %s", device_name)
            return True

        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            logger.info("Apple MPS GPU detected")
            return True

        logger.info("GPU not detected, using CPU")
        return False
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
