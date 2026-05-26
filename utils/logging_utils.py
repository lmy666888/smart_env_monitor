"""Logging setup."""

import logging
import sys
from typing import Optional, Type


def setup_logging(level_name: str = "INFO", logger_name: str = "smart_env_monitor") -> None:
    """Configure root logging."""
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger(logger_name).setLevel(level)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    base = "smart_env_monitor"
    return logging.getLogger(f"{base}.{name}" if name else base)
