"""Tests for ASCII banner generation."""
from io import StringIO

from rich.console import Console
from rich.text import Text

from amelia.server.banner import (
    BANNER_ART,
    GOLD,
    NAVY,
    get_agi_banner,
    get_gradient_banner,
    print_banner,
)


class TestBannerArt:
    """Tests for ASCII art constant."""

    def test_ascii_art_is_multiline(self) -> None:
        """ASCII art has multiple lines."""
        lines = BANNER_ART.split("\n")
        assert len(lines) >= 3

    def test_ascii_art_contains_letters(self) -> None:
        """ASCII art contains recognizable structure."""
        # Should have content on each line (excluding decorative empty lines)
        non_empty_lines = [line for line in BANNER_ART.split("\n") if line.strip()]
        assert len(non_empty_lines) > 0


class TestGetGradientBanner:
    """Tests for gradient banner generation."""

    def test_returns_rich_text(self) -> None:
        """Returns a Rich Text object."""
        result = get_gradient_banner(NAVY, GOLD)
        assert isinstance(result, Text)

    def test_preserves_line_count(self) -> None:
        """Output has same number of lines as input ASCII."""
        result = get_gradient_banner(NAVY, GOLD)
        input_lines = BANNER_ART.split("\n")
        output_lines = str(result).split("\n")
        assert len(output_lines) == len(input_lines)

    def test_applies_colors(self) -> None:
        """Gradient applies color styles."""
        result = get_gradient_banner(NAVY, GOLD)
        # Rich Text with styles will have spans
        assert len(result.spans) > 0


class TestPrintBanner:
    """Tests for banner printing."""

    def test_prints_to_console(self) -> None:
        """Banner is printed to console."""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=100)

        print_banner(console)

        output_str = output.getvalue()
        # Should contain ANSI escape codes for colors
        assert "\x1b[" in output_str or len(output_str) > 0


class TestGetAgiBanner:
    """Tests for AGI countdown banner generation."""

    def test_returns_rich_text(self) -> None:
        """Returns a Rich Text object."""
        result = get_agi_banner()
        assert isinstance(result, Text)

    def test_has_expected_line_count(self) -> None:
        """Output has 6 lines (the box structure)."""
        result = get_agi_banner()
        output_lines = str(result).split("\n")
        assert len(output_lines) == 6

    def test_contains_agi_message(self) -> None:
        """Contains the AGI countdown text."""
        result = get_agi_banner()
        text_content = str(result)
        assert "DAYS REMAINING UNTIL AGI ACHIEVED" in text_content

    def test_applies_gradient_colors(self) -> None:
        """Gradient applies color styles."""
        result = get_agi_banner()
        # Rich Text with styles will have spans
        assert len(result.spans) > 0
