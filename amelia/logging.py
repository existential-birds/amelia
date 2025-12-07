"""Logging configuration with Amelia dashboard color palette.

Uses colors from the Amelia dashboard for consistent branding across
CLI and web interfaces.
"""

import sys
from typing import TYPE_CHECKING

from loguru import logger


if TYPE_CHECKING:
    from loguru import Record


# Dashboard color palette (from amelia-dashboard-dark.html)
COLORS = {
    "gold": "#FFC857",  # Active, warnings, primary accent
    "sage_green": "#5B8A72",  # Success, completed
    "forest_dark": "#0D1A12",  # Background (not for console)
    "teal_dark": "#1F332E",  # Container background
    "sage_muted": "#88A896",  # Secondary text, debug
    "cream": "#EFF8E2",  # Primary text
    "rust_red": "#A33D2E",  # Error, blocked
    "blue": "#5B9BD5",  # Info, identifiers
    "sage_light": "#C8D9CE",  # Message text
    "sage_pending": "#4A5C54",  # Pending states
}

# ANSI reset code
RESET = "\033[0m"


def _log_format(record: "Record") -> str:
    """Custom log format with dashboard colors.

    Args:
        record: Loguru record containing log metadata and message.

    Returns:
        Format string with ANSI color codes for the log message.

    Note:
        Colors by level:
            - DEBUG: sage muted (#88A896)
            - INFO: blue (#5B9BD5)
            - SUCCESS: sage green (#5B8A72)
            - WARNING: gold (#FFC857)
            - ERROR/CRITICAL: rust red (#A33D2E)
    """
    level = record["level"].name

    # Color mappings using loguru's color tag syntax
    level_colors = {
        "TRACE": f"<fg {COLORS['sage_pending']}>",
        "DEBUG": f"<fg {COLORS['sage_muted']}>",
        "INFO": f"<fg {COLORS['blue']}>",
        "SUCCESS": f"<fg {COLORS['sage_green']}>",
        "WARNING": f"<fg {COLORS['gold']}>",
        "ERROR": f"<fg {COLORS['rust_red']}>",
        "CRITICAL": f"<fg {COLORS['rust_red']}><bold>",
    }

    color = level_colors.get(level, f"<fg {COLORS['cream']}>")

    # Loguru uses </> to close any open color tag
    close = "</>"

    # Format: timestamp | level | module | message
    # Using gradient-inspired styling with dashboard colors
    fmt = (
        f"<fg {COLORS['sage_muted']}>{{time:HH:mm:ss}}{close}"
        f" <fg {COLORS['sage_pending']}>│{close} "
        f"{color}{{level: <8}}{close}"
        f"<fg {COLORS['sage_pending']}>│{close} "
        f"<fg {COLORS['sage_muted']}>{{name}}{close}"
        f"<fg {COLORS['sage_pending']}>:{close}"
        f"<fg {COLORS['cream']}>{{message}}{close}\n"
    )

    # Add exception formatting if present
    if record["exception"]:
        fmt += "{exception}\n"

    return fmt


def configure_logging(level: str = "INFO") -> None:
    """Configure loguru logging with Amelia dashboard colors.

    Args:
        level: Minimum log level to display.
    """
    # Remove default handler
    logger.remove()

    # Add custom formatted handler
    logger.add(
        sys.stderr,
        level=level,
        format=_log_format,
        colorize=True,
    )


def log_server_startup(host: str, port: int, database_path: str, version: str) -> None:
    """Log server startup information with styled formatting.

    Args:
        host: Server bind host.
        port: Server bind port.
        database_path: Path to SQLite database.
        version: Application version.
    """
    # Log configuration details with consistent styling
    gold = "\033[38;2;255;200;87m"
    sage = "\033[38;2;91;138;114m"
    blue = "\033[38;2;91;155;213m"
    muted = "\033[38;2;136;168;150m"

    config_lines = [
        f"  {muted}Version:{RESET}  {gold}v{version}{RESET}",
        f"  {muted}Server:{RESET}   {blue}http://{host}:{port}{RESET}",
        f"  {muted}Database:{RESET} {sage}{database_path}{RESET}",
        "",
    ]
    sys.stderr.write("\n".join(config_lines))
    sys.stderr.flush()
