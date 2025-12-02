"""Tests for server logging module."""
from amelia.server.logging import logger


class TestServerLogging:
    """Tests for server logging exports."""

    def test_logger_is_loguru(self) -> None:
        """Server exports loguru logger."""
        # Verify it's a loguru logger by checking for loguru-specific attributes
        assert hasattr(logger, "opt")
        assert hasattr(logger, "bind")
        assert hasattr(logger, "catch")

    def test_logger_has_standard_methods(self) -> None:
        """Logger has standard logging methods."""
        assert hasattr(logger, "debug")
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
        assert hasattr(logger, "critical")
