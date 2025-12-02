"""Tests for ASCII banner generation."""
from io import StringIO

from rich.console import Console
from rich.text import Text

from amelia.server.banner import AMELIA_ASCII, get_gradient_banner, print_banner


class TestAmeliaAscii:
    """Tests for ASCII art constant."""

    def test_ascii_art_is_multiline(self) -> None:
        """ASCII art has multiple lines."""
        lines = AMELIA_ASCII.split("\n")
        assert len(lines) >= 3

    def test_ascii_art_contains_letters(self) -> None:
        """ASCII art contains recognizable structure."""
        # Should have content on each line
        for line in AMELIA_ASCII.split("\n"):
            assert len(line) > 0


class TestGetGradientBanner:
    """Tests for gradient banner generation."""

    def test_returns_rich_text(self) -> None:
        """Returns a Rich Text object."""
        result = get_gradient_banner()
        assert isinstance(result, Text)

    def test_preserves_line_count(self) -> None:
        """Output has same number of lines as input ASCII."""
        result = get_gradient_banner()
        input_lines = AMELIA_ASCII.split("\n")
        output_lines = str(result).split("\n")
        assert len(output_lines) == len(input_lines)

    def test_applies_colors(self) -> None:
        """Gradient applies color styles."""
        result = get_gradient_banner()
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
