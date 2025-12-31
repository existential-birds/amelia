"""Token usage tracking and cost calculation."""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


# Pricing per million tokens (as of 2025)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-20250514": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,  # 90% discount on cached input
        "cache_write": 18.75,  # 25% premium on cache creation
    },
    "claude-sonnet-4-20250514": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
}


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
        cost_usd: Net cost after cache adjustments.
        timestamp: When tokens were consumed.
    """

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier",
    )
    workflow_id: str = Field(..., description="Workflow ID")
    agent: str = Field(..., description="Agent that consumed tokens")
    model: str = Field(
        default="claude-sonnet-4-20250514",
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
    cost_usd: float | None = Field(
        default=None,
        description="Calculated cost in USD",
    )
    timestamp: datetime = Field(..., description="When consumed")


def calculate_token_cost(usage: TokenUsage) -> float:
    """Calculate USD cost for token usage with cache adjustments.

    Args:
        usage: Token usage record with model and token counts.

    Returns:
        Total cost in USD, rounded to 6 decimal places (micro-dollars).

    Formula:
        cost = (base_input * input_rate) + (cache_read * cache_read_rate)
             + (cache_write * cache_write_rate) + (output * output_rate)

    Where base_input = input_tokens - cache_read_tokens (non-cached input).
    """
    # Default to sonnet pricing if model unknown
    rates = MODEL_PRICING.get(usage.model, MODEL_PRICING["claude-sonnet-4-20250514"])

    # Cache reads are already included in input_tokens, so subtract them
    base_input_tokens = usage.input_tokens - usage.cache_read_tokens

    cost = (
        (base_input_tokens * rates["input"] / 1_000_000)
        + (usage.cache_read_tokens * rates["cache_read"] / 1_000_000)
        + (usage.cache_creation_tokens * rates["cache_write"] / 1_000_000)
        + (usage.output_tokens * rates["output"] / 1_000_000)
    )

    return round(cost, 6)
