"""Tests for token usage models."""

import pytest
from datetime import datetime, UTC

from amelia.server.models.tokens import TokenUsage, MODEL_PRICING, calculate_token_cost


class TestTokenUsage:
    """Tests for TokenUsage model."""

    def test_create_basic_token_usage(self):
        """TokenUsage can be created with required fields."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            input_tokens=1000,
            output_tokens=500,
            timestamp=datetime.now(UTC),
        )

        assert usage.workflow_id == "wf-123"
        assert usage.agent == "architect"
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500

    def test_default_model_is_sonnet(self):
        """Default model is claude-sonnet-4."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            input_tokens=1000,
            output_tokens=500,
            timestamp=datetime.now(UTC),
        )

        assert usage.model == "claude-sonnet-4-20250514"

    def test_cache_tokens_default_zero(self):
        """Cache tokens default to zero."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            input_tokens=1000,
            output_tokens=500,
            timestamp=datetime.now(UTC),
        )

        assert usage.cache_read_tokens == 0
        assert usage.cache_creation_tokens == 0

    def test_token_usage_with_cache(self):
        """TokenUsage can include cache token counts."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="developer",
            input_tokens=2000,
            output_tokens=1000,
            cache_read_tokens=500,
            cache_creation_tokens=100,
            timestamp=datetime.now(UTC),
        )

        assert usage.cache_read_tokens == 500
        assert usage.cache_creation_tokens == 100


class TestModelPricing:
    """Tests for model pricing constants."""

    def test_sonnet_pricing_defined(self):
        """Sonnet pricing is defined."""
        assert "claude-sonnet-4-20250514" in MODEL_PRICING
        sonnet = MODEL_PRICING["claude-sonnet-4-20250514"]
        assert sonnet["input"] == 3.0
        assert sonnet["output"] == 15.0
        assert sonnet["cache_read"] == 0.3
        assert sonnet["cache_write"] == 3.75

    def test_opus_pricing_defined(self):
        """Opus pricing is defined."""
        assert "claude-opus-4-20250514" in MODEL_PRICING
        opus = MODEL_PRICING["claude-opus-4-20250514"]
        assert opus["input"] == 15.0
        assert opus["output"] == 75.0


class TestCostCalculation:
    """Tests for cost calculation function."""

    def test_basic_cost_calculation(self):
        """Basic cost calculation without cache."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="claude-sonnet-4-20250514",
            input_tokens=1_000_000,  # 1M tokens
            output_tokens=1_000_000,
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Input: 1M * $3/M = $3
        # Output: 1M * $15/M = $15
        # Total: $18
        assert cost == 18.0

    def test_cost_with_cache_reads(self):
        """Cost calculation with cache reads (discounted)."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="claude-sonnet-4-20250514",
            input_tokens=1_000_000,
            output_tokens=0,
            cache_read_tokens=500_000,  # Half from cache
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Base input: (1M - 500K) * $3/M = $1.50
        # Cache read: 500K * $0.30/M = $0.15
        # Total: $1.65
        assert cost == 1.65

    def test_cost_with_cache_writes(self):
        """Cost calculation with cache creation (premium rate)."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="claude-sonnet-4-20250514",
            input_tokens=1_000_000,
            output_tokens=0,
            cache_creation_tokens=100_000,  # 100K cache writes
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Base input: 1M * $3/M = $3.00
        # Cache write: 100K * $3.75/M = $0.375
        # Total: $3.375
        assert cost == 3.375

    def test_cost_with_opus_model(self):
        """Cost calculation uses correct model pricing."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="claude-opus-4-20250514",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Input: 1M * $15/M = $15
        # Output: 1M * $75/M = $75
        # Total: $90
        assert cost == 90.0

    def test_cost_with_unknown_model_uses_sonnet(self):
        """Unknown models fall back to Sonnet pricing."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="unknown-model-2025",
            input_tokens=1_000_000,
            output_tokens=0,
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Falls back to Sonnet: 1M * $3/M = $3
        assert cost == 3.0

    def test_cost_rounds_to_micro_dollars(self):
        """Cost is rounded to 6 decimal places (micro-dollars)."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="claude-sonnet-4-20250514",
            input_tokens=1,  # Very small
            output_tokens=1,
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Should be a small number with at most 6 decimal places
        assert cost == round(cost, 6)
