"""Tests for the logging setup.

These tests ensure that calling ``configure_logging`` initialises the root
logger with the expected level and that subsequent calls do not add
duplicate handlers.
"""

import logging
from multicam_editor.logging_setup import configure_logging


def test_configure_logging_idempotent() -> None:
    """Calling configure_logging multiple times should not duplicate handlers."""
    # Reset logging configuration by removing handlers from the root logger.
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    configure_logging()
    initial_handlers = list(logging.getLogger().handlers)
    assert logging.getLogger().level == logging.INFO

    # A second call should leave the handlers unchanged.
    configure_logging()
    assert list(logging.getLogger().handlers) == initial_handlers