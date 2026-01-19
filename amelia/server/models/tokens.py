"""Token usage tracking and cost calculation."""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


# Pricing per million tokens
# Sources: https://www.anthropic.com/pricing, https://openrouter.ai/pricing (last updated: 2026-01-19)
# Note: Update this when providers change pricing. Short aliases map to full model IDs.
# Cache pricing varies by provider:
# - Anthropic: cache_read = 0.1× input (90% discount), cache_write = 1.25× input (25% premium)
# - OpenAI: cache_read = 0.5× input, cache_write = 0 (free)
# - Google: cache_read = 0.25× input, cache_write = 0 (free)
# - DeepSeek: cache_read = 0.1× input, cache_write = 1× input
MODEL_PRICING: dict[str, dict[str, float]] = {
    # ==========================================================================
    # Anthropic Claude 4.5 (current generation - 2026)
    # ==========================================================================
    "claude-opus-4-5-20251101": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.5,  # 90% discount on cached input
        "cache_write": 6.25,  # 25% premium on cache creation
    },
    "claude-sonnet-4-5-20251101": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
    "claude-haiku-4-5-20251101": {
        "input": 1.0,
        "output": 5.0,
        "cache_read": 0.1,
        "cache_write": 1.25,
    },
    # ==========================================================================
    # OpenAI (via OpenRouter)
    # ==========================================================================
    "openai/gpt-4o": {
        "input": 2.5,
        "output": 10.0,
        "cache_read": 1.25,  # 0.5× input
        "cache_write": 0,  # free
    },
    "openai/o1": {
        "input": 15.0,
        "output": 60.0,
        "cache_read": 7.5,  # 0.5× input
        "cache_write": 0,  # free
    },
    "openai/o3-mini": {
        "input": 1.1,
        "output": 4.4,
        "cache_read": 0.55,  # 0.5× input
        "cache_write": 0,  # free
    },
    # ==========================================================================
    # Google Gemini (via OpenRouter)
    # ==========================================================================
    "google/gemini-2.0-flash": {
        "input": 0.1,
        "output": 0.4,
        "cache_read": 0.025,  # 0.25× input
        "cache_write": 0,  # free
    },
    "google/gemini-2.0-pro": {
        "input": 1.25,
        "output": 5.0,
        "cache_read": 0.3125,  # 0.25× input
        "cache_write": 0,  # free
    },
    # ==========================================================================
    # DeepSeek (via OpenRouter) - Very cost-effective
    # ==========================================================================
    "deepseek/deepseek-coder-v3": {
        "input": 0.14,
        "output": 0.28,
        "cache_read": 0.014,  # 0.1× input
        "cache_write": 0.14,  # 1× input
    },
    "deepseek/deepseek-v3": {
        "input": 0.14,
        "output": 0.28,
        "cache_read": 0.014,  # 0.1× input
        "cache_write": 0.14,  # 1× input
    },
    # ==========================================================================
    # Mistral (via OpenRouter)
    # ==========================================================================
    "mistral/codestral-latest": {
        "input": 0.3,
        "output": 0.9,
        "cache_read": 0.03,
        "cache_write": 0.3,
    },
    # ==========================================================================
    # Qwen (via OpenRouter) - Open source
    # ==========================================================================
    "qwen/qwen-2.5-coder-32b": {
        "input": 0.18,
        "output": 0.18,
        "cache_read": 0.018,
        "cache_write": 0.18,
    },
    "qwen/qwen-2.5-72b": {
        "input": 0.35,
        "output": 0.40,
        "cache_read": 0.035,
        "cache_write": 0.35,
    },
    # ==========================================================================
    # MiniMax (via OpenRouter)
    # ==========================================================================
    "minimax/minimax-m2": {
        "input": 0.20,
        "output": 1.00,
        "cache_read": 0.02,
        "cache_write": 0.20,
    },
    "minimax/minimax-m1": {
        "input": 0.40,
        "output": 2.20,
        "cache_read": 0.04,
        "cache_write": 0.40,
    },
    # ==========================================================================
    # Legacy Anthropic models (for historical data)
    # ==========================================================================
    "claude-opus-4-20250514": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,
        "cache_write": 18.75,
    },
    "claude-sonnet-4-20250514": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
    "claude-3-5-sonnet-20241022": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
    "claude-3-5-haiku-20241022": {
        "input": 0.8,
        "output": 4.0,
        "cache_read": 0.08,
        "cache_write": 1.0,
    },
    "claude-3-opus-20240229": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,
        "cache_write": 18.75,
    },
    "claude-3-haiku-20240307": {
        "input": 0.25,
        "output": 1.25,
        "cache_read": 0.03,
        "cache_write": 0.30,
    },
    # ==========================================================================
    # Short aliases for driver model strings
    # ==========================================================================
    "sonnet": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
    "opus": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    "haiku": {
        "input": 1.0,
        "output": 5.0,
        "cache_read": 0.1,
        "cache_write": 1.25,
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
        cost_usd: Net cost after cache adjustments (required).
        duration_ms: Execution time in milliseconds.
        num_turns: Number of conversation turns.
        timestamp: When tokens were consumed.
    """

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier",
    )
    workflow_id: str = Field(..., description="Workflow ID")
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
    rates = MODEL_PRICING.get(usage.model, MODEL_PRICING["claude-sonnet-4-5-20251101"])

    # Cache reads are already included in input_tokens, so subtract them
    base_input_tokens = usage.input_tokens - usage.cache_read_tokens

    cost = (
        (base_input_tokens * rates["input"] / 1_000_000)
        + (usage.cache_read_tokens * rates["cache_read"] / 1_000_000)
        + (usage.cache_creation_tokens * rates["cache_write"] / 1_000_000)
        + (usage.output_tokens * rates["output"] / 1_000_000)
    )

    return round(cost, 6)
