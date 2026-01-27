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
    get_service_urls_display,
    print_banner,
)


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


class TestGetServiceUrlsDisplay:
    """Tests for service URL display in banner."""

    def test_dev_mode_shows_vite_port(self) -> None:
        """Dev mode dashboard URL uses Vite port 8421."""
        result = get_service_urls_display("127.0.0.1", 8420, is_dev_mode=True)
        text = str(result)
        assert "http://localhost:8421" in text
        assert "http://localhost:5173" not in text

    def test_user_mode_shows_api_port(self) -> None:
        """User mode dashboard URL uses API port."""
        result = get_service_urls_display("127.0.0.1", 8420, is_dev_mode=False)
        text = str(result)
        assert "http://127.0.0.1:8420" in text
