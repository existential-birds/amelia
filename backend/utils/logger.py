"""
Structured logging setup using structlog and rich.
"""
import logging
import sys
from typing import Optional
import structlog
from rich.logging import RichHandler


def setup_logger(
    name: str,
    level: str = "INFO"
) -> logging.Logger:
    """
    Setup and return a configured logger instance.

    Args:
        name: Logger name (typically __name__)
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Setup Python logging with Rich handler
    logging.basicConfig(
        level=level.upper(),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)]
    )

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    return logger
