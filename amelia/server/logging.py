"""Structured logging configuration for the server."""
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import structlog


# Captured logs for testing
_captured_logs: list[dict[str, Any]] = []
_capturing = False


def _capture_processor(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor that captures logs for testing."""
    if _capturing:
        _captured_logs.append(event_dict.copy())
    return event_dict


def configure_logging(json_output: bool = True) -> Any:
    """Configure structured logging for the server.

    Args:
        json_output: If True, output JSON. If False, output console format.

    Returns:
        Configured structlog logger.
    """
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _capture_processor,
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()


@contextmanager
def capture_logs() -> Generator[list[dict[str, Any]], None, None]:
    """Context manager to capture log entries for testing.

    Yields:
        List of captured log entries as dicts.
    """
    global _capturing, _captured_logs
    _captured_logs = []
    _capturing = True
    try:
        yield _captured_logs
    finally:
        _capturing = False


# Default logger instance
logger = configure_logging()
