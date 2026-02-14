"""User-friendly error display helpers."""

from rich.console import Console
from rich.panel import Panel


def print_db_error(console: Console, error: ConnectionError) -> None:
    """Display a database connection error in a Rich panel.

    Args:
        console: Rich console for output.
        error: The connection error to display.
    """
    console.print(
        Panel(
            str(error),
            title="Database Connection Error",
            border_style="red",
        )
    )
