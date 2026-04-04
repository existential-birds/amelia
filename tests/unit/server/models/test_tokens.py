"""Tests for token usage models and pricing."""

import asyncio
import time
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from amelia.server.models.model_cache import (
    ModelCacheCapabilities,
    ModelCacheEntry,
    ModelCacheModalities,
)
from amelia.server.models.tokens import (
    STATIC_FALLBACK_PRICING,
    ModelPricing,
    TokenUsage,
    calculate_token_cost,
    fetch_openrouter_pricing,
    get_pricing,
)


_default_wf_id = uuid4()


def make_usage(**overrides: Any) -> TokenUsage:
    """Create a TokenUsage with sensible defaults."""
    defaults: dict[str, Any] = {
        "workflow_id": _default_wf_id,
        "agent": "architect",
        "input_tokens": 1_000_000,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "timestamp": datetime(2025, 1, 1, 12, 0, 0),
    }
    return TokenUsage(**{**defaults, **overrides})


def make_cached_model_entry(
    model_id: str = "anthropic/claude-sonnet-4",
) -> ModelCacheEntry:
    """Create a cached model entry with pricing data."""
    now = datetime(2025, 1, 1, 12, 0, 0)
    return ModelCacheEntry(
        id=model_id,
        name="Claude Sonnet 4",
        provider="anthropic",
        context_length=200_000,
        max_output_tokens=16_000,
        input_cost_per_m=3.0,
        output_cost_per_m=15.0,
        capabilities=ModelCacheCapabilities(tool_call=True, reasoning=True, structured_output=True),
        modalities=ModelCacheModalities(input=["text"], output=["text"]),
        raw_response={"id": model_id},
        fetched_at=now,
        created_at=now,
    )


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

        assert usage.workflow_id is not None
        assert usage.agent == "developer"
        assert usage.input_tokens == 2000
        assert usage.output_tokens == 1000
        assert usage.cache_read_tokens == 500
        assert usage.cache_creation_tokens == 100


class TestModelPricing:
    """Tests for ModelPricing Pydantic model."""

    def test_model_pricing_fields(self) -> None:
        """ModelPricing has all expected fields."""
        pricing = ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75)
        assert pricing.input == 3.0
        assert pricing.output == 15.0
        assert pricing.cache_read == 0.3
        assert pricing.cache_write == 3.75


class TestStaticFallbackPricing:
    """Tests for STATIC_FALLBACK_PRICING dict."""

    def test_contains_current_gen_anthropic(self) -> None:
        """Static fallback has current-gen Anthropic models."""
        assert "claude-opus-4-5-20251101" in STATIC_FALLBACK_PRICING
        assert "claude-sonnet-4-5-20251101" in STATIC_FALLBACK_PRICING
        assert "claude-haiku-4-5-20251101" in STATIC_FALLBACK_PRICING

    def test_contains_previous_gen_anthropic(self) -> None:
        """Static fallback has previous-gen Anthropic models."""
        assert "claude-opus-4-20250514" in STATIC_FALLBACK_PRICING
        assert "claude-sonnet-4-20250514" in STATIC_FALLBACK_PRICING

    def test_contains_legacy_models(self) -> None:
        """Static fallback has legacy Anthropic models."""
        assert "claude-3-5-sonnet-20241022" in STATIC_FALLBACK_PRICING
        assert "claude-3-5-haiku-20241022" in STATIC_FALLBACK_PRICING
        assert "claude-3-opus-20240229" in STATIC_FALLBACK_PRICING
        assert "claude-3-haiku-20240307" in STATIC_FALLBACK_PRICING

    def test_short_aliases(self) -> None:
        """Short aliases resolve to correct pricing."""
        sonnet = STATIC_FALLBACK_PRICING["sonnet"]
        assert sonnet.input == 3.0
        assert sonnet.output == 15.0

        opus = STATIC_FALLBACK_PRICING["opus"]
        assert opus.input == 5.0
        assert opus.output == 25.0

        haiku = STATIC_FALLBACK_PRICING["haiku"]
        assert haiku.input == 1.0
        assert haiku.output == 5.0

    def test_all_entries_are_model_pricing(self) -> None:
        """Every entry is a ModelPricing instance."""
        for key, val in STATIC_FALLBACK_PRICING.items():
            assert isinstance(val, ModelPricing), f"{key} is not ModelPricing"

    def test_does_not_contain_openrouter_models(self) -> None:
        """Static fallback should NOT have OpenRouter-prefixed models."""
        for key in STATIC_FALLBACK_PRICING:
            assert "/" not in key, f"Found OpenRouter model {key} in static fallback"


class TestFetchOpenRouterPricing:
    """Tests for fetch_openrouter_pricing()."""

    async def test_no_api_key_returns_empty(self) -> None:
        """When OPENROUTER_API_KEY is not set, returns empty dict."""
        with patch.dict("os.environ", {}, clear=False):
            # Ensure the key is absent
            import os

            os.environ.pop("OPENROUTER_API_KEY", None)
            result = await fetch_openrouter_pricing()
            assert result == {}

    async def test_parses_openrouter_response(self) -> None:
        """Correctly parses OpenRouter API response and converts prices."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "anthropic/claude-sonnet-4",
                    "pricing": {
                        "prompt": "0.000003",
                        "completion": "0.000015",
                        "cache_read": "0.0000003",
                        "cache_write": "0.00000375",
                    },
                },
                {
                    "id": "openai/gpt-4o",
                    "pricing": {
                        "prompt": "0.0000025",
                        "completion": "0.00001",
                    },
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}),
            patch("amelia.server.models.tokens.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await fetch_openrouter_pricing()

        assert "anthropic/claude-sonnet-4" in result
        sonnet = result["anthropic/claude-sonnet-4"]
        assert sonnet.input == pytest.approx(3.0)  # 0.000003 * 1_000_000
        assert sonnet.output == pytest.approx(15.0)
        assert sonnet.cache_read == pytest.approx(0.3)
        assert sonnet.cache_write == pytest.approx(3.75)

        # Model with missing cache fields defaults to 0.0
        gpt4o = result["openai/gpt-4o"]
        assert gpt4o.input == pytest.approx(2.5)
        assert gpt4o.output == pytest.approx(10.0)
        assert gpt4o.cache_read == 0.0
        assert gpt4o.cache_write == 0.0

    async def test_null_pricing_fields_default_to_zero(self) -> None:
        """cache_read and cache_write default to 0.0 when null in response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "some/model",
                    "pricing": {
                        "prompt": "0.000001",
                        "completion": "0.000002",
                        "cache_read": None,
                        "cache_write": None,
                    },
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}),
            patch("amelia.server.models.tokens.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await fetch_openrouter_pricing()

        model = result["some/model"]
        assert model.cache_read == 0.0
        assert model.cache_write == 0.0

    async def test_free_model_with_zero_price_string(self) -> None:
        """Models with price "0" are included (not skipped as falsy)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "free/model",
                    "pricing": {
                        "prompt": "0",
                        "completion": "0",
                    },
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}),
            patch("amelia.server.models.tokens.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await fetch_openrouter_pricing()

        assert "free/model" in result
        free = result["free/model"]
        assert free.input == 0.0
        assert free.output == 0.0

    async def test_malformed_entry_skipped_without_discarding_others(self) -> None:
        """One malformed entry doesn't discard all pricing data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "good/model",
                    "pricing": {
                        "prompt": "0.000003",
                        "completion": "0.000015",
                    },
                },
                {
                    "id": "bad/model",
                    "pricing": {
                        "prompt": "not-a-number",
                        "completion": "0.000015",
                    },
                },
                {
                    "id": "also-good/model",
                    "pricing": {
                        "prompt": "0.000001",
                        "completion": "0.000002",
                    },
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}),
            patch("amelia.server.models.tokens.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await fetch_openrouter_pricing()

        assert "good/model" in result
        assert "also-good/model" in result
        assert "bad/model" not in result

    async def test_non_dict_entry_skipped(self) -> None:
        """Non-dict entries in data array are skipped without affecting others."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [
                "not-a-dict",
                None,
                {
                    "id": "good/model",
                    "pricing": {
                        "prompt": "0.000003",
                        "completion": "0.000015",
                    },
                },
                {
                    "id": "bad-pricing",
                    "pricing": "not-a-dict",
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}),
            patch("amelia.server.models.tokens.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await fetch_openrouter_pricing()

        assert "good/model" in result
        assert len(result) == 1

    async def test_network_error_returns_empty_dict(self) -> None:
        """On network error, returns empty dict and logs warning."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}),
            patch("amelia.server.models.tokens.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await fetch_openrouter_pricing()
            assert result == {}


class TestGetPricing:
    """Tests for get_pricing() with cache behavior."""

    def _reset_cache(self) -> None:
        """Reset module-level cache state between tests."""
        import amelia.server.models.tokens as tokens_mod

        tokens_mod._cached_pricing = {}
        tokens_mod._cache_expires_at = 0.0
        tokens_mod._cache_lock = asyncio.Lock()

    async def test_returns_static_fallback_when_fetch_fails(self) -> None:
        """When fetch fails, static fallback pricing is used."""
        self._reset_cache()
        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value={},
        ):
            pricing = await get_pricing("claude-sonnet-4-5-20251101")
            assert pricing is not None
            assert pricing.input == 3.0
            assert pricing.output == 15.0

    async def test_returns_cached_pricing(self) -> None:
        """Cached pricing is returned within TTL window."""
        self._reset_cache()
        cached = ModelPricing(input=99.0, output=99.0, cache_read=0.0, cache_write=0.0)

        import amelia.server.models.tokens as tokens_mod

        tokens_mod._cached_pricing = {"my-model": cached}
        tokens_mod._cache_expires_at = time.time() + 86400  # valid for 24h

        pricing = await get_pricing("my-model")
        assert pricing is not None
        assert pricing.input == 99.0

    async def test_refetches_after_ttl_expiry(self) -> None:
        """Cache is refreshed after TTL expires."""
        self._reset_cache()
        import amelia.server.models.tokens as tokens_mod

        # Set expired cache
        tokens_mod._cached_pricing = {"old-model": ModelPricing(input=1.0, output=1.0, cache_read=0.0, cache_write=0.0)}
        tokens_mod._cache_expires_at = time.time() - 1  # expired

        new_pricing = {"new-model": ModelPricing(input=5.0, output=10.0, cache_read=0.0, cache_write=0.0)}
        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value=new_pricing,
        ):
            pricing = await get_pricing("new-model")
            assert pricing is not None
            assert pricing.input == 5.0

    async def test_returns_none_for_unknown_model(self) -> None:
        """Returns None when model is not in cache or fallback."""
        self._reset_cache()
        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value={},
        ):
            pricing = await get_pricing("totally-unknown-model-xyz")
            assert pricing is None

    async def test_cache_prevents_concurrent_fetches(self) -> None:
        """Lock prevents multiple simultaneous fetches."""
        self._reset_cache()
        fetch_count = 0

        async def slow_fetch() -> dict[str, ModelPricing]:
            nonlocal fetch_count
            fetch_count += 1
            await asyncio.sleep(0.05)
            return {"test-model": ModelPricing(input=1.0, output=2.0, cache_read=0.0, cache_write=0.0)}

        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            side_effect=slow_fetch,
        ):
            results = await asyncio.gather(
                get_pricing("test-model"),
                get_pricing("test-model"),
                get_pricing("test-model"),
            )

        # Only one fetch should have happened due to locking
        assert fetch_count == 1
        # All should get the same result
        for r in results:
            assert r is not None
            assert r.input == 1.0

    async def test_ttl_set_even_on_fetch_failure(self) -> None:
        """TTL is set even when fetch returns empty dict (failure)."""
        self._reset_cache()
        import amelia.server.models.tokens as tokens_mod

        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value={},
        ):
            await get_pricing("anything")
            # TTL should be set even though fetch returned empty
            assert tokens_mod._cache_expires_at > time.time()

    async def test_preserves_cache_on_empty_refresh(self) -> None:
        """When fetch returns empty, previous cached pricing is preserved."""
        self._reset_cache()
        import amelia.server.models.tokens as tokens_mod

        old_pricing = ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75)
        tokens_mod._cached_pricing = {"anthropic/claude-sonnet-4": old_pricing}
        tokens_mod._cache_expires_at = time.time() - 1  # expired

        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value={},  # fetch failure
        ):
            pricing = await get_pricing("anthropic/claude-sonnet-4")
            assert pricing is not None
            assert pricing.input == 3.0  # preserved from old cache

    async def test_cached_pricing_preferred_over_static(self) -> None:
        """Cached (live) pricing is preferred over static fallback."""
        self._reset_cache()
        live_sonnet = ModelPricing(input=99.0, output=99.0, cache_read=0.0, cache_write=0.0)

        import amelia.server.models.tokens as tokens_mod

        tokens_mod._cached_pricing = {"claude-sonnet-4-5-20251101": live_sonnet}
        tokens_mod._cache_expires_at = time.time() + 86400

        pricing = await get_pricing("claude-sonnet-4-5-20251101")
        assert pricing is not None
        assert pricing.input == 99.0  # live, not static 3.0

    async def test_prefers_fresh_database_model_cache_when_available(self) -> None:
        """Database-backed model metadata is used before live pricing fetch."""
        self._reset_cache()
        repo = MagicMock()
        repo.get_model = AsyncMock(return_value=make_cached_model_entry())
        repo.is_stale = AsyncMock(return_value=False)

        with (
            patch("amelia.server.models.tokens._get_model_cache_repository", return_value=repo),
            patch(
                "amelia.server.models.tokens.fetch_openrouter_pricing",
                new_callable=AsyncMock,
                return_value={},
            ) as fetch_pricing,
        ):
            pricing = await get_pricing("anthropic/claude-sonnet-4")

        assert pricing is not None
        assert pricing.input == 3.0
        assert pricing.output == 15.0
        fetch_pricing.assert_not_awaited()


class TestCalculateTokenCost:
    """Tests for async calculate_token_cost()."""

    def _reset_cache(self) -> None:
        """Reset module-level cache state between tests."""
        import amelia.server.models.tokens as tokens_mod

        tokens_mod._cached_pricing = {}
        tokens_mod._cache_expires_at = 0.0
        tokens_mod._cache_lock = asyncio.Lock()

    async def test_basic_cost(self) -> None:
        """Cost calculation for basic input/output tokens."""
        self._reset_cache()
        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value={},
        ):
            # Uses static fallback for sonnet
            cost = await calculate_token_cost(
                model="claude-sonnet-4-5-20251101",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            )
            # Input: 1M * $3/M = $3, Output: 1M * $15/M = $15
            assert cost == 18.0

    async def test_cost_with_cache_reads(self) -> None:
        """Cache reads are charged at discounted rate."""
        self._reset_cache()
        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value={},
        ):
            cost = await calculate_token_cost(
                model="claude-sonnet-4-5-20251101",
                input_tokens=1_000_000,
                output_tokens=0,
                cache_read_tokens=500_000,
            )
            # Base: (1M - 500K) * $3/M = $1.50, Cache: 500K * $0.30/M = $0.15
            assert cost == 1.65

    async def test_cost_with_cache_writes(self) -> None:
        """Cache creation is charged at premium rate."""
        self._reset_cache()
        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value={},
        ):
            cost = await calculate_token_cost(
                model="claude-sonnet-4-5-20251101",
                input_tokens=1_000_000,
                output_tokens=0,
                cache_creation_tokens=100_000,
            )
            # Base: 1M * $3/M = $3.00, Cache write: 100K * $3.75/M = $0.375
            assert cost == 3.375

    async def test_cost_with_opus_model(self) -> None:
        """Cost calculation uses correct model pricing."""
        self._reset_cache()
        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value={},
        ):
            cost = await calculate_token_cost(
                model="claude-opus-4-20250514",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            )
            # Input: 1M * $15/M = $15, Output: 1M * $75/M = $75
            assert cost == 90.0

    async def test_unknown_model_returns_zero(self) -> None:
        """Unknown models return 0.0 cost (no fallback to Sonnet)."""
        self._reset_cache()
        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value={},
        ):
            cost = await calculate_token_cost(
                model="unknown-model-2025",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            )
            assert cost == 0.0

    async def test_cost_precision(self) -> None:
        """Cost is rounded to 6 decimal places."""
        self._reset_cache()
        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value={},
        ):
            cost = await calculate_token_cost(
                model="claude-sonnet-4-5-20251101",
                input_tokens=1,
                output_tokens=1,
            )
            assert cost == round(cost, 6)

    async def test_cost_with_live_pricing(self) -> None:
        """Cost calculation uses live cached pricing when available."""
        self._reset_cache()
        import amelia.server.models.tokens as tokens_mod

        tokens_mod._cached_pricing = {
            "openai/gpt-4o": ModelPricing(input=2.5, output=10.0, cache_read=1.25, cache_write=0.0),
        }
        tokens_mod._cache_expires_at = time.time() + 86400

        cost = await calculate_token_cost(
            model="openai/gpt-4o",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # Input: 1M * $2.5/M = $2.5, Output: 1M * $10/M = $10
        assert cost == 12.5

    async def test_short_alias_cost(self) -> None:
        """Short aliases resolve to correct pricing for cost calculation."""
        self._reset_cache()
        with patch(
            "amelia.server.models.tokens.fetch_openrouter_pricing",
            new_callable=AsyncMock,
            return_value={},
        ):
            cost = await calculate_token_cost(
                model="sonnet",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            )
            # Same as claude-sonnet-4-5-20251101: $3 + $15 = $18
            assert cost == 18.0
