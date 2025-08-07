"""Logging configuration for the application."""

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """
    Configure the root logger for the application.
    """
    logger = logging.getLogger()
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
