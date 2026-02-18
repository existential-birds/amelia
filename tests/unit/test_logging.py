"""Tests for amelia/logging.py format functions."""

from typing import Any
from unittest.mock import MagicMock

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
