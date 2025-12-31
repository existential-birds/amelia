"""Tests for core utility functions."""

import pytest

from amelia.core.utils import strip_ansi


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("\x1b[31mERROR\x1b[0m", "ERROR"),  # Red
        ("\x1b[1;32mSUCCESS\x1b[0m", "SUCCESS"),  # Bold green
        ("\x1b[34mINFO\x1b[0m", "INFO"),  # Blue
        ("\x1b[1;33mWARNING\x1b[0m", "WARNING"),  # Yellow bold
    ],
    ids=["red", "bold_green", "blue", "yellow_bold"],
)
def test_strip_ansi_removes_color_codes(input_text: str, expected: str) -> None:
    """Test that common color codes are removed."""
    assert strip_ansi(input_text) == expected


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("\x1b[2K\x1b[1G", ""),  # Clear line and move to column 1
        ("\x1b[A", ""),  # Move cursor up
        ("\x1b[10;20H", ""),  # Move cursor to position
    ],
    ids=["clear_line", "cursor_up", "cursor_position"],
)
def test_strip_ansi_removes_cursor_movement(input_text: str, expected: str) -> None:
    """Test that cursor movement sequences are removed."""
    assert strip_ansi(input_text) == expected


def test_strip_ansi_preserves_plain_text() -> None:
    """Test that plain text passes through unchanged."""
    plain_text = "This is plain text with no ANSI codes"
    assert strip_ansi(plain_text) == plain_text

    # Text with special characters but no ANSI
    text_with_chars = "Test √ ✓ × ÷ symbols"
    assert strip_ansi(text_with_chars) == text_with_chars


def test_strip_ansi_handles_empty_string() -> None:
    """Test edge case of empty string."""
    assert strip_ansi("") == ""


@pytest.mark.parametrize(
    "input_text,expected,description",
    [
        # Multiple color codes in one string
        (
            "\x1b[32m✓\x1b[0m All tests \x1b[1mpassed\x1b[0m successfully",
            "✓ All tests passed successfully",
            "mixed_colors",
        ),
        # Multiple lines with different formatting
        (
            "\x1b[31mError:\x1b[0m Something went wrong\n\x1b[32mSuccess:\x1b[0m Fixed it",
            "Error: Something went wrong\nSuccess: Fixed it",
            "multiline",
        ),
        # OSC (Operating System Command) sequences
        (
            "\x1b]0;Terminal Title\x07Content",
            "Content",
            "terminal_title",
        ),
        # Combined title and color codes
        (
            "\x1b]2;Title\x07\x1b[32mGreen Text\x1b[0m",
            "Green Text",
            "title_and_color",
        ),
        # Git-like status output
        (
            "\x1b[32m M\x1b[0m file.txt\n\x1b[31m D\x1b[0m old.txt\n\x1b[32m??\x1b[0m new.txt",
            " M file.txt\n D old.txt\n?? new.txt",
            "git_status",
        ),
        # Progress indicator
        (
            "\x1b[2K\x1b[1G\x1b[32m[=====>   ]\x1b[0m 50%",
            "[=====>   ] 50%",
            "progress_bar",
        ),
    ],
    ids=lambda x: x if isinstance(x, str) and len(x) < 20 else None,
)
def test_strip_ansi_complex_patterns(
    input_text: str, expected: str, description: str
) -> None:
    """Test real-world patterns with multiple ANSI codes."""
    assert strip_ansi(input_text) == expected
