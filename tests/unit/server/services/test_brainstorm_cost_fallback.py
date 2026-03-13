"""Tests for cost calculation fallback in brainstorm message creation."""

from unittest.mock import AsyncMock, patch

import pytest

from amelia.drivers.base import DriverUsage
from amelia.server.services.brainstorm import _build_message_usage


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


class TestBrainstormCostFallback:
    """Test cost calculation fallback when driver doesn't provide cost."""

    @patch("amelia.server.services.brainstorm.calculate_token_cost", new_callable=AsyncMock)
    async def test_calls_calculate_token_cost_when_driver_has_no_cost(
        self, mock_calc: AsyncMock
    ):
        """When driver_usage.cost_usd is None, calculate_token_cost is called."""
        mock_calc.return_value = 0.0105

        usage = _make_driver_usage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=None,
            model="claude-sonnet-4-5-20251101",
        )

        result = await _build_message_usage(usage)

        assert result.input_tokens == 1000
        assert result.output_tokens == 500
        assert result.cost_usd == pytest.approx(0.0105, abs=1e-6)
        mock_calc.assert_awaited_once_with(
            model="claude-sonnet-4-5-20251101",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )

    @patch("amelia.server.services.brainstorm.calculate_token_cost", new_callable=AsyncMock)
    async def test_passes_through_driver_provided_cost(self, mock_calc: AsyncMock):
        """When driver provides cost_usd, it's used directly without fallback."""
        usage = _make_driver_usage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05,
            model="claude-sonnet-4-5-20251101",
        )

        result = await _build_message_usage(usage)

        assert result.cost_usd == 0.05
        mock_calc.assert_not_awaited()

    @patch("amelia.server.services.brainstorm.calculate_token_cost", new_callable=AsyncMock)
    async def test_skips_calculation_when_model_is_none(self, mock_calc: AsyncMock):
        """When driver_usage.model is None, cost stays 0.0 (no calculation)."""
        usage = _make_driver_usage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=None,
            model=None,
        )

        result = await _build_message_usage(usage)

        assert result.cost_usd == 0.0
        mock_calc.assert_not_awaited()

    @patch("amelia.server.services.brainstorm.calculate_token_cost", new_callable=AsyncMock)
    async def test_includes_cache_tokens_in_calculation(self, mock_calc: AsyncMock):
        """Cache read/write tokens are passed to calculate_token_cost."""
        mock_calc.return_value = 0.010335

        usage = _make_driver_usage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=None,
            model="claude-sonnet-4-5-20251101",
            cache_read_tokens=200,
            cache_creation_tokens=100,
        )

        result = await _build_message_usage(usage)

        assert result.cost_usd == pytest.approx(0.010335, abs=1e-6)
        mock_calc.assert_awaited_once_with(
            model="claude-sonnet-4-5-20251101",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=200,
            cache_creation_tokens=100,
        )

    @patch("amelia.server.services.brainstorm.calculate_token_cost", new_callable=AsyncMock)
    async def test_zero_cost_triggers_fallback(self, mock_calc: AsyncMock):
        """When driver provides cost_usd=0.0, fallback is triggered."""
        mock_calc.return_value = 0.0105

        usage = _make_driver_usage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0,
            model="claude-sonnet-4-5-20251101",
        )

        result = await _build_message_usage(usage)

        assert result.cost_usd > 0.0
        mock_calc.assert_awaited_once()

    @patch("amelia.server.services.brainstorm.calculate_token_cost", new_callable=AsyncMock)
    async def test_fallback_model_used_when_driver_usage_model_is_none(
        self, mock_calc: AsyncMock
    ):
        """When driver_usage.model is None but fallback_model is provided, cost is calculated."""
        mock_calc.return_value = 0.0105

        usage = _make_driver_usage(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=None,
            model=None,
        )

        result = await _build_message_usage(usage, fallback_model="claude-sonnet-4-5-20251101")

        assert result.cost_usd == pytest.approx(0.0105, abs=1e-6)
        mock_calc.assert_awaited_once_with(
            model="claude-sonnet-4-5-20251101",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
