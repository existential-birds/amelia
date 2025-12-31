"""Logging configuration with Amelia dashboard color palette.

Uses colors from the Amelia dashboard for consistent branding across
CLI and web interfaces.
"""

import json
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
    """Generate custom log format string with Amelia dashboard colors.

    Creates a colored log format using Loguru color tags. Applies different
    colors based on log level and includes structured extra fields if present.

    Args:
        record: Loguru record containing log metadata, message, and level.

    Returns:
        Formatted string with Loguru color tags for the log message.
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

    # Format: timestamp | level | module | message [extra]
    # Using gradient-inspired styling with dashboard colors
    fmt = (
        f"<fg {COLORS['sage_muted']}>{{time:HH:mm:ss}}{close}"
        f" <fg {COLORS['sage_pending']}>│{close} "
        f"{color}{{level: <8}}{close}"
        f"<fg {COLORS['sage_pending']}>│{close} "
        f"<fg {COLORS['sage_muted']}>{{name}}{close}"
        f"<fg {COLORS['sage_pending']}>:{close}"
        f"<fg {COLORS['cream']}>{{message}}{close}"
    )

    # Add structured fields if present
    extra = record["extra"]
    if extra:
        # Format extra fields as key=value pairs
        extra_str = " ".join(f"{k}={v!r}" for k, v in extra.items())
        # Escape braces to prevent Loguru format string injection
        extra_str = extra_str.replace("{", "{{").replace("}", "}}")
        fmt += f" <fg {COLORS['sage_muted']}>│ {extra_str}{close}"

    fmt += "\n"

    # Add exception formatting if present
    if record["exception"]:
        fmt += "{exception}\n"

    return fmt


def configure_logging(level: str = "INFO") -> None:
    """Configure loguru logging with Amelia dashboard color palette.

    Removes default handler and adds custom formatted handler with
    dashboard-themed colors and structured field support.

    Args:
        level: Minimum log level to display (e.g., "DEBUG", "INFO", "WARNING").
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
    """Log server startup information with Amelia-styled formatting.

    Outputs colored server configuration details including version, URL,
    and database path using the Amelia dashboard color palette.

    Args:
        host: Server bind host address.
        port: Server bind port number.
        database_path: Path to SQLite database file.
        version: Application version string.
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


def _ansi_color(hex_color: str) -> str:
    """Convert hex color code to ANSI 24-bit escape sequence.

    Args:
        hex_color: Hex color string with or without # prefix (e.g., "#FFC857").

    Returns:
        ANSI escape code for 24-bit RGB foreground color.
    """
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"\033[38;2;{r};{g};{b}m"


def log_claude_result(
    result_type: str,
    content: str | None = None,
    session_id: str | None = None,
    tool_name: str | None = None,
    tool_input: dict[str, object] | None = None,
    result_text: str | None = None,
    subtype: str | None = None,
    duration_ms: int | None = None,
    num_turns: int | None = None,
    cost_usd: float | None = None,
) -> None:
    """Pretty-print Claude CLI stream events with dashboard color styling.

    Formats different Claude CLI event types (assistant messages, tool calls,
    results, errors, system messages) with visual distinction using the
    Amelia dashboard color palette. Outputs to stderr.

    Args:
        result_type: Event type (assistant, tool_use, result, error, system).
        content: Text content for assistant/error/system events.
        session_id: Session ID from result events for session continuity.
        tool_name: Tool name for tool_use events.
        tool_input: Tool input parameters dictionary for tool_use events.
        result_text: Final result text from result events.
        subtype: Result subtype indicating success or error.
        duration_ms: Execution duration in milliseconds from result events.
        num_turns: Number of conversation turns from result events.
        cost_usd: Total cost in USD from result events.
    """
    # ANSI color codes from palette
    gold = _ansi_color(COLORS["gold"])
    sage = _ansi_color(COLORS["sage_green"])
    blue = _ansi_color(COLORS["blue"])
    muted = _ansi_color(COLORS["sage_muted"])
    rust = _ansi_color(COLORS["rust_red"])
    cream = _ansi_color(COLORS["cream"])
    pending = _ansi_color(COLORS["sage_pending"])

    # Box drawing character for visual structure
    vertical = "│"

    lines: list[str] = []

    if result_type == "assistant":
        # Claude's thinking/response - use cream for main text
        header = f"{blue}◆ Claude{RESET}"
        lines.append(f"  {header}")
        if content:
            # Wrap content at ~80 chars and indent
            for line in content.split("\n"):
                wrapped = line[:120] + ("…" if len(line) > 120 else "")
                lines.append(f"  {muted}{vertical}{RESET} {cream}{wrapped}{RESET}")

    elif result_type == "tool_use":
        # Tool execution - use gold for emphasis
        header = f"{gold}⚡ Tool: {tool_name or 'unknown'}{RESET}"
        lines.append(f"  {header}")
        if tool_input:
            # Pretty-print tool input with truncation
            try:
                input_str = json.dumps(tool_input, indent=2)
                input_lines = input_str.split("\n")
                # Limit to first 10 lines to avoid log spam
                for line in input_lines[:10]:
                    lines.append(f"  {muted}{vertical}{RESET} {pending}{line}{RESET}")
                if len(input_lines) > 10:
                    lines.append(f"  {muted}{vertical}{RESET} {pending}... ({len(input_lines) - 10} more lines){RESET}")
            except (TypeError, ValueError):
                lines.append(f"  {muted}{vertical}{RESET} {pending}{str(tool_input)[:200]}{RESET}")

    elif result_type == "result":
        # Completion result - use sage green for success, rust for error
        is_success = subtype == "success"
        status_color = sage if is_success else rust
        status_icon = "✓" if is_success else "✗"
        header = f"{status_color}{status_icon} Result{RESET}"
        lines.append(f"  {header}")

        # Stats line with duration, turns, and cost
        stats_parts = []
        if duration_ms is not None:
            duration_sec = duration_ms / 1000
            if duration_sec >= 60:
                mins = int(duration_sec // 60)
                secs = duration_sec % 60
                stats_parts.append(f"{mins}m {secs:.1f}s")
            else:
                stats_parts.append(f"{duration_sec:.1f}s")
        if num_turns is not None:
            stats_parts.append(f"{num_turns} turns")
        if cost_usd is not None:
            stats_parts.append(f"${cost_usd:.4f}")
        if stats_parts:
            stats = f" {muted}•{RESET} ".join(
                f"{gold}{part}{RESET}" for part in stats_parts
            )
            lines.append(f"  {muted}{vertical}{RESET} {stats}")

        # Session ID (truncated)
        if session_id:
            short_session = session_id[:8] + "…" if len(session_id) > 8 else session_id
            lines.append(f"  {muted}{vertical}{RESET} {muted}session:{RESET} {blue}{short_session}{RESET}")

        # Result text preview (first ~200 chars, first line only)
        if result_text:
            # Get first non-empty line
            first_line = result_text.strip().split("\n")[0]
            total_lines = len(result_text.strip().split("\n"))
            preview = first_line[:200] + ("…" if len(first_line) > 200 else "")
            lines.append(f"  {muted}{vertical}{RESET} {cream}{preview}{RESET}")
            if total_lines > 1:
                lines.append(f"  {muted}{vertical} ({total_lines} lines total){RESET}")

    elif result_type == "error":
        # Error - use rust red
        header = f"{rust}✗ Error{RESET}"
        lines.append(f"  {header}")
        if content:
            for line in content.split("\n")[:5]:  # Limit error lines
                lines.append(f"  {muted}{vertical}{RESET} {rust}{line}{RESET}")

    elif result_type == "system":
        # System message - use muted sage
        header = f"{muted}○ System{RESET}"
        lines.append(f"  {header}")
        if content:
            lines.append(f"  {muted}{vertical} {content}{RESET}")

    # Output to stderr (same as loguru)
    if lines:
        sys.stderr.write("\n".join(lines) + "\n")
        sys.stderr.flush()
