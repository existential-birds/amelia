"""Typed models for cached OpenRouter metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ModelCacheCapabilities(BaseModel):
    """Normalized capabilities extracted from OpenRouter metadata."""

    tool_call: bool = False
    reasoning: bool = False
    structured_output: bool = False


class ModelCacheModalities(BaseModel):
    """Normalized input and output modalities for a model."""

    input: list[str] = Field(default_factory=list)
    output: list[str] = Field(default_factory=list)


class ModelCacheEntry(BaseModel):
    """Persisted OpenRouter model metadata."""

    id: str
    name: str
    provider: str
    context_length: int | None = None
    max_output_tokens: int | None = None
    input_cost_per_m: float | None = None
    output_cost_per_m: float | None = None
    cache_read_cost_per_m: float | None = None
    cache_write_cost_per_m: float | None = None
    capabilities: ModelCacheCapabilities = Field(default_factory=ModelCacheCapabilities)
    modalities: ModelCacheModalities = Field(default_factory=ModelCacheModalities)
    raw_response: dict[str, Any] | None = None
    fetched_at: datetime
    created_at: datetime


class ModelLookupCost(BaseModel):
    """Dashboard-facing cost information."""

    input: float | None = None
    output: float | None = None


class ModelLookupLimit(BaseModel):
    """Dashboard-facing token limits."""

    context: int | None = None
    output: int | None = None


class ModelLookupResponse(BaseModel):
    """Normalized response returned by the model lookup API."""

    id: str
    name: str
    provider: str
    capabilities: ModelCacheCapabilities
    cost: ModelLookupCost
    limit: ModelLookupLimit
    modalities: ModelCacheModalities


def _get_provider(model_id: str) -> str:
    """Extract provider prefix from an OpenRouter model id."""
    slash_index = model_id.find("/")
    return model_id[:slash_index] if slash_index != -1 else "unknown"


def _parse_price_per_million(value: Any) -> float | None:
    """Convert per-token string pricing to a per-million float."""
    if value is None:
        return None
    try:
        return float(value) * 1_000_000
    except (TypeError, ValueError):
        return None


def _as_string_list(value: Any) -> list[str]:
    """Normalize OpenRouter list-like fields into string lists."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def normalize_openrouter_model(
    model_data: dict[str, Any],
    *,
    fetched_at: datetime | None = None,
) -> ModelCacheEntry | None:
    """Normalize a raw OpenRouter model payload into a cache entry."""
    model_id = model_data.get("id")
    name = model_data.get("name")
    if not isinstance(model_id, str) or not isinstance(name, str):
        return None

    pricing = model_data.get("pricing")
    architecture = model_data.get("architecture")
    top_provider = model_data.get("top_provider")
    supported_parameters = model_data.get("supported_parameters")

    fetched = fetched_at or datetime.now(UTC)
    if not isinstance(pricing, dict):
        pricing = {}
    if not isinstance(architecture, dict):
        architecture = {}
    if not isinstance(top_provider, dict):
        top_provider = {}
    if not isinstance(supported_parameters, list):
        supported_parameters = []

    context_length = model_data.get("context_length")
    top_provider_context = top_provider.get("context_length")
    max_output_tokens = top_provider.get("max_completion_tokens")

    normalized_context: int | None
    if isinstance(context_length, int) and context_length > 0:
        normalized_context = context_length
    elif isinstance(top_provider_context, int) and top_provider_context > 0:
        normalized_context = top_provider_context
    else:
        normalized_context = None

    normalized_output = max_output_tokens if isinstance(max_output_tokens, int) else None

    return ModelCacheEntry(
        id=model_id,
        name=name,
        provider=_get_provider(model_id),
        context_length=normalized_context,
        max_output_tokens=normalized_output,
        input_cost_per_m=_parse_price_per_million(pricing.get("prompt")),
        output_cost_per_m=_parse_price_per_million(pricing.get("completion")),
        cache_read_cost_per_m=_parse_price_per_million(pricing.get("cache_read")),
        cache_write_cost_per_m=_parse_price_per_million(pricing.get("cache_write")),
        capabilities=ModelCacheCapabilities(
            tool_call=True,
            reasoning="reasoning" in supported_parameters,
            structured_output="response_format" in supported_parameters,
        ),
        modalities=ModelCacheModalities(
            input=_as_string_list(architecture.get("input_modalities")),
            output=_as_string_list(architecture.get("output_modalities")),
        ),
        raw_response=model_data,
        fetched_at=fetched,
        created_at=fetched,
    )


def to_model_lookup_response(entry: ModelCacheEntry) -> ModelLookupResponse:
    """Convert a cache entry into the dashboard-facing API response."""
    return ModelLookupResponse(
        id=entry.id,
        name=entry.name,
        provider=entry.provider,
        capabilities=entry.capabilities,
        cost=ModelLookupCost(
            input=entry.input_cost_per_m,
            output=entry.output_cost_per_m,
        ),
        limit=ModelLookupLimit(
            context=entry.context_length,
            output=entry.max_output_tokens,
        ),
        modalities=entry.modalities,
    )
