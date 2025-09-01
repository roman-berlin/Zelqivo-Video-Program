"""Centralised logging configuration for MultiCamEditor.

This module provides a single function, :func:`configure_logging`, which
initialises the root Python logging system with a sensible default
configuration.  It sets the log level to ``INFO`` and formats log
messages with a timestamp, log level, logger name and the message.

The configuration is applied using ``logging.basicConfig`` with
``force=True`` so it overwrites any existing handlers.  Downstream
modules should call this function once at application startup to ensure
consistent logging throughout the application.

Example:

    >>> from multicam_editor.logging_setup import configure_logging
    >>> configure_logging()
    >>> import logging
    >>> logging.getLogger(__name__).info("Hello from logger")

"""

from __future__ import annotations

import logging

_DEF_FMT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Initialise the root logger with a single ``StreamHandler``.

    A call to :func:`configure_logging` installs a stream handler on the root
    logger if no handlers have been configured yet.  It then sets the
    root logger's level to ``level``.  Subsequent calls are idempotent:
    additional handlers are not added and the existing handler remains
    unchanged.  This behaviour prevents test suites from accumulating
    duplicate handlers when :func:`configure_logging` is invoked multiple
    times.

    Args:
        level: The logging level to use for the root logger.  Defaults
            to :data:`logging.INFO`.
    """
    root = logging.getLogger()
    # Only attach a new handler the first time.  Subsequent calls will
    # reuse the existing handler.  Avoid using ``basicConfig`` here
    # because it always creates a new handler when ``force=True`` and
    # resets the configuration when ``force=False``.
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_DEF_FMT))
        root.addHandler(handler)
    # Always set the level so that later calls can raise or lower it.
    root.setLevel(level)