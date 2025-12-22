"""Export debug package (zip) for QA/support.

Creates a zip containing:
- app logs (if file logging enabled)
- diarization.json
- cut_plan.json
- processing_summary.json
- environment_info.json (app version, ffmpeg/ffprobe paths)
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from .qa_artifacts import get_last_run_folder

logger = logging.getLogger(__name__)

APP_VERSION = "0.1.0"


def _get_ffmpeg_path() -> Optional[str]:
    """Get ffmpeg executable path, or None if not found."""
    try:
        from ..utils.ffmpeg import _find_ffmpeg
        return _find_ffmpeg()
    except Exception:
        return None


def _get_ffprobe_path() -> Optional[str]:
    """Get ffprobe executable path, or None if not found."""
    try:
        from ..utils.ffprobe import _find_ffprobe
        return _find_ffprobe()
    except Exception:
        return None


def _collect_environment_info() -> dict:
    """Collect environment info for debug package."""
    return {
        "app_version": APP_VERSION,
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "ffmpeg_path": _get_ffmpeg_path(),
        "ffprobe_path": _get_ffprobe_path(),
    }


def export_debug_package(output_path: str) -> tuple[bool, str, list[str]]:
    """Export debug package to specified zip path.

    Args:
        output_path: Where to save the zip file

    Returns:
        Tuple of (success, message, warnings)
        - success: True if zip was created
        - message: Success/error message
        - warnings: List of warnings about missing files
    """
    warnings: list[str] = []
    files_added: list[str] = []

    # Create temp directory for staging
    temp_dir = tempfile.mkdtemp(prefix="multicam_debug_")
    try:
        # 1. Write environment_info.json
        env_info = _collect_environment_info()
        env_path = Path(temp_dir) / "environment_info.json"
        with open(env_path, "w", encoding="utf-8") as f:
            json.dump(env_info, f, indent=2)
        files_added.append("environment_info.json")
        logger.info("Debug export: added environment_info.json")

        # 2. Copy QA artifacts from last run folder
        run_folder = get_last_run_folder()
        if run_folder and run_folder.exists():
            qa_files = [
                "diarization.json",
                "cut_plan.json",
                "processing_summary.json",
            ]
            for fname in qa_files:
                src = run_folder / fname
                if src.exists():
                    dst = Path(temp_dir) / fname
                    shutil.copy2(src, dst)
                    files_added.append(fname)
                    logger.info("Debug export: added %s", fname)
                else:
                    warnings.append(f"{fname} not found in run folder")
                    logger.warning("Debug export: %s not found", fname)
        else:
            warnings.append("No QA run folder found (process videos first)")
            logger.warning("Debug export: no run folder found")

        # 3. Collect app logs (from root logger handlers if file handler exists)
        log_collected = _collect_logs_to_dir(temp_dir)
        if log_collected:
            files_added.append("app.log")
            logger.info("Debug export: added app.log")
        else:
            warnings.append("No log file available (logs only in console)")

        # 4. Create zip
        if not files_added:
            return False, "No files to export", warnings

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in files_added:
                src = Path(temp_dir) / fname
                if src.exists():
                    zf.write(src, fname)

        logger.info("Debug package exported: %s (%d files)", output_path, len(files_added))
        return True, f"Exported {len(files_added)} file(s)", warnings

    except Exception as e:
        logger.error("Debug export failed: %s", e, exc_info=True)
        return False, f"Export failed: {e}", warnings
    finally:
        # Cleanup temp dir
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def _collect_logs_to_dir(temp_dir: str) -> bool:
    """Attempt to collect logs from file handlers.

    Returns True if logs were collected.
    """
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            try:
                log_path = handler.baseFilename
                if os.path.isfile(log_path):
                    dst = Path(temp_dir) / "app.log"
                    shutil.copy2(log_path, dst)
                    return True
            except Exception:
                pass

    # No file handler found - create a summary from recent log records
    # Since we use StreamHandler by default, we don't have persistent logs
    return False
