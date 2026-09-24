"""Logging configuration for the CLI (roadmap section 64).

Structured, level-based logging is available to every layer through the
``songlab`` logger hierarchy. Library modules must never configure logging
themselves; only the CLI entry point does that.
"""

from __future__ import annotations

import logging
import sys

__all__ = ["LOGGER_NAME", "configure_logging", "get_logger"]

LOGGER_NAME = "songlab"

#: Verbosity level mapped to logging levels. ``0`` is the default.
_LEVELS = {
    -1: logging.WARNING,  # --quiet
    0: logging.INFO,
    1: logging.DEBUG,  # --verbose
    2: logging.DEBUG,  # --debug (adds tracebacks)
}


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger inside the ``songlab`` hierarchy."""
    if not name or name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def configure_logging(verbosity: int = 0, *, force: bool = True) -> logging.Logger:
    """Configure the root ``songlab`` logger.

    Args:
        verbosity: ``-1`` quiet, ``0`` normal, ``1`` verbose, ``2`` debug.
        force: Replace handlers installed by a previous call (used by tests).

    Returns:
        The configured ``songlab`` logger.
    """
    verbosity = max(-1, min(2, verbosity))
    level = _LEVELS[verbosity]
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    if force:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    handler = logging.StreamHandler(stream=sys.stderr)
    if verbosity >= 1:
        handler.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)
    return logger
