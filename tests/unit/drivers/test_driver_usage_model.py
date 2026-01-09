"""Tests for DriverUsage model."""
from amelia.drivers.base import DriverUsage


class TestDriverUsageModel:
    """Tests for the DriverUsage Pydantic model."""

    def test_driver_usage_all_fields_optional(self) -> None:
        """DriverUsage should allow all fields to be None."""
        usage = DriverUsage()

        assert usage.input_tokens is None
        assert usage.output_tokens is None
        assert usage.cache_read_tokens is None
        assert usage.cache_creation_tokens is None
        assert usage.cost_usd is None
        assert usage.duration_ms is None
        assert usage.num_turns is None
        assert usage.model is None

    def test_driver_usage_with_all_fields(self) -> None:
        """DriverUsage should accept all fields when provided."""
        usage = DriverUsage(
            input_tokens=1500,
            output_tokens=500,
            cache_read_tokens=1000,
            cache_creation_tokens=200,
            cost_usd=0.025,
            duration_ms=5000,
            num_turns=3,
            model="openrouter:anthropic/claude-3.5-sonnet",
        )

        assert usage.input_tokens == 1500
        assert usage.output_tokens == 500
        assert usage.cache_read_tokens == 1000
        assert usage.cache_creation_tokens == 200
        assert usage.cost_usd == 0.025
        assert usage.duration_ms == 5000
        assert usage.num_turns == 3
        assert usage.model == "openrouter:anthropic/claude-3.5-sonnet"

    def test_driver_usage_partial_fields(self) -> None:
        """DriverUsage should work with only some fields set."""
        usage = DriverUsage(
            input_tokens=100,
            output_tokens=50,
            model="test-model",
        )

        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.model == "test-model"
        assert usage.cost_usd is None
        assert usage.duration_ms is None
