from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..config import APP_LOG_DIR, ensure_app_dirs


def configure_logging(log_file: Path | None = None) -> logging.Logger:
    ensure_app_dirs()
    target_file = log_file or APP_LOG_DIR / "app.log"
    target_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("v2e")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        target_file,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger
