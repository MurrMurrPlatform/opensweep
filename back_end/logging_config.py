"""Structured colored logger for OpenSweep."""

import logging
import os
import sys


def _setting(name: str, default: str) -> str:
    """Read from pydantic Settings so `.env` values (which pydantic-settings
    loads WITHOUT exporting to os.environ) are honored. Falls back to raw
    os.environ if settings can't be imported yet — logging is configured very
    early and must never crash on an import cycle or a bad .env."""
    try:
        from config import settings

        return str(getattr(settings, name))
    except Exception:
        return os.environ.get(name, default)

_GREY = "\x1b[38;5;245m"
_BLUE = "\x1b[38;5;111m"
_GREEN = "\x1b[38;5;114m"
_YELLOW = "\x1b[38;5;215m"
_RED = "\x1b[38;5;203m"
_RESET = "\x1b[0m"

_COLOR_FOR_LEVEL = {
    logging.DEBUG: _GREY,
    logging.INFO: _BLUE,
    logging.WARNING: _YELLOW,
    logging.ERROR: _RED,
    logging.CRITICAL: _RED,
}


class OpenSweepFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _COLOR_FOR_LEVEL.get(record.levelno, _RESET)
        service = _setting("LOG_SERVICE_NAME", "opensweep")
        ts = self.formatTime(record, "%H:%M:%S")
        tag = getattr(record, "tag", None)
        tag_str = f" {_GREEN}[{tag}]{_RESET}" if tag else ""
        message = (
            f"{_GREY}{ts}{_RESET} {color}{record.levelname:<7}{_RESET} "
            f"{_GREY}{service}{_RESET}{tag_str} {record.getMessage()}"
        )
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            message = f"{message}\n{self.formatStack(record.stack_info)}"
        return message


def _build_logger() -> logging.Logger:
    level = _setting("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(OpenSweepFormatter())
    log = logging.getLogger("opensweep")
    log.setLevel(level)
    if not log.handlers:
        log.addHandler(handler)
    log.propagate = False
    return log


logger = _build_logger()


def configure_uvicorn_logging() -> None:
    """Route uvicorn logs through the same handler so output stays cohesive."""
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        u = logging.getLogger(name)
        u.handlers = list(logger.handlers)
        u.propagate = False
        u.setLevel(logger.level)
