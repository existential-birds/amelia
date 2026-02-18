"""Tests for amelia/logging.py format functions."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from amelia.logging import _plain_log_format


def _make_record(**extra: Any) -> MagicMock:
    """Create a minimal loguru Record-like dict for testing format functions."""
    record = MagicMock()
    record.__getitem__ = lambda self, key: {
        "extra": extra,
        "level": MagicMock(name="INFO"),
        "exception": None,
    }[key]
    return record


class TestPlainLogFormatBraceEscaping:
    """_plain_log_format must escape braces in extra field repr output."""

    def test_nested_dict_braces_are_escaped(self) -> None:
        """Nested dict in extra should not cause KeyError in format_map."""
        record = _make_record(details={"key": "value"})
        fmt = _plain_log_format(record)
        # Braces from repr should be doubled for loguru format_map safety
        assert "{{" in fmt
        assert "}}" in fmt

    def test_list_of_dicts_braces_are_escaped(self) -> None:
        """List of dicts in extra should not cause KeyError in format_map."""
        record = _make_record(todos=[{"content": "Fix X", "status": "pending"}])
        fmt = _plain_log_format(record)
        assert "{{" in fmt

    def test_scalar_extra_unchanged(self) -> None:
        """Scalar extra fields without braces should pass through normally."""
        record = _make_record(count=42, name="test")
        fmt = _plain_log_format(record)
        assert "count=42" in fmt
        assert "name='test'" in fmt

    def test_empty_extra_no_separator(self) -> None:
        """No extra separator when extra dict is empty."""
        record = _make_record()
        fmt = _plain_log_format(record)
        assert "│" in fmt  # timestamp/level separators exist
        # Should not have a trailing separator for empty extra
        assert fmt.count("│") == 2  # time │ level │ name:message


class TestLogTodos:
    """log_todos renders rich table on TTY, no-op on piped stderr."""

    def test_no_output_when_not_tty(self, capsys: pytest.CaptureFixture[str]) -> None:
        """log_todos should be a no-op when stderr is not a TTY."""
        from amelia.logging import log_todos

        with patch("sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = False
            log_todos([{"content": "Fix bug", "status": "completed"}])
            mock_stderr.write.assert_not_called()

    def test_renders_on_tty(self) -> None:
        """log_todos should write to stderr when it is a TTY."""
        from amelia.logging import log_todos

        with patch("sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = True
            with patch("amelia.logging.Console") as mock_console_cls:
                mock_console = MagicMock()
                mock_console_cls.return_value = mock_console
                log_todos([{"content": "Fix bug", "status": "completed"}])
                mock_console.print.assert_called_once()

    def test_handles_empty_list(self) -> None:
        """log_todos should handle empty todo list gracefully."""
        from amelia.logging import log_todos

        with patch("sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = True
            with patch("amelia.logging.Console") as mock_console_cls:
                mock_console = MagicMock()
                mock_console_cls.return_value = mock_console
                log_todos([])
                mock_console.print.assert_called_once()  # Still prints table (empty)
