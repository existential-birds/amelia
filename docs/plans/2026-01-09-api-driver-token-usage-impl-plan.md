# API Driver Token Usage Tracking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add token usage tracking to `ApiDriver` so the Usage card and Past Runs display accurate costs, token counts, and model names for workflows run via `api:openrouter`.

**Architecture:** Add a `DriverUsage` Pydantic model to `amelia/drivers/base.py` and a `get_usage()` method to `DriverInterface`. `ApiDriver` accumulates usage from LangChain's `usage_metadata` and OpenRouter's `response_metadata` during streaming, then returns it via `get_usage()`. `ClaudeCliDriver` translates its existing `last_result_message` data to `DriverUsage`. The orchestrator's `_save_token_usage()` uses `get_usage()` instead of driver-specific attribute access.

**Tech Stack:** Python 3.12+, Pydantic, pytest, pytest-asyncio, LangChain

---

## Task 1: Add DriverUsage Model

**Files:**
- Modify: `amelia/drivers/base.py:1-50`
- Test: `tests/unit/drivers/test_driver_usage_model.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/drivers/test_driver_usage_model.py`:

```python
"""Tests for DriverUsage model."""
import pytest

from amelia.drivers.base import DriverUsage


class TestDriverUsageModel:
    """Tests for the DriverUsage Pydantic model."""

    def test_driver_usage_all_fields_optional(self) -> None:
        """DriverUsage should allow all fields to be None."""
        usage = DriverUsage()

        assert usage.input_tokens is None
        assert usage.output_tokens is None
        assert usage.cache_read_tokens is None
        assert usage.cache_creation_tokens is None
        assert usage.cost_usd is None
        assert usage.duration_ms is None
        assert usage.num_turns is None
        assert usage.model is None

    def test_driver_usage_with_all_fields(self) -> None:
        """DriverUsage should accept all fields when provided."""
        usage = DriverUsage(
            input_tokens=1500,
            output_tokens=500,
            cache_read_tokens=1000,
            cache_creation_tokens=200,
            cost_usd=0.025,
            duration_ms=5000,
            num_turns=3,
            model="openrouter:anthropic/claude-3.5-sonnet",
        )

        assert usage.input_tokens == 1500
        assert usage.output_tokens == 500
        assert usage.cache_read_tokens == 1000
        assert usage.cache_creation_tokens == 200
        assert usage.cost_usd == 0.025
        assert usage.duration_ms == 5000
        assert usage.num_turns == 3
        assert usage.model == "openrouter:anthropic/claude-3.5-sonnet"

    def test_driver_usage_partial_fields(self) -> None:
        """DriverUsage should work with only some fields set."""
        usage = DriverUsage(
            input_tokens=100,
            output_tokens=50,
            model="test-model",
        )

        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.model == "test-model"
        assert usage.cost_usd is None
        assert usage.duration_ms is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/drivers/test_driver_usage_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'DriverUsage' from 'amelia.drivers.base'`

**Step 3: Write minimal implementation**

Add to `amelia/drivers/base.py` after the imports (around line 8):

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

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/drivers/test_driver_usage_model.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/base.py tests/unit/drivers/test_driver_usage_model.py
git commit -m "feat(drivers): add DriverUsage model for driver-agnostic usage tracking

Part of #210 - API driver token usage tracking"
```

---

## Task 2: Add get_usage() to DriverInterface Protocol

**Files:**
- Modify: `amelia/drivers/base.py:123-173`

**Step 1: Write the failing test**

Add to `tests/unit/drivers/test_driver_usage_model.py`:

```python
from typing import Protocol, runtime_checkable


class TestDriverInterfaceProtocol:
    """Tests for DriverInterface protocol changes."""

    def test_driver_interface_has_get_usage_method(self) -> None:
        """DriverInterface protocol should define get_usage() method."""
        from amelia.drivers.base import DriverInterface

        # Check that get_usage is in the protocol's annotations
        assert hasattr(DriverInterface, "get_usage")

        # Verify it's a callable that returns DriverUsage | None
        import inspect
        sig = inspect.signature(DriverInterface.get_usage)
        assert sig.return_annotation == "DriverUsage | None"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/drivers/test_driver_usage_model.py::TestDriverInterfaceProtocol -v`
Expected: FAIL with `AssertionError` (get_usage not found)

**Step 3: Write minimal implementation**

Add to `DriverInterface` protocol in `amelia/drivers/base.py` after the `execute_agentic` method:

```python
    def get_usage(self) -> DriverUsage | None:
        """Return accumulated usage from last execution, or None if unavailable."""
        ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/drivers/test_driver_usage_model.py::TestDriverInterfaceProtocol -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/base.py tests/unit/drivers/test_driver_usage_model.py
git commit -m "feat(drivers): add get_usage() to DriverInterface protocol

Part of #210 - API driver token usage tracking"
```

---

## Task 3: Implement get_usage() in ClaudeCliDriver

**Files:**
- Modify: `amelia/drivers/cli/claude.py:450-453`
- Test: `tests/unit/drivers/test_cli_driver_usage.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/drivers/test_cli_driver_usage.py`:

```python
"""Tests for ClaudeCliDriver.get_usage() method."""
from unittest.mock import MagicMock

import pytest

from amelia.drivers.base import DriverUsage
from amelia.drivers.cli.claude import ClaudeCliDriver


class TestClaudeCliDriverGetUsage:
    """Tests for ClaudeCliDriver.get_usage() method."""

    def test_get_usage_returns_none_when_no_last_result(self) -> None:
        """get_usage() should return None when no execution has occurred."""
        driver = ClaudeCliDriver(model="sonnet")

        result = driver.get_usage()

        assert result is None

    def test_get_usage_returns_none_when_no_usage_data(self) -> None:
        """get_usage() should return None when last_result_message has no usage."""
        driver = ClaudeCliDriver(model="sonnet")
        driver.last_result_message = MagicMock()
        driver.last_result_message.usage = None

        result = driver.get_usage()

        assert result is None

    def test_get_usage_translates_sdk_fields(self) -> None:
        """get_usage() should translate SDK ResultMessage fields to DriverUsage."""
        driver = ClaudeCliDriver(model="sonnet")

        # Mock ResultMessage with full usage data
        mock_result = MagicMock()
        mock_result.usage = {
            "model": "claude-sonnet-4-20250514",
            "input_tokens": 1500,
            "output_tokens": 500,
            "cache_read_input_tokens": 1000,
            "cache_creation_input_tokens": 200,
        }
        mock_result.total_cost_usd = 0.025
        mock_result.duration_ms = 5000
        mock_result.num_turns = 3
        driver.last_result_message = mock_result

        result = driver.get_usage()

        assert isinstance(result, DriverUsage)
        assert result.input_tokens == 1500
        assert result.output_tokens == 500
        assert result.cache_read_tokens == 1000
        assert result.cache_creation_tokens == 200
        assert result.cost_usd == 0.025
        assert result.duration_ms == 5000
        assert result.num_turns == 3
        assert result.model == "claude-sonnet-4-20250514"

    def test_get_usage_falls_back_to_driver_model(self) -> None:
        """get_usage() should use driver.model when usage.model is missing."""
        driver = ClaudeCliDriver(model="opus")

        mock_result = MagicMock()
        mock_result.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            # No model in usage
        }
        mock_result.total_cost_usd = 0.01
        mock_result.duration_ms = 1000
        mock_result.num_turns = 1
        driver.last_result_message = mock_result

        result = driver.get_usage()

        assert result is not None
        assert result.model == "opus"

    def test_get_usage_handles_partial_usage_data(self) -> None:
        """get_usage() should handle ResultMessage with partial usage fields."""
        driver = ClaudeCliDriver(model="sonnet")

        mock_result = MagicMock()
        mock_result.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            # Missing cache tokens
        }
        mock_result.total_cost_usd = None  # Missing cost
        mock_result.duration_ms = None  # Missing duration
        mock_result.num_turns = None  # Missing turns
        driver.last_result_message = mock_result

        result = driver.get_usage()

        assert result is not None
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.cache_read_tokens is None
        assert result.cache_creation_tokens is None
        assert result.cost_usd is None
        assert result.duration_ms is None
        assert result.num_turns is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/drivers/test_cli_driver_usage.py -v`
Expected: FAIL with `AttributeError: 'ClaudeCliDriver' object has no attribute 'get_usage'`

**Step 3: Write minimal implementation**

Add to `amelia/drivers/cli/claude.py` after `clear_tool_history()` method:

```python
    def get_usage(self) -> DriverUsage | None:
        """Return usage from last execution.

        Translates SDK ResultMessage fields to the driver-agnostic DriverUsage model.

        Returns:
            DriverUsage with accumulated usage data, or None if no execution occurred
            or no usage data is available.
        """
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

Also add the import at the top of `amelia/drivers/cli/claude.py`:

```python
from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage, GenerateResult
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/drivers/test_cli_driver_usage.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/cli/claude.py tests/unit/drivers/test_cli_driver_usage.py
git commit -m "feat(cli-driver): implement get_usage() for driver-agnostic usage tracking

Translates SDK ResultMessage fields to DriverUsage model.
Part of #210 - API driver token usage tracking"
```

---

## Task 4: Add Usage Tracking to ApiDriver

**Files:**
- Modify: `amelia/drivers/api/deepagents.py:155-177` (init)
- Modify: `amelia/drivers/api/deepagents.py:283-418` (execute_agentic)
- Test: `tests/unit/drivers/test_api_driver_usage.py` (create)

**Step 4.1: Write the failing test for get_usage before execution**

Create `tests/unit/drivers/test_api_driver_usage.py`:

```python
"""Tests for ApiDriver token usage tracking."""
import os
from unittest.mock import MagicMock, patch

import pytest

from amelia.drivers.base import DriverUsage


class TestApiDriverGetUsage:
    """Tests for ApiDriver.get_usage() method."""

    def test_get_usage_returns_none_before_execution(self) -> None:
        """get_usage() should return None before any execution."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            from amelia.drivers.api.deepagents import ApiDriver

            driver = ApiDriver(model="openrouter:test/model")

            result = driver.get_usage()

            assert result is None
```

**Step 4.2: Run test to verify it fails**

Run: `uv run pytest tests/unit/drivers/test_api_driver_usage.py::TestApiDriverGetUsage::test_get_usage_returns_none_before_execution -v`
Expected: FAIL with `AttributeError: 'ApiDriver' object has no attribute 'get_usage'`

**Step 4.3: Write minimal implementation for get_usage skeleton**

Add to `ApiDriver.__init__` in `amelia/drivers/api/deepagents.py`:

```python
def __init__(self, model: str | None = None, cwd: str | None = None):
    """Initialize the API driver.

    Args:
        model: Model identifier for langchain (e.g., 'openrouter:minimax/minimax-m2').
        cwd: Working directory for agentic execution. Required for execute_agentic().
    """
    self.model = model or self.DEFAULT_MODEL
    self.cwd = cwd
    self._usage: DriverUsage | None = None
```

Add `get_usage()` method after `execute_agentic`:

```python
def get_usage(self) -> DriverUsage | None:
    """Return accumulated usage from last execution.

    Returns:
        DriverUsage with accumulated totals, or None if no execution occurred.
    """
    return self._usage
```

Add import at top of file:

```python
from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverInterface,
    DriverUsage,
    GenerateResult,
)
```

**Step 4.4: Run test to verify it passes**

Run: `uv run pytest tests/unit/drivers/test_api_driver_usage.py::TestApiDriverGetUsage::test_get_usage_returns_none_before_execution -v`
Expected: PASS

**Step 4.5: Commit**

```bash
git add amelia/drivers/api/deepagents.py tests/unit/drivers/test_api_driver_usage.py
git commit -m "feat(api-driver): add get_usage() skeleton

Part of #210 - API driver token usage tracking"
```

---

## Task 5: Implement Usage Accumulation During execute_agentic

**Files:**
- Modify: `amelia/drivers/api/deepagents.py:283-418`
- Test: `tests/unit/drivers/test_api_driver_usage.py`

**Step 5.1: Write the failing test for usage accumulation**

Add to `tests/unit/drivers/test_api_driver_usage.py`:

```python
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class TestApiDriverUsageAccumulation:
    """Tests for ApiDriver usage accumulation during execute_agentic."""

    @pytest.fixture
    def mock_deepagents_for_usage(self):
        """Set up mock for DeepAgents with usage metadata."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), \
             patch("amelia.drivers.api.deepagents.create_deep_agent") as mock_create, \
             patch("amelia.drivers.api.deepagents.init_chat_model"), \
             patch("amelia.drivers.api.deepagents.LocalSandbox"):

            yield mock_create

    async def test_accumulates_usage_from_ai_messages(
        self, mock_deepagents_for_usage: MagicMock
    ) -> None:
        """execute_agentic should accumulate usage from AIMessage.usage_metadata."""
        from amelia.drivers.api.deepagents import ApiDriver

        # Create AIMessages with usage_metadata
        msg1 = AIMessage(content="First response")
        msg1.usage_metadata = {"input_tokens": 100, "output_tokens": 50}

        msg2 = AIMessage(content="Second response")
        msg2.usage_metadata = {"input_tokens": 200, "output_tokens": 100}

        # Set up mock agent to yield chunks with these messages
        stream_chunks = [
            {"messages": [HumanMessage(content="test"), msg1]},
            {"messages": [HumanMessage(content="test"), msg1, msg2]},
        ]

        async def mock_astream(*args, **kwargs):
            for chunk in stream_chunks:
                yield chunk

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_deepagents_for_usage.return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        # Consume the generator
        messages = []
        async for msg in driver.execute_agentic("test prompt", "/tmp"):
            messages.append(msg)

        # Verify accumulated usage
        usage = driver.get_usage()
        assert usage is not None
        assert usage.input_tokens == 300  # 100 + 200
        assert usage.output_tokens == 150  # 50 + 100
        assert usage.model == "openrouter:test/model"
        assert usage.num_turns == 2

    async def test_extracts_cost_from_openrouter_metadata(
        self, mock_deepagents_for_usage: MagicMock
    ) -> None:
        """execute_agentic should extract cost from OpenRouter response_metadata."""
        from amelia.drivers.api.deepagents import ApiDriver

        # Create AIMessage with OpenRouter cost in response_metadata
        msg = AIMessage(content="Response")
        msg.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        msg.response_metadata = {"openrouter": {"cost": 0.0025}}

        stream_chunks = [{"messages": [msg]}]

        async def mock_astream(*args, **kwargs):
            for chunk in stream_chunks:
                yield chunk

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_deepagents_for_usage.return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        async for _ in driver.execute_agentic("test", "/tmp"):
            pass

        usage = driver.get_usage()
        assert usage is not None
        assert usage.cost_usd == 0.0025

    async def test_accumulates_cost_from_multiple_messages(
        self, mock_deepagents_for_usage: MagicMock
    ) -> None:
        """Cost should accumulate from multiple AIMessages with response_metadata."""
        from amelia.drivers.api.deepagents import ApiDriver

        msg1 = AIMessage(content="First")
        msg1.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        msg1.response_metadata = {"openrouter": {"cost": 0.001}}

        msg2 = AIMessage(content="Second")
        msg2.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        msg2.response_metadata = {"openrouter": {"cost": 0.002}}

        stream_chunks = [
            {"messages": [msg1]},
            {"messages": [msg1, msg2]},
        ]

        async def mock_astream(*args, **kwargs):
            for chunk in stream_chunks:
                yield chunk

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_deepagents_for_usage.return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        async for _ in driver.execute_agentic("test", "/tmp"):
            pass

        usage = driver.get_usage()
        assert usage is not None
        assert usage.cost_usd == 0.003  # 0.001 + 0.002

    async def test_tracks_duration_ms(
        self, mock_deepagents_for_usage: MagicMock
    ) -> None:
        """execute_agentic should track execution duration in milliseconds."""
        from amelia.drivers.api.deepagents import ApiDriver

        msg = AIMessage(content="Done")
        msg.usage_metadata = {"input_tokens": 10, "output_tokens": 5}

        async def mock_astream(*args, **kwargs):
            await asyncio.sleep(0.1)  # 100ms delay
            yield {"messages": [msg]}

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_deepagents_for_usage.return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        async for _ in driver.execute_agentic("test", "/tmp"):
            pass

        usage = driver.get_usage()
        assert usage is not None
        assert usage.duration_ms >= 100  # At least 100ms

    async def test_resets_usage_on_new_execution(
        self, mock_deepagents_for_usage: MagicMock
    ) -> None:
        """Each execute_agentic call should reset and start fresh usage tracking."""
        from amelia.drivers.api.deepagents import ApiDriver

        msg1 = AIMessage(content="First run")
        msg1.usage_metadata = {"input_tokens": 100, "output_tokens": 50}

        msg2 = AIMessage(content="Second run")
        msg2.usage_metadata = {"input_tokens": 200, "output_tokens": 100}

        call_count = 0

        async def mock_astream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield {"messages": [msg1]}
            else:
                yield {"messages": [msg2]}

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_deepagents_for_usage.return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        # First execution
        async for _ in driver.execute_agentic("first", "/tmp"):
            pass
        usage1 = driver.get_usage()

        # Second execution
        async for _ in driver.execute_agentic("second", "/tmp"):
            pass
        usage2 = driver.get_usage()

        # Usage should be from second run only, not accumulated
        assert usage1.input_tokens == 100
        assert usage2.input_tokens == 200


# Add asyncio import at the top of the test file
import asyncio
```

**Step 5.2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/drivers/test_api_driver_usage.py::TestApiDriverUsageAccumulation -v`
Expected: FAIL (usage not accumulated)

**Step 5.3: Implement usage accumulation in execute_agentic**

Modify `execute_agentic` in `amelia/drivers/api/deepagents.py`:

```python
async def execute_agentic(
    self,
    prompt: str,
    cwd: str,
    session_id: str | None = None,
    instructions: str | None = None,
    schema: type[BaseModel] | None = None,
) -> AsyncIterator[AgenticMessage]:
    """Execute prompt with autonomous tool access using DeepAgents.

    Uses the DeepAgents library to create an autonomous agent that can
    use filesystem tools to complete tasks.

    Args:
        prompt: The prompt to execute.
        cwd: Working directory for tool execution.
        session_id: Unused (API driver has no session support).
        instructions: Unused (system prompt set at agent creation).
        schema: Unused (structured output not supported in agentic mode).

    Yields:
        AgenticMessage for each event (thinking, tool_call, tool_result, result).

    Raises:
        ValueError: If prompt is empty.
        RuntimeError: If execution fails.
    """
    import time

    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty")

    # Reset usage tracking for this execution
    start_time = time.perf_counter()
    total_input = 0
    total_output = 0
    total_cost = 0.0
    num_turns = 0
    seen_message_ids: set[int] = set()  # Track messages we've already counted

    try:
        chat_model = _create_chat_model(self.model)
        backend = LocalSandbox(root_dir=cwd)
        agent = create_deep_agent(
            model=chat_model,
            system_prompt="",
            backend=backend,
        )

        logger.debug(
            "Starting agentic execution",
            model=self.model,
            cwd=cwd,
            prompt_length=len(prompt),
        )

        last_message: AIMessage | None = None

        async for chunk in agent.astream(
            {"messages": [HumanMessage(content=prompt)]},
            stream_mode="values",
        ):
            messages = chunk.get("messages", [])
            if not messages:
                continue

            message = messages[-1]

            if isinstance(message, AIMessage):
                last_message = message
                msg_id = id(message)

                # Only count usage for new messages
                if msg_id not in seen_message_ids:
                    seen_message_ids.add(msg_id)
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

                # Text blocks in list content -> THINKING (intermediate text during tool use)
                # Plain string content is NOT yielded as THINKING - it will be yielded as RESULT
                # at the end to avoid duplicate content (same pattern as ClaudeCliDriver where
                # TextBlock -> THINKING and ResultMessage.result -> RESULT are distinct sources)
                if isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            yield AgenticMessage(
                                type=AgenticMessageType.THINKING,
                                content=block.get("text", ""),
                                model=self.model,
                            )

                # Tool calls
                for tool_call in message.tool_calls or []:
                    tool_raw_name = tool_call["name"]
                    # Normalize tool name to standard format
                    tool_normalized = normalize_tool_name(tool_raw_name)
                    yield AgenticMessage(
                        type=AgenticMessageType.TOOL_CALL,
                        tool_name=tool_normalized,
                        tool_input=tool_call.get("args", {}),
                        tool_call_id=tool_call.get("id"),
                        model=self.model,
                    )

            elif isinstance(message, ToolMessage):
                # Normalize tool name to standard format
                result_raw_name = message.name
                result_normalized: str | None = (
                    normalize_tool_name(result_raw_name)
                    if result_raw_name
                    else None
                )
                yield AgenticMessage(
                    type=AgenticMessageType.TOOL_RESULT,
                    tool_name=result_normalized,
                    tool_output=str(message.content),
                    tool_call_id=message.tool_call_id,
                    is_error=message.status == "error",
                    model=self.model,
                )

        # Store accumulated usage
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        self._usage = DriverUsage(
            input_tokens=total_input if total_input > 0 else None,
            output_tokens=total_output if total_output > 0 else None,
            cost_usd=total_cost if total_cost > 0 else None,
            duration_ms=duration_ms,
            num_turns=num_turns if num_turns > 0 else None,
            model=self.model,
        )

        # Final result from last AI message
        if last_message:
            final_content = ""
            if isinstance(last_message.content, str):
                final_content = last_message.content
            elif isinstance(last_message.content, list):
                for block in last_message.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        final_content += block.get("text", "")

            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content=final_content,
                session_id=None,  # API driver has no session support
                model=self.model,
            )
        else:
            # Always yield RESULT per interface contract
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Agent produced no output",
                session_id=None,
                is_error=True,
                model=self.model,
            )

    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Agentic execution failed: {e}") from e
```

**Step 5.4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/drivers/test_api_driver_usage.py -v`
Expected: PASS

**Step 5.5: Commit**

```bash
git add amelia/drivers/api/deepagents.py tests/unit/drivers/test_api_driver_usage.py
git commit -m "feat(api-driver): implement token usage accumulation during execute_agentic

Tracks input/output tokens from usage_metadata, cost from OpenRouter's
response_metadata, duration, and turn count.
Part of #210 - API driver token usage tracking"
```

---

## Task 6: Update Orchestrator's _save_token_usage to Use get_usage()

**Files:**
- Modify: `amelia/core/orchestrator.py:89-149`
- Test: `tests/unit/core/test_save_token_usage.py` (create)

**Step 6.1: Write the failing test for new _save_token_usage behavior**

Create `tests/unit/core/test_save_token_usage.py`:

```python
"""Tests for orchestrator _save_token_usage using DriverUsage."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.drivers.base import DriverUsage
from amelia.server.models.tokens import TokenUsage


class TestSaveTokenUsageWithDriverUsage:
    """Tests for _save_token_usage() using get_usage() method."""

    async def test_saves_usage_from_driver_get_usage(self) -> None:
        """_save_token_usage should call driver.get_usage() and save to repository."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.get_usage.return_value = DriverUsage(
            input_tokens=1500,
            output_tokens=500,
            cache_read_tokens=1000,
            cache_creation_tokens=200,
            cost_usd=0.025,
            duration_ms=5000,
            num_turns=3,
            model="test-model",
        )

        mock_repository = AsyncMock()

        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=mock_repository,
        )

        mock_driver.get_usage.assert_called_once()
        mock_repository.save_token_usage.assert_called_once()

        saved_usage = mock_repository.save_token_usage.call_args[0][0]
        assert isinstance(saved_usage, TokenUsage)
        assert saved_usage.workflow_id == "wf-123"
        assert saved_usage.agent == "developer"
        assert saved_usage.model == "test-model"
        assert saved_usage.input_tokens == 1500
        assert saved_usage.output_tokens == 500
        assert saved_usage.cache_read_tokens == 1000
        assert saved_usage.cache_creation_tokens == 200
        assert saved_usage.cost_usd == 0.025
        assert saved_usage.duration_ms == 5000
        assert saved_usage.num_turns == 3

    async def test_noop_when_get_usage_returns_none(self) -> None:
        """_save_token_usage should not save when get_usage() returns None."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.get_usage.return_value = None

        mock_repository = AsyncMock()

        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=mock_repository,
        )

        mock_repository.save_token_usage.assert_not_called()

    async def test_noop_when_repository_is_none(self) -> None:
        """_save_token_usage should not attempt save when repository is None."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.get_usage.return_value = DriverUsage(input_tokens=100)

        # Should not raise
        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=None,
        )

        # No assertion on get_usage - we short-circuit before calling it

    async def test_defaults_none_fields_to_zero(self) -> None:
        """_save_token_usage should use 0 for None fields in DriverUsage."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.model = "fallback-model"
        mock_driver.get_usage.return_value = DriverUsage(
            input_tokens=100,
            output_tokens=50,
            # All other fields None
        )

        mock_repository = AsyncMock()

        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="architect",
            repository=mock_repository,
        )

        saved_usage = mock_repository.save_token_usage.call_args[0][0]
        assert saved_usage.input_tokens == 100
        assert saved_usage.output_tokens == 50
        assert saved_usage.cache_read_tokens == 0  # Default
        assert saved_usage.cache_creation_tokens == 0  # Default
        assert saved_usage.cost_usd == 0.0  # Default
        assert saved_usage.duration_ms == 0  # Default
        assert saved_usage.num_turns == 1  # Default

    async def test_uses_driver_model_when_usage_model_is_none(self) -> None:
        """_save_token_usage should fall back to driver.model when DriverUsage.model is None."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.model = "driver-model"
        mock_driver.get_usage.return_value = DriverUsage(
            input_tokens=100,
            output_tokens=50,
            model=None,  # No model in usage
        )

        mock_repository = AsyncMock()

        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=mock_repository,
        )

        saved_usage = mock_repository.save_token_usage.call_args[0][0]
        assert saved_usage.model == "driver-model"

    async def test_uses_unknown_when_no_model_available(self) -> None:
        """_save_token_usage should use 'unknown' when model unavailable everywhere."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock(spec=["get_usage"])  # No model attribute
        mock_driver.get_usage.return_value = DriverUsage(
            input_tokens=100,
            output_tokens=50,
            model=None,
        )

        mock_repository = AsyncMock()

        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="reviewer",
            repository=mock_repository,
        )

        saved_usage = mock_repository.save_token_usage.call_args[0][0]
        assert saved_usage.model == "unknown"

    async def test_handles_driver_without_get_usage(self) -> None:
        """_save_token_usage should handle drivers without get_usage gracefully."""
        from amelia.core.orchestrator import _save_token_usage

        # Driver without get_usage (uses spec to exclude it)
        mock_driver = MagicMock(spec=["generate", "execute_agentic"])

        mock_repository = AsyncMock()

        # Should not raise
        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=mock_repository,
        )

        mock_repository.save_token_usage.assert_not_called()

    async def test_handles_repository_error_gracefully(self) -> None:
        """_save_token_usage should log but not raise on repository errors."""
        from amelia.core.orchestrator import _save_token_usage

        mock_driver = MagicMock()
        mock_driver.get_usage.return_value = DriverUsage(
            input_tokens=100,
            output_tokens=50,
        )

        mock_repository = AsyncMock()
        mock_repository.save_token_usage.side_effect = Exception("DB error")

        # Should not raise
        await _save_token_usage(
            driver=mock_driver,
            workflow_id="wf-123",
            agent="developer",
            repository=mock_repository,
        )
```

**Step 6.2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_save_token_usage.py -v`
Expected: FAIL (current implementation uses last_result_message, not get_usage)

**Step 6.3: Implement updated _save_token_usage**

Replace `_save_token_usage` in `amelia/core/orchestrator.py`:

```python
async def _save_token_usage(
    driver: Any,
    workflow_id: str,
    agent: str,
    repository: "WorkflowRepository | None",
) -> None:
    """Extract token usage from driver and save to repository.

    This is a best-effort operation - failures are logged but don't fail the workflow.
    Uses the driver-agnostic get_usage() method when available.

    Args:
        driver: The driver that was used for execution.
        workflow_id: Current workflow ID.
        agent: Agent name (architect, developer, reviewer).
        repository: Repository to save usage to (may be None in CLI mode).
    """
    if repository is None:
        return

    # Get usage via the driver-agnostic get_usage() method
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
        logger.debug(
            "Token usage saved",
            agent=agent,
            workflow_id=workflow_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
        )
    except Exception:
        # Best-effort - don't fail workflow on token tracking errors
        logger.exception(
            "Failed to save token usage",
            agent=agent,
            workflow_id=workflow_id,
        )
```

Add import at top of `amelia/core/orchestrator.py`:

```python
from amelia.drivers.base import DriverUsage
```

**Step 6.4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_save_token_usage.py -v`
Expected: PASS

**Step 6.5: Commit**

```bash
git add amelia/core/orchestrator.py tests/unit/core/test_save_token_usage.py
git commit -m "refactor(orchestrator): use get_usage() for driver-agnostic token tracking

Replaces direct last_result_message access with the DriverUsage abstraction.
Part of #210 - API driver token usage tracking"
```

---

## Task 7: Verify Existing Token Usage Tests Still Pass

**Files:**
- Verify: `tests/unit/core/test_token_usage_extraction.py`

**Step 7.1: Run existing tests**

Run: `uv run pytest tests/unit/core/test_token_usage_extraction.py -v`
Expected: Some tests may fail due to the refactored _save_token_usage

**Step 7.2: Update tests if needed**

If tests fail because they mock `last_result_message` directly instead of `get_usage()`, update the mocks:

```python
# Old style (if present):
mock_driver.last_result_message = mock_result_message_with_usage

# New style:
mock_driver.get_usage.return_value = DriverUsage(
    input_tokens=1500,
    output_tokens=500,
    ...
)
```

**Step 7.3: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: PASS

**Step 7.4: Commit if changes were needed**

```bash
git add tests/unit/core/test_token_usage_extraction.py
git commit -m "test: update token usage tests for get_usage() refactor

Part of #210 - API driver token usage tracking"
```

---

## Task 8: Integration Test for API Driver Token Tracking

**Files:**
- Test: `tests/integration/test_api_driver_token_tracking.py` (create)

**Step 8.1: Write integration test**

Create `tests/integration/test_api_driver_token_tracking.py`:

```python
"""Integration tests for API driver token usage tracking.

These tests verify that ApiDriver correctly accumulates token usage
by mocking at the HTTP boundary (the LangChain model's invoke calls).
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from amelia.drivers.api.deepagents import ApiDriver
from amelia.drivers.base import DriverUsage


class TestApiDriverTokenTrackingIntegration:
    """Integration tests for end-to-end token tracking in ApiDriver."""

    @pytest.fixture
    def mock_http_boundary(self):
        """Mock at the HTTP boundary - the LangChain model layer."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), \
             patch("amelia.drivers.api.deepagents.init_chat_model") as mock_init, \
             patch("amelia.drivers.api.deepagents.create_deep_agent") as mock_create:

            # Create mock chat model
            mock_chat_model = MagicMock()
            mock_init.return_value = mock_chat_model

            yield {
                "init_chat_model": mock_init,
                "create_deep_agent": mock_create,
                "chat_model": mock_chat_model,
            }

    async def test_full_execution_accumulates_usage(
        self, mock_http_boundary: dict
    ) -> None:
        """Full agentic execution should accumulate usage from all turns."""
        # Simulate a multi-turn conversation with tool use
        turn1 = AIMessage(content=[{"type": "text", "text": "Let me check..."}])
        turn1.usage_metadata = {"input_tokens": 500, "output_tokens": 100}
        turn1.response_metadata = {"openrouter": {"cost": 0.001}}
        turn1.tool_calls = [{"name": "read_file", "args": {"path": "test.py"}, "id": "tc1"}]

        turn2 = AIMessage(content="Here's what I found: the file contains tests.")
        turn2.usage_metadata = {"input_tokens": 800, "output_tokens": 200}
        turn2.response_metadata = {"openrouter": {"cost": 0.002}}
        turn2.tool_calls = []

        chunks = [
            {"messages": [HumanMessage(content="Read test.py"), turn1]},
            {"messages": [HumanMessage(content="Read test.py"), turn1, turn2]},
        ]

        async def mock_astream(*args, **kwargs):
            for chunk in chunks:
                yield chunk

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_http_boundary["create_deep_agent"].return_value = mock_agent

        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")

        # Run full execution
        messages = []
        async for msg in driver.execute_agentic("Read test.py", "/tmp"):
            messages.append(msg)

        # Verify usage was accumulated correctly
        usage = driver.get_usage()

        assert usage is not None
        assert usage.input_tokens == 1300  # 500 + 800
        assert usage.output_tokens == 300  # 100 + 200
        assert usage.cost_usd == 0.003  # 0.001 + 0.002
        assert usage.num_turns == 2
        assert usage.model == "openrouter:anthropic/claude-3.5-sonnet"
        assert usage.duration_ms > 0

    async def test_usage_includes_model_name(
        self, mock_http_boundary: dict
    ) -> None:
        """Usage should include the model name from driver initialization."""
        msg = AIMessage(content="Done")
        msg.usage_metadata = {"input_tokens": 10, "output_tokens": 5}

        async def mock_astream(*args, **kwargs):
            yield {"messages": [msg]}

        mock_agent = MagicMock()
        mock_agent.astream = mock_astream
        mock_http_boundary["create_deep_agent"].return_value = mock_agent

        driver = ApiDriver(model="openrouter:minimax/minimax-m2")

        async for _ in driver.execute_agentic("test", "/tmp"):
            pass

        usage = driver.get_usage()
        assert usage.model == "openrouter:minimax/minimax-m2"

    async def test_generate_does_not_track_usage(
        self, mock_http_boundary: dict
    ) -> None:
        """generate() should not affect get_usage() (only execute_agentic tracks)."""
        msg = AIMessage(content="Response")

        async def mock_ainvoke(*args, **kwargs):
            return {"messages": [msg]}

        mock_agent = MagicMock()
        mock_agent.ainvoke = mock_ainvoke
        mock_http_boundary["create_deep_agent"].return_value = mock_agent

        driver = ApiDriver(model="openrouter:test/model")

        # Call generate (not execute_agentic)
        await driver.generate("test prompt")

        # get_usage should still be None (only execute_agentic tracks)
        usage = driver.get_usage()
        assert usage is None
```

**Step 8.2: Run integration test**

Run: `uv run pytest tests/integration/test_api_driver_token_tracking.py -v`
Expected: PASS

**Step 8.3: Commit**

```bash
git add tests/integration/test_api_driver_token_tracking.py
git commit -m "test(integration): add API driver token tracking integration tests

Part of #210 - API driver token usage tracking"
```

---

## Task 9: Run Full Test Suite and Type Checking

**Step 9.1: Run linting**

Run: `uv run ruff check amelia tests`
Expected: No errors (fix any that appear)

**Step 9.2: Run type checking**

Run: `uv run mypy amelia`
Expected: No errors (fix any that appear)

**Step 9.3: Run full test suite**

Run: `uv run pytest`
Expected: All tests pass

**Step 9.4: Commit any fixes**

```bash
git add -A
git commit -m "fix: address linting and type checking issues

Part of #210 - API driver token usage tracking"
```

---

## Task 10: Final Verification and Cleanup

**Step 10.1: Verify the implementation against the design document**

Read: `docs/plans/2026-01-09-api-driver-token-usage-design.md`

Checklist:
- [ ] `DriverUsage` model matches design specification
- [ ] `get_usage()` added to `DriverInterface` protocol
- [ ] `ApiDriver` tracks usage during `execute_agentic()`
- [ ] `ApiDriver` extracts cost from OpenRouter's `response_metadata`
- [ ] `ClaudeCliDriver` implements `get_usage()` translating SDK fields
- [ ] `_save_token_usage()` uses `get_usage()` instead of direct attribute access
- [ ] All specified tests exist and pass

**Step 10.2: Run pre-push checks**

Run: `uv run ruff check amelia tests && uv run mypy amelia && uv run pytest`
Expected: All pass

**Step 10.3: Final commit if needed**

```bash
git status
# If any unstaged changes:
git add -A
git commit -m "chore: final cleanup for API driver token usage tracking

Closes #210"
```

---

Plan complete and saved to `docs/plans/2026-01-09-api-driver-token-usage-impl-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
