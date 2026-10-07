"""
PixelForge - Structured Logging
==================================

Adds a custom TRACE level below DEBUG and configures a rotating file handler
plus a console handler. Call ``configure_logging()`` once at startup (both CLI
and GUI entry points do this).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys

TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")


def _trace(self, message, *args, **kwargs):
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kwargs)


logging.Logger.trace = _trace  # type: ignore[attr-defined]


def configure_logging(log_dir: str = "logs", level: str = "INFO", app_name: str = "pixelforge") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(app_name)
    logger.setLevel(TRACE_LEVEL)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(threadName)-14s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, f"{app_name}.log"), maxBytes=5_000_000, backupCount=5, encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(TRACE_LEVEL)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
