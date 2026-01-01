"""Tests for token usage models."""

from datetime import datetime
from typing import Any

from amelia.server.models.tokens import MODEL_PRICING, TokenUsage, calculate_token_cost


def make_usage(**overrides: Any) -> TokenUsage:
    """Create a TokenUsage with sensible defaults."""
    defaults: dict[str, Any] = {
        "workflow_id": "wf-123",
        "agent": "architect",
        "input_tokens": 1_000_000,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "timestamp": datetime(2025, 1, 1, 12, 0, 0),
    }
    return TokenUsage(**{**defaults, **overrides})


class TestTokenUsage:
    """Tests for TokenUsage model."""

    def test_create_token_usage(self) -> None:
        """TokenUsage can be created with all fields."""
        usage = make_usage(
            agent="developer",
            input_tokens=2000,
            output_tokens=1000,
            cache_read_tokens=500,
            cache_creation_tokens=100,
        )

        assert usage.workflow_id == "wf-123"
        assert usage.agent == "developer"
        assert usage.input_tokens == 2000
        assert usage.output_tokens == 1000
        assert usage.cache_read_tokens == 500
        assert usage.cache_creation_tokens == 100


class TestModelPricing:
    """Tests for model pricing constants."""

    def test_sonnet_pricing(self) -> None:
        """Sonnet pricing is correctly defined."""
        sonnet = MODEL_PRICING["claude-sonnet-4-20250514"]
        assert sonnet["input"] == 3.0
        assert sonnet["output"] == 15.0
        assert sonnet["cache_read"] == 0.3
        assert sonnet["cache_write"] == 3.75

    def test_opus_pricing(self) -> None:
        """Opus pricing is correctly defined."""
        opus = MODEL_PRICING["claude-opus-4-20250514"]
        assert opus["input"] == 15.0
        assert opus["output"] == 75.0


class TestCostCalculation:
    """Tests for cost calculation function."""

    def test_basic_cost(self) -> None:
        """Cost calculation for basic input/output tokens."""
        usage = make_usage(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = calculate_token_cost(usage)
        # Input: 1M * $3/M = $3, Output: 1M * $15/M = $15
        assert cost == 18.0

    def test_cost_with_cache_reads(self) -> None:
        """Cache reads are charged at discounted rate."""
        usage = make_usage(
            input_tokens=1_000_000,
            cache_read_tokens=500_000,
        )
        cost = calculate_token_cost(usage)
        # Base: (1M - 500K) * $3/M = $1.50, Cache: 500K * $0.30/M = $0.15
        assert cost == 1.65

    def test_cost_with_cache_writes(self) -> None:
        """Cache creation is charged at premium rate."""
        usage = make_usage(
            input_tokens=1_000_000,
            cache_creation_tokens=100_000,
        )
        cost = calculate_token_cost(usage)
        # Base: 1M * $3/M = $3.00, Cache write: 100K * $3.75/M = $0.375
        assert cost == 3.375

    def test_cost_with_opus_model(self) -> None:
        """Cost calculation uses correct model pricing."""
        usage = make_usage(
            model="claude-opus-4-20250514",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        cost = calculate_token_cost(usage)
        # Input: 1M * $15/M = $15, Output: 1M * $75/M = $75
        assert cost == 90.0

    def test_unknown_model_uses_sonnet_pricing(self) -> None:
        """Unknown models fall back to Sonnet pricing."""
        usage = make_usage(model="unknown-model-2025")
        cost = calculate_token_cost(usage)
        # Falls back to Sonnet: 1M * $3/M = $3
        assert cost == 3.0

    def test_cost_precision(self) -> None:
        """Cost is rounded to 6 decimal places."""
        usage = make_usage(input_tokens=1, output_tokens=1)
        cost = calculate_token_cost(usage)
        assert cost == round(cost, 6)
