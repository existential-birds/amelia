"""Logging configuration with Amelia dashboard color palette.

Uses colors from the Amelia dashboard for consistent branding across
CLI and web interfaces.
"""

import random
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

# ANSI gradient effect using RGB escape codes
GRADIENT_AMELIA = [
    "\033[38;2;255;200;87m",   # Gold
    "\033[38;2;212;178;90m",   # Gold-sage transition
    "\033[38;2;169;156;93m",   # Mid transition
    "\033[38;2;126;134;96m",   # Sage transition
    "\033[38;2;91;138;114m",   # Sage green
]
RESET = "\033[0m"


def _make_gradient_text(text: str, colors: list[str]) -> str:
    """Apply a gradient effect across text characters.

    Args:
        text: Input text to colorize.
        colors: List of ANSI escape codes for gradient colors.

    Returns:
        Text string with ANSI gradient coloring applied.
    """
    if not text:
        return ""

    result = []
    step = max(1, len(text) // len(colors))

    for i, char in enumerate(text):
        color_idx = min(i // step, len(colors) - 1)
        result.append(f"{colors[color_idx]}{char}")

    result.append(RESET)
    return "".join(result)


def _amelia_banner() -> str:
    """Generate the Amelia startup banner with gradient.

    Returns:
        Multi-line string containing the styled ASCII art banner.
    """
    # Generate random number between 14-1000
    days_until_agi = random.randint(14, 1000)
    days_until_agi_text = f"{days_until_agi}"

    # Center the text within 39 chars (inner box width)
    inner_width = 39
    centered_text = days_until_agi_text.center(inner_width)

    lines = [
        "",
        _make_gradient_text("    ╔═══════════════════════════════════════╗", GRADIENT_AMELIA),
        _make_gradient_text("    ║                                       ║", GRADIENT_AMELIA),
        _make_gradient_text("    ║   DAYS REMAINING UNTIL AGI ACHIEVED:  ║", GRADIENT_AMELIA),
        _make_gradient_text(f"    ║{centered_text}║", GRADIENT_AMELIA),
        _make_gradient_text("    ║                                       ║", GRADIENT_AMELIA),
        _make_gradient_text("    ╚═══════════════════════════════════════╝", GRADIENT_AMELIA),
        "",
    ]
    return "\n".join(lines)


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


def configure_logging(level: str = "INFO", show_banner: bool = False) -> None:
    """Configure loguru logging with Amelia dashboard colors.

    Args:
        level: Minimum log level to display.
        show_banner: Whether to print the Amelia startup banner.
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

    if show_banner:
        # Print banner directly (bypasses log formatting)
        sys.stderr.write(_amelia_banner())
        sys.stderr.flush()


def log_server_startup(host: str, port: int, database_path: str, version: str) -> None:
    """Log server startup information with styled formatting.

    Args:
        host: Server bind host.
        port: Server bind port.
        database_path: Path to SQLite database.
        version: Application version.
    """
    # Print banner
    sys.stderr.write(_amelia_banner())
    sys.stderr.flush()

    # Log configuration details with consistent styling
    gold = "\033[38;2;255;200;87m"
    sage = "\033[38;2;91;138;114m"
    blue = "\033[38;2;91;155;213m"
    muted = "\033[38;2;136;168;150m"
    reset = RESET

    config_lines = [
        f"  {muted}Version:{reset}  {gold}v{version}{reset}",
        f"  {muted}Server:{reset}   {blue}http://{host}:{port}{reset}",
        f"  {muted}Database:{reset} {sage}{database_path}{reset}",
        "",
    ]
    sys.stderr.write("\n".join(config_lines))
    sys.stderr.flush()
