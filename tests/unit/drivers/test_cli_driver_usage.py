"""Tests for ClaudeCliDriver.get_usage() method."""
from unittest.mock import MagicMock

from amelia.drivers.base import DriverUsage
from amelia.drivers.cli.claude import ClaudeCliDriver


class TestClaudeCliDriverGetUsage:
    """Tests for ClaudeCliDriver.get_usage() method."""

    def test_get_usage_returns_none_when_no_last_result(self) -> None:
        """get_usage() should return None when no execution has occurred."""
        driver = ClaudeCliDriver(model="sonnet")

        result = driver.get_usage()

        assert result is None

    def test_get_usage_returns_none_when_no_usage_data(self) -> None:
        """get_usage() should return None when last_result_message has no usage."""
        driver = ClaudeCliDriver(model="sonnet")
        driver.last_result_message = MagicMock()
        driver.last_result_message.usage = None

        result = driver.get_usage()

        assert result is None

    def test_get_usage_translates_sdk_fields(self) -> None:
        """get_usage() should translate SDK ResultMessage fields to DriverUsage."""
        driver = ClaudeCliDriver(model="sonnet")

        # Mock ResultMessage with full usage data
        mock_result = MagicMock()
        mock_result.usage = {
            "model": "claude-sonnet-4-20250514",
            "input_tokens": 1500,
            "output_tokens": 500,
            "cache_read_input_tokens": 1000,
            "cache_creation_input_tokens": 200,
        }
        mock_result.total_cost_usd = 0.025
        mock_result.duration_ms = 5000
        mock_result.num_turns = 3
        driver.last_result_message = mock_result

        result = driver.get_usage()

        assert isinstance(result, DriverUsage)
        assert result.input_tokens == 1500
        assert result.output_tokens == 500
        assert result.cache_read_tokens == 1000
        assert result.cache_creation_tokens == 200
        assert result.cost_usd == 0.025
        assert result.duration_ms == 5000
        assert result.num_turns == 3
        assert result.model == "claude-sonnet-4-20250514"

    def test_get_usage_falls_back_to_driver_model(self) -> None:
        """get_usage() should use driver.model when usage.model is missing."""
        driver = ClaudeCliDriver(model="opus")

        mock_result = MagicMock()
        mock_result.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            # No model in usage
        }
        mock_result.total_cost_usd = 0.01
        mock_result.duration_ms = 1000
        mock_result.num_turns = 1
        driver.last_result_message = mock_result

        result = driver.get_usage()

        assert result is not None
        assert result.model == "opus"

    def test_get_usage_handles_partial_usage_data(self) -> None:
        """get_usage() should handle ResultMessage with partial usage fields."""
        driver = ClaudeCliDriver(model="sonnet")

        mock_result = MagicMock()
        mock_result.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            # Missing cache tokens
        }
        mock_result.total_cost_usd = None  # Missing cost
        mock_result.duration_ms = None  # Missing duration
        mock_result.num_turns = None  # Missing turns
        driver.last_result_message = mock_result

        result = driver.get_usage()

        assert result is not None
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.cache_read_tokens is None
        assert result.cache_creation_tokens is None
        assert result.cost_usd is None
        assert result.duration_ms is None
        assert result.num_turns is None
