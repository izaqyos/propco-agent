"""Structured logging via structlog: JSON in containers, readable console locally.

Per-turn context (``thread_id``, ``request_id``) is bound with contextvars so every line a
turn emits carries it. Nothing sensitive is logged: no prompts, no API keys.
"""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog
from structlog.typing import FilteringBoundLogger


def configure_logging(*, json_output: bool, level: str = "INFO") -> None:
    """(Re)configure structlog. Safe to call more than once."""
    numeric_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric_level)
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> FilteringBoundLogger:
    """A bound logger for ``name``."""
    logger: FilteringBoundLogger = structlog.get_logger(name)
    return logger


def new_request_id() -> str:
    """Short, unique id for one user turn."""
    return uuid.uuid4().hex[:12]


@contextmanager
def bind_request(**context: Any) -> Iterator[None]:
    """Attach ``context`` (thread_id, request_id, ...) to every log line inside the block."""
    structlog.contextvars.bind_contextvars(**context)
    try:
        yield
    finally:
        structlog.contextvars.unbind_contextvars(*context)
