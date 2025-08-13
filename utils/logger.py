"""Logging configuration for the application."""

from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger for the application."""
    logger = logging.getLogger()
    logger.setLevel(level)

    # Avoid duplicate handlers in dev sessions and unit tests.
    if any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)