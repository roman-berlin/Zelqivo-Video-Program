"""Centralised logging configuration for MultiCamEditor.

This module provides a single function, :func:`configure_logging`, which
initialises the root Python logging system with a sensible default
configuration.  It sets the log level to ``INFO`` and formats log
messages with a timestamp, log level, logger name and the message.

Logs are written to both the console (StreamHandler) and to a rotating
log file in the user's AppData directory (Windows) or home directory.
The file handler uses RotatingFileHandler to limit disk usage.

Example:

    >>> from multicam_editor.logging_setup import configure_logging
    >>> configure_logging()
    >>> import logging
    >>> logging.getLogger(__name__).info("Hello from logger")

"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_DEF_FMT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_LOG_FILE_NAME = "zelqivo.log"
_MAX_LOG_BYTES = 1 * 1024 * 1024  # 1 MB per log file
_BACKUP_COUNT = 5  # Keep 5 rotated log files


def _get_log_directory() -> Path:
    """Return the log directory path, creating it if necessary.
    
    On Windows: %LOCALAPPDATA%/Zelqivo/logs/
    On other platforms: ~/.zelqivo/logs/
    
    Returns:
        Path to the log directory.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        log_dir = base / "Zelqivo" / "logs"
    else:
        log_dir = Path.home() / ".zelqivo" / "logs"
    return log_dir


def _create_file_handler() -> logging.Handler | None:
    """Create a rotating file handler with safe error handling.
    
    Returns:
        A RotatingFileHandler if successful, None if directory creation
        or file access fails.
    """
    try:
        log_dir = _get_log_directory()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / _LOG_FILE_NAME
        
        handler = RotatingFileHandler(
            log_path,
            maxBytes=_MAX_LOG_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(_DEF_FMT))
        return handler
    except (OSError, PermissionError) as e:
        # Log to stderr but don't crash the application
        print(f"WARNING: Could not create log file: {e}", file=sys.stderr)
        return None


def configure_logging(level: int = logging.INFO) -> None:
    """Initialise the root logger with console and file handlers.

    A call to :func:`configure_logging` installs handlers on the root
    logger if no handlers have been configured yet.  It then sets the
    root logger's level to ``level``.  Subsequent calls are idempotent:
    additional handlers are not added and the existing handler remains
    unchanged.  This behaviour prevents test suites from accumulating
    duplicate handlers when :func:`configure_logging` is invoked multiple
    times.

    Handlers installed:
        - StreamHandler: logs to console (always)
        - RotatingFileHandler: logs to file (if directory is writable)

    Args:
        level: The logging level to use for the root logger.  Defaults
            to :data:`logging.INFO`.
    """
    root = logging.getLogger()
    # Only attach new handlers the first time.  Subsequent calls will
    # reuse the existing handlers.
    if not root.handlers:
        # Console handler (always added)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(_DEF_FMT))
        root.addHandler(console_handler)
        
        # File handler (added if possible, fails gracefully)
        file_handler = _create_file_handler()
        if file_handler:
            root.addHandler(file_handler)
    
    # Always set the level so that later calls can raise or lower it.
    root.setLevel(level)