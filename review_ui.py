"""
Neon terminal UI components for review_fix_loop.py.

Implements a 1980s neon terminal aesthetic using the Rich library,
with a Dracula-based color theme and animated elements.
"""

import re
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pyfiglet
from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.style import Style
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme


# =============================================================================
# Color Theme (Dracula-based)
# =============================================================================

NEON_COLORS = {
    "background": "#282A36",
    "foreground": "#F8F8F2",
    "red": "#FF5555",
    "green": "#50FA7B",
    "yellow": "#F1FA8C",
    "purple": "#BD93F9",
    "pink": "#FF79C6",
    "cyan": "#8BE9FD",
    "orange": "#FFB86C",
}

NEON_THEME = Theme({
    "neon.bg": NEON_COLORS["background"],
    "neon.fg": NEON_COLORS["foreground"],
    "neon.red": NEON_COLORS["red"],
    "neon.green": NEON_COLORS["green"],
    "neon.yellow": NEON_COLORS["yellow"],
    "neon.purple": NEON_COLORS["purple"],
    "neon.pink": NEON_COLORS["pink"],
    "neon.cyan": NEON_COLORS["cyan"],
    "neon.orange": NEON_COLORS["orange"],
    # Semantic styles
    "neon.error": f"bold {NEON_COLORS['red']}",
    "neon.success": f"bold {NEON_COLORS['green']}",
    "neon.warning": f"bold {NEON_COLORS['yellow']}",
    "neon.info": NEON_COLORS["cyan"],
    "neon.dim": f"dim {NEON_COLORS['foreground']}",
    "neon.tool": f"bold {NEON_COLORS['pink']}",
    "neon.path": NEON_COLORS["cyan"],
    "neon.number": NEON_COLORS["yellow"],
    "neon.string": NEON_COLORS["orange"],
})

GRADIENT_COLORS = [
    "#881177",
    "#aa3355",
    "#cc6666",
    "#ee9944",
    "#eedd00",
    "#99dd55",
    "#44dd88",
    "#22ccbb",
    "#00bbcc",
    "#0099cc",
    "#3366bb",
    "#663399",
]

# Status configuration mapping
STATUS_CONFIG = {
    "pending": {"icon": "\u23f2", "color": NEON_COLORS["yellow"]},  # ⏲
    "in_progress": {"icon": "\u2b95", "color": NEON_COLORS["cyan"]},  # ⮕
    "completed": {"icon": "\u2714", "color": NEON_COLORS["green"]},  # ✔
    "failed": {"icon": "\u2717", "color": NEON_COLORS["red"]},  # ✗
}


# =============================================================================
# NeonConsole Class
# =============================================================================


class NeonConsole:
    """
    Wrapper around Rich Console providing themed output methods.

    This class encapsulates all the neon-styled output functionality,
    providing a consistent visual theme across all terminal output.
    """

    def __init__(self, console: Console | None = None) -> None:
        """
        Initialize the NeonConsole.

        Args:
            console: Optional Rich Console instance. If not provided,
                    a new Console with the neon theme will be created.
        """
        self.console = console or Console(theme=NEON_THEME)
        self._throbber = NeonThrobber()

    def print(self, *args: Any, **kwargs: Any) -> None:
        """Pass-through to underlying console.print()."""
        self.console.print(*args, **kwargs)

    def clear(self) -> None:
        """Clear the terminal screen."""
        self.console.clear()


def create_console() -> Console:
    """Create a Rich Console with neon theme applied."""
    return Console(theme=NEON_THEME)


# =============================================================================
# Header Component
# =============================================================================


def print_header(console: Console, text: str) -> None:
    """
    Print a neon-bordered header panel.

    Creates a prominent header with pink border and purple text,
    using double-edge box styling for a retro terminal look.

    Args:
        console: Rich Console instance for output.
        text: The header text to display.
    """
    header_panel = Panel(
        Text(text, style=Style(color=NEON_COLORS["purple"], bold=True)),
        box=box.DOUBLE_EDGE,
        border_style=Style(color=NEON_COLORS["pink"]),
        padding=(0, 2),
    )
    console.print(header_panel)


# =============================================================================
# ASCII Art Header Component
# =============================================================================

# Gradient colors for ASCII art header (cyan -> pink -> purple)
ASCII_GRADIENT_COLORS = [
    "#8BE9FD",  # Cyan (Dracula)
    "#7DDFFA",
    "#6FD5F7",
    "#61CBF4",
    "#53C1F1",
    "#45B7EE",
    "#5AABE5",
    "#6F9FDC",
    "#8493D3",
    "#9987CA",
    "#AE7BC1",
    "#C36FB8",
    "#D863AF",
    "#ED57A6",
    "#FF79C6",  # Pink (Dracula)
    "#F07DC1",
    "#E181BC",
    "#D285B7",
    "#C389B2",
    "#B48DAD",
    "#A591A8",
    "#9695A3",
    "#87999E",
    "#A08FAB",
    "#B985B8",
    "#BD93F9",  # Purple (Dracula)
]


def _interpolate_color(color1: str, color2: str, t: float) -> str:
    """
    Interpolate between two hex colors.

    Args:
        color1: Starting hex color (e.g., "#8BE9FD").
        color2: Ending hex color (e.g., "#FF79C6").
        t: Interpolation factor (0.0 = color1, 1.0 = color2).

    Returns:
        Interpolated hex color string.
    """
    r1, g1, b1 = int(color1[1:3], 16), int(color1[3:5], 16), int(color1[5:7], 16)
    r2, g2, b2 = int(color2[1:3], 16), int(color2[3:5], 16), int(color2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _get_gradient_color(position: float) -> str:
    """
    Get a color from the gradient based on position (0.0 to 1.0).

    The gradient smoothly transitions: cyan -> pink -> purple.

    Args:
        position: Position in gradient (0.0 = start, 1.0 = end).

    Returns:
        Hex color string at the given position.
    """
    # Clamp position
    position = max(0.0, min(1.0, position))

    # Map position to gradient array index
    index = position * (len(ASCII_GRADIENT_COLORS) - 1)
    lower_idx = int(index)
    upper_idx = min(lower_idx + 1, len(ASCII_GRADIENT_COLORS) - 1)

    # Interpolate between the two nearest colors
    t = index - lower_idx
    return _interpolate_color(
        ASCII_GRADIENT_COLORS[lower_idx],
        ASCII_GRADIENT_COLORS[upper_idx],
        t,
    )


def print_ascii_header(console: Console, text: str) -> None:
    """
    Print a visually striking ASCII art header with neon gradient.

    Uses pyfiglet to generate ASCII art and applies a horizontal
    gradient from cyan (#8BE9FD) -> pink (#FF79C6) -> purple (#BD93F9)
    character-by-character across each line.

    Args:
        console: Rich Console instance for output.
        text: The text to render as ASCII art.
    """
    # Generate ASCII art using pyfiglet with 'ansi_shadow' font
    # This font creates a nice blocky 3D effect
    try:
        ascii_art = pyfiglet.figlet_format(text, font="ansi_shadow")
    except pyfiglet.FigletError:
        # Fallback to 'slant' if ansi_shadow not available
        try:
            ascii_art = pyfiglet.figlet_format(text, font="slant")
        except pyfiglet.FigletError:
            # Final fallback to standard font
            ascii_art = pyfiglet.figlet_format(text, font="standard")

    lines = ascii_art.rstrip("\n").split("\n")

    # Find the maximum line width for gradient calculation
    max_width = max(len(line) for line in lines) if lines else 1

    # Build the gradient text
    gradient_text = Text()

    for line_idx, line in enumerate(lines):
        if not line.strip():
            # Empty or whitespace-only line
            gradient_text.append(line + "\n")
            continue

        # Apply gradient character by character
        for char_idx, char in enumerate(line):
            if char == " ":
                gradient_text.append(char)
            else:
                # Calculate position in gradient based on character position
                position = char_idx / max_width if max_width > 0 else 0
                color = _get_gradient_color(position)
                gradient_text.append(char, style=Style(color=color, bold=True))

        if line_idx < len(lines) - 1:
            gradient_text.append("\n")

    # Create a subtle tagline
    tagline = Text()
    tagline.append("\n")
    tagline.append("    ", style=Style())
    tagline.append("~", style=Style(color=NEON_COLORS["purple"], dim=True))
    tagline.append(" automated code review ", style=Style(color=NEON_COLORS["pink"], dim=True))
    tagline.append("&", style=Style(color=NEON_COLORS["cyan"], dim=True))
    tagline.append(" fix loop ", style=Style(color=NEON_COLORS["pink"], dim=True))
    tagline.append("~", style=Style(color=NEON_COLORS["purple"], dim=True))

    # Combine ASCII art and tagline
    full_content = Text()
    full_content.append_text(gradient_text)
    full_content.append_text(tagline)

    # Create panel with dim purple border for subtle framing
    panel = Panel(
        full_content,
        box=box.DOUBLE_EDGE,
        border_style=Style(color=NEON_COLORS["purple"], dim=True),
        padding=(0, 2),
    )

    console.print()  # Add some spacing before
    console.print(panel)


# =============================================================================
# Phase Component
# =============================================================================


def print_phase(
    console: Console,
    phase_num: int,
    description: str,
    status: str = "in_progress",
) -> None:
    """
    Print a phase indicator with status.

    Displays a numbered phase with an appropriate status icon and
    color-coded border based on the current status.

    Args:
        console: Rich Console instance for output.
        phase_num: The phase number to display.
        description: Description of the phase.
        status: One of "pending", "in_progress", "completed", "failed".
    """
    config = STATUS_CONFIG.get(status, STATUS_CONFIG["pending"])
    icon = config["icon"]
    color = config["color"]

    phase_text = Text()
    phase_text.append(f"{icon} ", style=Style(color=color))
    phase_text.append(f"Phase {phase_num}: ", style=Style(color=color, bold=True))
    phase_text.append(description, style=Style(color=NEON_COLORS["foreground"]))

    panel = Panel(
        phase_text,
        box=box.ROUNDED,
        border_style=Style(color=color),
        padding=(0, 1),
    )
    console.print(panel)


# =============================================================================
# Pill Badge Component
# =============================================================================


def pill(text: str, bg_color: str, fg_color: str) -> Text:
    """
    Create a pill-shaped badge with the given colors.

    Uses the pattern: [bg]foreground[/bg] to create a badge effect
    with half-block characters on the edges.

    Args:
        text: The text to display inside the pill.
        bg_color: Background color hex code.
        fg_color: Foreground (text) color hex code.

    Returns:
        Rich Text object containing the styled pill.
    """
    result = Text()
    # Left edge
    result.append("\u258c", style=Style(color=bg_color))
    # Center text with background
    result.append(text, style=Style(color=fg_color, bgcolor=bg_color, bold=True))
    # Right edge
    result.append("\u2590", style=Style(color=bg_color))
    return result


# =============================================================================
# Tool Call Component
# =============================================================================

# Pattern for tool argument colorization
_TOOL_ARG_PATTERN = re.compile(r"(\w+)=((?:'[^']*'|\"[^\"]*\"|[^,\s]+))")


def _colorize_tool_args(args: dict[str, object]) -> Text:
    """
    Apply neon syntax highlighting to tool call arguments.

    Colorizes parameter names and values based on their types:
    - Keys in cyan
    - Strings in orange (paths in cyan)
    - Numbers in yellow
    - Booleans in purple

    Args:
        args: Dictionary of argument key-value pairs.

    Returns:
        Rich Text with neon styling applied.
    """
    result = Text()

    for i, (key, value) in enumerate(args.items()):
        if i > 0:
            result.append(", ", style=Style(color=NEON_COLORS["foreground"]))

        # Key in cyan
        result.append(str(key), style=Style(color=NEON_COLORS["cyan"]))
        result.append("=", style=Style(color=NEON_COLORS["purple"]))

        # Value styling based on type
        if isinstance(value, bool):
            # Boolean in purple
            result.append(str(value), style=Style(color=NEON_COLORS["purple"]))
        elif isinstance(value, (int, float)):
            # Numeric value in yellow
            result.append(str(value), style=Style(color=NEON_COLORS["yellow"]))
        elif isinstance(value, str):
            # String value - check for file paths
            if "/" in value or value.endswith((".py", ".js", ".ts", ".md", ".json", ".yaml", ".yml")):
                result.append(value, style=Style(color=NEON_COLORS["cyan"]))
            else:
                result.append(value, style=Style(color=NEON_COLORS["orange"]))
        elif value is None:
            result.append("None", style=Style(color=NEON_COLORS["purple"]))
        else:
            # Other values (dicts, lists, etc.) in foreground
            result.append(str(value), style=Style(color=NEON_COLORS["foreground"]))

    return result


def print_tool_call(
    console: Console,
    name: str,
    args: dict[str, object],
    quiet_mode: bool = False,
) -> None:
    """
    Print a tool call with its arguments.

    Displays the tool name with a wrench icon, followed by the arguments
    in a styled panel. All tool calls are wrapped in a Panel with dark
    background and purple border.

    Special handling for Skill tool calls: uses sparkles icon and displays
    the skill name as a pink pill badge.

    Special handling for Bash tool calls: shows description and optionally
    the command (hidden in quiet mode).

    Args:
        console: Rich Console instance for output.
        name: Name of the tool being called.
        args: Dictionary of arguments passed to the tool.
        quiet_mode: If True, hide command details for Bash tools.
    """
    # Newline before tool call for separation
    console.print()

    # Special handling for Skill tool calls
    if name == "Skill":
        # Build header line
        header_line = Text()
        header_line.append("\u25b6 ", style=Style(color=NEON_COLORS["cyan"]))  # ▶
        header_line.append("\u2728 ", style=Style(color=NEON_COLORS["yellow"]))  # ✨
        header_line.append("Skill", style=Style(color=NEON_COLORS["cyan"], bold=True))

        # Build content
        content = Text()
        content.append_text(header_line)
        content.append("\n")

        # Extract and display skill name as cyan pill badge
        skill_name = str(args.get("skill", ""))
        skill_pill = pill(f" {skill_name} ", NEON_COLORS["cyan"], NEON_COLORS["background"])
        content.append_text(skill_pill)

        # Show args in non-quiet mode (if present)
        if not quiet_mode:
            skill_args = args.get("args")
            if skill_args:
                content.append("\n")
                content.append("args=", style=Style(color=NEON_COLORS["purple"]))
                content.append(str(skill_args), style=Style(color=NEON_COLORS["orange"]))

        panel = Panel(
            content,
            box=box.ROUNDED,
            border_style=Style(color=NEON_COLORS["cyan"]),  # Cyan border
            style=Style(bgcolor="#1e1e2e"),
            padding=(0, 1),
        )
        console.print(panel)
        return

    # Special handling for Bash tool calls
    if name == "Bash":
        # Build header line
        header_line = Text()
        header_line.append("\u25b6 ", style=Style(color=NEON_COLORS["cyan"]))  # ▶
        header_line.append("\U0001f527 ", style=Style(color=NEON_COLORS["orange"]))  # 🔧
        header_line.append("Bash", style=Style(color=NEON_COLORS["pink"], bold=True))

        # Build content
        content = Text()
        content.append_text(header_line)

        # Add description if present
        description = str(args.get("description", ""))
        if description:
            content.append("\n")
            content.append(description, style=Style(color=NEON_COLORS["cyan"]))

        # Add command if not in quiet mode
        if not quiet_mode:
            command = str(args.get("command", ""))
            if command:
                content.append("\n")
                content.append("$ ", style=Style(dim=True))
                content.append(command, style=Style(dim=True))

        panel = Panel(
            content,
            box=box.ROUNDED,
            border_style=Style(color=NEON_COLORS["purple"]),
            style=Style(bgcolor="#1e1e2e"),
            padding=(0, 1),
        )
        console.print(panel)
        return

    # Special handling for Write tool with markdown files
    if name == "Write":
        file_path = str(args.get("file_path", ""))
        content_str = str(args.get("content", ""))

        # Build header line
        header_line = Text()
        header_line.append("\u25b6 ", style=Style(color=NEON_COLORS["cyan"]))  # ▶
        header_line.append("\U0001f527 ", style=Style(color=NEON_COLORS["orange"]))  # 🔧
        header_line.append("Write", style=Style(color=NEON_COLORS["pink"], bold=True))

        # Build content with file path
        content = Text()
        content.append_text(header_line)
        content.append("\n")
        content.append("file_path=", style=Style(color=NEON_COLORS["cyan"]))
        content.append(file_path, style=Style(color=NEON_COLORS["cyan"]))

        # Check if it's a markdown file
        panel_content: Group | Text
        if file_path.endswith(".md") and content_str and not quiet_mode:
            # Render markdown content
            md_content = Markdown(content_str)
            panel_content = Group(content, Text("\n"), md_content)
        else:
            # Show truncated content preview for non-markdown files
            if content_str and not quiet_mode:
                content.append("\n")
                preview = content_str[:200] + "..." if len(content_str) > 200 else content_str
                content.append(preview, style=Style(color=NEON_COLORS["foreground"], dim=True))
            panel_content = content

        panel = Panel(
            panel_content,
            box=box.ROUNDED,
            border_style=Style(color=NEON_COLORS["purple"]),
            style=Style(bgcolor="#1e1e2e"),
            padding=(0, 1),
        )
        console.print(panel)
        return

    # Standard tool call display (other tools)
    # Build header line
    header_line = Text()
    header_line.append("\u25b6 ", style=Style(color=NEON_COLORS["cyan"]))  # ▶
    header_line.append("\U0001f527 ", style=Style(color=NEON_COLORS["orange"]))  # 🔧
    header_line.append(name, style=Style(color=NEON_COLORS["pink"], bold=True))

    # Build content
    content = Text()
    content.append_text(header_line)

    # Add formatted key=value pairs
    if args:
        content.append("\n")
        args_text = _colorize_tool_args(args)
        content.append_text(args_text)

    panel = Panel(
        content,
        box=box.ROUNDED,
        border_style=Style(color=NEON_COLORS["purple"]),
        style=Style(bgcolor="#1e1e2e"),
        padding=(0, 1),
    )
    console.print(panel)


# =============================================================================
# Tool Result Component
# =============================================================================

# Patterns for syntax highlighting in tool output
_FILE_PATH_PATTERN = re.compile(r"(\.?/?(?:[\w.-]+/)*[\w.-]+\.\w+)")
_LINE_NUMBER_PATTERN = re.compile(r"^(\s*)(\d+)([:\-\|])")
_ERROR_KEYWORDS = re.compile(r"\b(error|Error|ERROR|failed|Failed|FAILED|exception|Exception|EXCEPTION|Traceback)\b")
_SUCCESS_KEYWORDS = re.compile(r"\b(passed|Passed|PASSED|success|Success|SUCCESS|ok|OK|done|Done|DONE)\b")
_WARNING_KEYWORDS = re.compile(r"\b(warning|Warning|WARNING|warn|Warn|WARN|skip|Skip|SKIP|skipped|Skipped)\b")
_NUMBER_PATTERN = re.compile(r"\b(\d+)\b")
_STRING_PATTERN = re.compile(r"(['\"])(.*?)\1")
_ARROW_PATTERN = re.compile(r"(->|=>|-->|==>)")
_BRACKET_PATTERN = re.compile(r"([\[\]{}()])")

# Git-specific colorization patterns
_GIT_ADDED_PATTERN = re.compile(r"^(\+(?!\+\+).*|A[ \t].*)$")
_GIT_DELETED_PATTERN = re.compile(r"^(-(?!--).*|D[ \t].*)$")
_GIT_MODIFIED_PATTERN = re.compile(r"^M[ \t].*$")
_GIT_DIFF_HEADER_PATTERN = re.compile(r"^(@@.*|diff --git.*|index .*)$")
_GIT_FILE_HEADER_PATTERN = re.compile(r"^(\+\+\+|---).*$")

# Bash-specific patterns for manual colorization
_SHELL_VAR_PATTERN = re.compile(r"(\$\{?\w+\}?)")
_SHELL_PROMPT_PATTERN = re.compile(r"^([$#>] )")
_PIPE_REDIRECT_PATTERN = re.compile(r"(\||>>|2>&1|>&2|&>|<|>)")
_COMMAND_PATTERN = re.compile(r"^(git|npm|pytest|python|uv|cd|ls|cat|grep|ruff|mypy|pip|docker|make|curl|wget|rm|mv|cp|mkdir|echo|export|source|bash|sh|zsh)\b")

# Patterns for shell syntax detection (for Rich Syntax highlighting)
_SHELL_DETECT_PROMPT_PATTERN = re.compile(r"^[$#]\s+", re.MULTILINE)
_SHEBANG_PATTERN = re.compile(r"^#!.*(?:ba)?sh", re.MULTILINE)
_SHELL_DETECT_COMMAND_PATTERN = re.compile(
    r"^\s*(?:export|alias|source|cd|ls|cat|grep|awk|sed|echo|printf|"
    r"mkdir|rm|cp|mv|chmod|chown|sudo|apt|yum|brew|pip|npm|git|docker|"
    r"curl|wget|tar|zip|unzip|find|xargs|sort|uniq|wc|head|tail|tee|"
    r"for\s+\w+\s+in|while\s+|if\s+\[|elif\s+\[|fi$|done$|esac$)\b",
    re.MULTILINE,
)


def _detect_shell_syntax(content: str) -> bool:
    """
    Detect if content looks like shell script or command output.

    Checks for common shell indicators such as:
    - Lines starting with $ or # (shell prompts)
    - Shebang lines (#!/bin/bash, etc.)
    - Multiple lines with common shell command patterns

    Args:
        content: The content to analyze.

    Returns:
        True if the content appears to be shell script or output.
    """
    # Check for shebang - strong indicator
    if _SHEBANG_PATTERN.search(content):
        return True

    # Count shell prompt lines ($ or # at start)
    prompt_matches = len(_SHELL_DETECT_PROMPT_PATTERN.findall(content))
    if prompt_matches >= 2:
        return True

    # Count shell command patterns
    command_matches = len(_SHELL_DETECT_COMMAND_PATTERN.findall(content))
    if command_matches >= 3:
        return True

    # Check combination: at least 1 prompt + 1 command
    return bool(prompt_matches >= 1 and command_matches >= 1)


def _colorize_git_line(line: str) -> Text | None:
    """
    Check if a line matches git output patterns and return styled Text.

    Args:
        line: The line to check.

    Returns:
        Rich Text with git-specific styling, or None if not git output.
    """
    # File headers (+++/---) - cyan bold
    if _GIT_FILE_HEADER_PATTERN.match(line):
        return Text(line, style=Style(color=NEON_COLORS["cyan"], bold=True))

    # Diff headers (@@, diff --git, index) - purple
    if _GIT_DIFF_HEADER_PATTERN.match(line):
        return Text(line, style=Style(color=NEON_COLORS["purple"]))

    # Added lines (+, A ) - green
    if _GIT_ADDED_PATTERN.match(line):
        return Text(line, style=Style(color=NEON_COLORS["green"]))

    # Deleted lines (-, D ) - red
    if _GIT_DELETED_PATTERN.match(line):
        return Text(line, style=Style(color=NEON_COLORS["red"]))

    # Modified lines (M ) - yellow
    if _GIT_MODIFIED_PATTERN.match(line):
        return Text(line, style=Style(color=NEON_COLORS["yellow"]))

    return None


def _colorize_line(line: str, is_error: bool = False) -> Text:
    """
    Apply neon syntax highlighting to a single line of output.

    Args:
        line: The line to colorize.
        is_error: Whether this is error output.

    Returns:
        Rich Text with neon styling applied.
    """
    # Check for git-specific patterns first
    git_result = _colorize_git_line(line)
    if git_result is not None:
        return git_result

    result = Text()

    if is_error:
        # Error output - still colorize but with red base
        # Highlight file paths in orange for visibility
        pos = 0
        for match in _FILE_PATH_PATTERN.finditer(line):
            if match.start() > pos:
                result.append(line[pos:match.start()], style=Style(color=NEON_COLORS["red"]))
            result.append(match.group(1), style=Style(color=NEON_COLORS["orange"], bold=True))
            pos = match.end()
        if pos < len(line):
            result.append(line[pos:], style=Style(color=NEON_COLORS["red"]))
        return result

    # Check for line number prefix (e.g., "  42:" or "123|")
    line_num_match = _LINE_NUMBER_PATTERN.match(line)
    if line_num_match:
        indent, num, sep = line_num_match.groups()
        result.append(indent, style=Style())
        result.append(num, style=Style(color=NEON_COLORS["yellow"]))
        result.append(sep, style=Style(color=NEON_COLORS["purple"]))
        line = line[line_num_match.end():]

    # Process the rest of the line for patterns
    segments: list[tuple[int, int, str, Style]] = []

    # Find all file paths (highest priority - cyan)
    for match in _FILE_PATH_PATTERN.finditer(line):
        segments.append((match.start(), match.end(), match.group(1),
                        Style(color=NEON_COLORS["cyan"])))

    # Find error keywords (red bold)
    for match in _ERROR_KEYWORDS.finditer(line):
        segments.append((match.start(), match.end(), match.group(1),
                        Style(color=NEON_COLORS["red"], bold=True)))

    # Find success keywords (green bold)
    for match in _SUCCESS_KEYWORDS.finditer(line):
        segments.append((match.start(), match.end(), match.group(1),
                        Style(color=NEON_COLORS["green"], bold=True)))

    # Find warning keywords (yellow bold)
    for match in _WARNING_KEYWORDS.finditer(line):
        segments.append((match.start(), match.end(), match.group(1),
                        Style(color=NEON_COLORS["yellow"], bold=True)))

    # Find strings (orange)
    for match in _STRING_PATTERN.finditer(line):
        segments.append((match.start(), match.end(), match.group(0),
                        Style(color=NEON_COLORS["orange"])))

    # Find arrows (pink)
    for match in _ARROW_PATTERN.finditer(line):
        segments.append((match.start(), match.end(), match.group(1),
                        Style(color=NEON_COLORS["pink"], bold=True)))

    # Find brackets (purple)
    for match in _BRACKET_PATTERN.finditer(line):
        segments.append((match.start(), match.end(), match.group(1),
                        Style(color=NEON_COLORS["purple"])))

    # Find shell variables $VAR and ${VAR} (yellow)
    for match in _SHELL_VAR_PATTERN.finditer(line):
        segments.append((match.start(), match.end(), match.group(1),
                        Style(color=NEON_COLORS["yellow"])))

    # Find shell prompts at line start (cyan)
    for match in _SHELL_PROMPT_PATTERN.finditer(line):
        segments.append((match.start(), match.end(), match.group(1),
                        Style(color=NEON_COLORS["cyan"])))

    # Find pipe and redirect operators (pink)
    for match in _PIPE_REDIRECT_PATTERN.finditer(line):
        segments.append((match.start(), match.end(), match.group(1),
                        Style(color=NEON_COLORS["pink"])))

    # Find common commands at line start (orange bold)
    for match in _COMMAND_PATTERN.finditer(line):
        segments.append((match.start(), match.end(), match.group(1),
                        Style(color=NEON_COLORS["orange"], bold=True)))

    # Sort segments by start position, then by length (longer matches first)
    segments.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    # Build the result, avoiding overlaps
    last_end = 0
    used_ranges: list[tuple[int, int]] = []

    for start, end, text, style in segments:
        # Check if this segment overlaps with any used range
        overlaps = any(not (end <= used_start or start >= used_end)
                      for used_start, used_end in used_ranges)
        if overlaps:
            continue

        if start > last_end:
            # Add default styled text before this segment
            result.append(line[last_end:start],
                         style=Style(color=NEON_COLORS["foreground"]))
        result.append(text, style=style)
        used_ranges.append((start, end))
        last_end = end

    # Add remaining text
    if last_end < len(line):
        result.append(line[last_end:],
                     style=Style(color=NEON_COLORS["foreground"]))

    return result


def print_tool_result(
    console: Console,
    content: str,
    is_error: bool = False,
    max_lines: int = 20,
) -> None:
    """
    Print a tool result with neon syntax highlighting.

    Displays the result content with colorized file paths, line numbers,
    and keyword highlighting. Uses red styling for errors. For shell scripts
    and command output, uses Rich's Syntax class for proper highlighting.

    Args:
        console: Rich Console instance for output.
        content: The result content to display.
        is_error: Whether this is an error result.
        max_lines: Maximum number of lines to display.
    """
    if not content or not content.strip():
        return

    lines = content.split("\n")
    truncated = False
    total_lines = len(lines)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    # For non-error shell content, use Rich Syntax highlighting
    if not is_error and _detect_shell_syntax(content):
        display_content = "\n".join(lines)
        syntax = Syntax(
            display_content,
            "bash",
            theme="dracula",
            line_numbers=False,
            word_wrap=True,
        )

        # Add truncation indicator if needed
        if truncated:
            truncation_text = Text()
            truncation_text.append(
                f"\n... ({total_lines - max_lines} more lines)",
                style=Style(color=NEON_COLORS["yellow"], italic=True),
            )
            # Create a group with syntax and truncation text
            panel_content: Group | Syntax = Group(syntax, truncation_text)
        else:
            panel_content = syntax

        panel = Panel(
            panel_content,
            box=box.ROUNDED,
            border_style=Style(color=NEON_COLORS["purple"]),
            title=f"[bold {NEON_COLORS['cyan']}]📤 Output[/bold {NEON_COLORS['cyan']}]",
            title_align="left",
            style=Style(bgcolor="#1e1e2e"),
            expand=False,
            padding=(0, 1),
        )
        console.print(panel)
        return

    # Build colorized text content using manual colorization
    result_text = Text()
    for i, line in enumerate(lines):
        result_text.append_text(_colorize_line(line, is_error))
        if i < len(lines) - 1:
            result_text.append("\n")

    # Add truncation indicator if needed
    if truncated:
        result_text.append("\n")
        result_text.append(
            f"... ({total_lines - max_lines} more lines)",
            style=Style(color=NEON_COLORS["yellow"], italic=True),
        )

    # Determine border color and title
    if is_error:
        border_color = NEON_COLORS["red"]
        title = "[bold red]❌ Error[/bold red]"
    else:
        border_color = NEON_COLORS["purple"]
        title = f"[bold {NEON_COLORS['cyan']}]📤 Output[/bold {NEON_COLORS['cyan']}]"

    panel = Panel(
        result_text,
        box=box.ROUNDED,
        border_style=Style(color=border_color),
        title=title,
        title_align="left",
        style=Style(bgcolor="#1e1e2e"),
        expand=False,
        padding=(0, 1),
    )
    console.print(panel)


# =============================================================================
# Code Result Component
# =============================================================================


def print_code_result(
    console: Console,
    content: str,
    filename: str = "",
    max_lines: int = 30,
) -> None:
    """
    Print code content with syntax highlighting.

    Uses Rich's Syntax component for proper highlighting and
    automatic line wrapping that respects terminal width.

    Args:
        console: Rich Console instance for output.
        content: The code content to display.
        filename: Optional filename to detect language (e.g., "test.py").
        max_lines: Maximum number of lines to display.
    """
    lines = content.split("\n")
    truncated = len(lines) > max_lines
    display_content = "\n".join(lines[:max_lines]) if truncated else content

    # Detect language from filename extension
    if "." in filename:
        lang = filename.rsplit(".", 1)[-1]
        # Map common extensions
        lang_map = {"py": "python", "js": "javascript", "ts": "typescript", "md": "markdown"}
        lang = lang_map.get(lang, lang)
    else:
        lang = "text"

    syntax = Syntax(
        display_content,
        lang,
        theme="dracula",
        line_numbers=True,
        word_wrap=True,
    )
    console.print(syntax)

    if truncated:
        console.print(
            f"[neon.dim]... ({len(lines) - max_lines} more lines)[/]"
        )


# =============================================================================
# Thinking Component
# =============================================================================


def print_thinking(console: Console, content: str, max_length: int = 300) -> None:
    """
    Print a thinking/reasoning panel.

    Displays the AI's thought process in a purple-styled panel
    with a thought bubble icon.

    Args:
        console: Rich Console instance for output.
        content: The thinking content to display.
        max_length: Maximum content length before truncation.
    """
    # Truncate if needed
    display_content = content if len(content) <= max_length else content[:max_length] + "..."

    panel = Panel(
        Text(display_content, style=Style(color=NEON_COLORS["purple"], italic=True)),
        title="\U0001f4ad Thinking",  # 💭
        title_align="left",
        box=box.ROUNDED,
        border_style=Style(color=NEON_COLORS["purple"]),
        padding=(0, 1),
    )
    console.print(panel)


# =============================================================================
# Feedback Table Component
# =============================================================================


def print_feedback_table(console: Console, items: list[dict[str, object]]) -> None:
    """
    Print a table of feedback items/issues.

    Creates a styled table with columns for issue number, status,
    description, file, and line number.

    Args:
        console: Rich Console instance for output.
        items: List of dicts with keys: status, description, file, line.
    """
    table = Table(
        title="\U0001f4cb Issues to Fix",  # 📋
        title_style=Style(color=NEON_COLORS["cyan"], bold=True),
        box=box.ROUNDED,
        border_style=Style(color=NEON_COLORS["purple"]),
        header_style=Style(color=NEON_COLORS["pink"], bold=True),
        show_lines=True,
    )

    table.add_column("#", justify="right", style=Style(color=NEON_COLORS["cyan"]))
    table.add_column("Status", justify="center")
    table.add_column("Description", style=Style(color=NEON_COLORS["foreground"]))
    table.add_column("File", style=Style(color=NEON_COLORS["orange"]))
    table.add_column("Line", justify="right", style=Style(color=NEON_COLORS["yellow"]))

    for i, item in enumerate(items, 1):
        status = str(item.get("status", "pending"))
        config = STATUS_CONFIG.get(status, STATUS_CONFIG["pending"])

        status_pill = pill(
            f" {config['icon']} {status.upper()} ",
            config["color"],
            NEON_COLORS["background"],
        )

        table.add_row(
            str(i),
            status_pill,
            str(item.get("description", "")),
            str(item.get("file", "")),
            str(item.get("line", "")),
        )

    console.print(table)


# =============================================================================
# Error Component
# =============================================================================


def print_error(console: Console, title: str, message: str) -> None:
    """
    Print an error panel with red styling.

    Creates a prominent error display with a warning icon
    and double-edge border.

    Args:
        console: Rich Console instance for output.
        title: Error title text.
        message: Detailed error message.
    """
    panel = Panel(
        Text(message, style=Style(color=NEON_COLORS["red"])),
        title=f"\u26a0\ufe0f  {title}",  # ⚠️
        title_align="left",
        box=box.DOUBLE_EDGE,
        border_style=Style(color=NEON_COLORS["red"]),
        padding=(0, 1),
    )
    console.print(panel)


# =============================================================================
# Warning Component
# =============================================================================


def print_warning(console: Console, message: str) -> None:
    """
    Print a warning panel with yellow styling.

    Args:
        console: Rich Console instance for output.
        message: Warning message to display.
    """
    panel = Panel(
        Text(message, style=Style(color=NEON_COLORS["yellow"])),
        box=box.ROUNDED,
        border_style=Style(color=NEON_COLORS["yellow"]),
        padding=(0, 1),
    )
    console.print(panel)


# =============================================================================
# Success Component
# =============================================================================


def print_success(console: Console, message: str) -> None:
    """
    Print a success message with green styling.

    Args:
        console: Rich Console instance for output.
        message: Success message to display.
    """
    console.print(f"[neon.success]✔[/] [neon.green]{message}[/]")


# =============================================================================
# Cost Component
# =============================================================================


def print_cost(console: Console, cost_usd: float) -> None:
    """
    Print a cost indicator with cyan styling.

    Args:
        console: Rich Console instance for output.
        cost_usd: The cost in USD.
    """
    console.print(f"[neon.cyan]💰[/] [neon.dim]${cost_usd:.4f}[/]")


# =============================================================================
# Info Component
# =============================================================================


def print_info(console: Console, message: str) -> None:
    """
    Print an info message with cyan styling.

    Args:
        console: Rich Console instance for output.
        message: Info message to display.
    """
    console.print(f"[neon.cyan]ℹ[/] [neon.fg]{message}[/]")


def print_dim(console: Console, message: str) -> None:
    """
    Print a dimmed message for secondary information.

    Args:
        console: Rich Console instance for output.
        message: Message to display in dimmed style.
    """
    console.print(f"[neon.dim]{message}[/]")


# =============================================================================
# Agent Text Component
# =============================================================================

# Track state for agent text blocks (gutter display)
_agent_text_line_started = False


def _highlight_agent_text(text: str) -> Text:
    """
    Apply syntax highlighting to agent text.

    Highlights:
    - Inline code (`code`)
    - File paths
    - Numbers
    - URLs
    - Bold (**text**) and italic (*text*)

    Args:
        text: Raw agent text to highlight.

    Returns:
        Rich Text with neon styling applied.
    """
    result = Text()

    # Patterns for highlighting
    code_pattern = re.compile(r"`([^`]+)`")
    bold_pattern = re.compile(r"\*\*([^*]+)\*\*")
    italic_pattern = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
    url_pattern = re.compile(r"https?://[^\s\])<>]+")
    file_path_pattern = re.compile(r"(?:^|[\s(])([./]?(?:[\w.-]+/)+[\w.-]+\.\w+)")

    # Process text character by character with pattern matching
    pos = 0
    segments: list[tuple[int, int, str, Style]] = []

    # Find all patterns
    for match in code_pattern.finditer(text):
        segments.append((
            match.start(),
            match.end(),
            match.group(1),  # Just the code, not backticks
            Style(color=NEON_COLORS["orange"], bgcolor="#3a3a3a"),
        ))

    for match in bold_pattern.finditer(text):
        segments.append((
            match.start(),
            match.end(),
            match.group(1),
            Style(color=NEON_COLORS["green"], bold=True),
        ))

    for match in italic_pattern.finditer(text):
        segments.append((
            match.start(),
            match.end(),
            match.group(1),
            Style(color=NEON_COLORS["green"], italic=True),
        ))

    for match in url_pattern.finditer(text):
        segments.append((
            match.start(),
            match.end(),
            match.group(0),
            Style(color=NEON_COLORS["cyan"], underline=True),
        ))

    for match in file_path_pattern.finditer(text):
        segments.append((
            match.start(1),
            match.end(1),
            match.group(1),
            Style(color=NEON_COLORS["cyan"]),
        ))

    # Sort segments by position, prefer longer matches
    segments.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    # Build result avoiding overlaps
    pos = 0
    used_ranges: list[tuple[int, int]] = []

    for start, end, display_text, style in segments:
        overlaps = any(
            not (end <= used_start or start >= used_end)
            for used_start, used_end in used_ranges
        )
        if overlaps:
            continue

        if start > pos:
            # Add default styled text - bright neon green
            result.append(text[pos:start], style=Style(color=NEON_COLORS["green"]))

        result.append(display_text, style=style)
        used_ranges.append((start, end))
        pos = end

    # Add remaining text - bright neon green
    if pos < len(text):
        result.append(text[pos:], style=Style(color=NEON_COLORS["green"]))

    return result


# =============================================================================
# AgentTextRenderer Class (Live Panel with buffering)
# =============================================================================

# Constants for agent text styling
AGENT_TEXT_BG = "#051208"  # Very dark green background
AGENT_TEXT_FG = NEON_COLORS["green"]  # Neon green text


class AgentTextRenderer:
    """
    Renderer for agent text using Rich Live Panel with buffering.

    This class buffers incoming text chunks and displays them in a
    Live-updating Panel that provides proper word wrapping. This solves
    the issue of broken line wrapping when streaming text character-by-character.

    Usage:
        renderer = AgentTextRenderer(console)
        renderer.start()
        for chunk in stream:
            renderer.append(chunk)
        renderer.finish()
    """

    def __init__(self, console: Console) -> None:
        """
        Initialize the renderer.

        Args:
            console: Rich Console instance for output.
        """
        self._console = console
        self._buffer: list[str] = []
        self._live: Live | None = None
        self._started = False

    def _render_panel(self) -> Panel:
        """
        Render the current buffer as a styled Panel.

        Returns:
            Rich Panel with highlighted text and neon green styling.
        """
        full_text = "".join(self._buffer)

        # Apply syntax highlighting to each line
        highlighted = Text()
        lines = full_text.split("\n")
        for i, line in enumerate(lines):
            if line:
                highlighted.append_text(_highlight_agent_text(line))
            if i < len(lines) - 1:
                highlighted.append("\n")

        return Panel(
            highlighted,
            box=box.ROUNDED,
            border_style=Style(color=AGENT_TEXT_FG),
            style=Style(bgcolor=AGENT_TEXT_BG),
            padding=(0, 1),
        )

    def start(self) -> None:
        """
        Start the Live context for real-time updates.

        Call this before appending any text chunks.
        """
        if self._started:
            return

        # Add newline for separation from previous output
        self._console.print()

        self._live = Live(
            self._render_panel(),
            console=self._console,
            refresh_per_second=10,
            transient=True,  # Remove the live display when done
        )
        self._live.start()
        self._started = True

    def append(self, text: str) -> None:
        """
        Append text to the buffer and update the display.

        Args:
            text: Text chunk to append.
        """
        if not text:
            return

        # Auto-start if not already started
        if not self._started:
            self.start()

        self._buffer.append(text)

        if self._live is not None:
            self._live.update(self._render_panel())

    def finish(self) -> None:
        """
        Stop the Live context and print the final Panel.

        Call this when all text has been received.
        """
        if self._live is not None:
            self._live.stop()
            self._live = None

        # Print the final panel (non-transient)
        if self._buffer:
            self._console.print(self._render_panel())

        # Reset state
        self._buffer = []
        self._started = False

    @property
    def has_content(self) -> bool:
        """Check if the buffer has any content."""
        return bool(self._buffer)


def print_agent_text(console: Console, text: str) -> None:
    """
    Print agent text output with streaming-friendly left gutter.

    Displays agent text with a neon-styled left border and
    markdown-aware syntax highlighting. The gutter prefix is
    shown on the first line, and the text flows with word wrapping.

    Args:
        console: Rich Console instance for output.
        text: The agent text to display.
    """
    global _agent_text_line_started

    if not text:
        return

    # Split into lines to handle multiline text
    lines = text.split("\n")

    for i, line in enumerate(lines):
        is_last = i == len(lines) - 1

        if not _agent_text_line_started:
            # Start of a new agent text block - add separation and gutter prefix
            console.print()  # Newline for separation from tool calls
            gutter = Text()
            gutter.append("│ ", style=Style(color=NEON_COLORS["green"]))
            console.print(gutter, end="")
            _agent_text_line_started = True

        # Highlight and print the line content with dark green background
        if line:
            highlighted = _highlight_agent_text(line)
            highlighted.stylize(Style(bgcolor="#051208"))  # Very dark green
            console.print(highlighted, end="")

        # Handle newlines - reset gutter state for next line
        if not is_last:
            console.print()  # Complete the current line
            _agent_text_line_started = False


def reset_agent_text_state() -> None:
    """
    Reset the agent text line state.

    Call this at the end of an agent response to ensure
    the next agent response starts with a fresh gutter.
    """
    global _agent_text_line_started
    _agent_text_line_started = False


def print_fix_progress(
    console: Console, item_num: int, total: int, description: str
) -> None:
    """
    Print fix progress indicator.

    Args:
        console: Rich Console instance for output.
        item_num: Current item number (1-indexed).
        total: Total number of items.
        description: Description of the fix.
    """
    text = Text()
    text.append("  ", style=Style())
    text.append(f"[{item_num}/{total}] ", style=Style(color=NEON_COLORS["cyan"], bold=True))
    text.append("Fixing: ", style=Style(color=NEON_COLORS["pink"]))
    # Truncate description
    desc = description[:60] + "..." if len(description) > 60 else description
    text.append(desc, style=Style(color=NEON_COLORS["foreground"]))
    console.print(text)


def print_fix_complete(console: Console, item_num: int, total: int) -> None:
    """
    Print fix completion indicator.

    Args:
        console: Rich Console instance for output.
        item_num: Current item number (1-indexed).
        total: Total number of items.
    """
    text = Text()
    text.append("  ", style=Style())
    text.append(f"[{item_num}/{total}] ", style=Style(color=NEON_COLORS["cyan"], bold=True))
    text.append("✔ Fix applied", style=Style(color=NEON_COLORS["green"]))
    console.print(text)


# =============================================================================
# Summary Component
# =============================================================================


@dataclass
class SummaryData:
    """Data class for summary information."""

    skill: str
    target: str
    feedback_count: int
    fixes_applied: int
    test_retries: int
    tests_passed: bool


def print_summary(console: Console, data: SummaryData) -> None:
    """
    Print a summary table with neon styling.

    Displays a comprehensive summary of the review/fix session
    with status badges for pass/fail.

    Args:
        console: Rich Console instance for output.
        data: SummaryData containing all summary fields.
    """
    table = Table(
        title="✨ Review Summary",
        title_style=Style(color=NEON_COLORS["green"], bold=True),
        box=box.ROUNDED,
        border_style=Style(color=NEON_COLORS["purple"]),
        show_header=False,
        padding=(0, 1),
    )

    table.add_column("Field", style=Style(color=NEON_COLORS["cyan"]))
    table.add_column("Value", style=Style(color=NEON_COLORS["foreground"]))

    # Create pass/fail pill
    if data.tests_passed:
        status_badge = pill(" PASSED ", NEON_COLORS["green"], NEON_COLORS["background"])
    else:
        status_badge = pill(" FAILED ", NEON_COLORS["red"], NEON_COLORS["background"])

    table.add_row("Skill", data.skill)
    table.add_row("Target", data.target)
    table.add_row("Issues Found", str(data.feedback_count))
    table.add_row("Fixes Applied", str(data.fixes_applied))
    table.add_row("Test Retries", str(data.test_retries))
    table.add_row("Tests", status_badge)

    console.print(table)


# =============================================================================
# Menu Component
# =============================================================================


def print_menu(console: Console, title: str, options: list[tuple[str, str]]) -> None:
    """
    Print a styled menu for user selection.

    Displays numbered options with descriptions in a neon-styled panel.

    Args:
        console: Rich Console instance for output.
        title: Menu title.
        options: List of (key, description) tuples.
    """
    menu_text = Text()
    for key, description in options:
        menu_text.append(f"  [{key}] ", style=Style(color=NEON_COLORS["cyan"], bold=True))
        menu_text.append(f"{description}\n", style=Style(color=NEON_COLORS["foreground"]))

    panel = Panel(
        menu_text,
        title=title,
        title_align="left",
        box=box.ROUNDED,
        border_style=Style(color=NEON_COLORS["pink"]),
        padding=(0, 1),
    )
    console.print(panel)


# =============================================================================
# Prompt Component
# =============================================================================


def prompt_user(console: Console, message: str, default: str = "") -> str:
    """
    Display a styled input prompt and get user input.

    Args:
        console: Rich Console instance for output.
        message: Prompt message to display.
        default: Default value if user enters nothing.

    Returns:
        User's input string, or default if empty.
    """
    prompt_text = Text()
    prompt_text.append("\u25b6 ", style=Style(color=NEON_COLORS["cyan"]))  # ▶
    prompt_text.append(message, style=Style(color=NEON_COLORS["cyan"]))
    if default:
        prompt_text.append(f" [{default}]", style=Style(color=NEON_COLORS["foreground"], dim=True))
    prompt_text.append(": ", style=Style(color=NEON_COLORS["cyan"]))

    console.print(prompt_text, end="")
    user_input = input()
    return user_input if user_input else default


# =============================================================================
# NeonThrobber Class
# =============================================================================


class NeonThrobber:
    """
    Animated gradient bar for progress indication.

    Creates a scrolling rainbow effect using horizontal line characters
    and the gradient color palette.
    """

    def __init__(self) -> None:
        """Initialize the throbber with offset tracking."""
        self._offset = 0
        self._char = "\u2501"  # ━

    def render(self, width: int = 40) -> Text:
        """
        Render the throbber bar with current animation frame.

        Args:
            width: Width of the throbber bar in characters.

        Returns:
            Rich Text object containing the styled throbber.
        """
        result = Text()
        num_colors = len(GRADIENT_COLORS)

        for i in range(width):
            color_index = (i + self._offset) % num_colors
            color = GRADIENT_COLORS[color_index]
            result.append(self._char, style=Style(color=color))

        # Advance offset for next frame
        self._offset = (self._offset + 1) % num_colors

        return result

    def reset(self) -> None:
        """Reset the animation offset to the beginning."""
        self._offset = 0


# =============================================================================
# LiveToolPanel Class
# =============================================================================


class LiveToolPanel:
    """
    Manages a single tool call panel with Live updates.

    Consolidates tool call display and result into a single live-updating panel.
    Shows an animated throbber while waiting for the result, then replaces it
    with the actual result content.

    In quiet mode, delegates to print_tool_call and skips result display.

    Usage:
        panel = LiveToolPanel(console, "tool-123", "Bash", {"command": "ls"})
        panel.start()
        # ... tool executes ...
        panel.set_result("file1.txt\nfile2.txt", is_error=False)
        panel.finish()
    """

    def __init__(
        self,
        console: Console,
        tool_use_id: str,
        name: str,
        args: dict[str, object],
        quiet_mode: bool = False,
    ) -> None:
        """
        Initialize the LiveToolPanel.

        Args:
            console: Rich Console instance for output.
            tool_use_id: Unique identifier for the tool use.
            name: Name of the tool being called.
            args: Dictionary of arguments passed to the tool.
            quiet_mode: If True, use static display instead of Live updates.
        """
        self._console = console
        self._tool_use_id = tool_use_id
        self._name = name
        self._args = args
        self._result: str | None = None
        self._is_error: bool = False
        self._live: Live | None = None
        self._throbber = NeonThrobber()
        self._quiet_mode = quiet_mode

    def _build_tool_header(self) -> Text:
        """
        Build the tool call header content.

        Reuses logic from print_tool_call for consistent styling.
        Handles special cases for Bash, Skill, and Write tools.

        Returns:
            Rich Text containing the styled tool header.
        """
        content = Text()

        # Special handling for Skill tool calls
        if self._name == "Skill":
            header_line = Text()
            header_line.append("\u25b6 ", style=Style(color=NEON_COLORS["cyan"]))  # Triangle
            header_line.append("\u2728 ", style=Style(color=NEON_COLORS["yellow"]))  # Sparkles
            header_line.append("Skill", style=Style(color=NEON_COLORS["cyan"], bold=True))
            content.append_text(header_line)
            content.append("\n")

            # Extract and display skill name as cyan pill badge
            skill_name = str(self._args.get("skill", ""))
            skill_pill = pill(f" {skill_name} ", NEON_COLORS["cyan"], NEON_COLORS["background"])
            content.append_text(skill_pill)

            # Show args if present (always in non-quiet mode since we're in Live panel)
            if not self._quiet_mode:
                skill_args = self._args.get("args")
                if skill_args:
                    content.append("\n")
                    content.append("args=", style=Style(color=NEON_COLORS["purple"]))
                    content.append(str(skill_args), style=Style(color=NEON_COLORS["orange"]))

            return content

        # Special handling for Bash tool calls
        if self._name == "Bash":
            header_line = Text()
            header_line.append("\u25b6 ", style=Style(color=NEON_COLORS["cyan"]))  # Triangle
            header_line.append("\U0001f527 ", style=Style(color=NEON_COLORS["orange"]))  # Wrench
            header_line.append("Bash", style=Style(color=NEON_COLORS["pink"], bold=True))
            content.append_text(header_line)

            # Add description if present
            description = str(self._args.get("description", ""))
            if description:
                content.append("\n")
                content.append(description, style=Style(color=NEON_COLORS["cyan"]))

            # Add command if not in quiet mode
            if not self._quiet_mode:
                command = str(self._args.get("command", ""))
                if command:
                    content.append("\n")
                    content.append("$ ", style=Style(dim=True))
                    content.append(command, style=Style(dim=True))

            return content

        # Special handling for Write tool
        if self._name == "Write":
            file_path = str(self._args.get("file_path", ""))

            header_line = Text()
            header_line.append("\u25b6 ", style=Style(color=NEON_COLORS["cyan"]))  # Triangle
            header_line.append("\U0001f527 ", style=Style(color=NEON_COLORS["orange"]))  # Wrench
            header_line.append("Write", style=Style(color=NEON_COLORS["pink"], bold=True))
            content.append_text(header_line)
            content.append("\n")
            content.append("file_path=", style=Style(color=NEON_COLORS["cyan"]))
            content.append(file_path, style=Style(color=NEON_COLORS["cyan"]))

            return content

        # Standard tool call display (other tools)
        header_line = Text()
        header_line.append("\u25b6 ", style=Style(color=NEON_COLORS["cyan"]))  # Triangle
        header_line.append("\U0001f527 ", style=Style(color=NEON_COLORS["orange"]))  # Wrench
        header_line.append(self._name, style=Style(color=NEON_COLORS["pink"], bold=True))
        content.append_text(header_line)

        # Add formatted key=value pairs
        if self._args:
            content.append("\n")
            args_text = _colorize_tool_args(self._args)
            content.append_text(args_text)

        return content

    def _build_result_content(self, max_lines: int = 20) -> Text | Syntax | Group:
        """
        Build the result content with syntax highlighting.

        Reuses logic from print_tool_result for consistent styling.

        Args:
            max_lines: Maximum number of lines to display.

        Returns:
            Rich renderable containing the styled result.
        """
        if self._result is None:
            return Text()

        content = self._result
        if not content.strip():
            return Text()

        lines = content.split("\n")
        truncated = False
        total_lines = len(lines)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            truncated = True

        # For non-error shell content, use Rich Syntax highlighting
        if not self._is_error and _detect_shell_syntax(content):
            display_content = "\n".join(lines)
            syntax = Syntax(
                display_content,
                "bash",
                theme="dracula",
                line_numbers=False,
                word_wrap=True,
            )

            if truncated:
                truncation_text = Text()
                truncation_text.append(
                    f"\n... ({total_lines - max_lines} more lines)",
                    style=Style(color=NEON_COLORS["yellow"], italic=True),
                )
                return Group(syntax, truncation_text)
            return syntax

        # Build colorized text content using manual colorization
        result_text = Text()
        for i, line in enumerate(lines):
            result_text.append_text(_colorize_line(line, self._is_error))
            if i < len(lines) - 1:
                result_text.append("\n")

        # Add truncation indicator if needed
        if truncated:
            result_text.append("\n")
            result_text.append(
                f"... ({total_lines - max_lines} more lines)",
                style=Style(color=NEON_COLORS["yellow"], italic=True),
            )

        return result_text

    def _render_panel(self) -> Panel:
        """
        Render the current state as a Panel.

        Shows tool call header + either throbber (if waiting) or result.

        Returns:
            Rich Panel containing the consolidated tool call display.
        """
        # Build header
        header = self._build_tool_header()

        # Determine border color based on tool type and error state
        if self._name == "Skill":
            border_color = NEON_COLORS["cyan"]
        elif self._is_error:
            border_color = NEON_COLORS["red"]
        else:
            border_color = NEON_COLORS["purple"]

        # Build content: header + separator + (throbber or result)
        if self._result is None:
            # Show throbber while waiting
            content = Group(
                header,
                Text("\n"),
                self._throbber.render(width=40),
            )
        else:
            # Show result
            result_content = self._build_result_content()

            # Add title for result section
            if self._is_error:
                result_title = Text()
                result_title.append("\u274c Error", style=Style(color=NEON_COLORS["red"], bold=True))
            else:
                result_title = Text()
                result_title.append("\U0001f4e4 Output", style=Style(color=NEON_COLORS["cyan"], bold=True))

            if isinstance(result_content, Text) and not result_content.plain.strip():
                # Empty result - just show header (wrap in Group for type consistency)
                content = Group(header)
            else:
                content = Group(
                    header,
                    result_title,
                    result_content,
                )

        return Panel(
            content,
            box=box.ROUNDED,
            border_style=Style(color=border_color),
            style=Style(bgcolor="#1e1e2e"),
            padding=(0, 1),
        )

    def __rich__(self) -> Panel:
        """Return renderable for Rich Live refresh."""
        return self._render_panel()

    def start(self) -> None:
        """
        Start the Live context and show tool call with animated throbber.

        In quiet mode, calls print_tool_call and returns without Live.
        """
        if self._quiet_mode:
            print_tool_call(self._console, self._name, self._args, quiet_mode=True)
            return

        # Add newline for separation
        self._console.print()

        self._live = Live(
            self,  # Pass self so __rich__() is called each refresh frame
            console=self._console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.start()

    def set_result(self, content: str, is_error: bool = False) -> None:
        """
        Store result and update the display.

        Args:
            content: The result content from the tool.
            is_error: Whether this is an error result.
        """
        self._result = content
        self._is_error = is_error

        if self._live is not None:
            self._live.update(self._render_panel())

    def finish(self) -> None:
        """
        Stop Live context and print final static panel.

        In quiet mode, this is a no-op.
        """
        if self._quiet_mode:
            return

        if self._live is not None:
            self._live.stop()
            self._live = None

        # Print final panel (non-transient)
        self._console.print(self._render_panel())


# =============================================================================
# LiveToolPanelRegistry Class
# =============================================================================


class LiveToolPanelRegistry:
    """
    Registry for tracking multiple concurrent tool panels.

    Provides a central registry for LiveToolPanel instances, indexed by
    tool_use_id. This enables correlation between ToolUseBlock and
    ToolResultBlock events when processing streaming responses.

    Usage:
        registry = LiveToolPanelRegistry(console, quiet_mode=False)
        panel = registry.create("tool-123", "Bash", {"command": "ls"})
        # ... tool executes ...
        panel.set_result("file1.txt", is_error=False)
        panel.finish()
        registry.remove("tool-123")
    """

    def __init__(self, console: Console, quiet_mode: bool = False) -> None:
        """
        Initialize the registry.

        Args:
            console: Rich Console instance for creating panels.
            quiet_mode: If True, panels use static display instead of Live updates.
        """
        self._console = console
        self._quiet_mode = quiet_mode
        self._panels: dict[str, LiveToolPanel] = {}

    def create(
        self,
        tool_use_id: str,
        name: str,
        args: dict[str, object],
    ) -> LiveToolPanel:
        """
        Create and register a new panel, then start it.

        Args:
            tool_use_id: Unique identifier for the tool use.
            name: Name of the tool being called.
            args: Dictionary of arguments passed to the tool.

        Returns:
            The created and started LiveToolPanel.
        """
        panel = LiveToolPanel(
            console=self._console,
            tool_use_id=tool_use_id,
            name=name,
            args=args,
            quiet_mode=self._quiet_mode,
        )
        self._panels[tool_use_id] = panel
        panel.start()
        return panel

    def get(self, tool_use_id: str) -> LiveToolPanel | None:
        """
        Get a panel by its tool_use_id.

        Args:
            tool_use_id: The unique identifier of the tool use.

        Returns:
            The LiveToolPanel if found, None otherwise.
        """
        return self._panels.get(tool_use_id)

    def remove(self, tool_use_id: str) -> None:
        """
        Remove a panel from the registry.

        Call this after finishing a panel to clean up the registry.

        Args:
            tool_use_id: The unique identifier of the tool use to remove.
        """
        self._panels.pop(tool_use_id, None)

    def finish_all(self) -> None:
        """
        Finalize all remaining panels.

        Calls finish() on each panel and clears the registry.
        Use this for cleanup when a response ends unexpectedly.
        """
        for panel in self._panels.values():
            panel.finish()
        self._panels.clear()


# =============================================================================
# NeonProgress Context Manager
# =============================================================================


@contextmanager
def neon_progress(
    console: Console,
    message: str,
    width: int = 40,
    refresh_rate: float = 0.1,
) -> Generator[None, None, None]:
    """
    Context manager for displaying an animated progress indicator.

    Shows an animated throbber while the wrapped operation executes,
    then clears it when done.

    Args:
        console: Rich Console instance for output.
        message: Message to display alongside the throbber.
        width: Width of the throbber bar.
        refresh_rate: Animation refresh rate in seconds.

    Yields:
        None - the context manager body executes with the animation running.

    Example:
        with neon_progress(console, "Loading..."):
            do_long_operation()
    """
    throbber = NeonThrobber()
    stop_event = threading.Event()

    def render_frame() -> Text:
        frame = Text()
        frame.append(f"{message} ", style=Style(color=NEON_COLORS["cyan"]))
        frame.append(throbber.render(width))
        return frame

    def animation_loop(live: Live) -> None:
        while not stop_event.is_set():
            live.update(render_frame())
            time.sleep(refresh_rate)

    with Live(render_frame(), console=console, refresh_per_second=10) as live:
        thread = threading.Thread(target=animation_loop, args=(live,), daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=0.5)


# =============================================================================
# Convenience Functions
# =============================================================================


def create_neon_console() -> NeonConsole:
    """
    Create and return a new NeonConsole instance.

    Returns:
        Configured NeonConsole ready for use.
    """
    return NeonConsole()


def get_status_style(status: str) -> Style:
    """
    Get the Rich Style for a given status.

    Args:
        status: One of "pending", "in_progress", "completed", "failed".

    Returns:
        Rich Style object with appropriate color.
    """
    config = STATUS_CONFIG.get(status, STATUS_CONFIG["pending"])
    return Style(color=config["color"])
