"""Tests for structured logging configuration."""
from amelia.server.logging import capture_logs, configure_logging


class TestStructuredLogging:
    """Tests for structlog configuration."""

    def test_configure_logging_returns_logger(self):
        """configure_logging returns a bound logger."""
        logger = configure_logging()
        assert logger is not None
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")

    def test_log_output_is_json(self):
        """Log output is JSON formatted."""
        logger = configure_logging()

        with capture_logs() as logs:
            logger.info("test message", key="value")

        # Verify we captured the log
        assert len(logs) >= 1
        log_entry = logs[0]
        assert log_entry.get("event") == "test message"
        assert log_entry.get("key") == "value"

    def test_log_includes_timestamp(self):
        """Log entries include ISO timestamp."""
        logger = configure_logging()

        with capture_logs() as logs:
            logger.info("test")

        assert len(logs) >= 1
        log_entry = logs[0]
        assert "timestamp" in log_entry

    def test_log_includes_level(self):
        """Log entries include log level."""
        logger = configure_logging()

        with capture_logs() as logs:
            logger.warning("test warning")

        assert len(logs) >= 1
        log_entry = logs[0]
        assert log_entry.get("level") == "warning"
