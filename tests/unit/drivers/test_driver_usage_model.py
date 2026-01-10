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


class TestDriverInterfaceProtocol:
    """Tests for DriverInterface protocol changes."""

    def test_driver_interface_has_get_usage_method(self) -> None:
        """DriverInterface protocol should define get_usage() method."""
        from amelia.drivers.base import DriverInterface, DriverUsage

        # Check that get_usage is in the protocol's annotations
        assert hasattr(DriverInterface, "get_usage")

        # Verify it's a callable that returns DriverUsage | None
        import inspect
        import types
        sig = inspect.signature(DriverInterface.get_usage)
        # Return annotation is a UnionType: DriverUsage | None
        ret = sig.return_annotation
        assert isinstance(ret, types.UnionType)
        assert DriverUsage in ret.__args__
        assert type(None) in ret.__args__
