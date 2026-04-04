"""Token usage tracking and cost calculation."""

import asyncio
import importlib
import os
import time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import httpx
from loguru import logger
from pydantic import BaseModel, Field

from amelia.server.models.model_cache import ModelCacheEntry


if TYPE_CHECKING:
    from amelia.server.database.model_cache_repository import ModelCacheRepository


class ModelPricing(BaseModel):
    """Pricing rates per million tokens for a model."""

    input: float
    output: float
    cache_read: float
    cache_write: float


# Static fallback pricing for Anthropic models used via direct API.
# Only contains Anthropic models + short aliases (~12 entries).
# Sources: https://www.anthropic.com/pricing (last updated: 2026-01-19)
STATIC_FALLBACK_PRICING: dict[str, ModelPricing] = {
    # Current generation (Claude 4.5)
    "claude-opus-4-5-20251101": ModelPricing(
        input=5.0, output=25.0, cache_read=0.5, cache_write=6.25
    ),
    "claude-sonnet-4-5-20251101": ModelPricing(
        input=3.0, output=15.0, cache_read=0.3, cache_write=3.75
    ),
    "claude-haiku-4-5-20251101": ModelPricing(
        input=1.0, output=5.0, cache_read=0.1, cache_write=1.25
    ),
    # Previous generation (Claude 4)
    "claude-opus-4-20250514": ModelPricing(
        input=15.0, output=75.0, cache_read=1.5, cache_write=18.75
    ),
    "claude-sonnet-4-20250514": ModelPricing(
        input=3.0, output=15.0, cache_read=0.3, cache_write=3.75
    ),
    # Legacy models
    "claude-3-5-sonnet-20241022": ModelPricing(
        input=3.0, output=15.0, cache_read=0.3, cache_write=3.75
    ),
    "claude-3-5-haiku-20241022": ModelPricing(
        input=0.8, output=4.0, cache_read=0.08, cache_write=1.0
    ),
    "claude-3-opus-20240229": ModelPricing(
        input=15.0, output=75.0, cache_read=1.5, cache_write=18.75
    ),
    "claude-3-haiku-20240307": ModelPricing(
        input=0.25, output=1.25, cache_read=0.03, cache_write=0.30
    ),
    # Short aliases (mapped to current-gen Anthropic pricing)
    "sonnet": ModelPricing(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75),
    "opus": ModelPricing(input=5.0, output=25.0, cache_read=0.5, cache_write=6.25),
    "haiku": ModelPricing(input=1.0, output=5.0, cache_read=0.1, cache_write=1.25),
}

# Module-level cache state
_cached_pricing: dict[str, ModelPricing] = {}
_cache_expires_at: float = 0.0
_cache_lock: asyncio.Lock = asyncio.Lock()


def _get_model_cache_repository() -> "ModelCacheRepository | None":
    """Return a database-backed model cache repository when the server DB is initialized."""
    try:
        dependencies_module = importlib.import_module("amelia.server.dependencies")
        repository_module = importlib.import_module("amelia.server.database.model_cache_repository")
    except ImportError:
        return None

    try:
        return cast(
            "ModelCacheRepository",
            repository_module.ModelCacheRepository(dependencies_module.get_database()),
        )
    except RuntimeError:
        return None


def _pricing_from_cache_entry(entry: ModelCacheEntry) -> ModelPricing | None:
    """Convert cached model metadata into pricing when both rates are present."""
    if entry.input_cost_per_m is None or entry.output_cost_per_m is None:
        return None

    return ModelPricing(
        input=entry.input_cost_per_m,
        output=entry.output_cost_per_m,
        cache_read=0.0,
        cache_write=0.0,
    )


async def fetch_openrouter_pricing() -> dict[str, ModelPricing]:
    """Fetch live model pricing from the OpenRouter API.

    Returns:
        Dict mapping model ID to ModelPricing. Empty dict on failure or missing API key.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            data = response.json()

        result: dict[str, ModelPricing] = {}
        for model_entry in data.get("data", []):
            try:
                if not isinstance(model_entry, dict):
                    continue
                model_id = model_entry.get("id")
                pricing = model_entry.get("pricing")
                if not model_id or not isinstance(pricing, dict):
                    continue

                prompt_str = pricing.get("prompt")
                completion_str = pricing.get("completion")
                if prompt_str is None or completion_str is None:
                    continue

                cache_read_str = pricing.get("cache_read")
                cache_write_str = pricing.get("cache_write")

                result[model_id] = ModelPricing(
                    input=float(prompt_str) * 1_000_000,
                    output=float(completion_str) * 1_000_000,
                    cache_read=float(cache_read_str) * 1_000_000 if cache_read_str is not None else 0.0,
                    cache_write=float(cache_write_str) * 1_000_000 if cache_write_str is not None else 0.0,
                )
            except (AttributeError, ValueError, KeyError, TypeError):
                logger.debug("Skipping malformed pricing entry", model_id=model_entry.get("id") if isinstance(model_entry, dict) else None)
                continue

        return result
    except Exception as e:
        logger.warning("Failed to fetch OpenRouter pricing", error=str(e))
        return {}


async def get_pricing(model: str) -> ModelPricing | None:
    """Get pricing for a model, using cached live data or static fallback.

    Uses double-checked locking to prevent concurrent fetches.

    Args:
        model: Model ID or short alias.

    Returns:
        ModelPricing if found, None otherwise.
    """
    global _cached_pricing, _cache_expires_at

    repo = _get_model_cache_repository()
    if repo is not None:
        cached_entry = await repo.get_model(model)
        if cached_entry is not None and not await repo.is_stale(model):
            cached_pricing = _pricing_from_cache_entry(cached_entry)
            if cached_pricing is not None:
                return cached_pricing

    # Fast path: cache is valid
    if time.time() < _cache_expires_at:
        if model in _cached_pricing:
            return _cached_pricing[model]
        return STATIC_FALLBACK_PRICING.get(model)

    # Slow path: need to refresh cache
    async with _cache_lock:
        # Double-check inside lock
        if time.time() < _cache_expires_at:
            if model in _cached_pricing:
                return _cached_pricing[model]
            return STATIC_FALLBACK_PRICING.get(model)

        # Fetch and update cache, keeping last good data on failure
        new_pricing = await fetch_openrouter_pricing()
        if new_pricing or not _cached_pricing:
            _cached_pricing = new_pricing
        _cache_expires_at = time.time() + 86400  # 24-hour TTL

    # Look up model in cached pricing, then static fallback
    if model in _cached_pricing:
        return _cached_pricing[model]
    return STATIC_FALLBACK_PRICING.get(model)


class TokenUsage(BaseModel):
    """Token consumption tracking per agent.

    Cache token semantics:
    - input_tokens: Total tokens processed (includes cache_read_tokens)
    - cache_read_tokens: Subset of input_tokens served from prompt cache (cheaper)
    - cache_creation_tokens: Tokens written to cache (billed at higher rate)
    - cost_usd: Calculated as input_cost + output_cost - cache_discount

    Attributes:
        id: Unique identifier.
        workflow_id: Workflow this usage belongs to.
        agent: Agent that consumed tokens.
        model: Model used for cost calculation.
        input_tokens: Total input tokens (includes cache reads).
        output_tokens: Output tokens generated.
        cache_read_tokens: Subset of input from cache (discounted).
        cache_creation_tokens: Tokens written to cache (premium rate).
        cost_usd: Net cost after cache adjustments (required).
        duration_ms: Execution time in milliseconds.
        num_turns: Number of conversation turns.
        timestamp: When tokens were consumed.
    """

    id: uuid.UUID = Field(
        default_factory=uuid4,
        description="Unique identifier",
    )
    workflow_id: uuid.UUID = Field(..., description="Workflow ID")
    agent: str = Field(..., description="Agent that consumed tokens")
    model: str = Field(
        default="claude-sonnet-4-5-20251101",
        description="Model used",
    )
    input_tokens: int = Field(..., ge=0, description="Total input tokens")
    output_tokens: int = Field(..., ge=0, description="Output tokens")
    cache_read_tokens: int = Field(
        default=0,
        ge=0,
        description="Input tokens from cache",
    )
    cache_creation_tokens: int = Field(
        default=0,
        ge=0,
        description="Tokens written to cache",
    )
    cost_usd: float = Field(..., description="Calculated cost in USD")
    duration_ms: int = Field(default=0, ge=0, description="Execution time in milliseconds")
    num_turns: int = Field(default=1, ge=1, description="Number of conversation turns")
    timestamp: datetime = Field(..., description="When consumed")


class TokenSummary(BaseModel):
    """Aggregated token usage summary for a workflow.

    Provides totals across all agents for high-level display,
    plus the breakdown for detailed views.

    Attributes:
        total_input_tokens: Sum of input tokens across all agents.
        total_output_tokens: Sum of output tokens across all agents.
        total_cache_read_tokens: Sum of cache read tokens across all agents.
        total_cost_usd: Sum of costs across all agents.
        total_duration_ms: Sum of durations across all agents.
        total_turns: Sum of turns across all agents.
        breakdown: Per-agent TokenUsage records for detail display.
    """

    total_input_tokens: int = Field(default=0, ge=0)
    total_output_tokens: int = Field(default=0, ge=0)
    total_cache_read_tokens: int = Field(default=0, ge=0)
    total_cost_usd: float = Field(default=0.0)
    total_duration_ms: int = Field(default=0, ge=0)
    total_turns: int = Field(default=0, ge=0)
    breakdown: list[TokenUsage] = Field(default_factory=list)


async def calculate_token_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """Calculate USD cost for token usage with cache adjustments.

    Args:
        model: Model ID or short alias.
        input_tokens: Total input tokens (includes cache reads).
        output_tokens: Output tokens generated.
        cache_read_tokens: Subset of input from cache (discounted).
        cache_creation_tokens: Tokens written to cache (premium rate).

    Returns:
        Total cost in USD, rounded to 6 decimal places (micro-dollars).
        Returns 0.0 if no pricing data is found for the model.

    Formula:
        cost = (base_input * input_rate) + (cache_read * cache_read_rate)
             + (cache_write * cache_write_rate) + (output * output_rate)

    Where base_input = input_tokens - cache_read_tokens (non-cached input).
    """
    rates = await get_pricing(model)
    if rates is None:
        return 0.0

    base_input_tokens = max(input_tokens - cache_read_tokens, 0)

    cost = (
        (base_input_tokens * rates.input / 1_000_000)
        + (cache_read_tokens * rates.cache_read / 1_000_000)
        + (cache_creation_tokens * rates.cache_write / 1_000_000)
        + (output_tokens * rates.output / 1_000_000)
    )

    return round(cost, 6)
