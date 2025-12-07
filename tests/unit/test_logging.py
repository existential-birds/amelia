"""Tests for amelia.logging module."""

import re
from io import StringIO
from unittest import mock

from amelia.logging import log_server_startup


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestLogServerStartup:
    """Tests for log_server_startup function."""

    def test_does_not_print_banner(self) -> None:
        """Banner is never printed - only Rich banner should be used."""
        with mock.patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            log_server_startup(
                host="127.0.0.1",
                port=8420,
                database_path="/tmp/test.db",
                version="1.0.0",
            )

            output = _strip_ansi(mock_stderr.getvalue())
            assert "DAYS REMAINING UNTIL AGI ACHIEVED" not in output

    def test_prints_config_details(self) -> None:
        """Config details are still printed."""
        with mock.patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            log_server_startup(
                host="127.0.0.1",
                port=8420,
                database_path="/tmp/test.db",
                version="1.0.0",
            )

            output = _strip_ansi(mock_stderr.getvalue())
            assert "v1.0.0" in output
            assert "127.0.0.1:8420" in output
            assert "/tmp/test.db" in output
