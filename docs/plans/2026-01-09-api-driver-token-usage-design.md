# API Driver Token Usage Tracking

**Issue:** #210 - Add token usage tracking for ApiDriver (api:openrouter)

**Date:** 2026-01-09

## Problem

The `api:openrouter` driver records no token usage. Users cannot see costs, token counts, or model names for workflows run with the API driver. The Usage card shows nothing, and Past Runs displays stale `cli:claude` data instead.

## Design Decisions

1. **Cost calculation:** Use OpenRouter's reported cost from `response_metadata` rather than maintaining a local pricing table. This works automatically for any model and requires no maintenance.

2. **Interface:** Add a driver-agnostic `get_usage()` method to `DriverInterface` rather than forcing ApiDriver to mimic CLI internals with a fake `last_result_message`.

3. **Accumulation:** Track usage in the driver during streaming execution. LangChain exposes `usage_metadata` on each `AIMessage` but DeepAgents provides no aggregate - we accumulate manually.

4. **Return type:** New `DriverUsage` Pydantic model with all optional fields. Each driver populates what it can.

## DriverUsage Model

New model in `amelia/drivers/base.py`:

```python
class DriverUsage(BaseModel):
    """Token usage data returned by drivers.

    All fields optional - drivers populate what they can.
    """
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None
    model: str | None = None
```

## DriverInterface Change

```python
class DriverInterface(Protocol):
    # ... existing methods ...

    def get_usage(self) -> DriverUsage | None:
        """Return accumulated usage from last execution, or None if unavailable."""
        ...
```

## ApiDriver Changes

Add usage tracking to `amelia/drivers/api/deepagents.py`:

```python
def __init__(self, model: str | None = None, cwd: str | None = None):
    self.model = model or self.DEFAULT_MODEL
    self.cwd = cwd
    self._usage: DriverUsage | None = None

async def execute_agentic(self, prompt, cwd, ...):
    # Reset and track usage
    start_time = time.perf_counter()
    total_input = 0
    total_output = 0
    total_cost = 0.0
    num_turns = 0

    async for chunk in agent.astream(...):
        message = messages[-1]

        if isinstance(message, AIMessage):
            num_turns += 1

            # Extract usage from message
            if hasattr(message, "usage_metadata") and message.usage_metadata:
                usage = message.usage_metadata
                total_input += usage.get("input_tokens", 0)
                total_output += usage.get("output_tokens", 0)

            # Extract cost from response_metadata (OpenRouter)
            if hasattr(message, "response_metadata") and message.response_metadata:
                meta = message.response_metadata
                if "openrouter" in meta:
                    total_cost += meta["openrouter"].get("cost", 0.0)

        # ... existing yield logic ...

    # Store accumulated usage
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    self._usage = DriverUsage(
        input_tokens=total_input,
        output_tokens=total_output,
        cost_usd=total_cost if total_cost > 0 else None,
        duration_ms=duration_ms,
        num_turns=num_turns,
        model=self.model,
    )

def get_usage(self) -> DriverUsage | None:
    return self._usage
```

## ClaudeCliDriver Changes

Add `get_usage()` to `amelia/drivers/cli/claude.py`:

```python
def get_usage(self) -> DriverUsage | None:
    """Return usage from last execution."""
    if self.last_result_message is None:
        return None

    usage_data = getattr(self.last_result_message, "usage", None)
    if usage_data is None:
        return None

    return DriverUsage(
        input_tokens=usage_data.get("input_tokens"),
        output_tokens=usage_data.get("output_tokens"),
        cache_read_tokens=usage_data.get("cache_read_input_tokens"),
        cache_creation_tokens=usage_data.get("cache_creation_input_tokens"),
        cost_usd=getattr(self.last_result_message, "total_cost_usd", None),
        duration_ms=getattr(self.last_result_message, "duration_ms", None),
        num_turns=getattr(self.last_result_message, "num_turns", None),
        model=usage_data.get("model") or self.model,
    )
```

## Orchestrator Changes

Update `_save_token_usage()` in `amelia/core/orchestrator.py`:

```python
async def _save_token_usage(driver, workflow_id, agent, repository):
    if repository is None:
        return

    # Get usage from driver (works for both CLI and API drivers)
    driver_usage = driver.get_usage() if hasattr(driver, "get_usage") else None
    if driver_usage is None:
        return

    try:
        usage = TokenUsage(
            workflow_id=workflow_id,
            agent=agent,
            model=driver_usage.model or getattr(driver, "model", "unknown"),
            input_tokens=driver_usage.input_tokens or 0,
            output_tokens=driver_usage.output_tokens or 0,
            cache_read_tokens=driver_usage.cache_read_tokens or 0,
            cache_creation_tokens=driver_usage.cache_creation_tokens or 0,
            cost_usd=driver_usage.cost_usd or 0.0,
            duration_ms=driver_usage.duration_ms or 0,
            num_turns=driver_usage.num_turns or 1,
            timestamp=datetime.now(UTC),
        )
        await repository.save_token_usage(usage)
    except Exception as e:
        logger.warning("Failed to save token usage", error=str(e), agent=agent)
```

## Testing Strategy

**Unit tests:**

1. `tests/unit/drivers/test_api_driver_usage.py`
   - `get_usage()` returns `None` before execution
   - Usage accumulates during `execute_agentic()` with mocked responses
   - Cost extracted from OpenRouter's `response_metadata`
   - `num_turns` increments correctly

2. `tests/unit/drivers/test_cli_driver_usage.py`
   - `get_usage()` returns `None` when no `last_result_message`
   - `get_usage()` translates SDK fields to `DriverUsage`

3. `tests/unit/core/test_save_token_usage.py`
   - `_save_token_usage()` works with `DriverUsage`
   - Defaults applied for `None` fields
   - No-op when `get_usage()` returns `None`

**Integration test:**

4. `tests/integration/test_api_driver_token_tracking.py`
   - Mock HTTP boundary to OpenRouter
   - Run real `ApiDriver.execute_agentic()`
   - Verify `get_usage()` returns accumulated totals

## Files to Modify

| File | Change |
|------|--------|
| `amelia/drivers/base.py` | Add `DriverUsage` model, update `DriverInterface` |
| `amelia/drivers/api/deepagents.py` | Add usage tracking, implement `get_usage()` |
| `amelia/drivers/cli/claude.py` | Implement `get_usage()` |
| `amelia/core/orchestrator.py` | Update `_save_token_usage()` |
| `tests/unit/drivers/test_api_driver_usage.py` | New |
| `tests/unit/drivers/test_cli_driver_usage.py` | New |
| `tests/unit/core/test_save_token_usage.py` | Update or new |
| `tests/integration/test_api_driver_token_tracking.py` | New |
