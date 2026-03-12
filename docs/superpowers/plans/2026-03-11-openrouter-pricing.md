# OpenRouter Live Pricing Integration — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static `MODEL_PRICING` dict with live pricing fetched from the OpenRouter API, cached in-memory with 24h TTL, falling back to a small Anthropic-only static table.

**Architecture:** New `ModelPricing` Pydantic model + async fetch/cache layer in `amelia/server/models/tokens.py`. Two callsites (`_save_token_usage` in nodes.py, brainstorm message creation in brainstorm.py) gain a cost fallback that calls `calculate_token_cost` when the driver doesn't provide cost.

**Tech Stack:** Python 3.12+, Pydantic, httpx (already a dependency), asyncio.Lock, loguru, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-11-openrouter-pricing-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `amelia/server/models/tokens.py` | `ModelPricing` model, `STATIC_FALLBACK_PRICING`, fetch/cache layer, async `calculate_token_cost` | Modify |
| `amelia/pipelines/nodes.py` | Cost fallback in `_save_token_usage()` | Modify |
| `amelia/server/services/brainstorm.py` | Cost fallback before `MessageUsage` construction | Modify |
| `tests/unit/server/models/test_tokens.py` | Unit tests for pricing fetch, cache, fallback, cost calc | Modify |
| `tests/unit/pipelines/test_nodes_cost_fallback.py` | Tests for `_save_token_usage` cost fallback | Create |
| `tests/unit/server/services/test_brainstorm_cost_fallback.py` | Tests for brainstorm cost fallback | Create |

---

## Chunk 1: Core pricing infrastructure

### Task 1: Add `ModelPricing` model and `STATIC_FALLBACK_PRICING`

**Files:**
- Modify: `amelia/server/models/tokens.py:1-190` (replace `MODEL_PRICING`)
- Test: `tests/unit/server/models/test_tokens.py`

- [ ] **Step 1: Write failing tests for `ModelPricing` and static fallback**

Add to `tests/unit/server/models/test_tokens.py`:

```python
from amelia.server.models.tokens import ModelPricing, STATIC_FALLBACK_PRICING


class TestModelPricing:
    """Tests for ModelPricing Pydantic model."""

    def test_create_model_pricing(self) -> None:
        pricing = ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75)
        assert pricing.input == 3.0
        assert pricing.output == 15.0
        assert pricing.cache_read == 0.3
        assert pricing.cache_write == 3.75


class TestStaticFallbackPricing:
    """Tests for the static Anthropic fallback pricing table."""

    def test_contains_current_gen_models(self) -> None:
        assert "claude-opus-4-5-20251101" in STATIC_FALLBACK_PRICING
        assert "claude-sonnet-4-5-20251101" in STATIC_FALLBACK_PRICING
        assert "claude-haiku-4-5-20251101" in STATIC_FALLBACK_PRICING

    def test_contains_previous_gen_models(self) -> None:
        assert "claude-opus-4-20250514" in STATIC_FALLBACK_PRICING
        assert "claude-sonnet-4-20250514" in STATIC_FALLBACK_PRICING

    def test_contains_legacy_models(self) -> None:
        assert "claude-3-5-sonnet-20241022" in STATIC_FALLBACK_PRICING
        assert "claude-3-5-haiku-20241022" in STATIC_FALLBACK_PRICING
        assert "claude-3-opus-20240229" in STATIC_FALLBACK_PRICING
        assert "claude-3-haiku-20240307" in STATIC_FALLBACK_PRICING

    def test_contains_short_aliases(self) -> None:
        assert "sonnet" in STATIC_FALLBACK_PRICING
        assert "opus" in STATIC_FALLBACK_PRICING
        assert "haiku" in STATIC_FALLBACK_PRICING

    def test_all_entries_are_model_pricing(self) -> None:
        for model_id, pricing in STATIC_FALLBACK_PRICING.items():
            assert isinstance(pricing, ModelPricing), f"{model_id} is not ModelPricing"

    def test_does_not_contain_non_anthropic_models(self) -> None:
        for model_id in STATIC_FALLBACK_PRICING:
            assert not model_id.startswith("openai/"), f"Found non-Anthropic: {model_id}"
            assert not model_id.startswith("google/"), f"Found non-Anthropic: {model_id}"
            assert not model_id.startswith("deepseek/"), f"Found non-Anthropic: {model_id}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/models/test_tokens.py::TestModelPricing -v && uv run pytest tests/unit/server/models/test_tokens.py::TestStaticFallbackPricing -v`
Expected: FAIL — `ModelPricing` and `STATIC_FALLBACK_PRICING` don't exist yet

- [ ] **Step 3: Implement `ModelPricing` and `STATIC_FALLBACK_PRICING`**

In `amelia/server/models/tokens.py`, replace the entire `MODEL_PRICING` dict (lines 10-190) with:

```python
import asyncio
import os
import time

import httpx
from loguru import logger


class ModelPricing(BaseModel):
    """Per-million-token pricing for a model."""

    input: float
    output: float
    cache_read: float
    cache_write: float


STATIC_FALLBACK_PRICING: dict[str, ModelPricing] = {
    # Current generation (Claude 4.5)
    "claude-opus-4-5-20251101": ModelPricing(input=5.0, output=25.0, cache_read=0.5, cache_write=6.25),
    "claude-sonnet-4-5-20251101": ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75),
    "claude-haiku-4-5-20251101": ModelPricing(input=1.0, output=5.0, cache_read=0.1, cache_write=1.25),
    # Previous generation (Claude 4)
    "claude-opus-4-20250514": ModelPricing(input=15.0, output=75.0, cache_read=1.5, cache_write=18.75),
    "claude-sonnet-4-20250514": ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75),
    # Legacy models
    "claude-3-5-sonnet-20241022": ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75),
    "claude-3-5-haiku-20241022": ModelPricing(input=0.8, output=4.0, cache_read=0.08, cache_write=1.0),
    "claude-3-opus-20240229": ModelPricing(input=15.0, output=75.0, cache_read=1.5, cache_write=18.75),
    "claude-3-haiku-20240307": ModelPricing(input=0.25, output=1.25, cache_read=0.03, cache_write=0.30),
    # Short aliases (map to current-gen Anthropic pricing)
    "sonnet": ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75),
    "opus": ModelPricing(input=5.0, output=25.0, cache_read=0.5, cache_write=6.25),
    "haiku": ModelPricing(input=1.0, output=5.0, cache_read=0.1, cache_write=1.25),
}
```

Also update the file's top imports to include `asyncio`, `os`, `time`, `httpx`, and `logger`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/models/test_tokens.py::TestModelPricing tests/unit/server/models/test_tokens.py::TestStaticFallbackPricing -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add amelia/server/models/tokens.py tests/unit/server/models/test_tokens.py
git commit -m "feat(pricing): add ModelPricing model and STATIC_FALLBACK_PRICING table"
```

---

### Task 2: Implement `fetch_openrouter_pricing()`

**Files:**
- Modify: `amelia/server/models/tokens.py`
- Test: `tests/unit/server/models/test_tokens.py`

- [ ] **Step 1: Write failing tests for `fetch_openrouter_pricing`**

Add to `tests/unit/server/models/test_tokens.py`:

```python
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from amelia.server.models.tokens import fetch_openrouter_pricing, ModelPricing


class TestFetchOpenrouterPricing:
    """Tests for fetching pricing from OpenRouter API."""

    async def test_parses_openrouter_response(self) -> None:
        """Converts per-token string prices to per-million-token floats."""
        mock_response = httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "anthropic/claude-sonnet-4",
                        "pricing": {
                            "prompt": "0.000003",
                            "completion": "0.000015",
                            "cache_read": "0.0000003",
                            "cache_write": "0.00000375",
                        },
                    }
                ]
            },
        )

        with patch("amelia.server.models.tokens.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
                result = await fetch_openrouter_pricing()

        assert "anthropic/claude-sonnet-4" in result
        pricing = result["anthropic/claude-sonnet-4"]
        assert isinstance(pricing, ModelPricing)
        assert pricing.input == pytest.approx(3.0)
        assert pricing.output == pytest.approx(15.0)
        assert pricing.cache_read == pytest.approx(0.3)
        assert pricing.cache_write == pytest.approx(3.75)

    async def test_missing_cache_fields_default_to_zero(self) -> None:
        """Models without cache pricing get 0.0 for cache fields."""
        mock_response = httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "some/model",
                        "pricing": {
                            "prompt": "0.000001",
                            "completion": "0.000002",
                        },
                    }
                ]
            },
        )

        with patch("amelia.server.models.tokens.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
                result = await fetch_openrouter_pricing()

        pricing = result["some/model"]
        assert pricing.cache_read == 0.0
        assert pricing.cache_write == 0.0

    async def test_no_api_key_returns_empty_dict(self) -> None:
        """When OPENROUTER_API_KEY is not set, returns empty dict without error."""
        env = os.environ.copy()
        env.pop("OPENROUTER_API_KEY", None)
        with patch.dict("os.environ", env, clear=True):
            result = await fetch_openrouter_pricing()

        assert result == {}

    async def test_network_error_returns_empty_dict(self) -> None:
        """Network failures return empty dict and log a warning."""
        with patch("amelia.server.models.tokens.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
                result = await fetch_openrouter_pricing()

        assert result == {}
```

Also add `import os` at the top of the test file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/models/test_tokens.py::TestFetchOpenrouterPricing -v`
Expected: FAIL — `fetch_openrouter_pricing` doesn't exist yet

- [ ] **Step 3: Implement `fetch_openrouter_pricing()`**

Add to `amelia/server/models/tokens.py` after `STATIC_FALLBACK_PRICING`:

```python
async def fetch_openrouter_pricing() -> dict[str, ModelPricing]:
    """Fetch model pricing from OpenRouter API.

    Returns:
        Mapping of model ID to pricing, or empty dict on failure/missing key.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
        result: dict[str, ModelPricing] = {}
        for model in data.get("data", []):
            model_id = model.get("id")
            pricing = model.get("pricing")
            if not model_id or not pricing:
                continue

            prompt_price = pricing.get("prompt")
            completion_price = pricing.get("completion")
            if prompt_price is None or completion_price is None:
                continue

            cache_read_price = pricing.get("cache_read")
            cache_write_price = pricing.get("cache_write")

            result[model_id] = ModelPricing(
                input=float(prompt_price) * 1_000_000,
                output=float(completion_price) * 1_000_000,
                cache_read=float(cache_read_price) * 1_000_000 if cache_read_price else 0.0,
                cache_write=float(cache_write_price) * 1_000_000 if cache_write_price else 0.0,
            )

        return result
    except Exception:
        logger.warning("Failed to fetch OpenRouter pricing")
        return {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/models/test_tokens.py::TestFetchOpenrouterPricing -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add amelia/server/models/tokens.py tests/unit/server/models/test_tokens.py
git commit -m "feat(pricing): implement fetch_openrouter_pricing with httpx"
```

---

### Task 3: Implement `get_pricing()` cache layer

**Files:**
- Modify: `amelia/server/models/tokens.py`
- Test: `tests/unit/server/models/test_tokens.py`

- [ ] **Step 1: Write failing tests for `get_pricing`**

Add to `tests/unit/server/models/test_tokens.py`:

```python
import asyncio

import amelia.server.models.tokens as tokens_module
from amelia.server.models.tokens import get_pricing


def _reset_cache() -> None:
    """Reset module-level cache state for test isolation."""
    tokens_module._cached_pricing = {}
    tokens_module._cache_expires_at = 0.0
    tokens_module._cache_lock = None


class TestGetPricing:
    """Tests for the caching pricing lookup."""

    def setup_method(self) -> None:
        _reset_cache()

    def teardown_method(self) -> None:
        _reset_cache()

    async def test_returns_cached_pricing(self) -> None:
        """Fetched pricing is returned for known OpenRouter models."""
        fake_pricing = {"anthropic/claude-sonnet-4": ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75)}

        with patch.object(tokens_module, "fetch_openrouter_pricing", new_callable=AsyncMock, return_value=fake_pricing):
            result = await get_pricing("anthropic/claude-sonnet-4")

        assert result is not None
        assert result.input == 3.0

    async def test_falls_back_to_static(self) -> None:
        """Models not in OpenRouter cache fall back to static table."""
        with patch.object(tokens_module, "fetch_openrouter_pricing", new_callable=AsyncMock, return_value={}):
            result = await get_pricing("claude-sonnet-4-5-20251101")

        assert result is not None
        assert result.input == 3.0

    async def test_unknown_model_returns_none(self) -> None:
        """Truly unknown model returns None."""
        with patch.object(tokens_module, "fetch_openrouter_pricing", new_callable=AsyncMock, return_value={}):
            result = await get_pricing("totally-unknown-model")

        assert result is None

    async def test_cache_ttl_prevents_refetch(self) -> None:
        """Within TTL window, cached data is reused without re-fetching."""
        fake_pricing = {"test/model": ModelPricing(input=1.0, output=2.0, cache_read=0.0, cache_write=0.0)}
        mock_fetch = AsyncMock(return_value=fake_pricing)
        fake_time = 1000.0

        with patch.object(tokens_module, "fetch_openrouter_pricing", mock_fetch):
            with patch.object(tokens_module.time, "time", return_value=fake_time):
                # First call — cache expired (expires_at is 0.0), triggers fetch
                await get_pricing("test/model")

            # Second call — cache valid (expires_at set to fake_time + 86400)
            with patch.object(tokens_module.time, "time", return_value=fake_time + 100):
                await get_pricing("test/model")

        assert mock_fetch.call_count == 1

    async def test_ttl_set_even_on_fetch_failure(self) -> None:
        """Failed fetch still sets TTL to avoid hammering the API."""
        mock_fetch = AsyncMock(return_value={})
        fake_time = 1000.0

        with patch.object(tokens_module, "fetch_openrouter_pricing", mock_fetch):
            with patch.object(tokens_module.time, "time", return_value=fake_time):
                await get_pricing("some-model")

            # Second call — TTL was set even though fetch returned empty
            with patch.object(tokens_module.time, "time", return_value=fake_time + 100):
                await get_pricing("some-model")

        assert mock_fetch.call_count == 1

    async def test_concurrent_access_single_fetch(self) -> None:
        """Concurrent calls with expired cache trigger only one fetch."""
        fake_pricing = {"test/model": ModelPricing(input=1.0, output=2.0, cache_read=0.0, cache_write=0.0)}
        fetch_count = 0

        async def slow_fetch() -> dict[str, ModelPricing]:
            nonlocal fetch_count
            fetch_count += 1
            await asyncio.sleep(0.05)
            return fake_pricing

        with patch.object(tokens_module, "fetch_openrouter_pricing", side_effect=slow_fetch):
            results = await asyncio.gather(
                get_pricing("test/model"),
                get_pricing("test/model"),
                get_pricing("test/model"),
            )

        assert fetch_count == 1
        # All calls should return valid pricing (from cache or static)
        for r in results:
            assert r is not None

    async def test_short_aliases_resolve(self) -> None:
        """Short aliases like 'sonnet' resolve from static fallback."""
        with patch.object(tokens_module, "fetch_openrouter_pricing", new_callable=AsyncMock, return_value={}):
            result = await get_pricing("sonnet")

        assert result is not None
        assert result.input == 3.0
        assert result.output == 15.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/models/test_tokens.py::TestGetPricing -v`
Expected: FAIL — `get_pricing` doesn't exist yet

- [ ] **Step 3: Implement cache state and `get_pricing()`**

Add module-level state and `get_pricing()` to `amelia/server/models/tokens.py` after `fetch_openrouter_pricing`:

```python
# Module-level cache state
_cached_pricing: dict[str, ModelPricing] = {}
_cache_expires_at: float = 0.0
_cache_lock: asyncio.Lock | None = None  # Lazy init to avoid event loop issues at import time


async def get_pricing(model: str) -> ModelPricing | None:
    """Look up pricing for a model, fetching from OpenRouter if cache is stale.

    Args:
        model: Model ID (e.g. "anthropic/claude-sonnet-4" or "claude-sonnet-4-5-20251101").

    Returns:
        Pricing data or None if model not found in any source.
    """
    global _cached_pricing, _cache_expires_at, _cache_lock

    if time.time() >= _cache_expires_at:
        if _cache_lock is None:
            _cache_lock = asyncio.Lock()
        async with _cache_lock:
            # Double-check after acquiring lock
            if time.time() >= _cache_expires_at:
                _cached_pricing = await fetch_openrouter_pricing()
                _cache_expires_at = time.time() + 86400  # 24 hours

    result = _cached_pricing.get(model)
    if result is not None:
        return result
    return STATIC_FALLBACK_PRICING.get(model)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/models/test_tokens.py::TestGetPricing -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add amelia/server/models/tokens.py tests/unit/server/models/test_tokens.py
git commit -m "feat(pricing): implement get_pricing with 24h cache and static fallback"
```

---

### Task 4: Make `calculate_token_cost` async with new signature

**Files:**
- Modify: `amelia/server/models/tokens.py:269-297`
- Modify: `tests/unit/server/models/test_tokens.py`

- [ ] **Step 1: Update existing tests for new async signature**

Replace the `TestCostCalculation` class in `tests/unit/server/models/test_tokens.py`:

```python
class TestCostCalculation:
    """Tests for async cost calculation function."""

    async def test_basic_cost(self) -> None:
        """Cost calculation for basic input/output tokens."""
        fake_pricing = ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75)
        with patch.object(tokens_module, "get_pricing", new_callable=AsyncMock, return_value=fake_pricing):
            cost = await calculate_token_cost(
                model="claude-sonnet-4-5-20251101",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            )
        # Input: 1M * $3/M = $3, Output: 1M * $15/M = $15
        assert cost == 18.0

    async def test_cost_with_cache_reads(self) -> None:
        """Cache reads are charged at discounted rate."""
        fake_pricing = ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75)
        with patch.object(tokens_module, "get_pricing", new_callable=AsyncMock, return_value=fake_pricing):
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
        fake_pricing = ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75)
        with patch.object(tokens_module, "get_pricing", new_callable=AsyncMock, return_value=fake_pricing):
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
        fake_pricing = ModelPricing(input=15.0, output=75.0, cache_read=1.5, cache_write=18.75)
        with patch.object(tokens_module, "get_pricing", new_callable=AsyncMock, return_value=fake_pricing):
            cost = await calculate_token_cost(
                model="claude-opus-4-20250514",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            )
        # Input: 1M * $15/M = $15, Output: 1M * $75/M = $75
        assert cost == 90.0

    async def test_unknown_model_returns_zero(self) -> None:
        """Unknown models return $0 cost (not Sonnet fallback)."""
        with patch.object(tokens_module, "get_pricing", new_callable=AsyncMock, return_value=None):
            cost = await calculate_token_cost(
                model="unknown-model-2025",
                input_tokens=1_000_000,
                output_tokens=0,
            )
        assert cost == 0.0

    async def test_cost_precision(self) -> None:
        """Cost is rounded to 6 decimal places."""
        fake_pricing = ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75)
        with patch.object(tokens_module, "get_pricing", new_callable=AsyncMock, return_value=fake_pricing):
            cost = await calculate_token_cost(
                model="claude-sonnet-4-5-20251101",
                input_tokens=1,
                output_tokens=1,
            )
        assert cost == round(cost, 6)
```

Also remove the `make_usage` helper (no longer needed — tests mock `get_pricing` directly instead of constructing `TokenUsage`). `TestTokenUsage` can remain as-is. Note: the old `test_unknown_model_uses_sonnet_pricing` is intentionally replaced by `test_unknown_model_returns_zero` — per spec, unknown models now return `$0.0` instead of silently billing at Sonnet rates.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/models/test_tokens.py::TestCostCalculation -v`
Expected: FAIL — `calculate_token_cost` still has old sync signature

- [ ] **Step 3: Rewrite `calculate_token_cost` with new async signature**

Replace `calculate_token_cost` in `amelia/server/models/tokens.py`:

```python
async def calculate_token_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """Calculate USD cost for token usage with cache adjustments.

    Args:
        model: Model ID for pricing lookup.
        input_tokens: Total input tokens (includes cache reads).
        output_tokens: Output tokens generated.
        cache_read_tokens: Input tokens served from cache.
        cache_creation_tokens: Tokens written to cache.

    Returns:
        Total cost in USD, rounded to 6 decimal places. Returns 0.0 if
        no pricing data found for the model.
    """
    rates = await get_pricing(model)
    if rates is None:
        return 0.0

    base_input_tokens = input_tokens - cache_read_tokens

    cost = (
        (base_input_tokens * rates.input / 1_000_000)
        + (cache_read_tokens * rates.cache_read / 1_000_000)
        + (cache_creation_tokens * rates.cache_write / 1_000_000)
        + (output_tokens * rates.output / 1_000_000)
    )

    return round(cost, 6)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/models/test_tokens.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run type checker**

Run: `uv run mypy amelia/server/models/tokens.py`
Expected: PASS (no type errors)

- [ ] **Step 6: Commit**

```bash
git add amelia/server/models/tokens.py tests/unit/server/models/test_tokens.py
git commit -m "feat(pricing): make calculate_token_cost async with raw-value params"
```

---

## Chunk 2: Callsite integration

### Task 5: Add cost fallback to `_save_token_usage()` in nodes.py

**Files:**
- Modify: `amelia/pipelines/nodes.py:128-182` (`_save_token_usage` function)
- Create: `tests/unit/pipelines/test_nodes_cost_fallback.py`

- [ ] **Step 1: Write failing tests for cost fallback in `_save_token_usage`**

Create `tests/unit/pipelines/test_nodes_cost_fallback.py`:

```python
"""Tests for cost fallback in _save_token_usage."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from amelia.pipelines.nodes import _save_token_usage


class TestSaveTokenUsageCostFallback:
    """Tests for cost calculation fallback when driver doesn't provide cost."""

    async def test_uses_driver_cost_when_provided(self) -> None:
        """When driver provides cost_usd, use it directly."""
        driver = MagicMock()
        driver.get_usage.return_value = MagicMock(
            model="anthropic/claude-sonnet-4",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            cost_usd=0.05,
            duration_ms=1000,
            num_turns=1,
        )
        driver.model = "anthropic/claude-sonnet-4"

        repo = AsyncMock()
        workflow_id = uuid4()

        with patch("amelia.pipelines.nodes.calculate_token_cost", new_callable=AsyncMock) as mock_calc:
            await _save_token_usage(driver, workflow_id, "developer", repo)

        # calculate_token_cost should NOT be called when driver provides cost
        mock_calc.assert_not_called()
        # Verify the saved usage has the driver-provided cost
        saved_usage = repo.save_token_usage.call_args[0][0]
        assert saved_usage.cost_usd == 0.05

    async def test_calculates_cost_when_driver_cost_is_zero(self) -> None:
        """When driver cost is 0, calculate from cached pricing."""
        driver = MagicMock()
        driver.get_usage.return_value = MagicMock(
            model="anthropic/claude-sonnet-4",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            cost_usd=0.0,
            duration_ms=1000,
            num_turns=1,
        )
        driver.model = "anthropic/claude-sonnet-4"

        repo = AsyncMock()
        workflow_id = uuid4()

        with patch("amelia.pipelines.nodes.calculate_token_cost", new_callable=AsyncMock, return_value=0.025) as mock_calc:
            await _save_token_usage(driver, workflow_id, "developer", repo)

        mock_calc.assert_called_once_with(
            model="anthropic/claude-sonnet-4",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )
        saved_usage = repo.save_token_usage.call_args[0][0]
        assert saved_usage.cost_usd == 0.025

    async def test_calculates_cost_when_driver_cost_is_none(self) -> None:
        """When driver cost is None, calculate from cached pricing."""
        driver = MagicMock()
        driver.get_usage.return_value = MagicMock(
            model="anthropic/claude-sonnet-4",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            cost_usd=None,
            duration_ms=1000,
            num_turns=1,
        )
        driver.model = "anthropic/claude-sonnet-4"

        repo = AsyncMock()
        workflow_id = uuid4()

        with patch("amelia.pipelines.nodes.calculate_token_cost", new_callable=AsyncMock, return_value=0.025):
            await _save_token_usage(driver, workflow_id, "developer", repo)

        saved_usage = repo.save_token_usage.call_args[0][0]
        assert saved_usage.cost_usd == 0.025
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/pipelines/test_nodes_cost_fallback.py -v`
Expected: FAIL — `calculate_token_cost` not imported in `nodes.py`, fallback logic not implemented

- [ ] **Step 3: Implement cost fallback in `_save_token_usage()`**

In `amelia/pipelines/nodes.py`:

1. Add import at top (with the other imports from `amelia.server.models`):

```python
from amelia.server.models.tokens import TokenUsage, calculate_token_cost
```

2. Replace the `try` block in `_save_token_usage` (the part that constructs and saves `TokenUsage`) with:

```python
    try:
        cost = driver_usage.cost_usd or 0.0

        # Compute cost from cached pricing if driver didn't provide it
        if not cost:
            model = driver_usage.model or getattr(driver, "model", "unknown")
            cost = await calculate_token_cost(
                model=model,
                input_tokens=driver_usage.input_tokens or 0,
                output_tokens=driver_usage.output_tokens or 0,
                cache_read_tokens=driver_usage.cache_read_tokens or 0,
                cache_creation_tokens=driver_usage.cache_creation_tokens or 0,
            )

        usage = TokenUsage(
            workflow_id=workflow_id,
            agent=agent,
            model=driver_usage.model or getattr(driver, "model", "unknown"),
            input_tokens=driver_usage.input_tokens or 0,
            output_tokens=driver_usage.output_tokens or 0,
            cache_read_tokens=driver_usage.cache_read_tokens or 0,
            cache_creation_tokens=driver_usage.cache_creation_tokens or 0,
            cost_usd=cost,
            duration_ms=driver_usage.duration_ms or 0,
            num_turns=driver_usage.num_turns or 1,
            timestamp=datetime.now(UTC),
        )
        await repository.save_token_usage(usage)
```

The rest of the try/except block (logger.debug and logger.exception) remains unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/pipelines/test_nodes_cost_fallback.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add amelia/pipelines/nodes.py tests/unit/pipelines/test_nodes_cost_fallback.py
git commit -m "feat(pricing): add cost fallback to _save_token_usage"
```

---

### Task 6: Add cost fallback to brainstorm service

**Files:**
- Modify: `amelia/server/services/brainstorm.py:693-701`
- Create: `tests/unit/server/services/test_brainstorm_cost_fallback.py`

- [ ] **Step 1: Write failing tests for brainstorm cost fallback**

Create `tests/unit/server/services/test_brainstorm_cost_fallback.py`. These tests extract the cost-fallback logic into a small helper that mirrors the brainstorm service's pattern, then verify that helper. This tests the logic that will be added to the brainstorm service:

```python
"""Tests for cost fallback logic used in brainstorm message creation.

Tests the cost-fallback pattern: use driver cost when available,
fall back to calculate_token_cost when not.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from amelia.server.models.brainstorm import MessageUsage
from amelia.server.models.tokens import calculate_token_cost


async def _compute_brainstorm_cost(driver_usage: MagicMock) -> MessageUsage:
    """Replicate the brainstorm service cost-fallback logic for testing."""
    cost = driver_usage.cost_usd or 0.0

    if not cost and driver_usage.model:
        cost = await calculate_token_cost(
            model=driver_usage.model,
            input_tokens=driver_usage.input_tokens or 0,
            output_tokens=driver_usage.output_tokens or 0,
            cache_read_tokens=driver_usage.cache_read_tokens or 0,
            cache_creation_tokens=driver_usage.cache_creation_tokens or 0,
        )

    return MessageUsage(
        input_tokens=driver_usage.input_tokens or 0,
        output_tokens=driver_usage.output_tokens or 0,
        cost_usd=cost,
    )


class TestBrainstormCostFallback:
    """Tests for cost calculation in brainstorm driver usage extraction."""

    async def test_uses_driver_cost_when_provided(self) -> None:
        """When driver provides cost_usd, use it for MessageUsage."""
        driver_usage = MagicMock(
            model="anthropic/claude-sonnet-4",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            cost_usd=0.05,
        )

        with patch("tests.unit.server.services.test_brainstorm_cost_fallback.calculate_token_cost", new_callable=AsyncMock) as mock_calc:
            result = await _compute_brainstorm_cost(driver_usage)

        mock_calc.assert_not_called()
        assert result.cost_usd == 0.05

    async def test_calculates_cost_when_driver_cost_is_zero(self) -> None:
        """When driver cost is 0, calculate from cached pricing."""
        driver_usage = MagicMock(
            model="anthropic/claude-sonnet-4",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=100,
            cache_creation_tokens=0,
            cost_usd=0.0,
        )

        with patch("tests.unit.server.services.test_brainstorm_cost_fallback.calculate_token_cost", new_callable=AsyncMock, return_value=0.025) as mock_calc:
            result = await _compute_brainstorm_cost(driver_usage)

        mock_calc.assert_called_once()
        assert result.cost_usd == 0.025

    async def test_skips_calculation_when_no_model(self) -> None:
        """When driver_usage has no model, skip calculation and use 0."""
        driver_usage = MagicMock(
            model=None,
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            cost_usd=0.0,
        )

        with patch("tests.unit.server.services.test_brainstorm_cost_fallback.calculate_token_cost", new_callable=AsyncMock) as mock_calc:
            result = await _compute_brainstorm_cost(driver_usage)

        mock_calc.assert_not_called()
        assert result.cost_usd == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_cost_fallback.py -v`
Expected: FAIL — `calculate_token_cost` still has old sync signature (until Task 4 is done). If running after Task 4, these should pass since they mock `calculate_token_cost`.

- [ ] **Step 3: Modify brainstorm service to add cost fallback**

In `amelia/server/services/brainstorm.py`:

1. Add import at the top with other imports:

```python
from amelia.server.models.tokens import calculate_token_cost
```

2. Replace lines 694-701 (the driver usage extraction block):

```python
            message_usage: MessageUsage | None = None
            driver_usage = driver.get_usage()
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
```

- [ ] **Step 4: Run tests to verify everything passes**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_cost_fallback.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add amelia/server/services/brainstorm.py tests/unit/server/services/test_brainstorm_cost_fallback.py
git commit -m "feat(pricing): add cost fallback to brainstorm service"
```

---

## Chunk 3: Verification

### Task 7: Full verification pass

**Files:** All modified files

- [ ] **Step 1: Check for any other callers of old `calculate_token_cost` signature**

Search for any imports or calls to `calculate_token_cost` that might still use the old `TokenUsage` arg:

Run: `uv run ruff check amelia tests && uv run mypy amelia`

Fix any type errors from callers still using the old sync signature.

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: ALL PASS with 0 failures

- [ ] **Step 3: Run linter**

Run: `uv run ruff check --fix amelia tests`
Expected: PASS (no remaining lint issues)

- [ ] **Step 4: Run type checker**

Run: `uv run mypy amelia`
Expected: PASS (no type errors)

- [ ] **Step 5: Final commit if any fixes were needed**

```bash
git add -u
git commit -m "fix(pricing): address lint and type errors from pricing refactor"
```
