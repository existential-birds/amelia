# OpenRouter Live Pricing Integration

**Issue:** #518 — Replace static MODEL_PRICING with OpenRouter pricing API
**Date:** 2026-03-11

## Problem

All API driver models show $0 cost in the dashboard. The `calculate_token_cost()` function in `amelia/server/models/tokens.py` uses a hardcoded `MODEL_PRICING` dict but is never called from any callsite. Cost is only populated when the provider includes it in response metadata (OpenRouter via `token_usage.cost`). The static pricing table is also a maintenance burden — prices go stale as providers update them.

## Solution

Replace the static `MODEL_PRICING` table with live pricing fetched from the OpenRouter API (`GET /api/v1/models`). Use an in-memory cache with a 24-hour TTL. Fall back to a small static table of Anthropic-only models when the fetch fails or the API key isn't configured.

## Design

### 1. Pricing fetch and cache (`amelia/server/models/tokens.py`)

**New `ModelPricing` Pydantic model** (the current codebase uses `dict[str, dict[str, float]]` with no named type):

```python
class ModelPricing(BaseModel):
    input: float          # per million tokens
    output: float         # per million tokens
    cache_read: float     # per million tokens
    cache_write: float    # per million tokens
```

**New module-level state:**

- `_cached_pricing: dict[str, ModelPricing]` — maps model ID to pricing data
- `_cache_expires_at: float` — Unix timestamp; cache is valid until this time (initialized to `0.0`)
- `_cache_lock: asyncio.Lock` — serializes cache refresh to prevent concurrent fetches

**`STATIC_FALLBACK_PRICING: dict[str, ModelPricing]`** replaces the current 30-model `MODEL_PRICING` dict. Contains only Anthropic models used via direct API, plus short aliases:

- `claude-opus-4-5-20251101`, `claude-sonnet-4-5-20251101`, `claude-haiku-4-5-20251101` (current generation)
- `claude-opus-4-20250514`, `claude-sonnet-4-20250514` (previous generation)
- Legacy models: `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`, `claude-3-opus-20240229`, `claude-3-haiku-20240307`
- Short aliases: `"sonnet"`, `"opus"`, `"haiku"` (mapped to current-gen Anthropic pricing)

These are the only models that go through a non-OpenRouter path. Short aliases are internal to this project and won't appear in OpenRouter's API response, so they must be in the static table.

**`async def fetch_openrouter_pricing() -> dict[str, ModelPricing]`:**

- If `OPENROUTER_API_KEY` is not set in the environment, returns empty dict immediately (no error — the key is optional for users who only use direct Anthropic API)
- Calls `GET https://openrouter.ai/api/v1/models` using `httpx.AsyncClient` with a 10-second timeout
- Response shape: `{"data": [{"id": "anthropic/claude-sonnet-4", "pricing": {"prompt": "0.000003", "completion": "0.000015", "cache_read": "0.0000003", "cache_write": "0.00000375"}}, ...]}`
- Parses each model's `pricing` object with explicit field mapping:
  - `pricing.prompt` → `ModelPricing.input`
  - `pricing.completion` → `ModelPricing.output`
  - `pricing.cache_read` → `ModelPricing.cache_read` (may be absent)
  - `pricing.cache_write` → `ModelPricing.cache_write` (may be absent — not all providers report this)
- Converts per-token string prices to per-million-token floats: `float(price_str) * 1_000_000`
- Handles missing/null pricing fields: `cache_read` and `cache_write` default to `0.0` when absent (many models don't support caching)
- Creates a new `httpx.AsyncClient` per fetch (not worth maintaining a persistent client for one call every 24 hours)
- Returns the full dict; on any error (network, parse, missing key), logs a warning via loguru and returns an empty dict

**`async def get_pricing(model: str) -> ModelPricing | None`:**

- Acquires `_cache_lock`, then re-checks TTL inside the lock (double-checked locking — if another coroutine already refreshed, skip the fetch)
- If cache is expired/empty, calls `fetch_openrouter_pricing()`, updates `_cached_pricing` and sets `_cache_expires_at` to `time.time() + 86400` (24 hours)
- Even if the fetch returns an empty dict (failure), the TTL is still set — avoids hammering the API on repeated failures. The static fallback provides coverage.
- Look up `model` in cached pricing first, then in `STATIC_FALLBACK_PRICING`
- Return `None` if model is not found in either source

**Model ID format note:** OpenRouter returns provider-prefixed IDs (e.g., `anthropic/claude-sonnet-4-5-20251101`) while direct Anthropic drivers use bare names (e.g., `claude-sonnet-4-5-20251101`). The API driver already reports the full OpenRouter model ID, so those match the cache. Direct Anthropic models are covered by `STATIC_FALLBACK_PRICING` — they won't match OpenRouter's cache keys, but that's fine since they have static pricing.

**`async def calculate_token_cost(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_creation_tokens: int = 0) -> float`:**

- New signature accepts raw values instead of a `TokenUsage` object — avoids coupling cost calculation to the persistence model, and avoids needing to construct throwaway `TokenUsage` objects at the brainstorm callsite
- Async because it calls `await get_pricing(model)`
- Same cost formula: `(base_input * input_rate) + (cache_read * cache_read_rate) + (cache_write * cache_write_rate) + (output * output_rate)` where `base_input = input_tokens - cache_read_tokens`
- Returns `0.0` if no pricing data is found for the model

**Behavioral change:** The current implementation falls back to Sonnet pricing for unknown models. The new implementation returns `0.0` for truly unknown models (not in OpenRouter's catalog and not in the static Anthropic table). This is intentional — showing $0 is more honest than silently billing at Sonnet rates for an unrelated model. The existing test `test_unknown_model_uses_sonnet_pricing` will be replaced with a test verifying the `0.0` return.

### 2. Callsite integration

**`amelia/pipelines/nodes.py` — `_save_token_usage()` function (~line 129):**

Inside `_save_token_usage()`, after constructing the `TokenUsage` object (line 155-167) and before saving it (line 168), add a cost fallback:

```python
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

**`amelia/server/services/brainstorm.py` (~line 693):**

The brainstorm path constructs a `MessageUsage` which only has `input_tokens`, `output_tokens`, and `cost_usd` — it lacks `model` and cache token fields. Since `calculate_token_cost` now accepts raw values (not a `TokenUsage` object), we compute cost from `driver_usage` before constructing `MessageUsage`:

```python
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

### 3. Cleanup

- Remove `MODEL_PRICING` dict (the large 30-model static table)
- Add `STATIC_FALLBACK_PRICING` with Anthropic models and short aliases (~12 entries)
- Add `ModelPricing` Pydantic model (new type, replaces `dict[str, float]` pattern)
- Add `_cached_pricing`, `_cache_expires_at`, `_cache_lock` module-level state

### 4. Testing

**Unit tests (`tests/unit/server/models/test_tokens.py`):**

- Test `fetch_openrouter_pricing()`: mock `httpx.AsyncClient.get` response with sample OpenRouter JSON, verify per-token string prices are converted to per-million-token floats correctly
- Test null/missing pricing fields: verify `cache_read` and `cache_write` default to `0.0` when absent from OpenRouter response
- Test cache TTL: verify cached data is returned within 24h window, refetch triggered after expiry (mock `time.time()`)
- Test concurrent access: verify `_cache_lock` prevents multiple simultaneous fetches
- Test fallback: when fetch fails (network error), verify static Anthropic pricing is used
- Test missing API key: when `OPENROUTER_API_KEY` is not set, verify fetch returns empty dict and static fallback is used
- Test `calculate_token_cost()`: update existing tests for async signature, verify cost calculation uses cached pricing data
- Test model not found: verify `0.0` is returned when model isn't in cache or fallback (replaces `test_unknown_model_uses_sonnet_pricing`)
- Test short aliases: verify `"sonnet"`, `"opus"`, `"haiku"` resolve to correct pricing from static fallback

**Callsite integration tests:**

- `tests/unit/pipelines/test_nodes_cost_fallback.py`: Test `_save_token_usage()` calls `calculate_token_cost` when `driver_usage.cost_usd` is `None`/`0`, and passes through driver-provided cost when present. Mock the driver and repository.
- `tests/unit/server/services/test_brainstorm_cost_fallback.py`: Test brainstorm message creation calls `calculate_token_cost` when driver doesn't provide cost, and skips calculation when cost is provided.

**No changes needed:**

- Dashboard — already displays whatever `cost_usd` the backend provides
- Database schema — no new tables or columns
- API routes — no changes to response shape

## Affected files

| File | Change |
|------|--------|
| `amelia/server/models/tokens.py` | Add `ModelPricing` model, replace `MODEL_PRICING` with fetch/cache + static fallback, make `calculate_token_cost` async |
| `amelia/pipelines/nodes.py` | Add cost calculation fallback in `_save_token_usage()` before saving |
| `amelia/server/services/brainstorm.py` | Add cost calculation fallback before constructing `MessageUsage` |
| `tests/unit/server/models/test_tokens.py` | Update for async, add fetch/cache/fallback/concurrency tests |
| `tests/unit/pipelines/test_nodes_cost_fallback.py` | New: test cost fallback in `_save_token_usage()` |
| `tests/unit/server/services/test_brainstorm_cost_fallback.py` | New: test cost fallback in brainstorm message creation |

## Decisions

- **In-memory cache, not DB-persisted** — a single lazy fetch on first use is fast; avoids schema migration
- **Lazy fetch, not startup** — pricing is fetched on first `get_pricing()` call, not on server startup. This avoids adding initialization hooks and means the server starts without requiring OpenRouter connectivity.
- **24-hour TTL** — pricing changes infrequently (monthly at most). TTL is set even on fetch failure to avoid hammering the API.
- **`asyncio.Lock` for cache refresh** — prevents concurrent requests from triggering parallel fetches to OpenRouter
- **Static fallback for Anthropic + aliases** — covers direct-API models and project-internal short aliases (`"sonnet"`, `"opus"`, `"haiku"`) that OpenRouter won't return
- **`OPENROUTER_API_KEY` is optional** — if not set, fetch is skipped silently. Users who only use direct Anthropic API still get pricing from the static fallback.
- **$0 for truly unknown models** — intentional change from current Sonnet-fallback behavior. Showing $0 is more accurate than silently applying Sonnet rates to unrelated models.
- **New `httpx.AsyncClient` per fetch** — one call every 24 hours doesn't justify a persistent client with lifecycle management
- **httpx for HTTP** — already a project dependency via FastAPI/Starlette
