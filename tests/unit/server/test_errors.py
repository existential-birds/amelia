"""Tests for server error display helpers."""

from rich.console import Console

from amelia.server.errors import print_db_error


class TestPrintDbError:
    """Tests for print_db_error."""

    def test_prints_panel_with_error_message(self) -> None:
        """print_db_error displays error in a titled panel."""
        console = Console(file=None, force_terminal=True, width=80)
        with console.capture() as capture:
            print_db_error(
                console, ConnectionError("Cannot connect to PostgreSQL")
            )
        output = capture.get()
        assert "Database Connection Error" in output
        assert "Cannot connect to PostgreSQL" in output

    def test_prints_multiline_error(self) -> None:
        """print_db_error handles multiline error messages."""
        console = Console(file=None, force_terminal=True, width=80)
        msg = "Cannot connect to PostgreSQL\n\nMake sure it is running."
        with console.capture() as capture:
            print_db_error(console, ConnectionError(msg))
        output = capture.get()
        assert "Cannot connect to PostgreSQL" in output
        assert "Make sure it is running" in output
