"""Core utility functions for Amelia."""
import re


# ANSI escape code pattern
# Matches:
# - CSI sequences: \x1b[<params><command> (e.g., \x1b[31m for red, \x1b[2K for clear line)
# - OSC sequences: \x1b]<params>\x07 (e.g., \x1b]0;Title\x07 for terminal title)
ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07')


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text.

    Handles:
    - Color codes (e.g., \\x1b[31m for red)
    - Cursor movement codes (e.g., \\x1b[2K for clear line)
    - Terminal title/setting codes (e.g., \\x1b]0;Title\\x07)

    Args:
        text: String that may contain ANSI codes

    Returns:
        Text with all ANSI escape sequences removed

    Example:
        >>> strip_ansi("\\x1b[31mERROR\\x1b[0m")
        'ERROR'
        >>> strip_ansi("\\x1b[32m✓\\x1b[0m All tests passed")
        '✓ All tests passed'
    """
    return ANSI_ESCAPE_PATTERN.sub('', text)
