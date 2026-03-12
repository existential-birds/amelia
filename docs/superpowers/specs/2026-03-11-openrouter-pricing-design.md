# OpenRouter Live Pricing Integration

**Issue:** #518 — Replace static MODEL_PRICING with OpenRouter pricing API
**Date:** 2026-03-11

## Problem

All API driver models show $0 cost in the dashboard. The `calculate_token_cost()` function in `amelia/server/models/tokens.py` uses a hardcoded `MODEL_PRICING` dict but is never called. Cost is only populated when the provider includes it in response metadata (OpenRouter via `token_usage.cost`). The static pricing table is also a maintenance burden — prices go stale as providers update them.

## Solution

Replace the static `MODEL_PRICING` table with live pricing fetched from the OpenRouter API (`GET /api/v1/models`). Use an in-memory cache with a 24-hour TTL. Fall back to a small static table of Anthropic-only models when the fetch fails or the API key isn't configured.

## Design

### 1. Pricing fetch and cache (`amelia/server/models/tokens.py`)

**New module-level state:**

- `_cached_pricing: dict[str, ModelPricing]` — maps model ID to pricing data
- `_cache_expires_at: float` — Unix timestamp; cache is valid until this time

**`STATIC_FALLBACK_PRICING`** replaces the current 30-model `MODEL_PRICING` dict. Contains only Anthropic models used via direct API (claude-opus-4-5, claude-sonnet-4-5, claude-haiku-4-5, and their versioned/aliased variants). These are the only models that go through a non-OpenRouter path.

**`async def fetch_openrouter_pricing() -> dict[str, ModelPricing]`:**

- Calls `GET https://openrouter.ai/api/v1/models` using `httpx.AsyncClient`
- Reads `OPENROUTER_API_KEY` from environment (required for the call)
- Parses each model's `pricing` object: converts per-token string prices (`"0.000003"`) to per-million-token floats (`3.0`) to match the existing `ModelPricing` format
- Maps fields: `prompt` -> `input`, `completion` -> `output`, `cache_read` -> `cache_read`, `cache_write` -> `cache_write`
- Returns the full dict; on any error (network, parse, missing key), logs a warning and returns an empty dict
- Timeout: 10 seconds

**`async def get_pricing(model: str) -> ModelPricing | None`:**

- If `time.time() < _cache_expires_at` and `_cached_pricing` is populated, use cache
- Otherwise, call `fetch_openrouter_pricing()`, update `_cached_pricing` and set `_cache_expires_at` to now + 86400 (24 hours)
- Look up `model` in cached pricing first, then in `STATIC_FALLBACK_PRICING`
- Return `None` if model is not found in either source

**`async def calculate_token_cost(usage: TokenUsage) -> float`:**

- Now async (was sync but never called)
- Calls `await get_pricing(usage.model)` instead of indexing into `MODEL_PRICING`
- Same cost formula: `(base_input * input_rate) + (cache_read * cache_read_rate) + (cache_write * cache_write_rate) + (output * output_rate)`
- Returns `0.0` if no pricing data is found

### 2. Callsite integration

**`amelia/pipelines/nodes.py` (~line 61):**

After `driver.get_usage()` returns `DriverUsage`, if `cost_usd` is `None` or `0`:

```python
if not driver_usage.cost_usd:
    driver_usage.cost_usd = await calculate_token_cost(token_usage)
```

This applies to all workflow agent executions (architect, developer, reviewer).

**`amelia/server/services/brainstorm.py` (~line 700):**

Same pattern — after extracting usage from the driver response, compute cost if the driver didn't provide it.

### 3. Cleanup

- Remove `MODEL_PRICING` dict (the large 30-model static table)
- Add `STATIC_FALLBACK_PRICING` (~6 Anthropic model entries)
- Remove any dead helper code that only served the old static table
- Keep `ModelPricing` TypedDict — still used by cache and fallback

### 4. Testing

**Unit tests (`tests/unit/server/models/test_tokens.py`):**

- Test `fetch_openrouter_pricing()`: mock `httpx` response with sample OpenRouter JSON, verify per-token strings are converted to per-million floats correctly
- Test cache TTL: verify cached data is returned within 24h window, refetch triggered after expiry
- Test fallback: when fetch fails (network error, missing API key), verify static Anthropic pricing is used
- Test `calculate_token_cost()`: update existing tests for async signature, verify cost calculation uses cached pricing data
- Test model not found: verify `0.0` is returned when model isn't in cache or fallback

**No changes needed:**

- Dashboard — already displays whatever `cost_usd` the backend provides
- Database schema — no new tables or columns
- API routes — no changes to response shape

## Affected files

| File | Change |
|------|--------|
| `amelia/server/models/tokens.py` | Replace `MODEL_PRICING` with fetch/cache, make `calculate_token_cost` async |
| `amelia/pipelines/nodes.py` | Add cost calculation fallback after driver usage extraction |
| `amelia/server/services/brainstorm.py` | Add cost calculation fallback after driver usage extraction |
| `tests/unit/server/models/test_tokens.py` | Update for async, add fetch/cache/fallback tests |

## Decisions

- **In-memory cache, not DB-persisted** — one API call on startup is fine; avoids schema migration
- **24-hour TTL** — pricing changes infrequently (monthly at most)
- **Static fallback for Anthropic only** — only models used via direct API (non-OpenRouter path)
- **Graceful degradation** — fetch failure logs a warning and uses fallback; never blocks execution
- **httpx for HTTP** — already a project dependency via FastAPI/Starlette
