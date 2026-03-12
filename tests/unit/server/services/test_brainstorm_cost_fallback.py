"""Tests for cost calculation fallback in brainstorm message creation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.drivers.base import DriverUsage
from amelia.server.models.brainstorm import MessageUsage


@pytest.fixture
def _mock_driver():
    """Create a mock driver with configurable usage."""
    driver = MagicMock()
    driver.get_usage.return_value = None
    return driver


def _make_driver_usage(
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cost_usd: float | None = None,
    model: str | None = "claude-sonnet-4-5-20251101",
    cache_read_tokens: int | None = 0,
    cache_creation_tokens: int | None = 0,
) -> DriverUsage:
    return DriverUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        model=model,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
    )


async def _run_cost_fallback(driver_usage: DriverUsage) -> MessageUsage | None:
    """Run the cost fallback logic extracted from brainstorm send_message.

    This mirrors the logic in BrainstormService.send_message around the
    MessageUsage construction, allowing us to test it in isolation.
    """
    from amelia.server.models.tokens import calculate_token_cost

    message_usage: MessageUsage | None = None
    if driver_usage:
        cost = driver_usage.cost_usd or 0.0

        # Compute cost from cached pricing if driver didn't provide it
        if not cost and driver_usage.model:
            cost = await calculate_token_cost(
                model=driver_usage.model,
                input_tokens=driver_usage.input_tokens or 0,
                output_tokens=driver_usage.output_tokens or 0,
                cache_read_tokens=driver_usage.cache_read_tokens or 0,
                cache_creation_tokens=driver_usage.cache_creation_tokens or 0,
            )

        message_usage = MessageUsage(
            input_tokens=driver_usage.input_tokens or 0,
            output_tokens=driver_usage.output_tokens or 0,
            cost_usd=cost,
        )
    return message_usage


class TestBrainstormCostFallback:
    """Test cost calculation fallback when driver doesn't provide cost."""

    @patch("amelia.server.models.tokens.get_pricing")
    async def test_calls_calculate_token_cost_when_driver_has_no_cost(
        self, mock_get_pricing: AsyncMock
    ):
        """When driver_usage.cost_usd is None, calculate_token_cost is called."""
        from amelia.server.models.tokens import ModelPricing

        mock_get_pricing.return_value = ModelPricing(
            input=3.0, output=15.0, cache_read=0.3, cache_write=3.75
        )

        usage = _make_driver_usage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=None,
            model="claude-sonnet-4-5-20251101",
        )

        result = await _run_cost_fallback(usage)

        assert result is not None
        assert result.input_tokens == 1000
        assert result.output_tokens == 500
        # Cost should be computed: (1000 * 3.0 / 1M) + (500 * 15.0 / 1M) = 0.003 + 0.0075 = 0.0105
        assert result.cost_usd == pytest.approx(0.0105, abs=1e-6)
        mock_get_pricing.assert_awaited_once_with("claude-sonnet-4-5-20251101")

    async def test_passes_through_driver_provided_cost(self):
        """When driver provides cost_usd, it's used directly without fallback."""
        usage = _make_driver_usage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05,
            model="claude-sonnet-4-5-20251101",
        )

        with patch(
            "amelia.server.models.tokens.get_pricing"
        ) as mock_get_pricing:
            result = await _run_cost_fallback(usage)

        assert result is not None
        assert result.cost_usd == 0.05
        mock_get_pricing.assert_not_awaited()

    @patch("amelia.server.models.tokens.get_pricing")
    async def test_skips_calculation_when_model_is_none(
        self, mock_get_pricing: AsyncMock
    ):
        """When driver_usage.model is None, cost stays 0.0 (no calculation)."""
        usage = _make_driver_usage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=None,
            model=None,
        )

        result = await _run_cost_fallback(usage)

        assert result is not None
        assert result.cost_usd == 0.0
        mock_get_pricing.assert_not_awaited()

    @patch("amelia.server.models.tokens.get_pricing")
    async def test_includes_cache_tokens_in_calculation(
        self, mock_get_pricing: AsyncMock
    ):
        """Cache read/write tokens are passed to calculate_token_cost."""
        from amelia.server.models.tokens import ModelPricing

        mock_get_pricing.return_value = ModelPricing(
            input=3.0, output=15.0, cache_read=0.3, cache_write=3.75
        )

        usage = _make_driver_usage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=None,
            model="claude-sonnet-4-5-20251101",
            cache_read_tokens=200,
            cache_creation_tokens=100,
        )

        result = await _run_cost_fallback(usage)

        assert result is not None
        # base_input = 1000 - 200 = 800
        # cost = (800 * 3.0 / 1M) + (200 * 0.3 / 1M) + (100 * 3.75 / 1M) + (500 * 15.0 / 1M)
        #      = 0.0024 + 0.00006 + 0.000375 + 0.0075 = 0.010335
        assert result.cost_usd == pytest.approx(0.010335, abs=1e-6)

    async def test_zero_cost_triggers_fallback(self):
        """When driver provides cost_usd=0.0, fallback is triggered."""
        from amelia.server.models.tokens import ModelPricing

        usage = _make_driver_usage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0,
            model="claude-sonnet-4-5-20251101",
        )

        with patch(
            "amelia.server.models.tokens.get_pricing",
            new_callable=AsyncMock,
            return_value=ModelPricing(
                input=3.0, output=15.0, cache_read=0.3, cache_write=3.75
            ),
        ) as mock_get_pricing:
            result = await _run_cost_fallback(usage)

        assert result is not None
        assert result.cost_usd > 0.0
        mock_get_pricing.assert_awaited_once()
